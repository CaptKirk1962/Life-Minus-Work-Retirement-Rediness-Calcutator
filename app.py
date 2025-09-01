
# app_fixed.py — LMW Questionnaire (hotfix build)
# - First name field
# - Mini Report robust (chart + bullets + teaser + unlock list)
# - Email secrets mapping: GMAIL_* or EMAIL_*
# - OpenAI call WITHOUT response_format (no SDK mismatch)
# - Verification flow + PDF email

import os, io, json, random, smtplib, ssl
from datetime import datetime, timezone
from email.message import EmailMessage

import streamlit as st
import matplotlib.pyplot as plt
from fpdf import FPDF

st.set_page_config(page_title="LMW Readiness — Hotfix", page_icon="🧭", layout="wide")

# ---- Secrets mapping
def sget(k, default=""):
    try:
        if k in st.secrets: return st.secrets[k]
    except Exception:
        pass
    return os.getenv(k, default)

EMAIL_SENDER = sget("GMAIL_USER") or sget("EMAIL_SENDER")
EMAIL_APP_PASSWORD = sget("GMAIL_APP_PASSWORD") or sget("EMAIL_APP_PASSWORD")
SENDER_NAME = sget("SENDER_NAME","Life Minus Work")
REPLY_TO = sget("REPLY_TO", EMAIL_SENDER)
AI_MODEL = sget("OPENAI_HIGH_MODEL","gpt-5-mini")

# ---- OpenAI client
_HAS_OPENAI=False
_client=None
try:
    from openai import OpenAI
    _client = OpenAI()
    _HAS_OPENAI=bool(sget("OPENAI_API_KEY"))
except Exception:
    _client=None
    _HAS_OPENAI=False

def ai_json(prompt: str, max_tokens: int = 1200) -> dict:
    if not (_HAS_OPENAI and _client): return {}
    try:
        # No response_format. Keep input as a single string for broad SDK compatibility.
        resp = _client.responses.create(model=AI_MODEL, input=prompt, max_output_tokens=max_tokens)
        text = getattr(resp, "output_text", "") or ""
        return json.loads(text) if text.strip().startswith("{") else {}
    except Exception:
        # final fallback: return empty
        return {}

# ---- Email
def _smtp_send(msg: EmailMessage):
    if not (EMAIL_SENDER and EMAIL_APP_PASSWORD):
        raise RuntimeError("Email sender/app password missing in Secrets.")
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
    msg["From"] = f"{SENDER_NAME} <{EMAIL_SENDER}>"
    msg["To"] = to_email
    if REPLY_TO: msg["Reply-To"]=REPLY_TO
    msg["Subject"] = "Your Life Minus Work verification code"
    hello = f"Hi {first_name}," if first_name else "Hi there,"
    msg.set_content(f"{hello}\n\nYour code is: {code}\nEnter this in the app.\n\n— Life Minus Work")
    _smtp_send(msg)

def send_pdf(to_email: str, pdf_bytes: bytes, filename: str, first_name: str=""):
    msg = EmailMessage()
    msg["From"] = f"{SENDER_NAME} <{EMAIL_SENDER}>"
    msg["To"] = to_email
    if REPLY_TO: msg["Reply-To"]=REPLY_TO
    msg["Subject"] = "Your Life Minus Work — Reflection Report (PDF)"
    hello = f"Hi {first_name}," if first_name else "Hi there,"
    msg.set_content(f"{hello}\n\nAttached is your Reflection Report (PDF).\n\n— Life Minus Work")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)
    _smtp_send(msg)

# ---- Questionnaire
THEMES = [
    "Purpose & Identity", "Social Health & Community Connection", "Health & Vitality",
    "Learning & Growth", "Adventure & Exploration", "Giving Back"
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
LABELS = {
    "Purpose & Identity":"Identity","Social Health & Community Connection":"Connection",
    "Health & Vitality":"Vitality","Learning & Growth":"Growth",
    "Adventure & Exploration":"Adventure","Giving Back":"Contribution"
}

def compute_scores(responses: dict) -> dict:
    scores={}
    for t,vals in responses.items():
        scores[t]=int(round(sum(vals)/len(vals))) if vals else 0
    return scores

def overall(scores: dict) -> int:
    return int(round(sum(scores.values())/max(1,len(scores))))

# ---- UI
st.title("Life Minus Work — Readiness Check (Hotfix)")
first_name = st.text_input("Your first name (optional)", key="first_name_input")

if "answers" not in st.session_state:
    st.session_state.answers = {t:[5]*len(QUESTIONS[t]) for t in THEMES}

for t in THEMES:
    st.subheader(t)
    for i,q in enumerate(QUESTIONS[t]):
        st.session_state.answers[t][i] = st.slider(q,0,10,st.session_state.answers[t][i],1, key=f"{t}:{i}")

scores = compute_scores(st.session_state.answers); total = overall(scores)

# ---- Mini Report (robust, Reflections-style)
st.divider()
st.subheader("Your Mini Report (Preview)")
top3 = [k for k,_ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:3]]
st.caption("Top themes: " + ", ".join(LABELS.get(k,k) for k in top3))

# chart
fig, ax = plt.subplots(figsize=(7,3))
ax.bar([LABELS.get(k,k) for k in THEMES],[scores.get(k,0) for k in THEMES])
ax.set_ylim(0,10); ax.set_title("Theme Snapshot"); plt.xticks(rotation=45, ha="right")
st.pyplot(fig, use_container_width=True)

prompt = (
    "Return strict JSON with keys: mini_headline, tiny_actions[3], week_teaser[3], unlock[4]. "
    f"First name: {first_name or 'friend'}. Scores: {json.dumps(scores)}."
)
ai = ai_json(prompt, max_tokens=900) if _HAS_OPENAI else {}

st.markdown("**Tiny actions to try this week:**")
for b in (ai.get("tiny_actions") if ai else [
    "Invite someone for a 20‑minute walk this week.",
    "Plan one micro‑adventure within 30 minutes from home.",
    "Offer a 30‑minute help session to someone this week.",
]):
    st.write(f"- {b}")

st.markdown("**Your next 7 days (teaser):**")
for b in (ai.get("week_teaser") if ai else [
    "Mon: choose one lever and block 10 minutes.",
    "Tue: one 20‑minute skill rep.",
    "Wed: invite one person to join a quick activity.",
]):
    st.write(f"- {b}")

st.markdown("**What you’ll unlock with the full report:**")
for b in (ai.get("unlock") if ai else [
    "Postcard from 1 month ahead (Future Snapshot).",
    "Personalized insights & Why Now.",
    "3 actions + If‑Then plan + 1‑week gentle plan.",
    "Printable checklist page + Tiny progress tracker."
]):
    st.write(f"- {b}")

# ---- Verify + PDF
st.divider()
st.header("Unlock your complete Reflection Report")
email = st.text_input("Your email", placeholder="you@example.com", key="email_input")
if "sent_code" not in st.session_state: st.session_state.sent_code=""
if "verified" not in st.session_state: st.session_state.verified=False

cA,cB = st.columns(2)
with cA:
    if st.button("Email me a 6‑digit code"):
        e=(email or "").strip()
        if not e or "@" not in e: st.error("Please enter a valid email.")
        else:
            code="".join(str(random.randint(0,9)) for _ in range(6))
            st.session_state.sent_code=code
            try:
                send_verification_code(e, code, first_name=first_name)
                st.success(f"We’ve emailed a code to {e}.")
            except Exception as ex:
                st.error(f"Could not send email: {ex}")
with cB:
    v=st.text_input("Verification code", max_chars=6)
    if st.button("Verify"):
        if v.strip()==st.session_state.sent_code:
            st.session_state.verified=True
            st.success("Verified!")
        else:
            st.error("That code doesn’t match.")

class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica","B",16); self.cell(0,10,"Life Minus Work — Reflection Report",ln=1,align="C")
    def footer(self):
        self.set_y(-15); self.set_font("Helvetica","",8); self.cell(0,8,"© Life Minus Work",align="C")
def _p(pdf, text, size=11, style=""):
    pdf.set_font("Helvetica",style,size); pdf.multi_cell(0,6,(text or "").encode("latin-1","ignore").decode("latin-1"))

def build_pdf(first_name, scores, overall):
    pdf=PDF(); pdf.set_auto_page_break(True,18); pdf.add_page()
    _p(pdf, f"Hi {first_name or 'there'},",12)
    _p(pdf, "Here’s a calm snapshot of your non‑financial readiness.",11)
    pdf.ln(2); pdf.set_font("Helvetica","B",13); pdf.cell(0,8,"Scores at a glance",ln=1)
    _p(pdf, f"Overall readiness: {overall}/10",11)
    for k,v in scores.items(): _p(pdf, f"{k}: {v}/10",11)
    out=io.BytesIO(); pdf.output(out); return out.getvalue()

if st.session_state.verified:
    pdf_bytes = build_pdf(first_name, scores, total)
    st.download_button("📄 Download your Reflection Report (PDF)", data=pdf_bytes, file_name="LMW_Reflection_Report.pdf", mime="application/pdf")
    if st.button("Email me the PDF"):
        try:
            send_pdf(email, pdf_bytes, "LMW_Reflection_Report.pdf", first_name=first_name)
            st.success("Sent! Check your inbox.")
        except Exception as ex:
            st.error(f"Could not send PDF: {ex}")
