from __future__ import annotations
import json
import os
from typing import Any
from pypdf import PdfReader
from .models import Criterion

PROVIDERS = {
    "OpenAI": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "OpenRouter": {"base_url": "https://openrouter.ai/api/v1", "model": "openai/gpt-4o-mini"},
    "Cohere": {"base_url": "https://api.cohere.ai/compatibility/v1", "model": "command-a-plus-05-2026"},
}

def provider_defaults(provider: str) -> dict[str, str]:
    if provider not in PROVIDERS: raise ValueError(f"Unsupported provider: {provider}")
    return PROVIDERS[provider].copy()

def _client(api_key: str | None = None, base_url: str | None = None):
    resolved_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_key: raise RuntimeError("No API key is configured. Test and enable a provider in the Provider connection panel.")
    from openai import OpenAI
    return OpenAI(api_key=resolved_key, base_url=base_url or os.getenv("OPENAI_BASE_URL") or None)

def validate_provider_connection(api_key: str, base_url: str, model: str) -> str:
    if not api_key.strip(): raise ValueError("Enter an API key before testing the connection.")
    if not model.strip(): raise ValueError("Enter a model name before testing the connection.")
    response = _client(api_key=api_key.strip(), base_url=base_url.strip()).chat.completions.create(model=model.strip(), messages=[{"role": "user", "content": 'Return JSON only: {"status": "READY"}'}], max_tokens=8, temperature=0, response_format={"type": "json_object"})
    content = (response.choices[0].message.content or "").strip()
    if not content: raise RuntimeError("The provider responded without usable content.")
    try: status = json.loads(content).get("status")
    except json.JSONDecodeError as exc: raise RuntimeError("The model did not return valid JSON for the required structured-output check.") from exc
    if not status: raise RuntimeError("The model returned JSON without a status value.")
    return str(status)

def extract_pdf_text(file: Any) -> str:
    reader = PdfReader(file)
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n".join(f"[Page {number}]\n{page.strip()}" for number, page in enumerate(pages, 1) if page.strip()).strip()
    if not text: raise ValueError("The PDF contains no extractable text. Scanned PDFs need OCR before evaluation.")
    if len(text) < 120: raise ValueError("The PDF contains too little extractable text for a defensible evaluation. Use an OCR-ready proposal PDF.")
    return text

def build_prompt(supplier_name: str, document_text: str, criteria: list[Criterion]) -> str:
    criteria_json = json.dumps([{**c.model_dump(include={"criterion_id", "name", "description", "max_score"}), "scoring_anchors": {"0": "No relevant, credible proposal evidence.", "midpoint": f"Partially addresses the criterion with material gaps (about {c.max_score / 2:g}/{c.max_score:g}).", "max": "Direct, specific, credible evidence fully addresses the criterion with no material gap."}} for c in criteria])
    return f'''You are an RFP evidence evaluator. Evaluate only the supplied proposal for {supplier_name}.
Active criteria: {criteria_json}
For every active criterion, return criterion_id, a numeric score from 0 through max_score, a concise justification, a direct verbatim evidence excerpt, its evidence_page from the [Page N] marker, and confidence from 0.0 through 1.0. Never invent facts or cite evidence that is not present. If evidence is missing, set evidence to an empty string, evidence_page to null, confidence to 0.0, clearly say it is missing, and score conservatively.
Return JSON only with this exact shape: {{"supplier_name": "{supplier_name}", "criteria": [{{"criterion_id": 1, "score": 0, "max_score": 10, "justification": "", "evidence": "", "evidence_page": 1, "confidence": 0.0}}], "risks": [], "overall_summary": ""}}.
Proposal:\n{document_text[:50000]}'''

def evaluate_with_openai(supplier_name: str, document_text: str, criteria: list[Criterion], *, api_key: str | None = None, base_url: str | None = None, model: str | None = None) -> dict[str, Any]:
    response = _client(api_key=api_key, base_url=base_url).chat.completions.create(model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"), messages=[{"role": "user", "content": build_prompt(supplier_name, document_text, criteria)}], response_format={"type": "json_object"}, temperature=0)
    return json.loads(response.choices[0].message.content or "{}")

def demo_evaluate(supplier_name: str, document_text: str, criteria: list[Criterion]) -> dict[str, Any]:
    text = document_text.lower()
    signals = {1: ["architecture", "integration", "scalab", "api"], 2: ["timeline", "milestone", "staff", "risk"], 3: ["price", "pricing", "cost", "assumption"], 4: ["security", "compliance", "privacy", "audit"], 5: ["support", "reference", "experience", "service level"]}
    items = []
    for criterion in criteria:
        found = [word for word in signals.get(criterion.criterion_id, []) if word in text]
        score = min(criterion.max_score, 2 + (2 * len(found))) if found else 0
        page, evidence, current_page = None, "", None
        for line in document_text.splitlines():
            if line.startswith("[Page ") and line.endswith("]"):
                try: current_page = int(line[6:-1])
                except ValueError: current_page = None
            elif found and any(word in line.lower() for word in found): evidence, page = line.strip()[:400], current_page; break
        items.append({"criterion_id": criterion.criterion_id, "score": score, "max_score": criterion.max_score, "justification": f"Offline demonstration score based on {len(found)} relevant evidence signals.", "evidence": evidence, "evidence_page": page, "confidence": 0.75 if evidence else 0.0})
    return {"supplier_name": supplier_name, "criteria": items, "risks": ["Demo mode uses deterministic keyword signals; use LLM mode for a real assessment."], "overall_summary": "Offline demonstration evaluation."}
