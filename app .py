# app.py — Life Minus Work • Online Questionnaire (Readiness + Reflections-style mini report)
# v2 — fixes OpenAI response_format, robust email secrets mapping, first-name capture, stronger Mini Report, Sheets logging, PDF generation.
# Requires: streamlit, openai>=1.35, gspread, fpdf, matplotlib

from __future__ import annotations
import os, io, json, smtplib, ssl, math, random
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from fpdf import FPDF

# ------------------------------
# Page + theme
# ------------------------------
st.set_page_config(page_title="Life Minus Work — Readiness Check", page_icon="🧭", layout="wide")
st.markdown(
    "<style> .stMetric { text-align: left !important; } .mini-muted{opacity:.8} .tight p{margin-bottom:.35rem;} </style>",
    unsafe_allow_html=True,
)

# ------------------------------
# Secrets helpers
# ------------------------------
def sget(key: str, default: str = "") -> str:
    """Prefer Streamlit secrets, else env var."""
    try:
        if key in st.secrets:
            v = st.secrets[key]
            if isinstance(v, (dict, list)):  # not string-like
                return default
            return str(v)
    except Exception:
        pass
    return os.getenv(key, default)

# Google Sheets settings (same keys as you already use)
LW_SHEET_URL = sget("LW_SHEET_URL", "").strip()
LW_SHEET_WORKSHEET = sget("LW_SHEET_WORKSHEET", "emails").strip()
LW_SHOW_EMAILS_ADMIN = sget("LW_SHOW_EMAILS_ADMIN", "")
LW_BCC_ON_DOWNLOAD = sget("LW_BCC_ON_DOWNLOAD", "0")  # "1" to bcc
SENDER_NAME = sget("SENDER_NAME", "Life Minus Work")
REPLY_TO = sget("REPLY_TO", sget("GMAIL_USER", sget("EMAIL_SENDER", "")))

# Map both secret styles: GMAIL_* (your Reflection app) and EMAIL_*
EMAIL_SENDER = sget("GMAIL_USER", sget("EMAIL_SENDER", "")).strip()
EMAIL_APP_PASSWORD = sget("GMAIL_APP_PASSWORD", sget("EMAIL_APP_PASSWORD", "")).strip()
EMAIL_BCC = sget("EMAIL_BCC", "")  # optional

# OpenAI config (keep your existing keys / names)
AI_MODEL = sget("OPENAI_HIGH_MODEL", "gpt-5-mini")
try:
    MAX_OUTPUT_TOKENS_HIGH = int(sget("MAX_OUTPUT_TOKENS_HIGH", "8000"))
except:
    MAX_OUTPUT_TOKENS_HIGH = 8000

# ------------------------------
# OpenAI client (new SDK) + safe fallback
# ------------------------------
_HAS_OPENAI = False
_client = None
try:
    from openai import OpenAI
    _client = OpenAI()
    # If OPENAI_API_KEY is not set, OpenAI() will still construct but calls will fail; keep a flag to short-circuit.
    _HAS_OPENAI = bool(sget("OPENAI_API_KEY"))
except Exception as _e:
    _HAS_OPENAI = False
    _client = None

def _responses_supports_response_format() -> bool:
    """Best-effort check for Responses API supporting response_format."""
    try:
        # Quick dry-run with no network call: inspect signature if available
        import inspect
        sig = inspect.signature(_client.responses.create)  # type: ignore[attr-defined]
        return "response_format" in sig.parameters
    except Exception:
        # Unknown; treat as supported (we also catch TypeError at call-time)
        return True

def ai_json(prompt: str, schema_hint: str = "", max_tokens: int = 1200) -> dict:
    """Returns JSON from the model. Never throws — returns {} when unavailable."""
    if not (_HAS_OPENAI and _client):
        return {}

    sys = (
        "You are a calm, encouraging coach for Life Minus Work. "
        "Return STRICT JSON only; do not include commentary."
    )
    user = f"{prompt}\n\nReturn JSON. {schema_hint}".strip()

    # Try new Responses API with response_format
    try:
        kwargs = dict(model=AI_MODEL, input=user, max_output_tokens=max_tokens)
        if _responses_supports_response_format():
            kwargs["response_format"] = {"type": "json_object"}
        resp = _client.responses.create(**kwargs)  # type: ignore
        text = getattr(resp, "output_text", "") or ""
        return json.loads(text) if text.strip().startswith("{") else {}
    except TypeError:
        # Older SDK that doesn't accept response_format; try again w/o it
        try:
            resp = _client.responses.create(model=AI_MODEL, input=user, max_output_tokens=max_tokens)  # type: ignore
            text = getattr(resp, "output_text", "") or ""
            return json.loads(text) if text.strip().startswith("{") else {}
        except Exception:
            pass
    except Exception:
        pass

    # Final fallback: try Chat Completions (older SDK users)
    try:
        import openai as openai_legacy  # type: ignore
        comp = openai_legacy.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":sys},{"role":"user","content":user}],
            temperature=0.2,
        )
        text = comp["choices"][0]["message"]["content"]
        return json.loads(text) if text and text.strip().startswith("{") else {}
    except Exception:
        return {}

# ------------------------------
# Email sending (Gmail app password). Works for both key styles.
# ------------------------------
def _smtp_send(msg: EmailMessage):
    if not (EMAIL_SENDER and EMAIL_APP_PASSWORD):
        raise RuntimeError("Email sender/app password missing in Secrets.")
    # Prefer STARTTLS on 587 (more common). Fallback to SSL:465.
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
            smtp.send_message(msg)
    except Exception:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
            smtp.send_message(msg)

def send_verification_code(to_email: str, code: str, first_name: str = ""):
    msg = EmailMessage()
    from_hdr = f"{SENDER_NAME} <{EMAIL_SENDER}>" if SENDER_NAME and EMAIL_SENDER else EMAIL_SENDER
    msg["From"] = from_hdr
    msg["To"] = to_email
    if REPLY_TO: msg["Reply-To"] = REPLY_TO
    if EMAIL_BCC: msg["Bcc"] = EMAIL_BCC
    msg["Subject"] = "Your Life Minus Work verification code"
    greeting = f"Hi {first_name}," if (first_name or '').strip() else "Hi there,"
    msg.set_content(
        f"{greeting}\n\n"
        "Here’s your 6‑digit verification code to unlock your full Reflection Report:\n"
        f"    {code}\n\n"
        "Enter this in the app (the code expires in ~10 minutes).\n\n"
        "— Life Minus Work"
    )
    _smtp_send(msg)

def send_pdf(to_email: str, pdf_bytes: bytes, filename: str, first_name: str = ""):
    msg = EmailMessage()
    from_hdr = f"{SENDER_NAME} <{EMAIL_SENDER}>" if SENDER_NAME and EMAIL_SENDER else EMAIL_SENDER
    msg["From"] = from_hdr
    msg["To"] = to_email
    if REPLY_TO: msg["Reply-To"] = REPLY_TO
    if EMAIL_BCC or LW_BCC_ON_DOWNLOAD == "1":
        bcc_addr = EMAIL_BCC or EMAIL_SENDER
        if bcc_addr: msg["Bcc"] = bcc_addr
    msg["Subject"] = "Your Life Minus Work — Reflection Report (PDF)"
    greeting = f"Hi {first_name}," if (first_name or '').strip() else "Hi there,"
    msg.set_content(
        f"{greeting}\n\n"
        "Attached is your Reflection Report (PDF). Keep it handy this month.\n\n"
        "— Life Minus Work"
    )
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)
    _smtp_send(msg)

# ------------------------------
# Google Sheets logging (like the Reflections app)
# ------------------------------
def gsheets_enabled() -> bool:
    try:
        return bool(st.secrets.get("gcp_service_account")) and bool(LW_SHEET_URL)
    except Exception:
        return False

@st.cache_resource(show_spinner=False)
def _get_ws():
    if not gsheets_enabled():
        return None
    import gspread
    sa = st.secrets["gcp_service_account"]
    gc = gspread.service_account_from_dict(sa)
    sh = gc.open_by_url(LW_SHEET_URL)
    try:
        ws = sh.worksheet(LW_SHEET_WORKSHEET)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=LW_SHEET_WORKSHEET, rows=2000, cols=8)
        ws.update("A1:F1", [["email","first_name","verified_at","model","scores","source"]])
    return ws

def log_email_capture(email: str, first_name: str, scores: dict, source: str = "verify"):
    row = {
        "email": (email or "").strip().lower(),
        "first_name": (first_name or "").strip(),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "model": AI_MODEL,
        "scores": json.dumps(scores or {}),
        "source": source,
    }
    try:
        ws = _get_ws()
        if ws:
            ws.append_row(
                [row["email"], row["first_name"], row["verified_at"], row["model"], row["scores"], row["source"]],
                value_input_option="USER_ENTERED",
            )
    except Exception as e:
        st.warning(f"(Sheets capture failed; continuing) {e}")

# ------------------------------
# Questionnaire content
# ------------------------------
THEMES = [
    "Purpose & Identity",
    "Social Health & Community Connection",
    "Health & Vitality",
    "Learning & Growth",
    "Adventure & Exploration",
    "Giving Back",
]

QUESTIONS = {
    "Purpose & Identity": [
        "I feel confident about who I am beyond my work role.",
        "I have a clear sense of purpose for my post‑work life.",
        "I rarely feel anxious or lost without my daily work routine.",
        "I can reflect on my career with clarity and without regret.",
    ],
    "Social Health & Community Connection": [
        "I have strong relationships outside of work.",
        "I actively nurture friendships and community connections.",
        "I feel comfortable reaching out to new people.",
        "Loneliness is not a concern for me right now.",
    ],
    "Health & Vitality": [
        "I maintain regular physical activity.",
        "My mental and emotional wellbeing feels stable.",
        "I prioritize sleep, nutrition, and stress management.",
        "I have no major health barriers to exploring new activities.",
    ],
    "Learning & Growth": [
        "I actively pursue new knowledge or skills.",
        "I enjoy learning challenges and have a growth mindset.",
        "I make time for reading, courses, or hobbies that expand my mind.",
        "Cognitive sharpness is a priority in my daily life.",
    ],
    "Adventure & Exploration": [
        "I try new places, experiences, or micro‑adventures regularly.",
        "I’m willing to step out of my comfort zone in small, safe ways.",
        "I have a list of things I’m curious to explore.",
        "I can plan and take short adventures without much friction.",
    ],
    "Giving Back": [
        "I find ways to contribute to others or my community.",
        "I see how my experience can be useful to someone else.",
        "I’m open to small acts of service that fit my energy and schedule.",
        "I have an idea for a tiny contribution this month.",
    ],
}

def compute_scores(responses: dict) -> dict[str,int]:
    scores = {}
    for theme, vals in responses.items():
        if vals:
            scores[theme] = int(round(sum(vals) / len(vals)))
        else:
            scores[theme] = 0
    return scores

def overall_score(scores: dict[str,int]) -> int:
    return int(round(sum(scores.values()) / max(1, len(scores))))

# Pretty labels for chart
LABELS = {
    "Purpose & Identity": "Identity",
    "Social Health & Community Connection": "Connection",
    "Health & Vitality": "Vitality",
    "Learning & Growth": "Growth",
    "Adventure & Exploration": "Adventure",
    "Giving Back": "Contribution",
}

# ------------------------------
# Mini Report (Reflections-style)
# ------------------------------
def render_mini_report(first_name: str, scores: dict, total: int):
    # Top 3 themes
    top3 = [k for k,_ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:3]]
    top_names = ", ".join([LABELS.get(k,k) for k in top3])

    st.subheader("Your Mini Report (Preview)")
    st.caption(f"Top themes: {top_names}")

    # Chart
    labels = [LABELS.get(k,k) for k in THEMES]
    values = [scores.get(k,0) for k in THEMES]
    fig, ax = plt.subplots(figsize=(8,3))
    ax.bar(labels, values)  # Do not specify colors (keeps default)
    ax.set_ylim(0,10)
    ax.set_ylabel("Score")
    ax.set_title("Theme Snapshot")
    plt.xticks(rotation=45, ha="right")
    st.pyplot(fig, use_container_width=True)

    # AI-enhanced bullets (or safe defaults)
    schema = """JSON schema:
    { "mini_headline": str,
      "mini_bullets": [str, ...],
      "tiny_actions": [str, ...],
      "week_teaser": [str, ...],
      "unlock": [str, ...]
    }"""
    prompt = (
        "Write a concise, encouraging preview based on these theme scores (0-10). "
        f"First name: {first_name or 'friend'}. "
        f"Scores JSON: {json.dumps(scores)}. "
        "Keep the tone warm and practical. Mini bullets should be short, specific. "
        "Week teaser should contain 3 short items (Mon–Wed)."
    )
    ai = ai_json(prompt, schema_hint=schema, max_tokens=900)

    col1, col2 = st.columns([1.2, 1], gap="large")
    with col1:
        if ai.get("mini_headline"):
            st.markdown(f"**{ai['mini_headline']}**")
        st.markdown("**Tiny actions to try this week:**")
        for b in (ai.get("tiny_actions") or [
            "Invite someone for a 20‑minute walk this week.",
            "Plan one micro‑adventure within 30 minutes from home.",
            "Offer a 30‑minute help session to someone this week.",
        ]):
            st.write(f"- {b}")

        st.markdown("**Your next 7 days (teaser):**")
        for b in (ai.get("week_teaser") or [
            "Mon: choose one lever and block 10 minutes.",
            "Tue: one 20‑minute skill rep.",
            "Wed: invite one person to join a quick activity.",
        ]):
            st.write(f"- {b}")

        st.markdown("**What you’ll unlock with the full report:**")
        for b in (ai.get("unlock") or [
            "Your postcard from 1 month ahead (Future Snapshot).",
            "Personalized insights & Why Now (short narrative).",
            "3 actions + If‑Then plan + 1‑week gentle plan.",
            "Printable checklist page + Tiny progress tracker."
        ]):
            st.write(f"- {b}")

    with col2:
        st.metric("Overall readiness", f"{total}/10")
        for k in top3:
            st.write(f"• **{LABELS.get(k,k)}**: {scores[k]}/10")

    st.caption("Unlock your complete report to see your 1‑month postcard, insights, plan & checklist.")

# ------------------------------
# Full report via AI (JSON pieces used to assemble a PDF)
# ------------------------------
def ai_full_report(first_name: str, scores: dict, total: int) -> dict:
    schema = """JSON schema:
    { "archetype": str,
      "core_need": str,
      "signature_metaphor": str,
      "signature_sentence": str,
      "insights": str,
      "why_now": str,
      "future_snapshot": str,
      "signature_strengths": [str, ...],
      "energizers": [str, ...],
      "drainers": [str, ...],
      "hidden_tensions": [str, ...],
      "watchout": str,
      "actions": [str, ...],
      "if_then": [str, ...],
      "one_week_plan": [str, ...]
    }"""
    prompt = (
        "Create a personalized, non‑financial Reflection Report in the Life Minus Work voice. "
        f"First name: {first_name or 'friend'}. Overall: {total}/10. "
        f"Theme scores: {json.dumps(scores)}. "
        "Keep it warm, human, and practical. Return strictly JSON per schema."
    )
    return ai_json(prompt, schema_hint=schema, max_tokens=MAX_OUTPUT_TOKENS_HIGH//2)

# ------------------------------
# PDF builder (simple, readable; mirrors the reflection report structure)
# ------------------------------
class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, "Life Minus Work — Reflection Report", ln=1, align="C")

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 8, f"© {datetime.now().year} Life Minus Work • lifeminuswork.com", align="C")

def _p(pdf: PDF, text: str, size=11, style=""):
    pdf.set_font("Helvetica", style, size)
    safe = (text or "").encode("latin-1", errors="ignore").decode("latin-1")
    pdf.multi_cell(0, 6, safe)

def build_pdf(first_name: str, scores: dict, overall: int, ai: dict) -> bytes:
    pdf = PDF(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    _p(pdf, f"Hi {first_name or 'there'},", 12)
    _p(pdf, "Here’s a calm snapshot of your non‑financial readiness.", 11)
    pdf.ln(3)
    pdf.set_font("Helvetica","B",13); pdf.cell(0,8,"Scores at a glance", ln=1)
    pdf.set_font("Helvetica","",11)
    pdf.cell(0,6, f"Overall readiness: {overall}/10", ln=1)
    for k,v in scores.items():
        pdf.cell(0,6, f"{LABELS.get(k,k)}: {v}/10", ln=1)

    if ai:
        pdf.ln(3); pdf.set_font("Helvetica","B",13); pdf.cell(0,8,"Your snapshot", ln=1)
        _p(pdf, ai.get("signature_sentence",""), 11)

        pdf.ln(1); pdf.set_font("Helvetica","B",13); pdf.cell(0,8,"Insights", ln=1)
        _p(pdf, ai.get("insights",""), 11)

        pdf.ln(1); pdf.set_font("Helvetica","B",13); pdf.cell(0,8,"Why now", ln=1)
        _p(pdf, ai.get("why_now",""), 11)

        pdf.ln(1); pdf.set_font("Helvetica","B",13); pdf.cell(0,8,"Future snapshot (1 month)", ln=1)
        _p(pdf, ai.get("future_snapshot",""), 11)

        def list_block(title, items):
            if items:
                pdf.ln(1); pdf.set_font("Helvetica","B",13); pdf.cell(0,8,title, ln=1)
                for it in items:
                    _p(pdf, f"• {it}", 11)
        list_block("Signature strengths", ai.get("signature_strengths"))
        list_block("Energizers", ai.get("energizers"))
        list_block("Drainers", ai.get("drainers"))
        list_block("Hidden tensions", ai.get("hidden_tensions"))

        pdf.ln(1); pdf.set_font("Helvetica","B",13); pdf.cell(0,8,"Watch‑out", ln=1)
        _p(pdf, ai.get("watchout",""), 11)

        list_block("3 next‑step actions (7 days)", ai.get("actions"))
        list_block("Implementation intentions (If‑Then)", ai.get("if_then"))
        list_block("1‑week gentle plan", ai.get("one_week_plan"))

    out = io.BytesIO()
    pdf.output(out)
    return out.getvalue()

# ------------------------------
# UI
# ------------------------------
st.title("Life Minus Work — Retirement Readiness (Non‑Financial)")
st.caption("A quick check on identity, connection, vitality, learning, adventure, and giving back — without any money math.")

# First name (personalizes mini + full report)
first_name = st.text_input("Your first name (optional, used to personalize your report)", max_chars=40, key="first_name_input")

with st.expander("How it works", expanded=False):
    st.write(
        "Use the sliders (0–10). You’ll get a **Mini Report** right away. "
        "To unlock your **full PDF** (with insights, a 1‑month postcard, and next steps), verify your email."
    )
    st.write("**Scale:** 0 = Not at all true · 5 = Somewhat true · 10 = Very true")

# Collect answers in session state
if "answers" not in st.session_state:
    st.session_state.answers = {t: [5]*len(QUESTIONS[t]) for t in THEMES}

# Render sliders
for t in THEMES:
    st.subheader(t)
    for i, q in enumerate(QUESTIONS[t]):
        st.session_state.answers[t][i] = st.slider(q, 0, 10, st.session_state.answers[t][i], 1, key=f"{t}:{i}")

# Compute scores
scores = compute_scores(st.session_state.answers)
total = overall_score(scores)

st.divider()
render_mini_report(first_name, scores, total)

# ------------------------------
# Verify email → unlock full report
# ------------------------------
st.divider()
st.header("Unlock your complete Reflection Report")
st.write("We’ll email a 6‑digit code to verify it’s really you. No spam—ever.")

if "pending_email" not in st.session_state:
    st.session_state.pending_email = ""
if "sent_code" not in st.session_state:
    st.session_state.sent_code = ""
if "verified" not in st.session_state:
    st.session_state.verified = False

colA, colB = st.columns([1,1])
with colA:
    email_input = st.text_input("Your email", placeholder="you@example.com")
    if st.button("Email me a 6‑digit code"):
        e = (email_input or "").strip()
        if not e or "@" not in e:
            st.error("Please enter a valid email.")
        else:
            code = "".join(str(random.randint(0,9)) for _ in range(6))
            st.session_state.sent_code = code
            st.session_state.pending_email = e
            try:
                send_verification_code(e, code, first_name=first_name)
                log_email_capture(e, first_name, {"scores": scores, "overall": total}, source="request-code")
                st.success(f"We’ve emailed a code to {e}.")
            except Exception as ex:
                st.error(f"Could not send email: {ex}")

with colB:
    code_entered = st.text_input("Verification code", max_chars=6)
    if st.button("Verify"):
        if code_entered and code_entered.strip() == st.session_state.sent_code:
            st.session_state.verified = True
            log_email_capture(st.session_state.pending_email, first_name, {"scores": scores, "overall": total}, source="verify")
            st.success("Verified! Your full report is unlocked.")
        else:
            st.error("That code doesn’t match. Try again.")

# ------------------------------
# Generate & download PDF (once verified)
# ------------------------------
if st.session_state.verified:
    ai_full = ai_full_report(first_name, scores, total) if _HAS_OPENAI else {}
    pdf_bytes = build_pdf(first_name, scores, total, ai_full or {})
    fname = "LifeMinusWork_Reflection_Report.pdf"
    st.download_button("📄 Download your Reflection Report (PDF)", data=pdf_bytes, file_name=fname, mime="application/pdf")
    if st.button("Email me the PDF"):
        try:
            send_pdf(st.session_state.pending_email, pdf_bytes, fname, first_name=first_name)
            st.success("Sent! Check your inbox.")
        except Exception as ex:
            st.error(f"Could not send PDF: {ex}")

# ------------------------------
# Admin: optional captured emails viewer
# ------------------------------
if LW_SHOW_EMAILS_ADMIN == "1":
    st.divider()
    with st.expander("Captured emails (admin)", expanded=False):
        st.write(f"Storage: {'Google Sheets' if gsheets_enabled() else 'disabled'}")
        try:
            ws = _get_ws()
            if ws:
                rows = ws.get_all_records()
                st.write(f"Total captured: {len(rows)}")
                if rows:
                    st.dataframe(rows, use_container_width=True)
            else:
                st.info("Sheets not configured.")
        except Exception as e:
            st.error(f"Could not load emails: {e}")
