#!/usr/bin/env python3
import hashlib
import os
from firebase_admin_client import get_firestore_client


def make_index_id(uid: str, term_normalized: str) -> str:
    return hashlib.sha1(f"{uid}::{term_normalized}".encode("utf-8")).hexdigest()


def main():
    db = get_firestore_client()
    users = db.collection("users").stream()

    total_users = 0
    total_keywords = 0
    total_written = 0

    for user_doc in users:
        total_users += 1
        uid = user_doc.id
        keywords = (
            db.collection("users")
            .document(uid)
            .collection("keywords")
            .where("enabled", "==", True)
            .stream()
        )

        for kw_doc in keywords:
            data = kw_doc.to_dict() or {}
            term_normalized = str(data.get("termNormalized") or "").strip()
            term = str(data.get("term") or term_normalized).strip()
            if not term_normalized:
                continue
            total_keywords += 1

            db.collection("keyword_subscriptions").document(make_index_id(uid, term_normalized)).set(
                {
                    "uid": uid,
                    "term": term,
                    "termNormalized": term_normalized,
                    "enabled": True,
                    "updatedAt": data.get("updatedAt"),
                },
                merge=True,
            )
            total_written += 1

    print(f"BACKFILL_OK users={total_users} keywords={total_keywords} written={total_written}")


if __name__ == "__main__":
    main()
