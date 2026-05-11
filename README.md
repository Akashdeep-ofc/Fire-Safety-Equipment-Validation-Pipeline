# Fire Extinguisher Validation Pipeline

A Python pipeline that takes photographs of a fire extinguisher submission and returns a structured JSON report covering five safety checks.

## Setup

### 1. Get a Gemini API key

1. Go to [aistudio.google.com](https://aistudio.google.com) and sign in with any Google account.
2. Accept the Terms of Service for Generative AI (one-time).
3. Click **Get API key → Create API key in new project**. Copy the key immediately.

### 2. Configure the key

```bash
cp .env.example .env
# Edit .env and paste your key:
# GEMINI_API_KEY=your_key_here
```

Or set it directly in your shell session:

```bash
export GEMINI_API_KEY="your_key_here"
```

**Never commit your API key.** The `.env` file is in `.gitignore`.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Python 3.10+ required.

---

## Running the pipeline

```bash
# Basic usage — point at a folder of images
python pipeline.py data/sample/

# With an explicit submission ID
python pipeline.py data/sample/ --submission-id unit_001

# Write the report to a custom path
python pipeline.py data/sample/ --output output/my_report.json
```

The pipeline accepts any folder containing JPEG or PNG images. It writes the JSON report to `output/report.json` by default, or to the path you specify. The committed sample run was generated with `--output output/sample_run.json`.

---

## Model and tier choices

| Check | Model tier | Reason |
| --- | --- | --- |
| 1. Subject verification | `gemini-3.1-flash-lite` | Simplest task — recognising a fire extinguisher in photos is straightforward object detection. Gemini 3.1 Flash Lite handles it reliably at the lowest cost. Chosen over `gemini-2.5-flash-lite` because the free tier on this account gives 3.1 Flash Lite 500 RPD vs only 20 RPD for 2.5 Flash Lite — 25× more daily headroom for the cheapest check. |
| 2. Refill status | `gemini-2.5-flash` | Hardest task — reads handwritten dates on a real-world label that may be skewed, partially lit, or on a curved surface, then reasons about date arithmetic. `gemini-2.5-pro` was the original choice, but the free tier on this account sets a hard limit of 0 requests/day for Pro (confirmed by API error: `limit: 0` on `generate_content_free_tier_requests`). `gemini-2.5-flash` is the strongest model actually accessible on the free tier. The prompt requires UNCERTAIN when dates are ambiguous, so model uncertainty surfaces as REVIEW rather than a false PASS. |
| 3. Pressure gauge | `gemini-2.5-flash` | Requires fine-grained visual inspection of a small gauge needle and assessment of physical integrity. Flash is more reliable than Flash-Lite for this precision task. |
| 4. Tamper seal | `gemini-2.5-flash` | Small-object inspection task requiring detection of seal presence and integrity across varied image angles. |
| 5. Serial number | `gemini-2.5-flash` | Printed OCR and structured extraction are well within Flash capability. A local SQLite deduplication check is performed after OCR extraction. |

An alternative architecture considered was a single multimodal API call generating all checks simultaneously. The final implementation instead uses one isolated API call per check to improve modularity, prompt isolation, debugging clarity, failure isolation, and per-check token accounting.

---

## Free tier rate limits (verified from AI Studio dashboard)

| Model | RPM | RPD |
| --- | --- | --- |
| `gemini-3.1-flash-lite` | 15 | 500 |
| `gemini-2.5-flash` | 5 | 20 |

With 1 call to Flash-Lite and 4 calls to Flash per submission, the binding constraint is Flash at 20 RPD — approximately **4–5 full pipeline runs per day** before hitting the daily ceiling. A second Google account with a separate API key is recommended as a backup during live demonstration.

---

## Image routing

The pipeline sends **all images** to every check. Rather than hard-coding which image number contains which feature (which would break on real-world submissions with different layouts), each check prompt instructs the model to scan across all provided images and identify the relevant component itself.

---

## UNCERTAIN as a first-class outcome

Every check prompt explicitly instructs the model: *"If you cannot see the relevant area clearly or are not confident, return UNCERTAIN rather than guessing."* A wrong PASS is worse than an UNCERTAIN — the pipeline will output `REVIEW` rather than `ACCEPT` when any check is uncertain, flagging the submission for human inspection.

---

## Deduplication store

Serial numbers are stored in `data/serials.db` (SQLite). The first submission with a given serial number is recorded; any subsequent submission with the same serial returns FAIL with details of the prior record.

The SQLite database is created automatically on first run. The repository does not include persisted submission records so evaluation starts from a clean deduplication state.

To reset the store for testing:

```bash
rm data/serials.db
```

---

## Sample run output

The JSON report for the included sample (`data/sample/`) is committed at `output/sample_run.json`.

### Sample run command

```bash
python pipeline.py data/sample/ --submission-id sample_001 --output output/sample_run.json
```

### Tokens and calls from the sample run

| Check | Model | Calls | Input tokens | Output tokens | Thinking tokens | Total tokens |
| --- | --- | --- | --- | --- | --- | --- |
| subject_verification | gemini-3.1-flash-lite | 1 | 4498 | 50 | 0 | 4548 |
| refill_status | gemini-2.5-flash | 1 | 1511 | 128 | 731 | 2370 |
| pressure_gauge | gemini-2.5-flash | 1 | 1423 | 83 | 504 | 2010 |
| tamper_seal | gemini-2.5-flash | 1 | 1429 | 73 | 462 | 1964 |
| serial_uniqueness | gemini-2.5-flash | 1 | 1266 | 66 | 399 | 1731 |
| **Total** | | **5** | **10127** | **400** | **2096** | **12623** |

Thinking tokens will be non-zero if the model engages its reasoning mode for a particular check. The exact numbers from the committed sample run are in `output/sample_run.json` under `usage_summary`.