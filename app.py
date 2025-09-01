# app.py — Life Minus Work • Retirement Readiness (Non-Financial)
# Mini Report → Email Verify → Full PDF. Google Sheets capture identical to Reflections app.

from __future__ import annotations
import os, io, json, math, smtplib, csv
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
import secrets as pysecrets

import streamlit as st
from fpdf import FPDF
from PIL import Image
import gspread
import pandas as pd

# =========================
# App & assets
# =========================
st.set_page_config(page_title="LMW — Retirement Readiness", page_icon="🌱", layout="wide")

APP_DIR = Path(__file__).resolve().parent
LOGO_PNG = st.secrets.get("LMW_LOGO_FILE", "Life-Minus-Work-Logo.png")
LOGO_WEBP = st.secrets.get("LMW_LOGO_FILE_WEBP", "Life-Minus-Work-Logo.webp")

def _resolve_logo() -> Path | None:
    png = APP_DIR / LOGO_PNG
    if png.exists():
        return png
    webp = APP_DIR / LOGO_WEBP
    if webp.exists():
        try:
            tmp = APP_DIR / "_lmw_logo_tmp.png"
            Image.open(webp).convert("RGBA").save(tmp)
            return tmp
        except Exception:
            return None
    return None

LOGO_PATH = _resolve_logo()

# =========================
# OpenAI (GPT-5-mini)
# =========================
AI_MODEL = "gpt-5-mini"
_HAS_OPENAI = False
try:
    from openai import OpenAI
    _client = OpenAI()
    _HAS_OPENAI = bool(st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"))
except Exception:
    _client = None
    _HAS_OPENAI = False

def ai_write_summary(payload: dict, max_tokens: int = 2000) -> dict:
    """
    Calls GPT-5-mini via Responses API. Returns dict with:
    { mini_headline, mini_bullets[], insights{}, actions[], postcard, tone }
    """
    if not _HAS_OPENAI or _client is None:
        return {}
    sys = (
        "You are a calm, encouraging coach for Life Minus Work. "
        "Use the scores (0-10) across six domains (Identity, Social, Health, Learning, Adventure, Giving) "
        "to compose helpful, non-judgmental reflections. Offer tiny, practical steps. "
        "Return ONLY valid JSON per the schema—no extra text."
    )
    user = {
        "task": "retirement_readiness_nonfinancial",
        "schema": {
            "mini_headline": "string (<= 90 chars)",
            "mini_bullets": ["string","string","string"],
            "insights": {
                "top_themes": ["string","string","string"],
                "balancing_opportunities": ["string","string","string"]
            },
            "actions": ["string","string","string","string","string"],
            "postcard": "string (a short, kind paragraph as if from '1 month ahead')",
            "tone": "string"
        },
        "inputs": payload
    }
    try:
        resp = _client.responses.create(
            model=AI_MODEL,
            max_output_tokens=min(5000, max_tokens),
            input=[
                {"role":"system","content":sys},
                {"role":"user","content":json.dumps(user)}
            ],
            response_format={"type":"json_object"},
        )
        text = resp.output_text or ""
        return json.loads(text) if text.strip().startswith("{") else {}
    except Exception as e:
        st.info(f"AI fell back to safe content ({e})")
        return {}

# =========================
# Email (Gmail App Password)
# =========================
EMAIL_SENDER = st.secrets.get("EMAIL_SENDER", "")
EMAIL_APP_PASSWORD = st.secrets.get("EMAIL_APP_PASSWORD", "")
EMAIL_BCC = st.secrets.get("EMAIL_BCC", "")

def _smtp_send(msg: EmailMessage):
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=25) as s:
        s.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
        s.send_message(msg)

def send_verification_code(to_email: str, code: str):
    if not (EMAIL_SENDER and EMAIL_APP_PASSWORD):
        raise RuntimeError("Email sender/app password missing in Secrets.")
    m = EmailMessage()
    m["From"] = EMAIL_SENDER
    m["To"] = to_email
    if EMAIL_BCC: m["Bcc"] = EMAIL_BCC
    m["Subject"] = "Your Life Minus Work verification code"
    m.set_content(
        f"Here’s your code: {code}\n\n"
        "Enter this in the app to unlock your full Retirement Readiness Report (PDF). "
        "Code expires in ~10 minutes."
    )
    _smtp_send(m)

def send_pdf(to_email: str, pdf_bytes: bytes, filename: str):
    if not (EMAIL_SENDER and EMAIL_APP_PASSWORD):
        raise RuntimeError("Email sender/app password missing in Secrets.")
    m = EmailMessage()
    m["From"] = EMAIL_SENDER
    m["To"] = to_email
    if EMAIL_BCC: m["Bcc"] = EMAIL_BCC
    m["Subject"] = "Your Life Minus Work — Retirement Readiness Report (PDF)"
    m.set_content("Attached is your full report. Keep it handy and revisit weekly to keep momentum.\n\n— Life Minus Work")
    m.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)
    _smtp_send(m)

# =========================
# Google Sheets capture (same as Reflections)
# =========================
LW_SHEET_URL = st.secrets.get("LW_SHEET_URL", "").strip()
LW_SHEET_WORKSHEET = st.secrets.get("LW_SHEET_WORKSHEET", "emails")
SHOW_EMAILS_ADMIN = st.secrets.get("LW_SHOW_EMAILS_ADMIN", "") == "1"

def gsheets_enabled() -> bool:
    try:
        return bool(st.secrets.get("gcp_service_account")) and bool(LW_SHEET_URL)
    except Exception:
        return False

@st.cache_resource(show_spinner=False)
def get_gs_client():
    sa = st.secrets.get("gcp_service_account", None)
    if not sa: raise RuntimeError("gcp_service_account not found in secrets")
    return gspread.service_account_from_dict(sa)

@st.cache_resource(show_spinner=False)
def get_email_ws():
    if not gsheets_enabled(): raise RuntimeError("Google Sheets not configured")
    gc = get_gs_client()
    sh = gc.open_by_url(LW_SHEET_URL)
    try:
        ws = sh.worksheet(LW_SHEET_WORKSHEET)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=LW_SHEET_WORKSHEET, rows=2000, cols=8)
    header = ["email","first_name","verified_at","model","scores","source"]
    existing = ws.row_values(1)
    if [h.strip().lower() for h in existing] != header:
        ws.update("A1:F1", [header])
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
    # Try Sheets first
    try:
        if gsheets_enabled():
            ws = get_email_ws()
            ws.append_row(
                [row["email"], row["first_name"], row["verified_at"], row["model"], row["scores"], row["source"]],
                value_input_option="USER_ENTERED",
            )
            return
    except Exception as e:
        st.warning(f"(Sheets capture failed; continuing) {e}")

# =========================
# Questionnaire (exact items; 0–10 sliders)
# =========================
QUESTIONS = {
    "Purpose & Identity": [
        "I feel confident about who I am beyond my work role.",
        "I have a clear sense of purpose for my post-work life.",
        "I rarely feel anxious or lost without my daily work routine.",
        "I can easily reflect on my career achievements without regret."
    ],
    "Social Health & Community Connection": [
        "I have strong relationships outside of work.",
        "I actively nurture friendships and community connections.",
        "I feel comfortable reaching out to new people.",
        "Loneliness is not a concern for me right now."
    ],
    "Health & Vitality": [
        "I maintain regular physical activity.",
        "My mental and emotional wellbeing feels stable.",
        "I prioritize sleep, nutrition, and stress management.",
        "I have no major health barriers to exploring new activities."
    ],
    "Learning & Growth": [
        "I actively pursue new knowledge or skills.",
        "I have a growth mindset and enjoy learning challenges.",
        "I make time for reading, courses, or hobbies that expand my mind.",
        "Cognitive sharpness is a priority in my daily life."
    ],
    "Adventure & Exploration": [
        "I seek out new experiences and adventures regularly.",
        "I feel excited about exploring unfamiliar places or activities.",
        "Novelty and discovery bring joy to my routine.",
        "I step outside my comfort zone without much hesitation."
    ],
    "Giving Back": [
        "I find ways to contribute to others or my community.",
        "Mentoring or volunteering feels fulfilling to me.",
        "I have opportunities to share my wisdom and experience.",
        "Giving back is an important part of my identity."
    ]
}

THEMES = list(QUESTIONS.keys())

def compute_scores(responses: dict[str, list[int]]) -> dict[str, int]:
    scores = {}
    for theme, vals in responses.items():
        if vals:
            scores[theme] = int(round(sum(vals) / len(vals)))
        else:
            scores[theme] = 0
    return scores

def overall_score(scores: dict[str, int]) -> int:
    if not scores: return 0
    return int(round(sum(scores.values()) / len(scores)))

# =========================
# UI
# =========================
st.title("Life Minus Work — Retirement Readiness (Non-Financial)")
st.caption("A quick check on identity, connection, vitality, learning, adventure, and giving back — without any money math.")

with st.expander("How it works", expanded=False):
    st.write(
        "Use the sliders (0–10). You’ll get a **Mini Report** right away. "
        "To unlock your **full PDF** (with insights, a 1-month-ahead postcard, and next steps), verify your email."
    )
    st.write("**Scale:** 0 = Not at all true · 5 = Somewhat true · 10 = Very true")

# Collect answers
if "answers" not in st.session_state:
    st.session_state.answers = {t: [5]*len(QUESTIONS[t]) for t in THEMES}

# Render sliders (keeps same look)
for t in THEMES:
    st.subheader(t)
    for idx, q in enumerate(QUESTIONS[t]):
        key = f"{t}:{idx}"
        st.session_state.answers[t][idx] = st.slider(q, 0, 10, st.session_state.answers[t][idx], 1, key=key)

# Compute
scores = compute_scores(st.session_state.answers)
total = overall_score(scores)
top3 = [k for k,_ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:3]]

st.divider()
st.subheader("Your Mini Report (Preview)")
c1, c2 = st.columns([1.0, 1.2], gap="large")
with c1:
    st.metric("Overall readiness", f"{total}/10")
    for k in top3:
        st.write(f"**Top strength** — {k}: {scores[k]}/10")
with c2:
    # AI short narrative
    payload = {
        "scores": scores,
        "overall": total,
        "top3": top3,
        "horizon_weeks": 4,     # stay aligned with Reflections app wording
    }
    ai_mini = ai_write_summary(payload, max_tokens=1200) if _HAS_OPENAI else {}
    if ai_mini:
        st.markdown(f"**{ai_mini.get('mini_headline','Your snapshot')}**")
        for b in ai_mini.get("mini_bullets", [])[:3]:
            st.write(f"- {b}")
    else:
        st.markdown("**Snapshot:** you’ve got real momentum.")
        st.write("- Keep what’s working; change one thing at a time.")
        st.write("- Add a tiny, social element to something you already enjoy.")
        st.write("- Schedule one small experiment this week.")

st.caption("Unlock your complete report to see your 1-month postcard, insights, and next steps.")

# =========================
# Verify email → unlock full report
# =========================
st.divider()
st.header("Unlock your complete report")
st.write("We’ll email a 6-digit code to verify it’s really you. No spam—ever.")

if "pending_email" not in st.session_state:
    st.session_state.pending_email = ""
if "sent_code" not in st.session_state:
    st.session_state.sent_code = ""
if "verified" not in st.session_state:
    st.session_state.verified = False

email_input = st.text_input("Your email")
colA, colB = st.columns([1,1])
with colA:
    if st.button("Email me a 6-digit code"):
        e = (email_input or "").strip()
        if not e or "@" not in e:
            st.error("Please enter a valid email.")
        else:
            code = "".join(str(pysecrets.randbelow(10)) for _ in range(6))
            st.session_state.sent_code = code
            st.session_state.pending_email = e
            try:
                send_verification_code(e, code)
                # store a row immediately (attempt) for analytics, marked source: request-code
                log_email_capture(e, st.session_state.get("first_name_input",""), {"scores": scores, "overall": total}, source="request-code")
                st.success(f"We’ve emailed a code to {e}.")
            except Exception as ex:
                st.error(f"Could not send email: {ex}")

with colB:
    code_entered = st.text_input("Verification code", max_chars=6)
    if st.button("Verify"):
        if code_entered and code_entered.strip() == st.session_state.sent_code:
            st.session_state.verified = True
            # durable capture on verify
            log_email_capture(st.session_state.pending_email, st.session_state.get("first_name_input",""),
                              {"scores": scores, "overall": total}, source="verify")
            st.success("Verified! Your full report is unlocked.")
        else:
            st.error("That code doesn’t match. Try again.")

# =========================
# PDF (same layout family as Reflections)
# =========================
class PDF(FPDF):
    def header(self):
        if LOGO_PATH and LOGO_PATH.exists():
            try:
                self.image(str(LOGO_PATH), x=12, y=10, w=36)
            except Exception:
                pass
        self.set_xy(14, 26)
        self.set_font("Arial", "B", 22)
        self.cell(0, 10, "Life Minus Work — Retirement Readiness", ln=1)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "", 8)
        self.cell(0, 8, f"© {datetime.now().year} Life Minus Work · lifeminuswork.com", align="C")

def _pdf_text(pdf: PDF, text: str, size=11, style=""):
    pdf.set_font("Arial", style, size)
    safe = text.encode("latin-1", errors="ignore").decode("latin-1")
    pdf.multi_cell(0, 6, safe)

def build_pdf(first_name: str, scores: dict, overall: int, ai: dict) -> bytes:
    pdf = PDF(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.ln(8)

    _pdf_text(pdf, f"Hi {first_name or 'there'},", 12)
    _pdf_text(pdf, "Here’s a calm snapshot of your non-financial retirement readiness.", 11)

    pdf.ln(2); pdf.set_font("Arial","B",14); pdf.cell(0,8,"Scores at a glance", ln=1)
    pdf.set_font("Arial","",11)
    pdf.cell(0,6, f"Overall readiness: {overall}/10", ln=1)
    for k,v in scores.items():
        pdf.cell(0,6, f"{k}: {v}/10", ln=1)

    if ai:
        pdf.ln(2); pdf.set_font("Arial","B",14); pdf.cell(0,8,"Your snapshot", ln=1)
        _pdf_text(pdf, ai.get("mini_headline",""), 12)
        for b in ai.get("mini_bullets", [])[:5]:
            _pdf_text(pdf, f"• {b}", 11)

        ins = ai.get("insights", {}) or {}
        top_themes = ins.get("top_themes") or []
        bal = ins.get("balancing_opportunities") or []

        pdf.ln(2); pdf.set_font("Arial","B",14); pdf.cell(0,8,"Top themes", ln=1)
        for t in top_themes: _pdf_text(pdf, f"• {t}", 11)

        pdf.set_font("Arial","B",14); pdf.cell(0,8,"Balancing opportunities", ln=1)
        for b in bal: _pdf_text(pdf, f"• {b}", 11)

        pdf.set_font("Arial","B",14); pdf.cell(0,8,"Next tiny steps", ln=1)
        for a in ai.get("actions", [])[:8]:
            _pdf_text(pdf, f"• {a}", 11)

        pdf.set_font("Arial","B",14); pdf.cell(0,8,"A note from 1 month ahead", ln=1)
        _pdf_text(pdf, ai.get("postcard",""), 11)

    out = pdf.output(dest="S")
    if isinstance(out, str):
        out = out.encode("latin-1", errors="ignore")
    return out

# =========================
# Unlock → Full report actions
# =========================
if st.session_state.verified:
    st.subheader("Your full report")
    st.caption("Heads up: generating your PDF might take ~1 minute.")

    # richer AI call for full report
    payload_full = {"scores": scores, "overall": total, "top3": top3, "horizon_weeks": 4}
    ai_full = ai_write_summary(payload_full, max_tokens=3500) if _HAS_OPENAI else {}

    with st.spinner("Building PDF…"):
        pdf_bytes = build_pdf(st.session_state.get("first_name_input",""), scores, total, ai_full or {})

    cdl, cem = st.columns([1,1])
    with cdl:
        st.download_button(
            "⬇️ Download my full report (PDF)",
            data=pdf_bytes,
            file_name="LMW_Retirement_Readiness_Report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    with cem:
        if st.button("📧 Email my report"):
            try:
                send_pdf(st.session_state.pending_email, pdf_bytes, "LMW_Retirement_Readiness_Report.pdf")
                st.success(f"Sent the PDF to {st.session_state.pending_email}.")
            except Exception as e:
                st.error(f"Could not send email: {e}")
else:
    st.info("Enter your 6-digit code to unlock the full PDF report and email options.")

# =========================
# Admin / debug
# =========================
with st.expander("AI status (debug)", expanded=False):
    st.write({
        "AI enabled": bool(_HAS_OPENAI),
        "Model": AI_MODEL,
        "Logo found": bool(LOGO_PATH and LOGO_PATH.exists()),
        "Sheets configured": gsheets_enabled(),
    })

if SHOW_EMAILS_ADMIN:
    with st.expander("Captured emails (admin)", expanded=False):
        st.write(f"Storage: {'Google Sheets' if gsheets_enabled() else 'disabled'}")
        try:
            if gsheets_enabled():
                rows = get_email_ws().get_all_records()
                st.write(f"Total captured: {len(rows)}")
                if rows:
                    st.dataframe(rows, use_container_width=True)
            else:
                st.info("Sheets not configured.")
        except Exception as e:
            st.error(f"Could not load emails: {e}")
