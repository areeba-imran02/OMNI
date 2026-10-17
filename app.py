import os
import io
import re
import json
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd

from backend.app.ai import generate, model_candidates
from backend.app.artifacts import make_pdf, make_docx, make_markdown_artifact

APP_DIR = Path(__file__).resolve().parent
AGENT_DIR = APP_DIR / "assets" / "agents"

st.set_page_config(
    page_title="OmniCraft AI",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Streamlit Cloud secrets take precedence; local environment variables also work.
try:
    secret_key = st.secrets.get("GEMINI_API_KEY", "")
except Exception:
    secret_key = ""
if secret_key and not os.getenv("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = str(secret_key)

CSS = """
<style>
:root { --oc-bg:#f8f7f2; --oc-ink:#26271f; --oc-muted:#707267; --oc-accent:#a15c38; --oc-accent2:#d6a17e; --oc-line:#e6e2d8; }
.stApp { background:var(--oc-bg); color:var(--oc-ink); }
[data-testid="stSidebar"] { background:#f0eee5; border-right:1px solid var(--oc-line); }
[data-testid="stSidebar"] * { color:var(--oc-ink); }
.block-container { padding-top:1.8rem; max-width:1440px; }
h1,h2,h3 { letter-spacing:-.035em; color:var(--oc-ink); }
.hero { padding:1.6rem 1.8rem; border:1px solid #e4d8cb; border-radius:24px; background:linear-gradient(125deg,#fffdf7 0%,#f6e8da 55%,#ead5bf 100%); margin-bottom:1.2rem; }
.hero-kicker { color:#925333; text-transform:uppercase; font-size:.76rem; font-weight:800; letter-spacing:.16em; }
.hero h1 { font-size:2.55rem; margin:.3rem 0 .45rem 0; line-height:1.1; }
.hero p { color:#62564d; font-size:1.05rem; max-width:800px; margin:0; }
.agent-card { display:flex; align-items:center; gap:12px; padding:12px; border:1px solid var(--oc-line); border-radius:15px; background:#fffdf8; margin-bottom:9px; }
.agent-card img { width:48px; height:48px; object-fit:contain; }
.agent-title { font-weight:750; font-size:.93rem; }
.agent-desc { color:var(--oc-muted); font-size:.78rem; }
.metric-card { padding:15px 16px; background:#fffdf8; border:1px solid var(--oc-line); border-radius:16px; min-height:90px; }
.small-muted { color:var(--oc-muted); font-size:.85rem; }
div.stButton > button, div.stDownloadButton > button { border-radius:12px; border:1px solid #c9a38b; min-height:2.65rem; }
div.stButton > button[kind="primary"] { background:#985a3a; color:white; border-color:#985a3a; }
[data-testid="stChatInput"] { border-radius:15px; }
hr { border-color:var(--oc-line); }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

AGENTS = [
    ("Planner", "Turns your request into a focused execution plan.", "planner.svg"),
    ("Research", "Organizes evidence; live web search requires a configured provider.", "research.svg"),
    ("Creator", "Generates explanations, code drafts, and diagram specifications.", "creator.svg"),
    ("Verifier", "Checks output structure and runs supported deterministic checks.", "verifier.svg"),
    ("Explainer", "Makes the result easier to understand and use.", "explainer.svg"),
]

if "history" not in st.session_state:
    st.session_state.history = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_prompt" not in st.session_state:
    st.session_state.last_prompt = ""

def agent_card(title, desc, image):
    path = AGENT_DIR / image
    if path.exists():
        import base64
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        src = f"data:image/svg+xml;base64,{encoded}"
        st.markdown(
            f'<div class="agent-card"><img src="{src}"/><div><div class="agent-title">{title}</div><div class="agent-desc">{desc}</div></div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f"**{title}**  \n{desc}")

def classify_task(prompt):
    p = prompt.lower()
    if any(k in p for k in ["diagram", "flowchart", "mind map", "uml", "architecture", "network topology", "er diagram"]):
        return "Diagram"
    if any(k in p for k in ["code", "python", "javascript", "build an app", "function", "debug", "program"]):
        return "Code & Apps"
    if any(k in p for k in ["research", "latest", "sources", "cite", "current", "references"]):
        return "Research brief"
    if any(k in p for k in ["explain", "teach", "learn", "quiz", "study notes", "what is"]):
        return "Learning"
    if any(k in p for k in ["report", "document", "proposal", "plan", "presentation"]):
        return "Document"
    return "General creation"

def build_system(task_type, detail):
    return f"""
You are OmniCraft AI, a careful task-oriented creation assistant.
Task category: {task_type}
Requested depth: {detail}
Rules:
- Answer the user's specific request, not a generic template. Adapt content to every prompt.
- Be clear about assumptions, limitations, and uncertainty.
- Do not invent citations, URLs, browsing activity, test results, or facts about tools you did not use.
- For diagrams, return valid Mermaid code in a fenced mermaid block plus a concise explanation.
- For code, provide runnable code and explain dependencies. Do not claim it was executed unless it actually was.
- For research requests, do not claim live web research was performed. Explain that live source retrieval is not configured and distinguish background knowledge from verified sources.
- Use well-structured Markdown with useful headings and examples.
"""

def verify_result(text, task_type):
    checks = []
    checks.append(("Non-empty output", bool(text.strip()), "Generated text exists." if text.strip() else "No output returned."))
    checks.append(("Readable length", len(text.strip()) >= 80, f"{len(text.strip())} characters returned."))
    if task_type == "Diagram":
        has_mermaid = bool(re.search(r"```mermaid\s+[\s\S]+?```", text, re.I))
        checks.append(("Mermaid source present", has_mermaid, "A Mermaid code block was found." if has_mermaid else "No Mermaid code block found; ask for a diagram revision."))
    return checks

def show_downloads(title, content):
    col1, col2, col3 = st.columns(3)
    md = make_markdown_artifact(title, content)["content"].encode("utf-8")
    with col1:
        st.download_button("Download Markdown", md, file_name="omnicraft_result.md", mime="text/markdown", use_container_width=True)
    with col2:
        try:
            pdf = make_pdf(title, content)
            st.download_button("Download PDF", pdf, file_name="omnicraft_result.pdf", mime="application/pdf", use_container_width=True)
        except Exception as exc:
            st.warning(f"PDF export unavailable: {exc}")
    with col3:
        try:
            docx = make_docx(title, content)
            st.download_button("Download DOCX", docx, file_name="omnicraft_result.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
        except Exception as exc:
            st.warning(f"DOCX export unavailable: {exc}")

with st.sidebar:
    st.markdown("## ✦ OmniCraft AI")
    st.caption("From any request to a useful creation.")
    if st.button("＋ New creation", use_container_width=True):
        st.session_state.last_result = None
        st.session_state.last_prompt = ""
        st.rerun()
    page = st.radio(
        "Workspace",
        ["Create", "Data & Statistics", "Agent team", "Settings"],
        label_visibility="collapsed",
    )
    st.divider()
    st.markdown("**Recent creations**")
    if st.session_state.history:
        for item in reversed(st.session_state.history[-5:]):
            st.caption(f"• {item['title'][:42]}")
    else:
        st.caption("Your completed tasks will appear here.")
    st.divider()
    st.caption("Gemini API key stays server-side. Never paste secrets into prompts.")

if page == "Create":
    st.markdown("""
    <div class="hero">
      <div class="hero-kicker">Your AI creation workspace</div>
      <h1>What would you like to create?</h1>
      <p>Research a topic, visualize an idea, analyze data, build something, or turn a complex task into a useful result.</p>
    </div>
    """, unsafe_allow_html=True)

    left, right = st.columns([1.8, 1], gap="large")
    with left:
        with st.form("creation_form", clear_on_submit=False):
            prompt = st.text_area(
                "Describe your task",
                value=st.session_state.last_prompt,
                height=160,
                placeholder="Example: Explain DNS with a Mermaid diagram, a beginner-friendly walkthrough, and a short quiz.",
            )
            c1, c2 = st.columns([1, 1])
            with c1:
                output_type = st.selectbox("Output style", ["Auto-detect", "Detailed explanation", "Step-by-step guide", "Diagram", "Code", "Research brief", "Study notes"])
            with c2:
                detail = st.select_slider("Depth", options=["Quick", "Balanced", "Detailed"], value="Balanced")
            attached = st.file_uploader("Attach a file (optional)", type=["txt", "md", "csv", "xlsx", "json", "py"], help="CSV/XLSX files can also be analyzed in Data & Statistics.")
            submitted = st.form_submit_button("Generate result  →", type="primary", use_container_width=True)

        st.markdown("**Try an example**")
        examples = [
            "Explain DNS with an interactive Mermaid flowchart and a short quiz.",
            "Create a Python function that validates email addresses and provide tests.",
            "Explain photosynthesis for a beginner using a labeled process diagram.",
            "Create a project plan for launching a student portfolio website.",
        ]
        excols = st.columns(2)
        for i, example in enumerate(examples):
            with excols[i % 2]:
                if st.button(example, key=f"example_{i}", use_container_width=True):
                    st.session_state.last_prompt = example
                    st.rerun()

    with right:
        st.markdown("### Your agent team")
        for title, desc, image in AGENTS:
            agent_card(title, desc, image)
        st.markdown('<div class="small-muted">Specialists are modular workers; the app only reports tasks it actually performs.</div>', unsafe_allow_html=True)

    if submitted:
        if not prompt.strip():
            st.error("Please describe what you want to create.")
        else:
            st.session_state.last_prompt = prompt
            task_type = output_type if output_type != "Auto-detect" else classify_task(prompt)
            user_prompt = prompt
            if attached is not None:
                raw = attached.getvalue()
                if attached.name.lower().endswith((".txt", ".md", ".py", ".json")):
                    extracted = raw.decode("utf-8", errors="replace")[:18000]
                    user_prompt += f"\n\nAttached file: {attached.name}\n--- file content start ---\n{extracted}\n--- file content end ---"
                elif attached.name.lower().endswith(".csv"):
                    try:
                        df_att = pd.read_csv(io.BytesIO(raw))
                        user_prompt += f"\n\nAttached CSV summary:\n{df_att.head(30).to_csv(index=False)}\nShape: {df_att.shape}\nColumns: {list(df_att.columns)}"
                    except Exception as exc:
                        st.warning(f"Could not parse attached CSV: {exc}")
                else:
                    user_prompt += f"\n\nAttached file name: {attached.name}. Its binary contents are not passed directly to the language model."
            with st.status("Working on your request…", expanded=True) as status:
                st.write("Planner: categorizing the request and preparing instructions.")
                st.write(f"Creator: requesting a tailored response for **{task_type}**.")
                try:
                    result = generate(user_prompt, system=build_system(task_type, detail), temperature=0.35)
                    st.write(f"Model returned a response: `{result.model}`.")
                    st.write("Verifier: running output-structure checks.")
                    checks = verify_result(result.text, task_type)
                    status.update(label="Task completed", state="complete", expanded=False)
                    st.session_state.last_result = {
                        "title": task_type,
                        "prompt": prompt,
                        "text": result.text,
                        "model": result.model,
                        "fallback_used": result.fallback_used,
                        "checks": checks,
                        "created_at": datetime.now().isoformat(timespec="minutes"),
                    }
                    st.session_state.history.append({"title": prompt, "created_at": datetime.now().isoformat(timespec="minutes")})
                except Exception as exc:
                    status.update(label="Generation failed", state="error", expanded=True)
                    st.error(str(exc))
                    st.info("Add a valid Gemini API key in Streamlit Cloud → App settings → Secrets, then retry. If a model is busy or rate-limited, the configured fallback chain is attempted automatically.")

    if st.session_state.last_result:
        r = st.session_state.last_result
        st.divider()
        st.markdown(f"## {r['title']}")
        st.caption(f"Model: {r['model']} · Created: {r['created_at']}" + (" · Fallback model used" if r["fallback_used"] else ""))
        st.markdown(r["text"])
        with st.expander("Verification checks", expanded=True):
            for name, passed, detail_text in r["checks"]:
                (st.success if passed else st.warning)(f"{'PASS' if passed else 'CHECK'} · **{name}** — {detail_text}")
            st.caption("These checks validate basic output structure, not factual correctness.")
        show_downloads(r["title"], r["text"])
        if st.button("Revise this result", use_container_width=False):
            st.session_state.last_prompt = "Revise the following result according to my next instruction:\n\n" + r["text"][:6000]
            st.rerun()

elif page == "Data & Statistics":
    st.markdown("## Data & Statistics Lab")
    st.write("Upload CSV or Excel data to calculate statistics using pandas. All displayed numbers come from the uploaded dataset.")
    file = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"], key="data_upload")
    if file:
        try:
            df = pd.read_csv(file) if file.name.lower().endswith(".csv") else pd.read_excel(file)
            a, b, c, d = st.columns(4)
            a.metric("Rows", f"{len(df):,}")
            b.metric("Columns", f"{len(df.columns):,}")
            c.metric("Missing cells", f"{int(df.isna().sum().sum()):,}")
            d.metric("Duplicate rows", f"{int(df.duplicated().sum()):,}")
            st.markdown("### Data preview")
            st.dataframe(df.head(100), use_container_width=True)
            st.markdown("### Descriptive statistics")
            st.dataframe(df.describe(include="all").transpose(), use_container_width=True)
            numeric = df.select_dtypes(include="number")
            if not numeric.empty:
                st.markdown("### Quick chart")
                column = st.selectbox("Numeric column", list(numeric.columns))
                st.bar_chart(numeric[column].dropna().reset_index(drop=True))
                if len(numeric.columns) > 1:
                    st.markdown("### Correlation matrix")
                    st.dataframe(numeric.corr(numeric_only=True), use_container_width=True)
            cleaned = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download dataset as CSV", cleaned, file_name="processed_data.csv", mime="text/csv")
            report = f"Rows: {len(df)}\nColumns: {len(df.columns)}\nMissing cells: {int(df.isna().sum().sum())}\nDuplicate rows: {int(df.duplicated().sum())}\n\nDescriptive statistics:\n{df.describe(include='all').to_string()}"
            st.download_button("Download statistics report", report.encode("utf-8"), file_name="data_report.txt", mime="text/plain")
        except Exception as exc:
            st.error(f"Could not read this file: {exc}")

elif page == "Agent team":
    st.markdown("## Meet the agent team")
    st.write("These are role-specific workers in the application workflow, not decorative status cards.")
    cols = st.columns(2)
    descriptions = {
        "Planner": "Determines the task category and prepares the generation instructions.",
        "Research": "Structures research requests; live search is not enabled until a search provider is configured.",
        "Creator": "Calls the configured Gemini model and receives the task-specific output.",
        "Verifier": "Runs deterministic checks such as non-empty output and presence of Mermaid source for diagram tasks.",
        "Explainer": "The prompt requests clear explanations and useful next steps as part of generated results.",
    }
    for i, (name, desc, image) in enumerate(AGENTS):
        with cols[i % 2]:
            agent_card(name, desc, image)
            st.write(descriptions[name])

elif page == "Settings":
    st.markdown("## Settings & deployment")
    st.write("Configure the Gemini API key through Streamlit secrets or environment variables.")
    st.code('GEMINI_API_KEY = "your-google-ai-studio-key"', language="toml")
    st.caption("On Streamlit Community Cloud: App → Settings → Secrets. Do not commit secrets.toml or .env to GitHub.")
    st.markdown("### Model fallback order")
    st.code("\n".join(model_candidates()), language="text")
    st.write("Set GEMINI_MODELS to a comma-separated list of models available to your Google AI Studio key.")
    st.markdown("### Current configuration")
    st.write("API key configured:", bool(os.getenv("GEMINI_API_KEY", "").strip()))
    st.write("Mode: live Gemini generation when a valid key is configured; no hardcoded AI responses.")
    st.warning("Live web search, isolated code execution, persistent database history, and PPTX/XLSX report generation are not implemented in this Streamlit build.")
