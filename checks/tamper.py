"""
Check 4 — Tamper seal
======================
Verifies the safety pin and/or numbered tamper-evident seal is present
and unbroken on the extinguisher's trigger mechanism.

Model tier: gemini-2.5-flash
Justification: Identifying a physical plastic seal or safety pin in an image
is a moderately detailed visual task — the object is small and may be partially
occluded. Flash provides reliable close-up object detection without needing
Pro-level reasoning. Matched tier to gauge check for consistency.
"""

from checks.base import CheckResult, UsageRecord
from utils.gemini_client import call_gemini

MODEL = "gemini-2.5-flash"

PROMPT = """You are a fire-safety equipment inspector checking the tamper-evident seal.

Look across ALL provided images and find the one(s) showing the handle/valve area
of the fire extinguisher — specifically the safety mechanism.

You are looking for a tamper-evident device. This could be:
  - A plastic numbered seal / tag (often yellow, red, or white) threaded through
    the safety pin and handle/trigger, preventing accidental discharge.
  - A metal safety pin (split ring) alone without a plastic seal.
  - A numbered plastic cable tie or wire seal.

Evaluate:
1. Is any form of tamper-evident seal or safety pin PRESENT? (yes / no / unsure)
2. If present, does it appear UNBROKEN and INTACT?
   - Broken, cut, missing, or deformed seal/pin = FAIL.
   - Seal present and visibly intact = PASS.
   - Cannot determine from images = UNCERTAIN.

Status rules:
- PASS: seal/pin clearly present and unbroken.
- FAIL: seal/pin clearly missing, broken, or tampered.
- UNCERTAIN: valve/handle area not visible in any image, or image too blurry to judge.

Do NOT fail just because the seal type differs from what you might expect —
different brands use different seal styles.

Respond ONLY with a JSON object — no markdown, no explanation outside the JSON:
{
  "status": "PASS" | "FAIL" | "UNCERTAIN",
  "confidence": <float 0.0 to 1.0>,
  "reason": "<single sentence: describe what was found and the decision>",
  "seal_present": <true | false | null>,
  "seal_type": "<description of seal, e.g. 'yellow numbered plastic tag' or null>"
}"""


def run(images: list[bytes], usage: UsageRecord) -> CheckResult:
    result = call_gemini(
        model=MODEL,
        images=images,
        prompt=PROMPT,
        usage=usage,
    )

    return CheckResult(
        status=result["status"],
        confidence=float(result["confidence"]),
        reason=result["reason"],
        extra={
            "seal_present": result.get("seal_present"),
            "seal_type": result.get("seal_type"),
        },
    )
