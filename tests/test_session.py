import os
import sys
import logging
import unittest
import subprocess

import pymongo

sys.path.append("..")
import pyquestions


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


MONGO_CONNECTION_STRING = os.getenv("QUESTIONS_TEST_MONGO_STRING", "")
if not MONGO_CONNECTION_STRING:
    raise ValueError("QUESTIONS_TEST_MONGO_STRING environment variable must be set")


TEST_DB_NAME = "questionstest"

TEST_SESSIONS = [
    pyquestions.QuestionSession(
        _id="123",
        name="Question Time 1",
        is_accepting_questions=True,
        is_visible=True,
        admin_password="bla"
    ),
    pyquestions.QuestionSession(
        _id="gotme",
        name="Got Me",
        is_accepting_questions=True,
        is_visible=True,
        admin_password="bla"
    ),
    pyquestions.QuestionSession(
        _id="bla",
        name="Another Session",
        is_accepting_questions=True,
        is_visible=True,
        admin_password="bla"
    ),
    pyquestions.QuestionSession(
        _id="notvisible",
        name="Got Me",
        is_accepting_questions=True,
        is_visible=False,
        admin_password="bla"
    ),
    pyquestions.QuestionSession(
        _id="notacceptingquestions",
        name="Got Me",
        is_accepting_questions=False,
        is_visible=True,
        admin_password="bla"
    )
]


class TestQuestionSessions(unittest.TestCase):
    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)

        self.server_instance = pyquestions.ServerInstance(
            instance_name="Testing Questions",
            base_url="http://localhost:8000",
            admin_password="bla",
            mongo_connection_string=MONGO_CONNECTION_STRING,
            database_name=TEST_DB_NAME
        )

    @classmethod
    def create_client(cls, mongo_connection_string):
        return pymongo.MongoClient(mongo_connection_string)

    @classmethod
    def get_db(cls, client):
        if client is None:
            raise ValueError("No client provided")
        return client[TEST_DB_NAME]

    @classmethod
    def cleanup_db(cls, mongo_connection_string):
        client = cls.create_client(mongo_connection_string)
        db = cls.get_db(client)
        if db is None:
            raise ValueError("No db provided")
        db.sessions.delete_many({})
        db.questions.delete_many({})
        client.close()

    @classmethod
    def setUpClass(cls):
        # Stand up the test server
        logger.info("Starting test server")
        subprocess.run(
            ["docker", "compose", "-f", "mongo-docker-compose.yml", "up", "-d"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        mongo_connection_string = MONGO_CONNECTION_STRING

        server_instance = pyquestions.ServerInstance(
            instance_name="Testing Questions",
            base_url="https://example.com",
            admin_password="blabla",
            mongo_connection_string=MONGO_CONNECTION_STRING
        )
        client = cls.create_client(mongo_connection_string)
        db = cls.get_db(client)
        cls.cleanup_db(mongo_connection_string)
        db.sessions.insert_many([session.__dict__ for session in TEST_SESSIONS])
        client.close()

        pass

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cleanup_db(MONGO_CONNECTION_STRING)

        # Kill the test server
        print("")
        logger.info("Killing test server")
        subprocess.run(
            ["docker", "compose", "-f", "mongo-docker-compose.yml", "down"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        return super().tearDownClass()

    def test_1_questions_session_returns(self):
        """Test only visible sessions and sessions accepting questions are returned"""
        sessions = [session for session in self.server_instance.db.get_question_sessions()]

        for session in sessions:
            self.assertTrue(session.is_accepting_questions, "Session is not accepting questions")
            self.assertTrue(session.is_visible, "Session is not visible")

        test_sessions = [session for session in TEST_SESSIONS if (session.is_accepting_questions == True and session.is_visible == True)]
        self.assertEqual(len(sessions), len(test_sessions), "Incorrect number of sessions returned")
        
        # Verify order is alphabetical
        session_names = [session.name for session in sessions]
        test_names = [session.name for session in test_sessions]
        test_names.sort()
        self.assertEqual(session_names, test_names, "Sessions are not ordered by name")

    def test_2_invisible_session_returns(self):
        """Test only publically viewable sessions are returned"""
        sessions = [session for session in self.server_instance.db.get_question_sessions(is_visible=False)]

        test_sessions = [session for session in TEST_SESSIONS if session.is_visible != True]
        self.assertEqual(len(sessions), len(test_sessions), "Incorrect number of sessions returned")

        for session in sessions:
            self.assertFalse(session.is_visible, "Session is visible")

    def test_3_closedsession_returns(self):
        """Test only sessions that aren't accepting questions are returned"""
        sessions = [session for session in self.server_instance.db.get_question_sessions(accepting_questions=False)]

        test_sessions = [session for session in TEST_SESSIONS if session.is_accepting_questions != True]
        self.assertEqual(len(sessions), len(test_sessions), "Incorrect number of sessions returned")

        for session in sessions:
            self.assertFalse(session.is_accepting_questions, "Session is accepting questions")
    
    def test_get_session_by_id(self):
        """Tests that a single session can be returned by a given ID"""
        session = self.server_instance.db.get_question_session_by_id("notacceptingquestions")

        self.assertEqual(session._id, "notacceptingquestions", "_id is not equal to notacceptingquestions")

    def test_get_non_existant_session(self):
        with self.assertRaises(pyquestions.NoSessionFoundException, msg="Invalid session did not raise an error"):
            self.server_instance.db.get_question_session_by_id("thisdoesnotexist")

    def test_creating_session(self):
        """Tests session creation"""
        admin_password = "test"
        new_session = pyquestions.QuestionSession(
            _id="newtestsession",
            name="New Test Session",
            is_accepting_questions=True,
            is_visible=True,
            admin_password=admin_password
        )
        self.server_instance.db.save_session(new_session)

        retrieved_session = self.server_instance.db.get_question_session_by_id("newtestsession", admin_password)
        self.assertEqual(retrieved_session._id, new_session._id, "Session IDs don't match")
        self.assertEqual(retrieved_session.name, new_session.name, "Session names don't match")
        self.assertEqual(retrieved_session.is_accepting_questions, new_session.is_accepting_questions, "Session is_accepting_questions don't match")
        self.assertEqual(retrieved_session.is_visible, new_session.is_visible, "Session is_visible don't match")
        self.assertEqual(retrieved_session.admin_password, new_session.admin_password, "Session admin passwords don't match")
        self.assertEqual(len(retrieved_session.questions), 0, "Session should have no questions")

    def test_adding_questions(self):
        """Test adding questions to a session"""
        session_id = "newtestsession2"
        new_session = pyquestions.QuestionSession(
            _id=session_id,
            name="New Test Session",
            is_accepting_questions=True,
            is_visible=True,
            admin_password="test"
        )
        self.server_instance.db.save_session(new_session)

        question = pyquestions.Question(
            session_id=session_id,
            text="My new question"
        )
        question2 = pyquestions.Question(
            session_id=session_id,
            text="My new question 2"
        )

        inserted_question_id = self.server_instance.db.add_new_question(question)
        inserted_question_id2 = self.server_instance.db.add_new_question(question2)
        question_session = self.server_instance.db.get_question_session_by_id(session_id)
        self.assertEqual(inserted_question_id, question._id, "Question ID does not match after save")
        self.assertTrue(len(question_session.questions) > 0, "Session has no questions, should have one")
        self.assertEqual(len(question_session.questions), 2, "Session should only have two questions")

    def test_question_failure_for_missing_session(self):
        with self.assertRaises(pyquestions.NoSessionFoundException):
            self.server_instance.db.add_new_question(pyquestions.Question(
                session_id="aaaaaaaaaaaaaaaaaaaabbbbbbbbbbbbbbbbbbbcccccccccccccc",
                text="My new question 2"
            ))

    def test_hiding_question(self):
        session_id = "testhidingquestions"
        admin_password = "testhidingquestions"
        new_session = pyquestions.QuestionSession(
            _id=session_id,
            name="test Hiding Questions",
            is_accepting_questions=True,
            is_visible=True,
            admin_password=admin_password
        )
        self.server_instance.db.save_session(new_session)

        question_id = self.server_instance.db.add_new_question(pyquestions.Question(
            session_id=session_id,
            text="Hide Me"
        ))

        if not question_id:
            raise ValueError("question_id is None")

        if not self.server_instance.db.hide_question(question_id):
            raise ValueError("Failed to hide question")

        if not self.server_instance.db.unhide_question(question_id):
            raise ValueError("Failed to unhide question")


    def test_upvoting_questions(self):
        """Test upvoting questions"""
        session_id = "newtestsession3"
        new_session = pyquestions.QuestionSession(
            _id=session_id,
            name="New Test Session",
            is_accepting_questions=True,
            is_visible=True,
            admin_password="test"
        )
        self.server_instance.db.save_session(new_session)

        question = pyquestions.Question(
            session_id=session_id,
            text="My new question"
        )

        question_id = self.server_instance.db.add_new_question(question)

        did_upvote_question = self.server_instance.db.upvote_question(question_id, "client_id")
        self.assertTrue(did_upvote_question, "Question was not upvoted")
        question_session = self.server_instance.db.get_question_session_by_id(session_id)
        self.assertEqual(len(question_session.questions[0].upvotes), 1, "Question should have one upvote")

        did_upvote_question = self.server_instance.db.upvote_question(question_id, "client_id")
        self.assertFalse(did_upvote_question, "Question was upvoted but should not have been")
        question_session = self.server_instance.db.get_question_session_by_id(session_id)
        self.assertEqual(len(question_session.questions[0].upvotes), 1, "Question should not be upvoted twice by the same client ID")

        self.server_instance.db.upvote_question(question_id, "client_id2")
        question_session = self.server_instance.db.get_question_session_by_id(session_id)
        self.assertEqual(len(question_session.questions[0].upvotes), 2, "Question should have two upvotes")

    def test_question_ordering(self):
        """Ensure questions are ordered by upvote count"""
        session_id = "newtestsession4"
        new_session = pyquestions.QuestionSession(
            _id=session_id,
            name="New Test Session",
            is_accepting_questions=True,
            is_visible=True,
            admin_password="test"
        )
        self.server_instance.db.save_session(new_session)

        question_id1 = self.server_instance.db.add_new_question(pyquestions.Question(
            session_id=session_id,
            text="My new question"
        ))
        question_id2 = self.server_instance.db.add_new_question(pyquestions.Question(
            session_id=session_id,
            text="My new question"
        ))
        question_id3 = self.server_instance.db.add_new_question(pyquestions.Question(
            session_id=session_id,
            text="My new question"
        ))
        question_id4 = self.server_instance.db.add_new_question(pyquestions.Question(
            session_id=session_id,
            text="My new question"
        ))
        question_order = [question_id2, question_id3, question_id1, question_id4]
        self.server_instance.db.upvote_question(question_id1, "client_id1")
        self.server_instance.db.upvote_question(question_id1, "client_id2")
        self.server_instance.db.upvote_question(question_id2, "client_id1")
        self.server_instance.db.upvote_question(question_id2, "client_id2")
        self.server_instance.db.upvote_question(question_id2, "client_id3")
        self.server_instance.db.upvote_question(question_id2, "client_id4")
        self.server_instance.db.upvote_question(question_id3, "client_id1")
        self.server_instance.db.upvote_question(question_id3, "client_id2")
        self.server_instance.db.upvote_question(question_id3, "client_id3")
        self.server_instance.db.upvote_question(question_id4, "client_id1")
        self.server_instance.db.upvote_question(question_id4, "client_id2")
        question_session = self.server_instance.db.get_question_session_by_id(session_id)
        question_session_question_ids = [question._id for question in question_session.questions]
        self.assertEqual(question_session_question_ids, question_order, "Questions not returned in order")
        question_session = self.server_instance.db.get_question_session_by_id(session_id)
        question_session_question_ids = [question._id for question in question_session.questions]
        self.assertEqual(question_session_question_ids, question_order, "Questions not returned in order")
        question_session = self.server_instance.db.get_question_session_by_id(session_id)
        question_session_question_ids = [question._id for question in question_session.questions]
        self.assertEqual(question_session_question_ids, question_order, "Questions not returned in order")

    def test_session_closing(self):
        """Ensure a session can be closed and no more questions can be added"""
        session_id = "newtestsession5"
        admin_password = "test"
        new_session = pyquestions.QuestionSession(
            _id=session_id,
            name="New Test Session 5",
            is_accepting_questions=True,
            is_visible=True,
            admin_password=admin_password
        )
        self.server_instance.db.save_session(new_session)

        self.server_instance.db.add_new_question(pyquestions.Question(
            session_id=session_id,
            text="My new question"
        ))

        self.server_instance.db.close_session(session_id, admin_password)

        with self.assertRaises(pyquestions.SessionNotAcceptingQuestions):
            self.server_instance.db.add_new_question(pyquestions.Question(
                session_id=session_id,
                text="My new question2"
            ))

        self.server_instance.db.open_session(session_id, admin_password)

        self.server_instance.db.add_new_question(pyquestions.Question(
            session_id=session_id,
            text="My new question3"
        ))

    def test_session_deleting(self):
        """Ensure a session can be deleted"""
        session_id = "testdeletingsession"
        admin_password = "test"
        new_session = pyquestions.QuestionSession(
            _id=session_id,
            name="Deleting Sessions",
            is_accepting_questions=True,
            is_visible=True,
            admin_password=admin_password
        )
        self.server_instance.db.save_session(new_session)

        self.server_instance.db.delete_session(session_id, admin_password)


if __name__ == "__main__":
    unittest.main()
