#!/usr/bin/env python3
import json
import os
from functools import lru_cache

import firebase_admin
from firebase_admin import credentials, firestore


@lru_cache(maxsize=1)
def get_firestore_client():
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise RuntimeError("Missing FIREBASE_SERVICE_ACCOUNT_JSON")

    if raw.startswith("{"):
        info = json.loads(raw)
        cred = credentials.Certificate(info)
    else:
        cred = credentials.Certificate(raw)

    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            cred,
            {"projectId": os.environ.get("FIREBASE_PROJECT_ID") or None},
        )

    return firestore.client()
