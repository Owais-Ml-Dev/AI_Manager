import os

from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError


# =========================================================
# GLOBAL DATABASE OBJECTS
# =========================================================

# These are initialized when the Flask app starts.
client = None
db = None


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def init_db():
    """
    Connect the Flask application to MongoDB.

    Environment variables:
        MONGO_URI
        MONGO_DB_NAME
    """

    global client, db

    mongo_uri = os.getenv(
        "MONGO_URI"
    )

    db_name = os.getenv(
        "MONGO_DB_NAME"
    )

    # Ensure required configuration exists.
    if not mongo_uri:
        raise ValueError(
            "MONGO_URI is not configured."
        )

    if not db_name:
        raise ValueError(
            "MONGO_DB_NAME is not configured."
        )

    try:
        # Create MongoDB client.
        client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=5000
        )

        # Ping MongoDB so application startup fails
        # immediately when the database is unavailable.
        client.admin.command(
            "ping"
        )

        # Select application database.
        db = client[db_name]

        print(
            f"MongoDB connected successfully: "
            f"{db_name}"
        )

        # Indexes are what keep queries fast as the task count
        # grows. Without them every lookup is a collection scan.
        ensure_indexes()

        return db

    except PyMongoError as error:

        print(
            f"MongoDB connection failed: "
            f"{error}"
        )

        raise


# =========================================================
# INDEXES
# =========================================================

def ensure_indexes():
    """
    Create the indexes the application queries rely on.

    Safe to call on every startup: create_index() is idempotent, so an
    index that already exists is left untouched and costs one cheap
    no-op round trip.

    Without these, MongoDB performs a full collection scan for every
    lookup. That is invisible with 3 test tasks and increasingly
    painful past a few hundred occurrence rows -- which one recurring
    task spanning a month already produces.

    Index choices follow the actual query shapes in the repositories:

        task_occurrences
            (task_id, scheduled_date)  one task's calendar, sorted
            (scheduled_date)           every task's rows for one day
            (task_id, status)          lifecycle sweeps by state

        tasks
            (task_type, status)        the main list endpoints
            (status, completed_at)     history / dashboard queries
    """

    if db is None:
        return

    try:
        db.task_occurrences.create_index(
            [
                ("task_id", ASCENDING),
                ("scheduled_date", ASCENDING),
            ],
            name="occ_task_date",
        )

        db.task_occurrences.create_index(
            [
                ("scheduled_date", ASCENDING),
            ],
            name="occ_date",
        )

        db.task_occurrences.create_index(
            [
                ("task_id", ASCENDING),
                ("status", ASCENDING),
            ],
            name="occ_task_status",
        )

        db.tasks.create_index(
            [
                ("task_type", ASCENDING),
                ("status", ASCENDING),
            ],
            name="task_type_status",
        )

        db.tasks.create_index(
            [
                ("status", ASCENDING),
                ("completed_at", ASCENDING),
            ],
            name="task_status_completed",
        )

        # Assistant drafts are short-lived server-owned state. MongoDB
        # automatically removes abandoned drafts after expires_at.
        db.assistant_drafts.create_index(
            [("expires_at", ASCENDING)],
            name="assistant_draft_ttl",
            expireAfterSeconds=0,
        )

        db.assistant_drafts.create_index(
            [("status", ASCENDING), ("updated_at", ASCENDING)],
            name="assistant_draft_status_updated",
        )

        print(
            "MongoDB indexes verified."
        )

    except PyMongoError as error:
        # A missing index slows queries down; it does not make them
        # wrong. Never let index setup stop the app from starting.
        print(
            f"MongoDB index setup skipped: {error}"
        )


# =========================================================
# GET DATABASE
# =========================================================

def get_db():
    """
    Return the initialized MongoDB database.

    Repository files use this function rather than
    creating their own MongoClient.
    """

    if db is None:
        raise RuntimeError(
            "Database has not been initialized. "
            "Call init_db() first."
        )

    return db
