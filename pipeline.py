#!/usr/bin/env python3
"""
Fire Extinguisher Validation Pipeline
======================================
Usage:
    python pipeline.py <folder_of_images> [--submission-id <id>] [--output <path>]

Examples:
    python pipeline.py data/sample/
    python pipeline.py data/sample/ --submission-id unit_42
    python pipeline.py data/sample/ --output output/my_report.json

The folder must contain at least one image (JPEG or PNG).
The JSON report is written to the output path (default: output/report.json)
and also printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env file before anything that reads GEMINI_API_KEY
load_dotenv()

from checks.base import CheckResult, UsageRecord, Verdict
import checks.subject as subject_check
import checks.refill as refill_check
import checks.gauge as gauge_check
import checks.tamper as tamper_check
import checks.serial as serial_check

# ---------------------------------------------------------------------------
# Image loading
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def load_images(folder: Path) -> list[bytes]:
    """Load all supported images from folder, sorted by filename."""
    paths = sorted(
        p for p in folder.iterdir()
        if p.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not paths:
        raise ValueError(
            f"No supported images found in '{folder}'. "
            f"Expected JPEG or PNG files."
        )
    print(f"  Loaded {len(paths)} image(s): {[p.name for p in paths]}")
    return [p.read_bytes() for p in paths]


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------

def compute_verdict(checks: dict[str, CheckResult]) -> Verdict:
    """
    REJECT  — any check is FAIL
    REVIEW  — no FAILs but at least one UNCERTAIN
    ACCEPT  — all checks are PASS
    """
    statuses = [r.status for r in checks.values()]
    if "FAIL" in statuses:
        return "REJECT"
    if "UNCERTAIN" in statuses:
        return "REVIEW"
    return "ACCEPT"


# ---------------------------------------------------------------------------
# Report serialisation
# ---------------------------------------------------------------------------

def serialise_check(name: str, result: CheckResult, usage: UsageRecord) -> dict:
    out = {
        "status": result.status,
        "confidence": round(result.confidence, 3),
        "reason": result.reason,
        "usage": {
            "model": usage.model,
            "calls": usage.calls,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
    }
    if result.extra:
        out["details"] = result.extra
    return out


def build_report(
    submission_id: str,
    folder: Path,
    checks_results: dict[str, tuple[CheckResult, UsageRecord]],
    verdict: Verdict,
) -> dict:
    total_calls = sum(u.calls for _, u in checks_results.values())
    total_in = sum(u.input_tokens for _, u in checks_results.values())
    total_out = sum(u.output_tokens for _, u in checks_results.values())

    return {
        "submission_id": submission_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "image_folder": str(folder),
        "checks": {
            name: serialise_check(name, result, usage)
            for name, (result, usage) in checks_results.items()
        },
        "verdict": verdict,
        "usage_summary": {
            "total_calls": total_calls,
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "per_check": {
                name: {
                    "model": usage.model,
                    "calls": usage.calls,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                }
                for name, (_, usage) in checks_results.items()
            },
        },
    }


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(
    folder: Path,
    submission_id: str,
    output_path: Path,
) -> dict:
    print(f"\n{'='*60}")
    print(f"  Fire Extinguisher Validation Pipeline")
    print(f"  Submission : {submission_id}")
    print(f"  Folder     : {folder}")
    print(f"{'='*60}\n")

    # --- Load images ---
    print("[0/5] Loading images...")
    images = load_images(folder)

    checks_results: dict[str, tuple[CheckResult, UsageRecord]] = {}

    # --- Check 1: Subject verification ---
    print("\n[1/5] Subject verification  (gemini-2.5-flash-lite)...")
    u1 = UsageRecord(model="gemini-2.5-flash-lite")
    r1 = subject_check.run(images, u1)
    checks_results["subject_verification"] = (r1, u1)
    _print_result(r1)

    # Early exit: if this isn't a fire extinguisher, skip remaining checks
    if r1.status == "FAIL":
        print("\n  ⚠  Subject verification FAILED — skipping remaining checks.")
        for name in ["refill_status", "pressure_gauge", "tamper_seal", "serial_uniqueness"]:
            skip_usage = UsageRecord(model="skipped")
            skip_result = CheckResult(
                status="UNCERTAIN",
                confidence=0.0,
                reason="Skipped: subject verification failed — not a fire extinguisher.",
            )
            checks_results[name] = (skip_result, skip_usage)
        verdict = "REJECT"
    else:
        # --- Check 2: Refill status ---
        print("\n[2/5] Refill status         (gemini-2.5-flash)...")
        u2 = UsageRecord(model="gemini-2.5-flash")
        r2 = refill_check.run(images, u2)
        checks_results["refill_status"] = (r2, u2)
        _print_result(r2)

        # --- Check 3: Pressure gauge ---
        print("\n[3/5] Pressure gauge        (gemini-2.5-flash)...")
        u3 = UsageRecord(model="gemini-2.5-flash")
        r3 = gauge_check.run(images, u3)
        checks_results["pressure_gauge"] = (r3, u3)
        _print_result(r3)

        # --- Check 4: Tamper seal ---
        print("\n[4/5] Tamper seal           (gemini-2.5-flash)...")
        u4 = UsageRecord(model="gemini-2.5-flash")
        r4 = tamper_check.run(images, u4)
        checks_results["tamper_seal"] = (r4, u4)
        _print_result(r4)

        # --- Check 5: Serial number + uniqueness ---
        print("\n[5/5] Serial number         (gemini-2.5-flash + SQLite)...")
        u5 = UsageRecord(model="gemini-2.5-flash")
        r5 = serial_check.run(
            images, u5,
            submission_id=submission_id,
            image_folder=str(folder),
        )
        checks_results["serial_uniqueness"] = (r5, u5)
        _print_result(r5)

        verdict = compute_verdict({n: r for n, (r, _) in checks_results.items()})

    # --- Build and write report ---
    report = build_report(submission_id, folder, checks_results, verdict)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))

    print(f"\n{'='*60}")
    print(f"  VERDICT: {verdict}")
    print(f"  Report written to: {output_path}")
    print(f"{'='*60}\n")

    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STATUS_ICON = {"PASS": "✓", "FAIL": "✗", "UNCERTAIN": "?"}


def _print_result(result: CheckResult) -> None:
    icon = _STATUS_ICON.get(result.status, "?")
    print(f"  {icon} {result.status} (confidence: {result.confidence:.2f})")
    print(f"    {result.reason}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Validate fire extinguisher submissions from a folder of images."
    )
    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing the submission images (JPEG/PNG)",
    )
    parser.add_argument(
        "--submission-id",
        default=None,
        help="Unique ID for this submission (auto-generated if not provided)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/report.json"),
        help="Path to write the JSON report (default: output/report.json)",
    )
    args = parser.parse_args()

    folder = args.folder.resolve()
    if not folder.is_dir():
        print(f"Error: '{folder}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    submission_id = args.submission_id or f"sub_{uuid.uuid4().hex[:8]}"

    report = run_pipeline(
        folder=folder,
        submission_id=submission_id,
        output_path=args.output,
    )

    # Also print the full JSON to stdout for piping
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()