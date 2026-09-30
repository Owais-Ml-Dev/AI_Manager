"""
Shared pytest configuration for the AI Task Manager backend.

The suite uses an isolated MongoDB database:
    ai_task_manager_test

It also disables the background scheduler during normal API tests.
Scheduler behavior is tested separately with mocks.
"""

import os

import pytest
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError


TEST_MONGO_URI = os.getenv(
    "TEST_MONGO_URI",
    "mongodb://localhost:27017"
)

TEST_DB_NAME = os.getenv(
    "TEST_MONGO_DB_NAME",
    "ai_task_manager_test"
)

# Force app imports to use the isolated test database.
os.environ["MONGO_URI"] = TEST_MONGO_URI
os.environ["MONGO_DB_NAME"] = TEST_DB_NAME


@pytest.fixture(scope="session", autouse=True)
def verify_test_mongodb():
    """
    Ensure MongoDB is available before tests start.
    """

    client = MongoClient(
        TEST_MONGO_URI,
        serverSelectionTimeoutMS=2000
    )

    try:
        client.admin.command("ping")
    except ServerSelectionTimeoutError:
        pytest.skip(
            "MongoDB is not running at "
            f"{TEST_MONGO_URI}. Start MongoDB first."
        )

    yield

    client.close()


@pytest.fixture(scope="session")
def app():
    """
    Create the real Flask app but disable the actual
    recurring background scheduler thread during tests.
    """

    import src.app as app_module

    app_module.start_recurring_scheduler = lambda: None

    flask_app = app_module.create_app()

    flask_app.config.update(
        TESTING=True
    )

    return flask_app


@pytest.fixture()
def client(app):
    """
    Flask test client.
    """

    return app.test_client()


@pytest.fixture(autouse=True)
def clean_test_database(request):
    """
    Clear only the isolated test database before and after
    every test.
    """

    # ---------------------------------------------------------
    # LIVE AI END-TO-END TESTS
    # ---------------------------------------------------------
    # These tests call the separately running Flask server over
    # HTTP. They must not use pytest's in-process test database.
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # TESTS THAT MUST NOT USE PYTEST'S DATABASE
    # ---------------------------------------------------------
    #
    # live_ai:
    #     Talks to the separately running Flask server over HTTP.
    #
    # no_db:
    #     Pure unit tests that do not touch MongoDB at all.
    # ---------------------------------------------------------

    if (
        request.node.get_closest_marker("live_ai")
        or request.node.get_closest_marker("no_db")
    ):
        yield
        return

    from src.config.db import get_db

    db = get_db()

    db.tasks.delete_many({})
    db.task_occurrences.delete_many({})
    db.assistant_preferences.delete_many({})
    db.assistant_credentials.delete_many({})
    db.assistant_drafts.delete_many({})

    yield

    db.tasks.delete_many({})
    db.task_occurrences.delete_many({})
    db.assistant_preferences.delete_many({})
    db.assistant_credentials.delete_many({})
    db.assistant_drafts.delete_many({})
