"""Small, defensive wrapper around Sarvam's documented REST APIs."""

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.sarvam.ai"
CHAT_MODEL = "sarvam-105b-conversations"
STT_MODEL = "saaras:v4"
TTS_MODEL = "bulbul:v4-flash"
FIELDS = ("name", "age", "age_unit", "visit_type", "hb", "bp", "weight_kg", "symptoms", "quotes")
SYSTEM_PROMPT = """Extract patient information only. Never diagnose, assess urgency, infer missing values, or guess. Support Hindi, Marathi, English and code-mixed Indian speech. A note may describe multiple patients; return one object per patient. Return only valid JSON array, no Markdown. Every extracted field must have a quote copied verbatim from the transcript; do not translate, normalize or paraphrase quotes. Unknown scalar values and their quotes are null; symptoms is always an array. Numeric structured values may be normalized. Each object must contain exactly name, age, age_unit (days/months/years/null), visit_type, hb, bp, weight_kg, symptoms, quotes. quotes has those field names (except quotes itself). If uncertain, use null."""


class SarvamError(RuntimeError):
    """Safe, user-displayable API error."""


def get_api_key() -> str:
    """Read the key from local .env/environment or hosted Streamlit Secrets."""
    load_dotenv(Path(__file__).with_name(".env"))
    key = os.getenv("SARVAM_API_KEY", "").strip()
    if not key:
        try:
            import streamlit as st
            key = str(st.secrets.get("SARVAM_API_KEY", "")).strip()
        except (FileNotFoundError, KeyError):
            key = ""
    if not key:
        raise SarvamError("SARVAM_API_KEY is missing. Set it in the environment or Streamlit Secrets.")
    return key


def is_configured() -> bool:
    """Check whether a key is available without returning or displaying it."""
    try:
        return bool(get_api_key())
    except SarvamError:
        return False


def _post(path: str, **kwargs: Any) -> requests.Response:
    headers = {"api-subscription-key": get_api_key()}
    try:
        response = requests.post(BASE_URL + path, headers=headers, timeout=90, **kwargs)
    except requests.RequestException as exc:
        raise SarvamError("Could not reach Sarvam. Check your connection and retry.") from exc
    if not response.ok:
        try:
            detail = response.json().get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            detail = ""
        raise SarvamError(f"Sarvam request failed ({response.status_code})" + (f": {detail}" if detail else "."))
    return response


def stt(audio_bytes: bytes) -> str:
    """Transcribe a short audio clip in its original language."""
    if not audio_bytes:
        raise SarvamError("No audio was provided.")
    response = _post("/speech-to-text", files={"file": ("recording.wav", audio_bytes, "audio/wav")},
                     data={"model": STT_MODEL})
    try:
        transcript = response.json()["transcript"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SarvamError("Sarvam returned an unreadable transcription response.") from exc
    if not isinstance(transcript, str) or not transcript.strip():
        raise SarvamError("Sarvam did not return a transcript.")
    return transcript.strip()


def _clean_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _validate_patients(raw: Any, transcript: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise SarvamError("Extraction did not return a patient list. Please retry.")
    result = []
    for item in raw:
        if not isinstance(item, dict):
            raise SarvamError("Extraction returned an invalid patient record. Please retry.")
        patient = {k: item.get(k) for k in FIELDS}
        if patient["name"] is not None and not isinstance(patient["name"], str):
            patient["name"] = None
        patient["age"] = _number(patient["age"])
        patient["hb"] = _number(patient["hb"])
        patient["weight_kg"] = _number(patient["weight_kg"])
        if patient["age_unit"] not in ("days", "months", "years"):
            patient["age_unit"] = None
        if patient["visit_type"] is not None and not isinstance(patient["visit_type"], str):
            patient["visit_type"] = None
        if patient["bp"] is not None and not isinstance(patient["bp"], str):
            patient["bp"] = None
        if not isinstance(patient["symptoms"], list):
            patient["symptoms"] = []
        patient["symptoms"] = [s for s in patient["symptoms"] if isinstance(s, str)]
        quotes = patient["quotes"] if isinstance(patient["quotes"], dict) else {}
        patient["quotes"] = {}
        for field in FIELDS[:-1]:
            quote = quotes.get(field)
            patient["quotes"][field] = quote if isinstance(quote, str) and quote in transcript else None
            if patient[field] is None or (field == "symptoms" and not patient[field]):
                patient["quotes"][field] = None
            elif patient["quotes"][field] is None:
                # Unsupported extracted values are discarded rather than shown as fact.
                patient[field] = [] if field == "symptoms" else None
        result.append(patient)
    return result


def extract(transcript: str) -> list[dict[str, Any]]:
    """Extract patient fields, keeping risk assessment out of the model."""
    if not transcript.strip():
        raise SarvamError("Transcript is empty.")
    response = _post("/v1/chat/completions", json={"model": CHAT_MODEL, "temperature": 0.1,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": transcript}]})
    try:
        content = response.json()["choices"][0]["message"]["content"]
        raw = json.loads(_clean_json(content))
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise SarvamError("Could not safely parse the extraction response. Please retry.") from exc
    return _validate_patients(raw, transcript)


def tts(text: str, lang: str = "hi-IN") -> bytes:
    """Synthesize speech and return decoded WAV bytes."""
    if not text.strip():
        raise SarvamError("No text was provided for speech.")
    response = _post("/text-to-speech", json={"text": text, "language_code": lang,
        "model": TTS_MODEL, "output_audio_codec": "wav"})
    try:
        encoded = response.json()["audios"][0]
        audio = base64.b64decode(encoded, validate=True)
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise SarvamError("Sarvam returned an unreadable audio response.") from exc
    if not audio:
        raise SarvamError("Sarvam returned empty audio.")
    return audio


if __name__ == "__main__":
    print("STT smoke test needs an audio file path; run: python sarvam_client.py sample.wav")
    import sys
    if len(sys.argv) == 2:
        try:
            print("[1/3] Testing Sarvam STT...")
            transcript = stt(open(sys.argv[1], "rb").read())
            print("SUCCESS")
            print("[2/3] Testing Sarvam Chat Completions...")
            patients = extract(transcript)
            print("SUCCESS")
            print("[3/3] Testing Sarvam TTS...")
            tts(transcript[:300])
            print("SUCCESS")
        except SarvamError as exc:
            print(f"FAILED: {exc}")
            raise SystemExit(1)
    elif os.getenv("SARVAM_API_KEY"):
        print("STT requires a valid local audio sample; no API calls were made.")
