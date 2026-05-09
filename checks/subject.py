"""
Check 1 — Subject verification
================================
Confirms the submission images show a real, physical fire extinguisher —
not a screenshot, stock photo, illustration, or unrelated object.

Model tier: gemini-2.5-flash-lite
Justification: This is the simplest visual recognition task. Flash-Lite
handles it accurately at the lowest cost (1 000 req/day free). No deep
reasoning required — just object identification across all images.
"""

from checks.base import CheckResult, UsageRecord
from utils.gemini_client import call_gemini

MODEL = "gemini-2.5-flash-lite"

PROMPT = """You are a fire-safety equipment inspector.

You will be given one or more photographs from a single submission.
Your task: determine whether the images show a real, physical fire extinguisher.

Rules:
- A real fire extinguisher is a pressurised cylindrical vessel with a handle,
  hose/nozzle, pressure gauge, and safety pin. It may be any colour or brand.
- FAIL if the images show: a screenshot of an extinguisher, a stock photo or
  illustration, a toy, a different type of safety equipment, or an unrelated object.
- UNCERTAIN if image quality is too poor to make a determination (very blurry,
  completely dark, or no relevant object visible).
- PASS only if at least one image clearly shows a real physical fire extinguisher.

Examine ALL provided images before deciding.

Respond ONLY with a JSON object — no markdown, no explanation outside the JSON:
{
  "status": "PASS" | "FAIL" | "UNCERTAIN",
  "confidence": <float 0.0 to 1.0>,
  "reason": "<single sentence explaining the decision>"
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
    )
