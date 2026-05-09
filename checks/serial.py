"""
Check 5 — Serial number + uniqueness
======================================
OCRs the serial number from the body label across all submitted images,
then checks a local SQLite store for duplicate submissions.

Duplicate → FAIL (with details of the prior matching record).
New serial → PASS (record is inserted for future dedup checks).

Model tier: gemini-2.5-flash
Justification: OCR of a printed (not handwritten) serial number is a well-defined
visual task — much simpler than reading handwritten dates. Flash handles printed text
reliably. We use Pro only where handwriting and date reasoning are both required (Check 2).

SQLite store: data/serials.db
Schema:
  serials(id INTEGER PK, serial_number TEXT UNIQUE, submission_id TEXT,
          image_folder TEXT, first_seen TEXT)
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from checks.base import CheckResult, UsageRecord
from utils.gemini_client import call_gemini

MODEL = "gemini-2.5-flash"

# Path to the SQLite database (relative to where pipeline.py is run from)
DB_PATH = Path("data/serials.db")

PROMPT = """You are a fire-safety equipment inspector reading the serial number label.

Look across ALL provided images and find the label that contains a serial number.
This is typically printed (not handwritten) on a sticker or embossed on the body.
It may be labelled: "SR. NO.", "Serial No.", "S/N", "Serial Number", or similar.

Your task:
1. Find and read the serial number exactly as printed — preserve any letters,
   numbers, and separators (hyphens, spaces, slashes).
2. If you can see a partial serial number but are unsure of some characters,
   report what you can see and flag your uncertainty.
3. If no serial number is visible in any image → return null.

Respond ONLY with a JSON object — no markdown, no explanation outside the JSON:
{
  "serial_number": "<the serial number as read, or null if not found>",
  "confidence": <float 0.0 to 1.0>,
  "reason": "<single sentence: describe where it was found and any uncertainty>"
}"""


def _get_db_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS serials (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            serial_number  TEXT    NOT NULL,
            submission_id  TEXT    NOT NULL,
            image_folder   TEXT    NOT NULL,
            first_seen     TEXT    NOT NULL
        )
    """)
    # Add unique index separately so we can check for duplicates without
    # relying on exceptions alone
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_serial
        ON serials(serial_number)
    """)
    conn.commit()
    return conn


def _check_and_insert(
    serial: str, submission_id: str, image_folder: str
) -> tuple[bool, dict | None]:
    """
    Returns (is_duplicate, prior_record_or_None).
    If not duplicate, inserts the new record.
    """
    conn = _get_db_connection()
    try:
        row = conn.execute(
            "SELECT serial_number, submission_id, image_folder, first_seen "
            "FROM serials WHERE serial_number = ?",
            (serial,),
        ).fetchone()

        if row:
            return True, {
                "serial_number": row[0],
                "submission_id": row[1],
                "image_folder": row[2],
                "first_seen": row[3],
            }

        # New serial — insert it
        conn.execute(
            "INSERT INTO serials (serial_number, submission_id, image_folder, first_seen) "
            "VALUES (?, ?, ?, ?)",
            (
                serial,
                submission_id,
                image_folder,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        return False, None
    finally:
        conn.close()


def run(
    images: list[bytes],
    usage: UsageRecord,
    submission_id: str = "unknown",
    image_folder: str = "",
) -> CheckResult:
    # Step 1: OCR the serial number
    ocr_result = call_gemini(
        model=MODEL,
        images=images,
        prompt=PROMPT,
        usage=usage,
    )

    serial = ocr_result.get("serial_number")
    ocr_confidence = float(ocr_result.get("confidence", 0.0))
    ocr_reason = ocr_result.get("reason", "")

    # If no serial found
    if not serial:
        return CheckResult(
            status="UNCERTAIN",
            confidence=0.1,
            reason=f"No serial number found in any image. {ocr_reason}",
            extra={"serial_number": None},
        )

    # Step 2: Deduplication check
    is_duplicate, prior = _check_and_insert(serial, submission_id, image_folder)

    if is_duplicate:
        return CheckResult(
            status="FAIL",
            confidence=0.99,
            reason=(
                f"Serial '{serial}' already seen in submission "
                f"'{prior['submission_id']}' on {prior['first_seen'][:10]}."
            ),
            extra={
                "serial_number": serial,
                "duplicate": True,
                "prior_record": prior,
            },
        )

    return CheckResult(
        status="PASS",
        confidence=ocr_confidence,
        reason=f"Serial '{serial}' read successfully; first occurrence — recorded.",
        extra={
            "serial_number": serial,
            "duplicate": False,
        },
    )
