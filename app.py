"""ASHA Voice Register: reviewable voice-note prototype."""

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from rules import assess_risk
from sarvam_client import SarvamError, extract, stt, tts

ROOT = Path(__file__).parent
DATA_PATH = ROOT / "synthetic_asha_worker_notes.json"
load_dotenv(ROOT / ".env")

st.set_page_config(page_title="ASHA Voice Register", page_icon="🩺", layout="wide")
st.markdown("""<style>
 .block-container{max-width:1120px;padding-top:2rem}
 [data-testid="stMetric"]{background:#f4f8f5;padding:1rem;border-radius:14px}
 .quote{color:#64748b;font-size:.88rem;margin-top:-.5rem}
</style>""", unsafe_allow_html=True)

st.title("🩺 ASHA Voice Register")
st.caption("Voice-first home visit documentation · हिंदी · मराठी · English")
st.info("Prototype decision-support tool. Risk rules must be verified against current MoHFW/NHM guidelines and do not replace clinical judgment.")

if "register" not in st.session_state:
    st.session_state.register = []
if "current" not in st.session_state:
    st.session_state.current = None
if "confirmed_ids" not in st.session_state:
    st.session_state.confirmed_ids = set()
if "audio_cache" not in st.session_state:
    st.session_state.audio_cache = {}

def _audio_once(cache_key: str, text: str, lang: str) -> None:
    if cache_key not in st.session_state.audio_cache:
        st.session_state.audio_cache[cache_key] = tts(text, lang)
    st.audio(st.session_state.audio_cache[cache_key], format="audio/wav")

try:
    notes = json.loads(DATA_PATH.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    notes = []

def _quote(patient: dict, field: str) -> str:
    quote = (patient.get("quotes") or {}).get(field)
    return f'↳ “{quote}”' if quote else "↳ No supporting quote"

def _load_transcript(transcript: str, source_note: dict | None = None) -> bool:
    if not os.getenv("SARVAM_API_KEY"):
        st.error("SARVAM_API_KEY is not configured. Add it to your .env file.")
        return False
    try:
        with st.spinner("Reading the note and organizing each patient…"):
            patients = extract(transcript)
        st.session_state.current = {"id": str(uuid.uuid4()), "transcript": transcript,
                                    "patients": patients, "source": source_note, "preloaded": False}
        return True
    except SarvamError as exc:
        st.error("We couldn't structure this note safely. Please retry.")
        with st.expander("Technical details"):
            st.caption(str(exc))
        if source_note and st.button("Use demo-safe fallback", key="safe_fallback"):
            fallback = [{**p, "quotes": {}} for p in source_note.get("patients", [])]
            truth = source_note.get("ground_truth")
            if not fallback and isinstance(truth, dict):
                name_value = truth.get("name")
                if not isinstance(name_value, str) or ";" not in name_value:
                    fallback = [{**truth, "age_unit": truth.get("age_unit"), "quotes": {}}]
                else:
                    st.warning("This note mentions multiple patients; preloaded fallback is available only for single-patient records.")
                    return False
            st.session_state.current = {"id": str(uuid.uuid4()), "transcript": transcript,
                "patients": fallback, "source": source_note, "preloaded": True}
            return True
    return False

with st.sidebar:
    st.subheader("Demo note")
    if notes:
        options = {f"{n['id']} — {n.get('language', 'Unknown')}": n for n in notes}
        selected_label = st.selectbox("Load demo note", list(options), index=None, placeholder="Choose a synthetic note")
        if st.button("Load selected note", use_container_width=True, disabled=selected_label is None):
            note = options[selected_label]
            if _load_transcript(note["spoken_text"], note):
                st.rerun()
    else:
        st.warning("Demo dataset is unavailable.")
    st.divider()
    st.caption("API status: " + ("Key configured" if os.getenv("SARVAM_API_KEY") else "Key missing"))
    st.caption("Demo notes are synthetic and skip microphone transcription only.")

st.subheader("1 · Record a home-visit note")
audio = st.audio_input("Record a note in Hindi, Marathi, English, or mixed speech", key="visit_audio")
if st.button("🎙️ Process Voice Note", type="primary", disabled=audio is None):
    try:
        with st.spinner("Transcribing your note…"):
            transcript = stt(audio.getvalue())
        if _load_transcript(transcript):
            st.rerun()
    except SarvamError as exc:
        st.error("Couldn't transcribe the audio. Please try again or use a demo note.")
        with st.expander("Technical details"):
            st.caption(str(exc))

current = st.session_state.current
if current:
    st.subheader("2 · Transcript")
    st.markdown(f"> {current['transcript']}")
    if current.get("source"):
        source_lang = current["source"].get("language", "Hindi")
        tts_lang = "mr-IN" if source_lang.lower().startswith("marathi") else "hi-IN"
        if st.button("🔊 Hear the ASHA worker note (generated voice)", key=f"hear_note_{current['id']}"):
            try:
                _audio_once(f"{current['id']}:worker_note", current["transcript"], tts_lang)
            except SarvamError:
                st.caption("Audio playback could not be generated.")
        elif f"{current['id']}:worker_note" in st.session_state.audio_cache:
            st.audio(st.session_state.audio_cache[f"{current['id']}:worker_note"], format="audio/wav")
    if current.get("preloaded"):
        st.warning("⚠ Preloaded synthetic demo data — Sarvam AI extraction was unavailable.")
    st.subheader("3 · Review extracted patients")
    for idx, patient in enumerate(current["patients"]):
        patient.setdefault("quotes", {})
        assessment = assess_risk(patient)
        patient["risk"] = assessment["risk"]
        patient["reasons"] = assessment["reasons"]
        name = patient.get("name") or f"Patient {idx + 1}"
        with st.container(border=True):
            st.markdown(f"### 👤 {name} · Patient {idx + 1} of {len(current['patients'])}")
            cols = st.columns(4)
            values = [("Age", patient.get("age"), "age"), ("Age unit", patient.get("age_unit"), "age_unit"),
                      ("Visit type", patient.get("visit_type"), "visit_type"), ("Hb", patient.get("hb"), "hb"),
                      ("BP", patient.get("bp"), "bp"), ("Weight (kg)", patient.get("weight_kg"), "weight_kg")]
            for j, (label, value, field) in enumerate(values):
                with cols[j % 4]:
                    st.markdown(f"**{label}:** {value if value is not None else 'Not mentioned'}")
                    st.markdown(f'<div class="quote">{_quote(patient, field)}</div>', unsafe_allow_html=True)
            symptoms = patient.get("symptoms") or []
            st.markdown("**Symptoms:** " + (", ".join(symptoms) if symptoms else "None mentioned"))
            st.markdown(f'<div class="quote">{_quote(patient, "symptoms")}</div>', unsafe_allow_html=True)
            risk_label, emoji = {"urgent": ("URGENT", "🔴"), "refer_soon": ("REFER SOON", "🟠"), "none": ("NO RULE-TRIGGERED CONCERN", "🟢")}[assessment["risk"]]
            st.markdown(f"#### {emoji} {risk_label}")
            if assessment["reasons"]:
                st.markdown("**Why**\n" + "\n".join(f"- {reason}" for reason in assessment["reasons"]))

            missing = [field for field in ("age", "weight_kg") if patient.get(field) is None]
            if missing:
                st.markdown("**Follow-up needed**")
                language = (current.get("source") or {}).get("language", "Hindi")
                for field in missing:
                    q = "कृपया मरीज की उम्र बताइए।" if field == "age" else "कृपया मरीज का वजन किलो में बताइए।"
                    if language.lower().startswith("marathi"):
                        q = "कृपया रुग्णाचे वय सांगा." if field == "age" else "कृपया रुग्णाचे वजन किलोमध्ये सांगा."
                    st.write(q)
                    try:
                        _audio_once(f"{current['id']}:{idx}:follow:{field}:{q}", q, "mr-IN" if language.lower().startswith("marathi") else "hi-IN")
                    except SarvamError:
                        st.caption("Audio playback could not be generated; you can still enter the answer below.")
                    answer = st.text_input("Answer (e.g. 25 saal / 52 kilo)", key=f"ans_{current['id']}_{idx}_{field}")
                    answer_audio = st.audio_input("Or record the answer", key=f"follow_audio_{current['id']}_{idx}_{field}")
                    if st.button("Transcribe answer", key=f"follow_submit_{current['id']}_{idx}_{field}", disabled=answer_audio is None):
                        try:
                            answer = stt(answer_audio.getvalue())
                            patient.setdefault("follow_up_audio", {})[field] = answer_audio.getvalue()
                            patient.setdefault("follow_up_response", {})[field] = answer
                            match = re.search(r"\d+(?:\.\d+)?", answer)
                            if match:
                                patient[field] = float(match.group())
                                if field == "age":
                                    patient["age_unit"] = "months" if re.search(r"maheene|months?|महिने|महीने", answer, re.I) else "days" if re.search(r"days?|दिन", answer, re.I) else "years"
                                patient["quotes"][field] = answer
                                updated = assess_risk(patient)
                                patient["risk"], patient["reasons"] = updated["risk"], updated["reasons"]
                                st.rerun()
                            else:
                                st.warning("Please say the number clearly; no value was added.")
                        except SarvamError:
                            st.warning("Couldn't transcribe that answer. Please retry or type it above.")
                    response_audio = (patient.get("follow_up_audio") or {}).get(field)
                    response_text = (patient.get("follow_up_response") or {}).get(field)
                    if response_audio:
                        st.caption(f"ASHA worker response: {response_text or 'Recorded answer'}")
                        st.audio(response_audio, format="audio/wav")
                    answer = answer or response_text
                    if answer:
                        if st.button("🔊 Hear response", key=f"hear_response_{current['id']}_{idx}_{field}"):
                            try:
                                _audio_once(f"{current['id']}:{idx}:response:{field}:{answer}", answer,
                                            "mr-IN" if language.lower().startswith("marathi") else "hi-IN")
                            except SarvamError:
                                st.caption("Response audio could not be generated.")
                        match = re.search(r"\d+(?:\.\d+)?", answer)
                        if match:
                            patient[field] = float(match.group())
                            if field == "age":
                                patient["age_unit"] = "months" if re.search(r"maheene|months?|महिने|महीने", answer, re.I) else "days" if re.search(r"days?|दिन", answer, re.I) else "years"
                            patient["quotes"][field] = answer
                            assessment = assess_risk(patient)
                            patient["risk"], patient["reasons"] = assessment["risk"], assessment["reasons"]
                        else:
                            st.warning("Please enter a number clearly; no value was added.")

            row_id = f"{current['id']}:{idx}"
            confirmation = f"{name}, {patient.get('age') or 'age not mentioned'} {patient.get('age_unit') or ''}. Risk category: {risk_label}. Is this correct?"
            try:
                _audio_once(f"{row_id}:confirm", confirmation, "hi-IN")
            except SarvamError:
                st.caption("🔊 Audio playback could not be generated; review the record manually.")
            left, right = st.columns(2)
            if left.button("✅ Confirm", key=f"confirm_{row_id}", use_container_width=True):
                if row_id not in st.session_state.confirmed_ids:
                    st.session_state.register.append({"Timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "Name": patient.get("name"), "Age": patient.get("age"), "Age Unit": patient.get("age_unit"),
                        "Visit Type": patient.get("visit_type"), "Hb": patient.get("hb"), "BP": patient.get("bp"),
                        "Weight (kg)": patient.get("weight_kg"), "Symptoms": ", ".join(patient.get("symptoms") or []),
                        "Risk": patient["risk"], "Reasons": "; ".join(patient["reasons"]) or "No configured rule triggered",
                        "_id": row_id})
                    st.session_state.confirmed_ids.add(row_id)
                st.success("Record added to the session register.")
            if right.button("🔄 Redo", key=f"redo_{row_id}", use_container_width=True):
                st.session_state.current = None
                st.rerun()

st.subheader("4 · Confirmed session register")
if st.session_state.register:
    frame = pd.DataFrame(st.session_state.register).drop(columns=["_id"], errors="ignore")
    st.dataframe(frame, use_container_width=True, hide_index=True)
    st.download_button("⬇ Download Register CSV", frame.to_csv(index=False).encode("utf-8-sig"),
                       "asha_register.csv", "text/csv", use_container_width=True)
else:
    st.caption("Confirmed patients will appear here during this session.")
