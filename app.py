import os
import sys
import html
import json
import uuid
import string
import random
import datetime
import dataclasses
import urllib.parse

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import bson
import pymongo
from flask import Flask, session, request, render_template, abort, redirect
from flask.json.provider import DefaultJSONProvider
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_pymongo import PyMongo

import pyquestions
# from pyquestions.classes import QuestionSession, Question


if not os.getenv("PYQUESTIONS_MONGO_URI"):
    raise ValueError("Environment variable PYQUESTIONS_MONGO_URI must be set")

if not os.getenv("PYQUESTIONS_BASE_URL"):
    raise ValueError("Environment variable PYQUESTIONS_BASE_URL must be set")

if not os.getenv("PYQUESTIONS_ADMIN_PASSWORD"):
    raise ValueError("Environment variable PYQUESTIONS_ADMIN_PASSWORD must be set")

INSTANCE_NAME = os.getenv("PYQUESTIONS_INSTANCE_NAME")
if not INSTANCE_NAME:
    raise ValueError("Environment variable PYQUESTIONS_INSTANCE_NAME must be set")


def new_utc_datetime():
    return datetime.datetime.now(datetime.UTC)


class CustomJSONEncoder(DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, datetime.date) or isinstance(o, datetime.datetime):
            return o.isoformat()
        elif isinstance(o, bson.ObjectId):
            return str(o)
        return super().default(o)


class CustomJSONEncoder2(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.date) or isinstance(o, datetime.datetime):
            return o.isoformat()
        elif isinstance(o, bson.ObjectId):
            return str(o)
        elif isinstance(o, pyquestions.Question):
            return o.__dict__
        elif isinstance(o, pyquestions.QuestionSession):
            return o.__dict__
        return super().default(o)


class QuestionsFlask(Flask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.questions_server: pyquestions.ServerInstance

app = QuestionsFlask(__name__)
socketio = SocketIO(app,cors_allowed_origins='*')
app.json = CustomJSONEncoder(app)
app.secret_key = b'46b30a8e86c74818f6b7'
app.config["MONGO_URI"] = os.getenv("PYQUESTIONS_MONGO_URI")
mongo = PyMongo(app)
app.questions_server = pyquestions.ServerInstance(
    instance_name=os.getenv("PYQUESTIONS_INSTANCE_NAME", ""),
    base_url=os.getenv("PYQUESTIONS_BASE_URL", ""),
    admin_password=os.getenv("PYQUESTIONS_ADMIN_PASSWORD", ""),
    mongo_connection_string=os.getenv("PYQUESTIONS_MONGO_URI", ""),
    database_name="pyqa",
)


def get_questions():
    results = mongo.db.questions.aggregate([ # type: ignore
        {
            "$addFields": {
                "upvote_count": {"$size": {"$ifNull": ["$upvotes", []]}}
            }
        },
        {
            "$sort": {"upvote_count": pymongo.DESCENDING, "created": pymongo.ASCENDING}
        }
    ])
    return results


def generate_admin_password(length=8):
    """Generate a random string to use as an Admin password"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


@app.before_request
def check_session():
    if "session_uuid" not in session:
        session["session_uuid"] = generate_session_key()


@app.route("/")
def home_page():
    header = render_template("header.html",
                            title=app.questions_server.instance_name,
                            base_url=app.questions_server.base_url)
    return render_template("index.html",
                           instance_name=app.questions_server.instance_name,
                           header=header)


@app.route("/help")
def help_page():
    header = render_template("header.html",
                            title=app.questions_server.instance_name,
                            base_url=app.questions_server.base_url)
    return render_template("help.html",
                           instance_name=app.questions_server.instance_name,
                           base_url=app.questions_server.base_url,
                           header=header)


@app.route("/s/<session_id>", methods=["PUT"])
def create_session(session_id):
    session_id = html.unescape(session_id)
    admin_password = generate_admin_password()
    session = pyquestions.QuestionSession(
        _id=session_id,
        name=session_id,
        is_accepting_questions=True,
        is_visible=True,
        admin_password=admin_password
    )
    new_session_id = app.questions_server.db.save_session(session)
    try:
        question_session = app.questions_server.db.get_question_session_by_id(new_session_id, admin_password)
        return json.dumps(question_session, cls=CustomJSONEncoder2)
    except pyquestions.NoSessionFoundException:
        abort(404)


@app.route("/s/<session_id>", methods=["GET"])
def question_session(session_id):
    session_id = html.unescape(session_id)
    try:
        question_session = app.questions_server.db.get_question_session_by_id(session_id)
    except pyquestions.NoSessionFoundException:
        error_message = html.escape(f"No Session Found for {session_id}")
        return redirect(f"../../?error={error_message}")
    question_session.questions = [question for question in question_session.questions if not question.hidden]

    header = render_template("header.html",
                            title=question_session.name,
                            base_url=app.questions_server.base_url)
    return render_template("session.html",
                           header=header,
                           instance_name=app.questions_server.instance_name,
                           question_session=question_session,
                           is_admin_page=False,
                           base_url=app.questions_server.base_url)


@app.route("/s/<session_id>/<admin_password>")
def question_session_admin(session_id, admin_password):
    session_id = html.unescape(session_id)
    try:
        question_session = app.questions_server.db.get_question_session_by_id(session_id, admin_password)
    except pyquestions.NoSessionFoundException:
        error_message = html.escape(f"No Session Found for {session_id}")
        return redirect(f"../../?error={error_message}")
    header = render_template("header.html",
                            title=question_session.name,
                            base_url=app.questions_server.base_url)
    return render_template("session.html",
                           header=header,
                           instance_name=app.questions_server.instance_name,
                           question_session=question_session,
                           is_admin_page=True,
                           base_url=app.questions_server.base_url)


@app.route("/admin")
def admin_page():
    auth = request.authorization
    if not auth or auth.password != os.getenv("PYQUESTIONS_ADMIN_PASSWORD"):
        return ('Unauthorized', 401, {
            'WWW-Authenticate': 'Basic realm="Login Required"'
        })
    # if auth.password != os.getenv("PYQUESTIONS_ADMIN_PASSWORD", "letmein"):
    #     return ('Unauthorized', 401, {
    #         'WWW-Authenticate': 'Basic realm="Login Required"'
    #     })
    session["is_admin"] = True
    question_sessions = app.questions_server.db.get_question_sessions()
    closed_sessions = app.questions_server.db.get_question_sessions(accepting_questions=False)

    header = render_template("header.html",
                            title=app.questions_server.instance_name,
                            base_url=app.questions_server.base_url)
    return render_template("admin.html",
                           header=header,
                           instance_name=app.questions_server.instance_name,
                           question_sessions=question_sessions,
                           closed_sessions=closed_sessions,
                           base_url=app.questions_server.base_url)


@socketio.on('join')
def on_join(session_id):
    session_id = html.unescape(session_id)
    join_room(session_id)
    try:
        question_session = app.questions_server.db.get_question_session_by_id(session_id)
    except pyquestions.NoSessionFoundException:
        emit("session_deleted", to=request.sid) # type: ignore
        return

    emit("session_update", json.dumps(question_session, cls=CustomJSONEncoder2), to=request.sid) # type: ignore


@socketio.on('leave')
def on_leave(session_id):
    session_id = html.unescape(session_id)
    leave_room(session_id)


@socketio.on('ask')
def handle_ask(question_dict: dict):
    """Save a new question to the database"""
    session_id = html.unescape(question_dict["session_id"])
    question = pyquestions.Question(
        session_id=session_id,
        text=question_dict["text"]
    )
    app.questions_server.db.add_new_question(question)

    question_session = app.questions_server.db.get_question_session_by_id(question.session_id)
    emit("session_update", json.dumps(question_session, cls=CustomJSONEncoder2), to=question_session._id)


@socketio.on('upvote')
def handle_upvote(question_dict: dict):
    """Hide a question from the UI"""
    did_upvote_question = app.questions_server.db.upvote_question(question_dict["question_id"], session["session_uuid"])
    if not did_upvote_question:
        # no update was made, ignore sending an update
        logger.error(f"Upvote for {question_dict["question_id"]} not added")
        return

    question_session = app.questions_server.db.get_question_session_by_id(question_dict["session_id"])
    emit("session_update", json.dumps(question_session, cls=CustomJSONEncoder2), to=question_session._id)


@socketio.on('hide')
def handle_hide(question_dict: dict):
    session_id = html.unescape(question_dict["session_id"])
    if app.questions_server.db.hide_question(question_dict["question_id"]):
        question_session = app.questions_server.db.get_question_session_by_id(session_id)
        emit("session_update", json.dumps(question_session, cls=CustomJSONEncoder2), to=question_session._id)
    else:
        logger.error(f"Question {question_dict["question_id"]} not hidden")


@socketio.on('unhide')
def handle_unhide(question_dict: dict):
    session_id = html.unescape(question_dict["session_id"])
    if app.questions_server.db.unhide_question(question_dict["question_id"]):
        question_session = app.questions_server.db.get_question_session_by_id(session_id)
        emit("session_update", json.dumps(question_session, cls=CustomJSONEncoder2), to=question_session._id)


@socketio.on('close_session')
def handle_close_session(session_dict: dict):
    session_id = html.unescape(session_dict["session_id"])
    question_session = app.questions_server.db.close_session(session_id, session_dict["admin_password"])
    emit("session_update", json.dumps(question_session, cls=CustomJSONEncoder2), to=question_session._id)


@socketio.on('open_session')
def handle_open_session(session_dict: dict):
    session_id = html.unescape(session_dict["session_id"])
    question_session = app.questions_server.db.open_session(session_id, session_dict["admin_password"])
    emit("session_update", json.dumps(question_session, cls=CustomJSONEncoder2), to=question_session._id)


@socketio.on('delete_session')
def handle_delete_session(session_dict: dict):
    session_id = html.unescape(session_dict["session_id"])
    was_session_deleted = app.questions_server.db.delete_session(session_id, session_dict["admin_password"])
    if was_session_deleted:
        emit("session_deleted", to=session_id)
    else:
        raise Exception("Session failed to delete")


def generate_session_key():
    return uuid.uuid4().hex


if __name__ == "__main__":
    app.run(port=8000)
