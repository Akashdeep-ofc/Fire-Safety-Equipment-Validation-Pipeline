"""
Check 2 — Refill status
========================
Reads the handwritten "Reffiling Date" and "Reffiling Due Date" fields
from the branding label (wherever they appear across the submitted images)
and determines if the unit is currently within its valid service period.

Model tier: gemini-2.5-flash
Justification: gemini-2.5-pro was the original choice for this check given
its superior vision-OCR and reasoning. However, the Gemini API free tier
sets a hard limit of 0 requests/day for gemini-2.5-pro (confirmed via
RESOURCE_EXHAUSTED with limit: 0 in the API error response) — meaning Pro
is not available on the free tier at all as of May 2026.

gemini-2.5-flash is the strongest model actually accessible on the free tier
(250 RPD, 10 RPM). It supports thinking mode, structured output, and has
the same 1M token context window and image understanding capabilities as Pro.
The prompt is written defensively — requiring UNCERTAIN when dates are
unclear — so any model uncertainty surfaces as REVIEW rather than a false PASS.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from checks.base import CheckResult, UsageRecord
from utils.gemini_client import call_gemini

MODEL = "gemini-2.5-flash"

PROMPT = """You are a fire-safety equipment inspector examining a refill compliance label.

Look across ALL provided images and find the label that contains:
  - A "Reffiling Date" (or "Refilling Date") field — the date the unit was last refilled
  - A "Reffiling Due Date" (or "Refilling Due Date") field — the date by which the next
    refill is required

These dates are typically handwritten into blank fields on a branded service label.
They may be in formats like DD/MM/YYYY, MM/YYYY, DD-MM-YY, or similar.

TODAY'S DATE: {today}

Your task:
1. Locate and read BOTH date fields from whichever image contains them.
2. Parse the dates as best you can, noting any ambiguity.
3. Determine if the unit is currently within its valid service period:
   - Reffiling Date must be in the past (already refilled).
   - Reffiling Due Date must be in the future (not yet expired).
   - If Reffiling Due Date has passed → FAIL (expired).
   - If Reffiling Due Date is in the future → PASS.
   - If you cannot read one or both dates with confidence → UNCERTAIN.

Important: If you are not confident about the date reading (handwriting is unclear,
image is blurry, dates are partially obscured), return UNCERTAIN rather than guessing.
A wrong PASS on an expired unit is worse than an UNCERTAIN result.

Respond ONLY with a JSON object — no markdown, no explanation outside the JSON:
{{
  "status": "PASS" | "FAIL" | "UNCERTAIN",
  "confidence": <float 0.0 to 1.0>,
  "reason": "<single sentence: state both dates read and the decision>",
  "refilling_date": "<date as read, e.g. 20/04/2026, or null if not found>",
  "refilling_due_date": "<date as read, e.g. 20/04/2027, or null if not found>"
}}"""


def run(images: list[bytes], usage: UsageRecord) -> CheckResult:
    today_str = date.today().strftime("%d/%m/%Y")
    prompt = PROMPT.format(today=today_str)

    result = call_gemini(
        model=MODEL,
        images=images,
        prompt=prompt,
        usage=usage,
    )

    return CheckResult(
        status=result["status"],
        confidence=float(result["confidence"]),
        reason=result["reason"],
        extra={
            "refilling_date": result.get("refilling_date"),
            "refilling_due_date": result.get("refilling_due_date"),
        },
    )