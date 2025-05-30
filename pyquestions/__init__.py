from __future__ import annotations
import uuid
import typing
import datetime
import dataclasses

import pymongo

import logging

import pymongo.errors

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NoSessionFoundException(BaseException):
    pass


class SessionNotAcceptingQuestions(BaseException):
    pass


class DBInsertFailed(BaseException):
    pass


class reversor:
    """Used for changing order when sorting
    
    Taken from https://stackoverflow.com/questions/37693373/how-to-sort-a-list-with-two-keys-but-one-in-reverse-order
    """
    def __init__(self, obj):
        self.obj = obj

    def __eq__(self, other):
        return other.obj == self.obj

    def __lt__(self, other):
        return other.obj < self.obj


class Question:
    """Question Class"""
    _id: str
    session_id: str
    text: str
    created: datetime.datetime
    upvotes: list[str]
    hidden: bool

    def __init__(self, session_id: str, text: str) -> None:
        self.session_id = session_id
        self.text = text
        self._id = uuid.uuid4().hex
        self.created = datetime.datetime.now(datetime.UTC)
        self.upvotes = []
        self.hidden = False

    @classmethod
    def from_mongo_dict(cls, mongo_dict: dict) -> Question:
        question = cls(
            session_id=mongo_dict["session_id"],
            text=mongo_dict["text"]
        )
        question._id = mongo_dict["_id"]
        question.created = mongo_dict["created"]
        question.upvotes = mongo_dict["upvotes"]
        question.hidden = mongo_dict["hidden"]
        return question


class QuestionSession:
    """A Question Session
    
    Args:
        _id (str):                      Unique Identifier for the session
        name (str):                     Name of the session
        is_accepting_questions (bool):  Is the session accepting new questions?
        is_visible (bool):              Is the session visible from the home page?
        admin_password (str):           Password used to administer a session
        questions (List[Question]):     A list of questions for this session
    """
    _id: str
    name: str
    is_accepting_questions: bool
    is_visible: bool
    admin_password: str
    questions: typing.List[Question]

    def __init__(self,
                 _id: str,
                 name: str,
                 is_accepting_questions: bool,
                 is_visible: bool,
                 admin_password: str):
        self._id = _id
        self.name = name
        self.is_accepting_questions = is_accepting_questions
        self.is_visible = is_visible
        self.admin_password = admin_password

        self.questions = []

    @classmethod
    def from_mongo_dict(cls, mongo_dict) -> QuestionSession:
        return cls(
            _id=mongo_dict["_id"],
            name=mongo_dict["name"],
            is_accepting_questions=mongo_dict["is_accepting_questions"],
            is_visible=mongo_dict["is_visible"],
            admin_password=mongo_dict["admin_password"]
        )


class DB(object):
    def __init__(self, mongo_connection_string: str, database_name: str = "pyqa"):
        self.__client = pymongo.MongoClient(mongo_connection_string)
        self.__db = self.__client[database_name]

    def __del__(self):
        self.__client.close()

    def get_question_sessions(self, accepting_questions=True, is_visible=True) -> typing.Generator[QuestionSession, None, None]:
        """Get a list of sessions
        
        Args:
            accepting_questions (bool):     Only return sessions that are accepting questions
            is_visible (bool):                Only return publically visible sessions
        
        Returns:
            List[QuestionSession]:  A list of question sessions
        """
        query_dict = {
            "is_accepting_questions": accepting_questions,
            "is_visible": is_visible
        }

        for session in self.__db.sessions.find(query_dict).sort({"name": pymongo.ASCENDING}):
            yield QuestionSession.from_mongo_dict(session)

    def get_question_session_by_id(self, session_id: str, admin_password=None) -> QuestionSession:
        """Get a single session
        
        Args:
            session_id (str):  ID of the session
            admin_password (str): Optionally provide the admin password
        
        Returns:
            QuestionSession
        
        Raises:
            NoSessionFoundException: When no session is found for the given ID
        """
        query_dict ={
            "_id": session_id
        }
        if admin_password:
            query_dict["admin_password"] = admin_password

        session = self.__db.sessions.find_one(query_dict)
        if not session:
            raise NoSessionFoundException(f"No sessions found for '{session_id}'")

        question_session = QuestionSession.from_mongo_dict(session)
        if not admin_password:
            question_session.admin_password = ""
        question_session.questions = self.get_questions_for_question_session(session_id=session_id)
        
        return question_session

    def get_questions_for_question_session(self, session_id: str) -> typing.List[Question]:
        results = self.__db.questions.find({"session_id": session_id})
        questions = [Question.from_mongo_dict(mongo_dict) for mongo_dict in results]
        questions.sort(key=lambda question: (len(question.upvotes), reversor(question.created)), reverse=True)
        return questions

    def save_session(self, question_session: QuestionSession) -> str:
        """Save a session to the DB
        
        Args:
            question_session (QuestionSession): The session to save
        
        Returns
            str: The inserted ID
        """
        result = self.__db.sessions.insert_one(question_session.__dict__)
        return result.inserted_id

    def open_session(self, session_id: str, admin_password: str):
        """Open a session so it can accept questions
        
        Args:
            session_id (str): The ID of the session to open
        """
        session = self.get_question_session_by_id(session_id=session_id, admin_password=admin_password)
        result = self.__db.sessions.update_one({"_id": session_id}, {"$set": {"is_accepting_questions": True}})
        return self.get_question_session_by_id(session_id)

    def close_session(self, session_id: str, admin_password: str):
        """Close a session so it cannot accept any more questions
        
        Args:
            session_id (str): The ID of the session to close
        """
        session = self.get_question_session_by_id(session_id=session_id, admin_password=admin_password)
        result = self.__db.sessions.update_one({"_id": session_id}, {"$set": {"is_accepting_questions": False}})
        return self.get_question_session_by_id(session_id)

    def delete_session(self, session_id: str, admin_password: str) -> bool:
        """Delete a session
        
        Args:
            session_id (str): The ID of the session to close
            admin_password (str): The admin password for the session
        
        Returns:
            A bool indicating whether the session was deleted
        """
        logger.debug(f"Deleting session {session_id}")
        session = self.get_question_session_by_id(session_id=session_id, admin_password=admin_password)
        logger.debug(f"Session ID found: {session._id}")
        question_result = self.__db.questions.delete_many({"session_id": session_id})
        logger.debug(f"Deleted questions: {question_result.deleted_count}")
        session_result = self.__db.sessions.delete_one({"_id": session_id})
        logger.debug(f"Deleted session: {session_result.deleted_count}")
        return session_result.deleted_count > 0


    def add_new_question(self, question: Question) -> str:
        """Add a new question to the database
        
        Args:
            question (Question): The question to save

        Returns:
            Optional the ID of the question

        Throws:
            NoSessionFoundException
            SessionNotAcceptingQuestions
            DBInsertFailed
        """
        session = self.get_question_session_by_id(question.session_id)

        if not session.is_accepting_questions:
            raise SessionNotAcceptingQuestions(f"Session {question.session_id} is not accepting questions")

        try:
            result = self.__db.questions.insert_one(question.__dict__)
        except pymongo.errors.PyMongoError as error:
            raise DBInsertFailed(f"Failed to insert into db: {error}")

        return result.inserted_id

    def upvote_question(self, question_id: str, client_id: str) -> bool:
        """Add an upvote to a question
        
        Args:
            question_id (str):      _id of the question
            client_id (str):        Unique ID for the client making the upvote
        
        Returns:
            bool: Was an upvote added
        """
        update_result = self.__db.questions.update_one({"_id": question_id}, {"$addToSet": {"upvotes": client_id}})
        return update_result.modified_count > 0

    def hide_question(self, question_id: str) -> bool:
        """Hide a question
        
        Args:
            question_id (str):      _id of the question
        
        Returns:
            bool: Was the question hidden
        """
        update_result = self.__db.questions.update_one({"_id": question_id}, {"$set": {"hidden": True}})
        return update_result.modified_count > 0

    def unhide_question(self, question_id: str) -> bool:
        """Unhide a question
        
        Args:
            question_id (str):      _id of the question
        
        Returns:
            bool: Was the question unhidden
        """
        update_result = self.__db.questions.update_one({"_id": question_id}, {"$set": {"hidden": False}})
        return update_result.modified_count > 0


class ServerInstance:
    def __init__(self,
                 instance_name: str,
                 base_url: str,
                 admin_password: str,
                 mongo_connection_string: str,
                 database_name: str = 'pyqa') -> None:
        """Create An instance of the PyQuestions server
    
        Args:
            instance_name (str):            Friendly name of the server (e.g. 'Question Time')
            base_url (str):                 Base URL of the server (e.g. https://questions.com)
            admin_password (str):           Admin password of the server
            mongo_connection_string (str):  MongoDB connection string
            database_name (str):            The name of the database to use (Default: pyqa)
        """
        self.instance_name = instance_name
        self.base_url = base_url
        self.admin_password = admin_password
        self.mongo_connection_string = mongo_connection_string
        self.database_name = database_name

        self.db = DB(
            mongo_connection_string=mongo_connection_string,
            database_name=self.database_name
        )
