"""MongoDB repository for assistant multi-task batches."""

from bson import ObjectId
from pymongo import ReturnDocument

from src.config.db import get_db


def insert_batch(document):
    db = get_db()
    result = db.assistant_task_batches.insert_one(document)
    return result.inserted_id


def find_batch(batch_id):
    db = get_db()
    return db.assistant_task_batches.find_one({"_id": ObjectId(batch_id)})

def attach_draft_to_active_item(
    batch_id,
    item_index,
    draft_id,
    updated_at,
    expires_at,
):
    """Attach a draft once, only to the currently active batch item."""

    db = get_db()
    return db.assistant_task_batches.find_one_and_update(
        {
            "_id": ObjectId(batch_id),
            "status": "in_progress",
            "current_index": item_index,
            "items": {
                "$elemMatch": {
                    "index": item_index,
                    "status": "active",
                    "draft_id": None,
                }
            },
        },
        {
            "$set": {
                "items.$.draft_id": str(draft_id),
                "updated_at": updated_at,
                "expires_at": expires_at,
            }
        },
        return_document=ReturnDocument.AFTER,
    )


def resolve_active_item_and_advance(
    batch_id,
    item_index,
    draft_id,
    resolved_status,
    resolved_at,
    expires_at,
    next_index=None,
    result=None,
):
    """Atomically resolve the current item and activate the next unresolved item.

    ``next_index`` may point forward or backward. This is required when a task
    was previously deferred with "Skip for now" and needs to be revisited after
    the still-pending tasks have been reviewed.
    """

    db = get_db()

    if resolved_status not in {"executed", "skipped"}:
        raise ValueError("resolved_status must be executed or skipped")

    if next_index is not None:
        if not isinstance(next_index, int) or next_index < 0:
            raise ValueError("next_index must be a non-negative integer or None")
        if next_index == item_index:
            raise ValueError("next_index cannot point to the item being resolved")

    set_fields = {
        f"items.{item_index}.status": resolved_status,
        f"items.{item_index}.resolved_at": resolved_at,
        "updated_at": resolved_at,
        "expires_at": expires_at,
    }

    if result is not None:
        set_fields[f"items.{item_index}.result"] = result

    query = {
        "_id": ObjectId(batch_id),
        "status": "in_progress",
        "current_index": item_index,
        f"items.{item_index}.status": "active",
        f"items.{item_index}.draft_id": str(draft_id),
    }

    if next_index is not None:
        query[f"items.{next_index}.status"] = {"$in": ["pending", "deferred"]}
        set_fields["current_index"] = next_index
        set_fields[f"items.{next_index}.status"] = "active"
    else:
        set_fields["status"] = "completed"
        set_fields["current_index"] = None

    return db.assistant_task_batches.find_one_and_update(
        query,
        {"$set": set_fields},
        return_document=ReturnDocument.AFTER,
    )


def defer_active_item_and_activate(
    batch_id,
    item_index,
    draft_id,
    next_index,
    deferred_at,
    expires_at,
):
    """Defer the current task without cancelling its draft, then activate another.

    The preserved draft is the key difference between Skip for Now and Discard.
    """

    db = get_db()

    if not isinstance(next_index, int) or next_index < 0 or next_index == item_index:
        raise ValueError("next_index must identify another batch item")

    return db.assistant_task_batches.find_one_and_update(
        {
            "_id": ObjectId(batch_id),
            "status": "in_progress",
            "current_index": item_index,
            f"items.{item_index}.status": "active",
            f"items.{item_index}.draft_id": str(draft_id),
            f"items.{next_index}.status": {"$in": ["pending", "deferred"]},
        },
        {
            "$set": {
                f"items.{item_index}.status": "deferred",
                f"items.{item_index}.deferred_at": deferred_at,
                f"items.{next_index}.status": "active",
                "current_index": next_index,
                "updated_at": deferred_at,
                "expires_at": expires_at,
            }
        },
        return_document=ReturnDocument.AFTER,
    )


def abort_active_batch(
    batch_id,
    item_index,
    draft_id,
    discarded_items,
    aborted_at,
    expires_at,
):
    """Abort all unfinished work if this draft is still the active one."""

    db = get_db()
    return db.assistant_task_batches.find_one_and_update(
        {
            "_id": ObjectId(batch_id),
            "status": "in_progress",
            "current_index": item_index,
            f"items.{item_index}.status": "active",
            f"items.{item_index}.draft_id": str(draft_id),
        },
        {
            "$set": {
                "status": "aborted",
                "current_index": None,
                "items": discarded_items,
                "aborted_at": aborted_at,
                "updated_at": aborted_at,
                "expires_at": expires_at,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
