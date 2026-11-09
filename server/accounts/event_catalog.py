import json
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings


@lru_cache(maxsize=1)
def event_records():
    source = Path(settings.BASE_DIR) / "app" / "app.js"
    text = source.read_text(encoding="utf-8")
    match = re.search(r"const RAW=(.*?);\nconst fmtT=", text, re.DOTALL)
    if not match:
        raise RuntimeError("The embedded RAW event dataset could not be found.")
    records = json.loads(match.group(1))
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise RuntimeError("The embedded RAW event dataset has an unexpected shape.")
    return records


@lru_cache(maxsize=1)
def event_ids():
    return frozenset(
        row["id"]
        for row in event_records()
        if isinstance(row.get("id"), str) and row["id"] and len(row["id"]) <= 128
    )
