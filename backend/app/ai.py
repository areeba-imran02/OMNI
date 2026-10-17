import os, json, urllib.request, urllib.error
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

@dataclass
class AIResult:
    text: str
    model: str
    fallback_used: bool

def model_candidates():
    raw = os.getenv("GEMINI_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash")
    return [x.strip() for x in raw.split(",") if x.strip()]

def _request_model(api_key: str, model: str, prompt: str, system: str, temperature: float) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    combined = (("SYSTEM INSTRUCTIONS (guidance):\n" + system + "\n\n") if system else "") + prompt
    payload = {
        "contents": [{"role": "user", "parts": [{"text": combined}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 4096}
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=75) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Gemini API HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"Gemini request failed: {exc}") from exc
    candidates = data.get("candidates") or []
    chunks = []
    for candidate in candidates:
        for part in (candidate.get("content") or {}).get("parts") or []:
            if isinstance(part.get("text"), str):
                chunks.append(part["text"])
    text = "\n".join(chunks).strip()
    if not text:
        reason = (data.get("promptFeedback") or {}).get("blockReason")
        raise RuntimeError(f"{model} returned no text (block reason: {reason or 'not provided'}).")
    return text

def generate(prompt: str, system: str = "", temperature: float = 0.35) -> AIResult:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add your Google AI Studio key in Streamlit Cloud → App settings → Secrets.")
    errors = []
    models = model_candidates()
    for idx, model in enumerate(models):
        try:
            return AIResult(_request_model(key, model, prompt, system, temperature), model, idx > 0)
        except Exception as exc:
            errors.append(f"{model}: {str(exc)[:180]}")
    raise RuntimeError("All configured Gemini models failed. " + " | ".join(errors))

def strip_fences(text: str) -> str:
    import re
    text = text.strip()
    text = re.sub(r"^```(?:json|markdown|md)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()
