# OmniCraft AI — Streamlit Edition

A Streamlit-based AI creation workspace powered by Google Gemini models. Includes a task composer, role-specific agent workflow, CSV/XLSX analysis, Mermaid diagram prompts, output checks, and Markdown/PDF/DOCX downloads.

## Features
- Streamlit entry point is `app.py` (required for Streamlit Community Cloud).
- Gemini model fallback chain: `gemini-2.5-flash` → `gemini-2.5-flash-lite` → `gemini-2.0-flash` by default.
- Configure available models using `GEMINI_MODELS`.
- Local SVG agent illustrations.
- CSV/XLSX data preview, missing-value and duplicate counts, descriptive statistics, numeric chart, and CSV/report downloads.
- Markdown, PDF, and DOCX result exports.
- No hardcoded sample answer is returned as a live AI response.

## Deploy to Streamlit Community Cloud
1. Upload the **contents** of this folder to a GitHub repository.
2. Open https://share.streamlit.io/ and create an app from that repository.
3. Set **Main file path** to `app.py`.
4. In Streamlit app settings → **Secrets**, add:

   ```toml
   GEMINI_API_KEY = "your-google-ai-studio-api-key"
   # Optional:
   GEMINI_MODELS = "gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash"
   ```

5. Deploy. The key is read server-side from Streamlit secrets; do not commit it to GitHub.

## Local run
```bash
python -m venv .venv
# Windows:
.venv\\Scripts\\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows; then edit .env
streamlit run app.py
```
You can alternatively set `GEMINI_API_KEY` as an environment variable. For local development, the app loads `backend/.env` if present, but Streamlit secrets/environment variables are recommended.

## Free-tier note
Google AI Studio offers free-tier access for eligible models/accounts, but free quota, rate limits, model availability, and terms can change. This project does not guarantee unlimited usage. When a model call fails, it tries the next configured model; if all configured models fail, it displays an error rather than inventing an answer.

## Honest limitations
- Live web research/citation retrieval is not configured; research prompts are answered from model knowledge and clearly instructed not to invent sources.
- Code is generated but not executed in an isolated sandbox.
- The agent roles are implemented as modular workflow stages; not every task calls every agent.
- History is in Streamlit session state and does not persist across sessions.
- Excel export, PPTX generation, database persistence, authentication, and cancellation/resume are not implemented.
- Output verification checks structure, not factual correctness.

## Security
- Never put API keys in frontend code or commit `.env` / `.streamlit/secrets.toml`.
- Set API key in Streamlit Community Cloud Secrets.
- Treat generated code as untrusted until reviewed; it is not sandbox-executed by this app.
