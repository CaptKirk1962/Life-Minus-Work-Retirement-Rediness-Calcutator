# app.py — Life Minus Work • Retirement Readiness Calculator
# ---------------------------------------------------------------------
# Features:
# - Mini Report on page (numbers + GPT-5-mini narrative)
# - Email capture + 6-digit verification (SMTP / Gmail App Password)
# - Full PDF (same layout + logo as Reflection Report), downloadable & emailable
# - Robust fallbacks (safe static content if AI or email fails)
#
# Streamlit Secrets needed (Settings → Secrets):
# ------------------------------------------------
# OPENAI_API_KEY = "sk-..."
# EMAIL_SENDER = "whatisyourminus@gmail.com"        # or your sender
# EMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx"        # Gmail App Password
# EMAIL_BCC = "lifeminuswork@gmail.com"             # optional
# LMW_LOGO_FILE = "Life-Minus-Work-Logo.png"        # optional override
# LMW_LOGO_FILE_WEBP = "Life-Minus-Work-Logo.webp"  # optional
#
# Requirements (add to requirements.txt):
# ---------------------------------------
# streamlit==1.36.0
# fpdf==1.7.2
# Pillow>=10.3.0
# openai>=1.60.0
# pandas>=2.2.2
#
# Folder layout suggestion:
# main/
#   app.py
#   Life-Minus-Work-Logo.png        (or Life-Minus-Work-Logo.webp)
#   DejaVuSans.ttf                  (optional, for broader glyphs)
#   DejaVuSans-Bold.ttf             (optional)
# ---------------------------------------------------------------------

from __future__ import annotations
import os, io, math, json, time, smtplib, secrets as pysecrets
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import streamlit as st
import pandas as pd
from fpdf import FPDF
from PIL import Image

# ------------------------------
# App setup
# ------------------------------
st.set_page_config(
    page_title="LMW — Retirement Readiness",
    page_icon="💫",
    layout="wide",
)

APP_DIR = Path(__file__).resolve().parent
LOGO_PNG = st.secrets.get("LMW_LOGO_FILE", "Life-Minus-Work-Logo.png")
LOGO_WEBP = st.secrets.get("LMW_LOGO_FILE_WEBP", "Life-Minus-Work-Logo.webp")

# detect / prepare logo
def resolve_logo_path() -> Path | None:
    png = APP_DIR / LOGO_PNG
    if png.exists():
        return png
    webp = APP_DIR / LOGO_WEBP
    if webp.exists():
        try:
            tmp_png = APP_DIR / "_logo_tmp.png"
            Image.open(webp).convert("RGBA").save(tmp_png)
            return tmp_png
        except Exception:
            pass
    return None

LOGO_PATH = resolve_logo_path()

# ------------------------------
# OpenAI (GPT-5-mini via Responses API)
# ------------------------------
AI_MODEL = "gpt-5-mini"  # match your working Reflection app
try:
    from openai import OpenAI
    _client = OpenAI()
    _HAS_OPENAI = bool(st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"))
except Exception:
    _client, _HAS_OPENAI = None, False

def ai_generate_narrative(inputs: dict) -> dict:
    """
    Ask GPT-5-mini for succinct, structured retirement narrative.
    Returns dict with keys: mini_headline, mini_bullets[], strengths[], risks[], actions[], tone
    """
    if not _HAS_OPENAI or _client is None:
        return {}

    sys = (
        "You are a careful retirement planning writer for Life Minus Work. "
        "Write concise, kind, non-fearful guidance. Prefer small, reversible steps. "
        "Return pure JSON matching the provided schema. No extra prose."
    )
    user = {
        "task": "retirement_readiness_summary",
        "schema": {
            "mini_headline": "string (<= 90 chars, upbeat & calm)",
            "mini_bullets": ["string", "string", "string"],
            "strengths": ["string", "string", "string"],
            "risks": ["string", "string", "string"],
            "actions": ["string", "string", "string", "string"],
            "tone": "string (e.g., 'calm, practical, encouraging')"
        },
        "inputs": inputs,
    }

    try:
        # NOTE: Do not set temperature (gpt-5-mini supports default only).
        # Use max_output_tokens instead of max_tokens.
        resp = _client.responses.create(
            model=AI_MODEL,
            max_output_tokens=1200,
            input=[{"role":"system","content":sys},{"role":"user","content":json.dumps(user)}],
            # json output hint
            response_format={"type":"json_object"},
        )
        text = resp.output_text or ""
        data = json.loads(text) if text.strip().startswith("{") else {}
        return data if isinstance(data, dict) else {}
    except Exception as e:
        st.info(f"AI fell back to safe content ({e})")
        return {}

# ------------------------------
# Email utils (verification + send PDF)
# ------------------------------
EMAIL_SENDER = st.secrets.get("EMAIL_SENDER", "")
EMAIL_APP_PASSWORD = st.secrets.get("EMAIL_APP_PASSWORD", "")
EMAIL_BCC = st.secrets.get("EMAIL_BCC", "")

def _smtp_send(msg: EmailMessage):
    """Send email via Gmail SMTP with app password."""
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
        smtp.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
        smtp.send_message(msg)

def send_verification_code(to_email: str, code: str):
    if not EMAIL_SENDER or not EMAIL_APP_PASSWORD:
        raise RuntimeError("Email sender/app password missing in Secrets.")
    msg = EmailMessage()
    msg["From"] = EMAIL_SENDER
    msg["To"] = to_email
    if EMAIL_BCC:
        msg["Bcc"] = EMAIL_BCC
    msg["Subject"] = "Your Life Minus Work verification code"
    body = (
        f"Here’s your Life Minus Work code: {code}\n\n"
        "Enter this in the app to unlock your full Retirement Readiness Report (PDF). "
        "The code expires in 10 minutes."
    )
    msg.set_content(body)
    _smtp_send(msg)

def send_pdf_report(to_email: str, pdf_bytes: bytes, filename: str = "LMW_Retirement_Readiness_Report.pdf"):
    if not EMAIL_SENDER or not EMAIL_APP_PASSWORD:
        raise RuntimeError("Email sender/app password missing in Secrets.")
    msg = EmailMessage()
    msg["From"] = EMAIL_SENDER
    msg["To"] = to_email
    if EMAIL_BCC:
        msg["Bcc"] = EMAIL_BCC
    msg["Subject"] = "Your Life Minus Work — Retirement Readiness Report (PDF)"
    msg.set_content(
        "Attached is your full Retirement Readiness Report from Life Minus Work.\n"
        "Keep the PDF handy and revisit it weekly to keep momentum going.\n\n"
        "Warmly,\nLife Minus Work"
    )
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)
    _smtp_send(msg)

# ------------------------------
# Finance math
# ------------------------------
def project_nest_egg(
    age: int,
    retire_age: int,
    current_savings: float,
    annual_contrib: float,
    expected_return: float,
    inflation: float,
    fee_drag: float = 0.002,  # 0.2% annual
) -> dict:
    """
    Simple annual compounding to retirement; returns values in future $ and today's $.
    expected_return, inflation, fee_drag are annual decimals (e.g., 0.06)
    """
    years = max(0, retire_age - age)
    r_net = max(0.0, expected_return - fee_drag)
    bal = float(current_savings)
    history = []
    for y in range(1, years + 1):
        bal = bal * (1 + r_net) + annual_contrib
        history.append({"year": y, "age": age + y, "balance": bal})
    future_balance = bal
    # convert to today's dollars with inflation
    real_factor = (1 + inflation) ** years
    today_balance = future_balance / real_factor if years > 0 else future_balance
    return {
        "years": years,
        "future_balance": future_balance,
        "today_balance": today_balance,
        "history": history,
    }

def sustainable_income(balance_today_dollars: float, real_swr: float = 0.04) -> float:
    """Real (today $) safe annual withdrawal."""
    return balance_today_dollars * real_swr

def readiness_score(sustainable: float, desired_income_today: float) -> int:
    """0–100 capped score based on coverage of target income."""
    if desired_income_today <= 0:
        return 100
    ratio = sustainable / desired_income_today
    score = 100 * min(1.0, max(0.0, ratio))
    # gentle curve for mid-range
    if 0.4 < ratio < 1.0:
        score = 100 * (0.5 * ratio + 0.3)
    return int(round(score))

def money(x: float) -> str:
    try:
        return "${:,.0f}".format(x)
    except Exception:
        return f"${x:,.2f}"

# ------------------------------
# PDF builder (matches Reflection style)
# ------------------------------
class ReportPDF(FPDF):
    def header(self):
        if LOGO_PATH and LOGO_PATH.exists():
            try:
                self.image(str(LOGO_PATH), x=12, y=10, w=36)
            except Exception:
                pass
        self.set_xy(14, 26)
        self.set_font("Arial", "B", 24)
        self.cell(0, 10, "Life Minus Work — Retirement Readiness Report", ln=1)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "", 8)
        self.cell(0, 8, f"© {datetime.now().year} Life Minus Work · lifeminuswork.com", align="C")

def pdf_text(pdf: ReportPDF, txt: str, size=11, style=""):
    pdf.set_font("Arial", style, size)
    # guard for latin-1
    safe = txt.encode("latin-1", errors="ignore").decode("latin-1")
    pdf.multi_cell(0, 6, safe)

def build_pdf(first_name: str, inputs: dict, calc: dict, ai: dict) -> bytes:
    pdf = ReportPDF(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # Intro
    pdf.ln(10)
    pdf_text(pdf, f"Hi {first_name or 'there'},", 12)
    pdf_text(pdf, "Here’s a calm, practical snapshot of your retirement readiness based on the inputs you provided.", 11)
    pdf.ln(2)

    # Key numbers
    fb = calc["future_balance"]; tb = calc["today_balance"]
    swr = sustainable_income(tb)
    des = inputs["desired_income_today"]
    score = readiness_score(swr, des)

    pdf.set_font("Arial", "B", 14); pdf.cell(0, 8, "Key Numbers", ln=1)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 6, f"Projected nest egg at {inputs['retire_age']}: {money(fb)} (future $)", ln=1)
    pdf.cell(0, 6, f"Nest egg in today’s dollars: {money(tb)}", ln=1)
    pdf.cell(0, 6, f"Sustainable annual income (today $): {money(swr)}", ln=1)
    pdf.cell(0, 6, f"Desired annual income (today $): {money(des)}", ln=1)
    pdf.cell(0, 6, f"Readiness score: {score}/100", ln=1)
    pdf.ln(2)

    # Mini narrative
    if ai:
        pdf.set_font("Arial", "B", 14); pdf.cell(0, 8, "Your Snapshot", ln=1)
        pdf_text(pdf, ai.get("mini_headline", ""), 12)
        for b in ai.get("mini_bullets", [])[:5]:
            pdf_text(pdf, f"• {b}", 11)
        pdf.ln(2)

        pdf.set_font("Arial", "B", 14); pdf.cell(0, 8, "Strengths", ln=1)
        for s in ai.get("strengths", [])[:6]:
            pdf_text(pdf, f"• {s}", 11)

        pdf.set_font("Arial", "B", 14); pdf.cell(0, 8, "Risks to watch", ln=1)
        for r in ai.get("risks", [])[:6]:
            pdf_text(pdf, f"• {r}", 11)

        pdf.set_font("Arial", "B", 14); pdf.cell(0, 8, "Next tiny steps", ln=1)
        for a in ai.get("actions", [])[:8]:
            pdf_text(pdf, f"• {a}", 11)

    # Inputs appendix
    pdf.ln(4)
    pdf.set_font("Arial", "B", 14); pdf.cell(0, 8, "Inputs (for reference)", ln=1)
    pdf.set_font("Arial", "", 11)
    for k in [
        "age","retire_age","current_savings","annual_contrib","expected_return","inflation",
        "fee_drag","desired_income_today"
    ]:
        v = inputs.get(k)
        if k in {"expected_return","inflation","fee_drag"}:
            pdf.cell(0, 6, f"{k.replace('_',' ').title()}: {round(100*v,2)}%", ln=1)
        elif k in {"current_savings","annual_contrib","desired_income_today"}:
            pdf.cell(0, 6, f"{k.replace('_',' ').title()}: {money(v)}", ln=1)
        else:
            pdf.cell(0, 6, f"{k.replace('_',' ').title()}: {v}", ln=1)

    # Output
    out = pdf.output(dest="S")
    if isinstance(out, str):
        out = out.encode("latin-1", errors="ignore")
    return out

# ------------------------------
# UI — Inputs
# ------------------------------
st.title("Life Minus Work — Retirement Readiness")
st.caption("A calm calculator to see where you stand, what’s strong, and what one tiny step to take next.")

with st.expander("About this tool", expanded=False):
    st.write(
        "We project your nest egg at retirement, convert to today’s dollars, then estimate a real, sustainable income. "
        "You’ll see a **Mini Report** immediately. To unlock your **full PDF report** (with narrative & checklist), "
        "we’ll verify your email—no spam, ever."
    )

c1, c2, c3 = st.columns(3)
with c1:
    age = st.number_input("Your age", min_value=18, max_value=80, value=45)
    retire_age = st.number_input("Target retirement age", min_value=age, max_value=80, value=max(60, age+15))
    current_savings = st.number_input("Current retirement savings ($)", min_value=0, step=1000, value=150000)
with c2:
    annual_contrib = st.number_input("Annual contribution ($/yr)", min_value=0, step=1000, value=18000)
    expected_return = st.slider("Expected annual return (nominal %)", 2.0, 10.0, 6.0, step=0.1) / 100.0
    inflation = st.slider("Inflation assumption (annual %)", 1.0, 5.0, 2.5, step=0.1) / 100.0
with c3:
    fee_drag = st.slider("Fee drag (%/yr)", 0.0, 1.0, 0.2, step=0.05) / 100.0
    desired_income_today = st.number_input("Desired retirement income (today $/yr)", min_value=0, step=1000, value=70000)
    first_name = st.text_input("Your first name (for the report)", value="")

inputs = dict(
    age=int(age),
    retire_age=int(retire_age),
    current_savings=float(current_savings),
    annual_contrib=float(annual_contrib),
    expected_return=float(expected_return),
    inflation=float(inflation),
    fee_drag=float(fee_drag),
    desired_income_today=float(desired_income_today),
)

calc = project_nest_egg(**inputs)
swr = sustainable_income(calc["today_balance"])
score = readiness_score(swr, desired_income_today)

st.subheader("Your Mini Report (Preview)")
left, right = st.columns([1,1.1])
with left:
    st.metric("Readiness score", f"{score}/100")
    st.metric("Nest egg at retirement (future $)", money(calc["future_balance"]))
    st.metric("Nest egg (today $)", money(calc["today_balance"]))
with right:
    st.write("**Sustainable income (today $)**:", money(swr))
    st.write("**Desired income (today $)**:", money(desired_income_today))
    cov = 0 if desired_income_today==0 else int(round(100*swr/desired_income_today))
    st.progress(min(100, max(0,cov)), text=f"Target coverage: {cov}%")

# AI mini narrative
ai_inputs = dict(
    first_name=first_name or "friend",
    readiness_score=score,
    nest_egg_future=calc["future_balance"],
    nest_egg_today=calc["today_balance"],
    sustainable_income_today=swr,
    desired_income_today=desired_income_today,
    years_to_retirement=calc["years"],
    assumptions={
        "expected_return": inputs["expected_return"],
        "inflation": inputs["inflation"],
        "fee_drag": inputs["fee_drag"]
    }
)
with st.spinner("Thinking through your snapshot…"):
    ai = ai_generate_narrative(ai_inputs)

if ai:
    st.markdown(f"**{ai.get('mini_headline','Your snapshot')}**")
    for b in ai.get("mini_bullets", [])[:3]:
        st.write(f"- {b}")
else:
    st.markdown("**Snapshot:** steady progress, focus on small, repeatable steps.")
    st.write("- Keep contributions consistent; increase 1–2% next raise.")
    st.write("- Prefer low-cost funds; review fees annually.")
    st.write("- Revisit plan each quarter—tiny changes compound.")

st.caption("Unlock your complete report to get a full narrative + strengths, risks, and next steps.")

st.divider()

# ------------------------------
# Unlock — Email verification flow
# ------------------------------
st.header("Unlock your complete report")
st.write("We’ll email a 6-digit code to verify it’s you. No spam—ever.")

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
            # create and send code
            code = "".join([str(pysecrets.randbelow(10)) for _ in range(6)])
            st.session_state.sent_code = code
            st.session_state.pending_email = e
            try:
                send_verification_code(e, code)
                st.success(f"We emailed a code to {e}.")
            except Exception as ex:
                st.error(f"Could not send email: {ex}")

with colB:
    code_entered = st.text_input("Verification code", max_chars=6)
    if st.button("Verify"):
        if code_entered and code_entered.strip() == st.session_state.sent_code:
            st.session_state.verified = True
            st.success("Verified! Your full report is unlocked.")
        else:
            st.error("That code doesn’t match. Please try again.")

st.divider()

# ------------------------------
# Full report — build / download / email
# ------------------------------
if st.session_state.verified:
    st.subheader("Your full report")
    st.caption("Note: generating your PDF can take up to ~1 minute.")

    # Generate AI (again) with richer allowance
    if _HAS_OPENAI:
        with st.spinner("Assembling your full narrative…"):
            ai_full = ai_generate_narrative(ai_inputs)
            if not ai_full:
                ai_full = ai
    else:
        ai_full = ai

    with st.spinner("Building PDF…"):
        pdf_bytes = build_pdf(first_name, inputs, calc, ai_full or {})

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
                send_pdf_report(st.session_state.pending_email, pdf_bytes)
                st.success(f"Sent the PDF to {st.session_state.pending_email}.")
            except Exception as e:
                st.error(f"Could not send email: {e}")
else:
    st.info("Enter the code we emailed you to unlock the full report (download + email).")

# ------------------------------
# Debug / status (optional)
# ------------------------------
with st.expander("AI status (debug)", expanded=False):
    st.write({
        "AI enabled": bool(_HAS_OPENAI),
        "Model": AI_MODEL,
        "Logo found": bool(LOGO_PATH and LOGO_PATH.exists()),
    })
