"""MongoDB repository for short-lived assistant drafts."""

from bson import ObjectId
from pymongo import ReturnDocument

from src.config.db import get_db


def insert_draft(document):
    db = get_db()
    result = db.assistant_drafts.insert_one(document)
    return result.inserted_id


def find_draft(draft_id):
    db = get_db()
    return db.assistant_drafts.find_one({"_id": ObjectId(draft_id)})


def update_draft(draft_id, fields):
    db = get_db()
    return db.assistant_drafts.find_one_and_update(
        {"_id": ObjectId(draft_id)},
        {"$set": fields},
        return_document=ReturnDocument.AFTER,
    )


def claim_draft(draft_id, allowed_statuses, claimed_at):
    """Atomically claim a draft so confirm/retry cannot execute twice."""
    db = get_db()
    return db.assistant_drafts.find_one_and_update(
        {
            "_id": ObjectId(draft_id),
            "status": {"$in": list(allowed_statuses)},
        },
        {
            "$set": {
                "status": "executing",
                "executing_at": claimed_at,
                "updated_at": claimed_at,
            }
        },
        return_document=ReturnDocument.AFTER,
    )


def mark_executed(draft_id, executed_at, result, final_command):
    db = get_db()
    return db.assistant_drafts.find_one_and_update(
        {"_id": ObjectId(draft_id), "status": "executing"},
        {
            "$set": {
                "status": "executed",
                "executed_at": executed_at,
                "updated_at": executed_at,
                "result": result,
                "final_command": final_command,
            }
        },
        return_document=ReturnDocument.AFTER,
    )


def release_claim(draft_id, status, updated_at, error_message=None):
    fields = {
        "status": status,
        "updated_at": updated_at,
        "executing_at": None,
    }
    if error_message:
        fields["last_execution_error"] = error_message

    db = get_db()
    return db.assistant_drafts.find_one_and_update(
        {"_id": ObjectId(draft_id), "status": "executing"},
        {"$set": fields},
        return_document=ReturnDocument.AFTER,
    )
