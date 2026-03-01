from fastapi import FastAPI, UploadFile, File, Query
import io
import re
import json
import os
from typing import Any, Dict, List, Optional

import pdfplumber
import requests

# --------------------------------------------------------------------------------------
# CONFIG (vLLM)
# --------------------------------------------------------------------------------------
# Set these in your shell (recommended):
#   export VLLM_BASE_URL="http://127.0.0.1:30001"
#   export VLLM_MODEL_ID="Qwen/Qwen2.5-1.5B-Instruct"
#
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://127.0.0.1:30001").rstrip("/")
MODEL_ID = os.getenv("VLLM_MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")

VLLM_MODELS_URL = f"{VLLM_BASE_URL}/v1/models"
VLLM_CHAT_URL = f"{VLLM_BASE_URL}/v1/chat/completions"

# --------------------------------------------------------------------------------------
# APP
# --------------------------------------------------------------------------------------
app = FastAPI(title="LeaseLens Backend", version="0.2.0")

# --------------------------------------------------------------------------------------
# PII
# --------------------------------------------------------------------------------------
PII_PATTERNS = {
    "email": re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}

def find_pii(text: str) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}
    for k, pattern in PII_PATTERNS.items():
        matches = pattern.findall(text or "")
        uniq = list(dict.fromkeys(matches))[:20]
        if uniq:
            found[k] = uniq
    return found

def redact_pii(text: str) -> str:
    redacted = text
    for k, pattern in PII_PATTERNS.items():
        redacted = pattern.sub(f"[REDACTED_{k.upper()}]", redacted)
    return redacted

# --------------------------------------------------------------------------------------
# PDF TEXT EXTRACTION
# --------------------------------------------------------------------------------------
def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        chunks = []
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
        return "\n".join(chunks).strip()

# --------------------------------------------------------------------------------------
# DETERMINISTIC RISK SCAN (backup/hybrid)
# --------------------------------------------------------------------------------------
RISK_RULES = [
    {
        "id": "auto_renewal",
        "title": "Automatic Renewal Clause",
        "severity": "medium",
        "points": 20,
        "patterns": [
            r"auto(?:matic)?\s+renew",
            r"automatically\s+renew",
            r"renews?\s+for\s+another\s+term",
            r"month[-\s]?to[-\s]?month\s+thereafter",
            r"month[-\s]?to[-\s]?month\s+agreement\s+automatically",
        ],
    },
    {
        "id": "late_fee",
        "title": "Late Payment Penalties",
        "severity": "low",
        "points": 10,
        "patterns": [
            r"late\s+fee",
            r"penalt(y|ies)",
            r"after\s+\d+\s+days?\s+late",
        ],
    },
    {
        "id": "non_refundable_deposit",
        "title": "Non-refundable Fees / Deposit Forfeiture",
        "severity": "high",
        "points": 25,
        "patterns": [
            r"non[-\s]?refundable",
            r"forfeit(ed|ure)?\s+deposit",
        ],
    },
]

def scan_risks(text: str) -> Dict[str, Any]:
    t = (text or "").lower()
    findings = []
    score = 0

    for rule in RISK_RULES:
        for pat in rule["patterns"]:
            if re.search(pat, t):
                findings.append(
                    {
                        "id": rule["id"],
                        "title": rule["title"],
                        "severity": rule["severity"],
                        "points": rule["points"],
                    }
                )
                score += int(rule["points"])
                break

    if score >= 40:
        level = "high"
    elif score >= 20:
        level = "medium"
    elif score > 0:
        level = "low"
    else:
        level = "none"

    return {"score": score, "level": level, "findings": findings}

# --------------------------------------------------------------------------------------
# LEASE FIELD EXTRACTION HELPERS
# --------------------------------------------------------------------------------------
def _money_to_decimal(match: Optional[str]) -> Optional[float]:
    if not match:
        return None
    s = match.replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except Exception:
        return None

def extract_rent_deposit_duration_notice(text: str) -> Dict[str, Any]:
    t = text or ""

    rent = None
    m = re.search(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{2})?)\s*(?:per\s+month|monthly)", t, re.IGNORECASE)
    if m:
        rent = _money_to_decimal(m.group(1))

    deposit = None
    m = re.search(
        r"(?:security\s+deposit|deposit)\s*(?:is|of|:)?\s*\$\s*([0-9][0-9,]*(?:\.[0-9]{2})?)",
        t,
        re.IGNORECASE,
    )
    if m:
        deposit = _money_to_decimal(m.group(1))

    duration_days = None
    if re.search(r"\bone\s+year\b", t, re.IGNORECASE):
        duration_days = 365
    elif re.search(r"\btwo\s+years\b", t, re.IGNORECASE):
        duration_days = 730

    notice_days = None
    m = re.search(r"at\s+least\s+(\d+)\s+days?\s+prior", t, re.IGNORECASE)
    if m:
        try:
            notice_days = int(m.group(1))
        except Exception:
            pass

    return {
        "rent_monthly": rent,
        "down_payment": deposit,
        "duration": duration_days,
        "notice_period": notice_days,
    }

# --------------------------------------------------------------------------------------
# vLLM (OpenAI-compatible) CALL
# --------------------------------------------------------------------------------------
def call_vllm_structured(title: str, user: str, raw_text: str) -> Dict[str, Any]:
    """
    Returns a dict matching the required output schema (STRICT JSON).
    """

    prompt = f"""
You are Leasify, an informational rental-lease analyzer (NOT a lawyer).
Your job: extract only what is explicitly present in the lease text and produce a short, reliable summary.
DO NOT guess. If something is missing or unclear, set it to null and explain briefly in "missing_reason".
Always support key outputs with an EXACT quote from the lease in "evidence_quote".
Try to produce at least 7 annotations.
For questions, generate 3-5 high-priority questions a tenant should ask to clarify risks/obligations.

INPUT
- LEASE TITLE / FILE: {title}
- RAW TEXT (may be partial): {raw_text[:20000]}

SPEED MODE
Only analyze the MOST IMPORTANT 6–10 clauses:
1) Rent amount & due date
2) Security deposit & deductions
3) Fees (late, cleaning, admin, utilities)
4) Lease term & renewal/auto-renew
5) Early termination / break lease
6) Maintenance responsibilities (who pays for what)
7) Landlord entry
8) Subletting/guests/pets
9) Arbitration / legal rights / attorney fees (if present)
10) Notice periods (move-out, renewal, rent increase)

RELIABILITY RULES
- Use ONLY information that appears in the RAW TEXT.
- Every numeric value must be supported by an evidence quote.
- If multiple values exist, list the options and mark "ambiguous": true.
- Evidence quotes must be EXACT and <= 280 characters.
- If text is truncated and you suspect missing sections, set "text_incomplete": true.

OUTPUT REQUIREMENT
Return ONLY valid JSON matching this schema exactly:

{{
  "title": "{title}",
  "text_incomplete": true/false,
  "basic_info": {{
    "address": {{
      "value": string|null,
      "evidence_quote": string|null,
      "missing_reason": string|null
    }}
  }},
  "overview": {{
    "risk_score": int,
    "overview_contents": string,
    "rent_monthly": {{
      "value": number|null,
      "evidence_quote": string|null,
      "missing_reason": string|null,
      "ambiguous": true/false
    }},
    "security_deposit": {{
      "value": number|null,
      "evidence_quote": string|null,
      "missing_reason": string|null,
      "ambiguous": true/false
    }},
    "lease_term_days": {{
      "value": int|null,
      "evidence_quote": string|null,
      "missing_reason": string|null,
      "ambiguous": true/false
    }},
    "notice_period": {{
      "value": string|null,
      "evidence_quote": string|null,
      "missing_reason": string|null
    }},
    "late_fees": {{
      "value": string|null,
      "evidence_quote": string|null,
      "missing_reason": string|null
    }},
    "early_termination": {{
      "value": string|null,
      "evidence_quote": string|null,
      "missing_reason": string|null
    }},
    "utilities": {{
      "value": string|null,
      "evidence_quote": string|null,
      "missing_reason": string|null
    }}
  }},
  "results": [
    {{
      "annotationText": "EXACT TEXT FROM THE LEASE AGREEMENT",
      "annotationLevel": "good"|"mix"|"bad",
      "annotationDesc": "CONCISE DESCRIPTION OF THE ANNOTATION, JUSTIFICATION OF LEVEL+IMPACT",
      "risk_title": string,
      "severity": "HIGH"|"MEDIUM"|"LOW",
      "evidence_location_hint": string|null
    }}
  ],
  "questions": [
    {{
      "question_priority": "high"|"medium"|"low",
      "question_explaination": string|null,
      "question_title": string
    }}
  ]
}}

STYLE
- overview_contents MUST be 10–15 bullet points using • or -
- annotationDesc must be concise (<= 50 words).
- evidence_location_hint: use any nearby header/keyword to help UI highlighting.
""".strip()

    payload = {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": "Return ONLY valid JSON. No markdown. Use double quotes for all keys/strings."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 1800,
        # If your vLLM supports it, this dramatically reduces invalid JSON.
        "response_format": {"type": "json_object"},
    }

    r = requests.post(VLLM_CHAT_URL, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"]

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except Exception:
                pass
        raise ValueError(f"MODEL_RETURNED_INVALID_JSON\nRAW:\n{content[:4000]}")

# --------------------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------------------
@app.get("/")
def root():
    return {"message": "LeaseLens backend running"}

@app.get("/llm/health")
def llm_health():
    r = requests.get(VLLM_MODELS_URL, timeout=10)
    r.raise_for_status()
    return {"ok": True, "vllm_base_url": VLLM_BASE_URL, "models": r.json()}

@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    title: str = Query("", description="Optional lease title/address override"),
    user: str = Query("demo_user", description="User name"),
    redact: bool = Query(False, description="If true, redact PII before returning preview"),
    do_ai: bool = Query(True, description="If true, generate structured lease analysis using AMD vLLM"),
):
    if not file.content_type or "pdf" not in file.content_type.lower():
        return {"error": "Please upload a PDF file."}

    contents = await file.read()
    text = extract_text_from_pdf(contents)

    pii_report = find_pii(text)
    text_for_preview = redact_pii(text) if redact else text

    risk_report = scan_risks(text)
    extracted_fields = extract_rent_deposit_duration_notice(text)

    lease_title = title.strip() or (file.filename or "Untitled Lease")

    ai_structured = None
    ai_error = None

    if do_ai:
        try:
            ai_structured = call_vllm_structured(
                title=lease_title,
                user=user,
                raw_text=text,
            )
        except Exception as e:
            ai_error = str(e)

    return {
        "filename": file.filename,
        "bytes_received": len(contents),
        "pii_found": pii_report,
        "risk": risk_report,
        "redaction_enabled": redact,
        "extracted_text_preview": text_for_preview[:1200],
        "extracted_fields": extracted_fields,
        "vllm_base_url": VLLM_BASE_URL,
        "model_id": MODEL_ID,
        "ai_enabled": do_ai,
        "ai_error": ai_error,
        "ai_structured": ai_structured,
    }