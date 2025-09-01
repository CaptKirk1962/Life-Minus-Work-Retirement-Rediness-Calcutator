
# app_hotfix2.py — LMW Questionnaire (Unicode + Sheets + Mini Report quality)
import os, io, json, random, smtplib, ssl, importlib.util
from datetime import datetime, timezone
from email.message import EmailMessage

import streamlit as st
import matplotlib.pyplot as plt
from fpdf import FPDF

# ---------------- Setup ----------------
st.set_page_config(page_title="Life Minus Work — Readiness Check", page_icon="🧭", layout="wide")

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
MAX_TOK = int(sget("MAX_OUTPUT_TOKENS_HIGH", "8000") or "8000")

# Google Sheets
LW_SHEET_URL = sget("LW_SHEET_URL","").strip()
LW_SHEET_WORKSHEET = sget("LW_SHEET_WORKSHEET","emails").strip()

# ---------------- OpenAI (compatible call) ----------------
_HAS_OPENAI=False
_client=None
try:
    from openai import OpenAI
    _client = OpenAI()
    _HAS_OPENAI = bool(sget("OPENAI_API_KEY"))
except Exception:
    _client=None
    _HAS_OPENAI=False

def ai_json(prompt: str, max_tokens: int = 1200) -> dict:
    if not (_HAS_OPENAI and _client): return {}
    try:
        resp = _client.responses.create(model=AI_MODEL, input=prompt, max_output_tokens=max_tokens)
        text = getattr(resp, "output_text", "") or ""
        return json.loads(text) if text.strip().startswith("{") else {}
    except Exception:
        return {}

# ---------------- Email ----------------
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

# ---------------- Google Sheets logging ----------------
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
    except Exception:
        ws = sh.add_worksheet(title=LW_SHEET_WORKSHEET, rows=2000, cols=8)
        ws.update("A1:E1", [["email","first_name","verified_at","scores","overall"]])
    return ws

def log_email_capture(email: str, first_name: str, scores: dict, overall: int):
    try:
        ws = _get_ws()
        if ws:
            ws.append_row([email.lower().strip(), first_name.strip(), datetime.now(timezone.utc).isoformat(), json.dumps(scores), overall], value_input_option="USER_ENTERED")
    except Exception as e:
        st.warning(f"(Sheets capture failed: {e})")

# ---------------- Questionnaire ----------------
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

# ---------------- Retirement-relevant mini report ----------------
def build_mini_copy(first_name: str, scores: dict):
    top3 = [k for k,_ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:3]]
    greeting = f"Hi {first_name}," if first_name else "Hi there,"
    return {
        "headline": f"{greeting} your current strengths are {', '.join(LABELS.get(k,k) for k in top3)}.",
        "tiny_actions": [
            "Send one message proposing a 20‑minute walk or coffee this week.",
            "Plan one micro‑adventure within 30 minutes from home (Fri or Sun).",
            "Offer a 30‑minute help session to someone who’d benefit from your experience."
        ],
        "teaser": [
            "Mon: choose one lever and block 10 minutes.",
            "Tue: one 20‑minute skill rep or short course video.",
            "Wed: invite one person to join a quick activity."
        ],
        "unlock": [
            "Future Snapshot (1‑month postcard).",
            "Insights & Why Now (short narrative).",
            "3 actions + If‑Then plan + 1‑week gentle plan.",
            "Printable checklist page + Tiny progress tracker."
        ]
    }

# ---------------- PDF (Unicode-safe) ----------------
def to_latin1(s: str) -> str:
    if not s: return ""
    rep = {"—":"-","–":"-","‑":"-","“":'"',"”":'"',"‘":"'", "’":"'", "…":"...", "•":"- ", "\xa0":" ", "→":"->"}
    for a,b in rep.items(): s = s.replace(a,b)
    return s.encode("latin-1","ignore").decode("latin-1")

class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica","B",16); self.cell(0,10,to_latin1("Life Minus Work — Reflection Report"),ln=1,align="C")
    def footer(self):
        self.set_y(-15); self.set_font("Helvetica","",8); self.cell(0,8,to_latin1("© Life Minus Work"),align="C")

def _p(pdf, text, size=11, style=""):
    pdf.set_font("Helvetica",style,size)
    pdf.multi_cell(0,6,to_latin1(text or ""))

def build_pdf(first_name, scores, overall_score):
    pdf=PDF(); pdf.set_auto_page_break(True,18); pdf.add_page()
    _p(pdf, f"Hi {first_name or 'there'},",12)
    _p(pdf, "Here’s a calm snapshot of your non‑financial readiness.",11)
    pdf.ln(2); pdf.set_font("Helvetica","B",13); pdf.cell(0,8,to_latin1("Scores at a glance"),ln=1)
    _p(pdf, f"Overall readiness: {overall_score}/10",11)
    for k,v in scores.items(): _p(pdf, f"{LABELS.get(k,k)}: {v}/10",11)
    out=io.BytesIO(); pdf.output(out); return out.getvalue()

# ---------------- UI ----------------
st.title("Life Minus Work — Readiness Check")
first_name = st.text_input("Your first name (optional)", key="first_name_input")

if "answers" not in st.session_state:
    st.session_state.answers = {t:[5]*len(QUESTIONS[t]) for t in THEMES}

for t in THEMES:
    st.subheader(t)
    for i,q in enumerate(QUESTIONS[t]):
        st.session_state.answers[t][i] = st.slider(q,0,10,st.session_state.answers[t][i],1, key=f"{t}:{i}")

scores = compute_scores(st.session_state.answers); total = overall(scores)

st.divider()
st.subheader("Your Mini Report (Preview)")
top3 = [k for k,_ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:3]]
st.caption("Top themes: " + ", ".join(LABELS.get(k,k) for k in top3))

import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(5.8,2.6), dpi=120)
ax.bar([LABELS.get(k,k) for k in THEMES],[scores.get(k,0) for k in THEMES])
ax.set_ylim(0,10); ax.set_title("Theme Snapshot"); plt.xticks(rotation=35, ha="right")
st.pyplot(fig, use_container_width=True)

mini = build_mini_copy(first_name, scores)
st.markdown("**Tiny actions to try this week:**")
for b in mini["tiny_actions"]: st.write(f"- {b}")
st.markdown("**Your next 7 days (teaser):**")
for b in mini["teaser"]: st.write(f"- {b}")
st.markdown("**What you’ll unlock with the full report:**")
for b in mini["unlock"]: st.write(f"- {b}")

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
                log_email_capture(e, first_name, scores, total)
                st.success(f"We’ve emailed a code to {e}.")
            except Exception as ex:
                st.error(f"Could not send email: {ex}")
with cB:
    v=st.text_input("Verification code", max_chars=6)
    if st.button("Verify"):
        if v.strip()==st.session_state.sent_code:
            st.session_state.verified=True
            log_email_capture(email, first_name, scores, total)
            st.success("Verified!")
        else:
            st.error("That code doesn’t match.")

if st.session_state.verified:
    pdf_bytes = build_pdf(first_name, scores, total)
    st.download_button("📄 Download your Reflection Report (PDF)", data=pdf_bytes, file_name="LMW_Reflection_Report.pdf", mime="application/pdf")
    if st.button("Email me the PDF"):
        try:
            send_pdf(email, pdf_bytes, "LMW_Reflection_Report.pdf", first_name=first_name)
            st.success("Sent! Check your inbox.")
        except Exception as ex:
            st.error(f"Could not send PDF: {ex}")
