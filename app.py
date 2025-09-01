
# app_hotfix3.py — Life Minus Work Questionnaire
# - Tiny chart footprint (matches screenshot vibe)
# - Retirement-relevant mini report (not generic wellness)
# - First-name capture
# - Email secrets mapping (GMAIL_* or EMAIL_*)
# - OpenAI Responses call WITHOUT response_format (avoids SDK mismatch)
# - Google Sheets logging (append)
# - PDF output fixed for fpdf 1.x: output(dest="S").encode("latin-1")
# - Unicode sanitizer for PDF text
# - Rich full report (AI-powered if key present; rule-based fallback)

import os, io, json, random, smtplib, ssl, importlib.util
from datetime import datetime, timezone
from email.message import EmailMessage

import streamlit as st
import matplotlib.pyplot as plt
from fpdf import FPDF

# ---------------- Page & helpers ----------------
st.set_page_config(page_title="Life Minus Work — Readiness Check", page_icon="🧭", layout="wide")

def sget(k, default=""):
    try:
        if k in st.secrets: return st.secrets[k]
    except Exception:
        pass
    return os.getenv(k, default)

# Email secrets (supports both key styles)
EMAIL_SENDER = sget("GMAIL_USER") or sget("EMAIL_SENDER")
EMAIL_APP_PASSWORD = sget("GMAIL_APP_PASSWORD") or sget("EMAIL_APP_PASSWORD")
SENDER_NAME = sget("SENDER_NAME","Life Minus Work")
REPLY_TO = sget("REPLY_TO", EMAIL_SENDER)

# OpenAI
AI_MODEL = sget("OPENAI_HIGH_MODEL","gpt-5-mini")
MAX_TOK = int(sget("MAX_OUTPUT_TOKENS_HIGH", "8000") or "8000")
_HAS_OPENAI=False
_client=None
try:
    from openai import OpenAI
    _client = OpenAI()
    _HAS_OPENAI = bool(sget("OPENAI_API_KEY"))
except Exception:
    _client=None
    _HAS_OPENAI=False

def ai_json(prompt: str, max_tokens: int = 1400) -> dict:
    """Best-effort JSON from OpenAI; returns {} on failure. No response_format used."""
    if not (_HAS_OPENAI and _client): return {}
    try:
        resp = _client.responses.create(model=AI_MODEL, input=prompt, max_output_tokens=max_tokens)
        text = getattr(resp, "output_text", "") or ""
        return json.loads(text) if text.strip().startswith("{") else {}
    except Exception:
        return {}

# Google Sheets
LW_SHEET_URL = sget("LW_SHEET_URL","").strip()
LW_SHEET_WORKSHEET = sget("LW_SHEET_WORKSHEET","emails").strip()

def gsheets_enabled() -> bool:
    try:
        return bool(st.secrets.get("gcp_service_account")) and bool(LW_SHEET_URL)
    except Exception:
        return False

@st.cache_resource(show_spinner=False)
def _get_ws():
    if not gsheets_enabled(): return None
    import gspread
    sa = st.secrets["gcp_service_account"]
    gc = gspread.service_account_from_dict(sa)
    sh = gc.open_by_url(LW_SHEET_URL)
    try:
        ws = sh.worksheet(LW_SHEET_WORKSHEET)
    except Exception:
        ws = sh.add_worksheet(title=LW_SHEET_WORKSHEET, rows=4000, cols=10)
        ws.update("A1:F1", [["email","first_name","verified_at","scores","overall","source"]])
    return ws

def log_email_capture(email: str, first_name: str, scores: dict, overall: int, source:str):
    try:
        ws = _get_ws()
        if ws:
            ws.append_row(
                [(email or "").lower().strip(), (first_name or "").strip(),
                 datetime.now(timezone.utc).isoformat(), json.dumps(scores), overall, source],
                value_input_option="USER_ENTERED"
            )
    except Exception as e:
        st.warning(f"(Sheets capture failed: {e})")

# Email
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

# Questionnaire
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

# Mini (retirement-focused)
RETIREMENT_MINI_DEFAULTS = {
    "tiny_actions":[
        "Write down your top 3 hopes for life after work.",
        "List one skill or hobby you’ll grow into your weekly routine.",
        "Message one retired friend and ask for a practical tip that helped them.",
    ],
    "teaser":[
        "Mon: Sketch your ‘ideal post‑work day’ in 5 lines.",
        "Tue: Choose 2 identities to strengthen (e.g., mentor, maker, explorer).",
        "Wed: Try one activity that mimics your future routine (class, volunteering, group).",
    ],
    "unlock":[
        "1‑month Future Snapshot of your retirement life.",
        "Personalized insights on purpose & identity after work.",
        "Action steps + If‑Then plan to ease your transition.",
        "Printable readiness checklist + progress tracker.",
    ]
}

def build_mini_copy(first_name: str, scores: dict):
    top3 = [k for k,_ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:3]]
    greeting = f"Hi {first_name}," if first_name else "Hi there,"
    return {
        "headline": f"{greeting} your strongest areas are {', '.join(LABELS.get(k,k) for k in top3)}.",
        **RETIREMENT_MINI_DEFAULTS
    }

# Rich full report (AI if available, else rule-based)
def ai_full_report(first_name: str, scores: dict, total: int) -> dict:
    schema = """Return strict JSON with keys:
    archetype, core_need, signature_metaphor, signature_sentence,
    insights, why_now, future_snapshot,
    signature_strengths[], energizers[], drainers[], hidden_tensions[],
    watchout, actions[], if_then[], one_week_plan[]"""
    prompt = (
        "Create a retirement‑readiness Reflection Report in the Life Minus Work voice. "
        f"First name: {first_name or 'friend'}. Overall: {total}/10. "
        f"Theme scores: {json.dumps(scores)}. "
        "Be warm, practical and specific to life after work. " + schema
    )
    return ai_json(prompt, max_tokens=min(2400, MAX_TOK//3))

def rule_based_full_report(first_name: str, scores: dict, total: int) -> dict:
    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    low = sorted(scores.items(), key=lambda kv: kv[1])
    top_names = [LABELS.get(k,k) for k,_ in top[:2]]
    low_names = [LABELS.get(k,k) for k,_ in low[:2]]
    return {
        "archetype": "Intentional Pathfinder",
        "core_need": "Clarity of identity beyond work and a rhythm that sustains energy.",
        "signature_metaphor": "A well-marked coastal path: steady, scenic, with room for detours.",
        "signature_sentence": f"I choose a clear, energizing rhythm after work, anchored by {top_names[0]} and {top_names[1]}.",
        "insights": (
            f"Your strengths in {', '.join(top_names)} provide a stable base. "
            f"To round out readiness, gently lift {', '.join(low_names)} with small, testable steps."
        ),
        "why_now": "Transitions stick when started early and practiced in small cycles. This month is for light experiments you can keep.",
        "future_snapshot": (
            f"Hi {first_name or 'there'} — one month from now, mornings start with a brief ritual, "
            "your week has one standing social touchpoint and a learning block you look forward to. "
            "You’ve sampled a low‑stakes contribution and it felt good to be useful."
        ),
        "signature_strengths": ["Reliability", "Willingness to learn", "Boundary sense", "Follow‑through"],
        "energizers": ["Meaningful 1:1 connections", "Short focused sessions", "Clear weekly anchors"],
        "drainers": ["Vague commitments", "Overscheduling", "Social small talk without depth"],
        "hidden_tensions": [
            "Freedom vs structure", "Helping others vs overcommitting",
            "Comfort with routine vs desire for novelty"
        ],
        "watchout": "Don’t let a love of calm become a reason to avoid tiny, useful risks.",
        "actions": [
            "Pick a weekly anchor: one social, one learning block.",
            "Choose a micro‑contribution (30–60 min) you can repeat.",
            "Name 2 identities to strengthen and put one small rep on the calendar."
        ],
        "if_then": [
            "If a request feels fuzzy, then ask for a clear why/when before saying yes.",
            "If energy dips, then shorten the session and finish with a visible win.",
            "If you skip a day, then restart with your smallest anchor next morning."
        ],
        "one_week_plan": [
            "Day 1: Draft your ideal post‑work day; pick 2 weekly anchors.",
            "Day 2: Schedule the first anchor and invite one person.",
            "Day 3: Add a 30‑minute learning block on a topic you enjoy.",
            "Day 4: Do one micro‑contribution; note how it felt.",
            "Day 5: Light adventure (new place or group) for 30 minutes.",
            "Day 6: Review energy; tweak anchors for next week.",
            "Day 7: Celebrate one small win; set the next week."
        ],
    }

# PDF utilities (unicode-safe for fpdf 1.x)
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
    pdf.set_font("Helvetica",style,size); pdf.multi_cell(0,6,to_latin1(text or ""))

def build_pdf(first_name, scores, overall_score, data:dict) -> bytes:
    pdf=PDF(); pdf.set_auto_page_break(True,18); pdf.add_page()
    _p(pdf, f"Hi {first_name or 'there'},",12)
    _p(pdf, "Here’s a calm snapshot of your non‑financial readiness for life after work.",11)
    pdf.ln(2); pdf.set_font("Helvetica","B",13); pdf.cell(0,8,to_latin1("Scores at a glance"),ln=1)
    _p(pdf, f"Overall readiness: {overall_score}/10",11)
    for k,v in scores.items(): _p(pdf, f"{LABELS.get(k,k)}: {v}/10",11)

    if data:
        def sec(title, body):
            pdf.ln(1); pdf.set_font("Helvetica","B",13); pdf.cell(0,8,to_latin1(title),ln=1)
            _p(pdf, body, 11)

        sec("Archetype", data.get("archetype",""))
        sec("Core Need", data.get("core_need",""))
        sec("Signature Metaphor", data.get("signature_metaphor",""))
        sec("Signature Sentence", data.get("signature_sentence",""))
        sec("Insights", data.get("insights",""))
        sec("Why Now", data.get("why_now",""))
        sec("Future Snapshot (1 month)", data.get("future_snapshot",""))

        def list_block(title, items):
            if items:
                pdf.ln(1); pdf.set_font("Helvetica","B",13); pdf.cell(0,8,to_latin1(title), ln=1)
                for it in items: _p(pdf, f"• {it}", 11)
        list_block("Signature Strengths", data.get("signature_strengths"))
        list_block("Energizers", data.get("energizers"))
        list_block("Drainers", data.get("drainers"))
        list_block("Hidden Tensions", data.get("hidden_tensions"))
        sec("Watch‑out", data.get("watchout",""))
        list_block("3 Next‑step Actions (7 days)", data.get("actions"))
        list_block("Implementation Intentions (If‑Then)", data.get("if_then"))
        list_block("1‑Week Gentle Plan", data.get("one_week_plan"))

    # fpdf 1.x: return as bytes string
    return pdf.output(dest="S").encode("latin-1")

# ---------------- UI ----------------
st.title("Life Minus Work — Readiness Check")
first_name = st.text_input("Your first name (optional; used to personalize your report)")

if "answers" not in st.session_state:
    st.session_state.answers = {t:[5]*len(QUESTIONS[t]) for t in THEMES}

for t in THEMES:
    st.subheader(t)
    for i,q in enumerate(QUESTIONS[t]):
        st.session_state.answers[t][i] = st.slider(q,0,10,st.session_state.answers[t][i],1, key=f"{t}:{i}")

scores = compute_scores(st.session_state.answers); total = overall(scores)

# Mini Report — smaller chart
st.divider()
st.subheader("Your Mini Report (Preview)")
top3 = [k for k,_ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:3]]
st.caption("Top strengths right now: " + ", ".join(LABELS.get(k,k) for k in top3))

fig, ax = plt.subplots(figsize=(3.8,1.8), dpi=110)  # significantly smaller
ax.bar([LABELS.get(k,k) for k in THEMES],[scores.get(k,0) for k in THEMES])
ax.set_ylim(0,10); ax.set_title("Theme Snapshot"); plt.xticks(rotation=35, ha="right")
st.pyplot(fig, use_container_width=False)  # don't stretch to container width

mini = build_mini_copy(first_name, scores)
left, right = st.columns([1.2, 1])
with left:
    st.markdown("**Tiny actions to try this week:**")
    for b in mini["tiny_actions"]: st.write(f"- {b}")
    st.markdown("**Your next 7 days (teaser):**")
    for b in mini["teaser"]: st.write(f"- {b}")
with right:
    st.markdown("**What you’ll unlock with the full report:**")
    for b in mini["unlock"]: st.write(f"- {b}")

# Verify + unlock
st.divider()
st.header("Unlock your complete Reflection Report")
email = st.text_input("Your email", placeholder="you@example.com")
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
                log_email_capture(e, first_name, scores, total, source="request-code")
                st.success(f"We’ve emailed a code to {e}.")
            except Exception as ex:
                st.error(f"Could not send email: {ex}")
with cB:
    v=st.text_input("Verification code", max_chars=6)
    if st.button("Verify"):
        if v.strip()==st.session_state.sent_code:
            st.session_state.verified=True
            log_email_capture(email, first_name, scores, total, source="verify")
            st.success("Verified!")
        else:
            st.error("That code doesn’t match.")

# Full report download/email
if st.session_state.verified:
    ai_data = ai_full_report(first_name, scores, total) if _HAS_OPENAI else {}
    if not ai_data:
        ai_data = rule_based_full_report(first_name, scores, total)
    pdf_bytes = build_pdf(first_name, scores, total, ai_data)
    st.download_button("📄 Download your Reflection Report (PDF)", data=pdf_bytes, file_name="LMW_Reflection_Report.pdf", mime="application/pdf")
    if st.button("Email me the PDF"):
        try:
            send_pdf(email, pdf_bytes, "LMW_Reflection_Report.pdf", first_name=first_name)
            st.success("Sent! Check your inbox.")
        except Exception as ex:
            st.error(f"Could not send PDF: {ex}")
