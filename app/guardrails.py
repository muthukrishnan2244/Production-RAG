"""Conservative, deterministic demo guardrails. Not a substitute for IAM or auth."""
import re
from fastapi import HTTPException

# Explicit attack patterns rather than blocking ordinary questions about passwords.
INJECTION = [
    r"\bignore\s+(?:all\s+|any\s+|the\s+|previous\s+|prior\s+)?(?:instructions|rules|system\s+prompt)\b",
    r"\b(?:reveal|print|show|dump|disclose)\s+(?:your\s+|the\s+|hidden\s+|internal\s+)*(?:system|developer)\s+(?:prompt|instructions)\b",
    r"\b(?:reveal|print|dump|expose|send)\s+(?:your\s+|all\s+|the\s+)*(?:api\s*keys?|passwords?|credentials?|secrets?|access\s+tokens?)\b",
    r"\b(?:bypass|disable|turn\s+off)\s+(?:all\s+|the\s+)?(?:guardrails|safety\s+checks|security\s+controls)\b",
    r"\b(?:pretend|act)\s+(?:you\s+are|as\s+if\s+you\s+are)\s+(?:the\s+)?(?:system|developer|administrator)\b",
]
SENSITIVE_OUTPUT = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:aws_secret_access_key|pinecone_api_key|database_url)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(?:password|api[_ -]?key|secret[_ -]?key)\s*[:=]\s*[\"']?[^\s\"']{12,}"),
]

class GuardrailBlocked(ValueError):
    pass

def classify_input(question: str) -> str | None:
    if not question or not question.strip():
        return 'empty_input'
    if any(re.search(pattern, question, re.I) for pattern in INJECTION):
        return 'prompt_injection_or_secret_request'
    return None

def check_input(question: str) -> str:
    reason = classify_input(question)
    if reason:
        raise HTTPException(status_code=400, detail=f'Input guardrail blocked this request ({reason}).')
    return question

def contains_sensitive_output(text: str) -> bool:
    return any(pattern.search(text or '') for pattern in SENSITIVE_OUTPUT)

def check_output(answer: str) -> str:
    if contains_sensitive_output(answer):
        return 'The response was blocked by the sensitive-data output guardrail.'
    return answer

def check_evidence(text: str) -> str:
    """Label retrieved document passages as untrusted. Never follow embedded instructions."""
    # We don't delete user documents or discard factual content based on regex.
    return text