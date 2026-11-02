# 🩺 ASHA Voice Register

A Streamlit prototype for turning ASHA home-visit voice notes into reviewable patient records. It supports Hindi, Marathi, English and code-mixed speech, with Sarvam transcription, structured extraction, traceable quotes, transparent Python rules, voice follow-up, read-back, confirmation, and CSV export.

## Features

- Sarvam Saaras v4 speech-to-text and Bulbul v4 Flash text-to-speech.
- Sarvam-105B Conversations extraction; the model extracts fields only.
- Verbatim transcript quotes are checked before display; unsupported values are discarded.
- Deterministic risk rules and reasons in `rules.py`.
- Missing age/weight prompts, voice answers, manual numeric fallback, and read-back.
- Confirmed session register with UTF-8 CSV download.
- Synthetic demo-note selector using `synthetic_asha_worker_notes.json` (`id`, `language`, `spoken_text`, `ground_truth`, `expected_risk`, `why`) and an explicitly labeled preloaded-data fallback if the API is unavailable.
- Listen to demo note narration in generated speech, spoken follow-up questions, and recorded ASHA-worker follow-up answers.

## Architecture

```text
Voice → Sarvam STT → Transcript → Sarvam LLM Extraction
                                      ↓
                             Deterministic Rules
                                      ↓
                         Review + Confirmation
                                      ↓
                         Session Register → CSV
```

## Setup

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Add a `.env` file in this folder:

```env
SARVAM_API_KEY=your_real_key_here
```

Never commit `.env` or expose `SARVAM_API_KEY`. `.env` and `.streamlit/secrets.toml` are ignored by Git. Locally the app reads the existing `.env`; on Streamlit Community Cloud it also reads `st.secrets`.

## Deploy the full app

The full Python application needs a Streamlit host; Netlify can host only the static `index.html` landing page.

1. Push the project files to a GitHub repository. Keep `.env` out of the repository.
2. In Streamlit Community Cloud, choose **Create app**, select the repository and branch, and set `app.py` as the entrypoint.
3. In **Advanced settings → Secrets**, add:

   ```toml
   SARVAM_API_KEY = "your_real_key"
   ```

4. Deploy. The app reads the key from Streamlit Secrets; no `.env` file needs to be uploaded.

The repository has no Git remote configured yet, so connect or create its GitHub repository before deploying.

## Run

```powershell
python test_rules.py
python sarvam_client.py path\to\sample.wav
streamlit run app.py
```

The smoke test requires a real local WAV sample and a configured key; it does not fake STT success. The demo selector skips STT but still calls the real extraction and TTS APIs. The optional demo-safe fallback uses the synthetic expected records only after an API failure and labels them clearly.

## Tests

`python test_rules.py` is offline and compares deterministic outcomes against the patient-level expected risks in `synthetic_asha_notes_fixed.json`.

## Medical disclaimer

Prototype decision-support tool. Risk rules must be verified against current MoHFW/NHM guidelines and do not replace clinical judgment. This is not a diagnostic device.
