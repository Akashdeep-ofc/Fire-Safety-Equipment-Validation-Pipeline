"""
Check 3 — Pressure gauge
=========================
Verifies the pressure gauge needle is in the green (safe) zone,
the gauge face is intact, and there are no signs of tampering or damage.

Model tier: gemini-2.5-flash
Justification: Reading a gauge needle position is a clear visual task that
requires moderate precision — distinguishing red vs green zone and spotting
physical damage. Flash provides sufficient vision quality at 10× the daily
quota of Pro. Flash-Lite was considered but may struggle with small gauge
details at lower resolution.
"""

from checks.base import CheckResult, UsageRecord
from utils.gemini_client import call_gemini

MODEL = "gemini-2.5-flash"

PROMPT = """You are a fire-safety equipment inspector checking the pressure gauge.

Look across ALL provided images and find the one(s) showing the pressure gauge —
the circular dial mounted on the extinguisher body or valve assembly.

Evaluate THREE things:
1. NEEDLE POSITION: Is the needle pointing to the green (safe/charged) zone?
   - Green zone = acceptable pressure. PASS.
   - Red zone (low or high) = unsafe pressure. FAIL.
   - Needle position ambiguous or gauge not clearly visible = UNCERTAIN.

2. GAUGE INTEGRITY: Is the gauge face intact?
   - Cracked glass, broken dial, bent casing = FAIL.
   - Clean and undamaged = PASS.

3. TAMPERING SIGNS: Are there any signs the gauge has been tampered with?
   - Evidence of the gauge being replaced, glued, painted over, or otherwise
     altered = FAIL.
   - No tampering signs = PASS.

Overall status rules:
- PASS: needle in green, gauge intact, no tampering.
- FAIL: any of the three sub-checks fail.
- UNCERTAIN: gauge not visible in any image, or image quality too poor to judge.

Respond ONLY with a JSON object — no markdown, no explanation outside the JSON:
{
  "status": "PASS" | "FAIL" | "UNCERTAIN",
  "confidence": <float 0.0 to 1.0>,
  "reason": "<single sentence summarising needle position, integrity, and tampering finding>",
  "needle_zone": "<'green' | 'red_low' | 'red_high' | 'unknown'>",
  "gauge_intact": <true | false | null>,
  "tampering_detected": <true | false | null>
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
            "needle_zone": result.get("needle_zone"),
            "gauge_intact": result.get("gauge_intact"),
            "tampering_detected": result.get("tampering_detected"),
        },
    )
