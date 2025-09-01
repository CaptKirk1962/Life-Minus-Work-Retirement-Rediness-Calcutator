# Life Minus Work — Retirement Readiness Report (fpdf 1.x)
# - Small top-left logo; body starts lower to avoid overlap
# - Horizontal bar charts (page + PDF), subtle grid
# - Bold **If** / **Then** in Implementation Intentions
# - Signature Week + Progress Tracker render cleanly (no {...})
# - Footer disclaimer on every page
# - Hardened text handling (lists/dicts/strings) for PDF
# - Gmail app-password email + Google Sheets logging
# - OpenAI Responses API (no response_format) with robust parsing + fallback

import os, io, json, random, smtplib, ssl, tempfile
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Dict, List

import streamlit as st
import matplotlib.pyplot as plt
from fpdf import FPDF
from PIL import Image

# ------------------------------ Page & Secrets ------------------------------
st.set_page_config(page_title="Life Minus Work — Retirement Readiness", page_icon="🧭", layout="wide")

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
_HAS_OPENAI=False
_client=None
try:
    from openai import OpenAI
    _client = OpenAI()
    _HAS_OPENAI = bool(sget("OPENAI_API_KEY"))
except Exception:
    _client=None
    _HAS_OPENAI=False

def _parse_response_text(resp) -> str:
    text = getattr(resp, "output_text", "") or ""
    if text:
        return text
    try:
        parts=[]
        for o in getattr(resp, "output", []):
            for c in getattr(o, "content", []):
                t = getattr(c, "text", None) or getattr(c, "output_text", None)
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    except Exception:
        return ""

def ai_json(prompt: str, max_tokens: int = 2400) -> dict:
    if not (_HAS_OPENAI and _client): return {}
    try:
        resp = _client.responses.create(model=AI_MODEL, input=prompt, max_output_tokens=max_tokens)
        text = _parse_response_text(resp)
        if not text: return {}
        if "{" in text and "}" in text:
            text = text[text.find("{"):text.rfind("}")+1]
        return json.loads(text)
    except Exception:
        return {}

# ------------------------------ Google Sheets ------------------------------
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
        ws.update("A1:G1", [["email","first_name","verified_at","scores","overall","source","note"]])
    return ws

def log_email_capture(email: str, first_name: str, scores: dict, overall: int, source:str, note:str=""):
    try:
        ws = _get_ws()
        if ws:
            ws.append_row(
                [(email or "").lower().strip(), (first_name or "").strip(),
                 datetime.now(timezone.utc).isoformat(), json.dumps(scores), overall, source, note],
                value_input_option="USER_ENTERED"
            )
    except Exception as e:
        st.warning(f"(Sheets capture failed: {e})")

# ------------------------------ Email ------------------------------
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
    msg["Subject"] = "Your Life Minus Work — Retirement Readiness Report (PDF)"
    hello = f"Hi {first_name}," if first_name else "Hi there,"
    msg.set_content(f"{hello}\n\nAttached is your Retirement Readiness Report (PDF).\n\n— Life Minus Work")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)
    _smtp_send(msg)

# ------------------------------ Questionnaire ------------------------------
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
        "I have a clear sense of purpose for my post-work life.",
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
        "I try new places, experiences, or micro-adventures regularly.",
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
    "Purpose & Identity":"Identity",
    "Social Health & Community Connection":"Connection",
    "Health & Vitality":"Vitality",
    "Learning & Growth":"Growth",
    "Adventure & Exploration":"Adventure",
    "Giving Back":"Contribution",
}

def compute_scores(responses: dict) -> dict:
    scores={}
    for t,vals in responses.items():
        scores[t]=int(round(sum(vals)/len(vals))) if vals else 0
    return scores

def overall(scores: dict) -> int:
    return int(round(sum(scores.values())/max(1,len(scores))))

# ------------------------------ Mini (retirement-focused) ------------------------------
RETIREMENT_MINI_DEFAULTS = {
    "tiny_actions":[
        "Write down your top 3 hopes for life after work.",
        "List one skill or hobby you’ll grow into your weekly routine.",
        "Message one retired friend and ask for a practical tip that helped them.",
    ],
    "teaser":[
        "Mon: Sketch your ‘ideal post-work day’ in 5 lines.",
        "Tue: Choose 2 identities to strengthen (e.g., mentor, maker, explorer).",
        "Wed: Try one activity that mimics your future routine (class, volunteering, group).",
    ],
    "unlock":[
        "1-month Future Snapshot of your retirement life.",
        "Personalized insights on purpose & identity after work.",
        "Action steps + If-Then plan to ease your transition.",
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

# ------------------------------ AI Full Report & Fallback ------------------------------
def ai_full_report(first_name: str, scores: dict, total: int, user_words: str) -> dict:
    schema = """Return strict JSON with keys:
    archetype, core_need, signature_metaphor, signature_sentence,
    top_themes[], theme_snapshot{theme->score},
    from_your_words, what_this_says,
    insights, why_now, future_snapshot,
    signature_strengths[], energizers[], drainers[], hidden_tensions[],
    watchout, actions[], if_then[], one_week_plan[],
    balancing_opportunity, keep_in_view[], signature_week[], tiny_progress_tracker[]"""
    prompt = (
        "Create a RETIREMENT READINESS report (emotional & mental preparedness) in the Life Minus Work voice. "
        f"First name: {first_name or 'friend'}. Overall: {total}/10. "
        f"Theme scores: {json.dumps(scores)}. "
        f"From user words (optional): {user_words or ''}. "
        "Warm, practical, respectful. Avoid financial advice. " + schema
    )
    return ai_json(prompt, max_tokens=min(4000, MAX_TOK//2))

def rule_based_full_report(first_name: str, scores: dict, total: int, user_words: str) -> dict:
    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    low = sorted(scores.items(), key=lambda kv: kv[1])
    top_names = [LABELS.get(k,k) for k,_ in top[:3]]
    low_names = [LABELS.get(k,k) for k,_ in low[:2]]
    return {
        "archetype": "Grounded Pathfinder",
        "core_need": "Clarity of identity beyond work and steady weekly anchors.",
        "signature_metaphor": "A lighthouse on a protected shore: steady, visible, guiding without haste.",
        "signature_sentence": f"I choose a calm, clear rhythm after work, anchored by {top_names[0]} and {top_names[1]}.",
        "top_themes": top_names,
        "theme_snapshot": {LABELS.get(k,k): v for k,v in scores.items()},
        "from_your_words": (user_words or "—"),
        "what_this_says": (
            f"Strong {', '.join(top_names)} form a stable base. "
            f"Gently lift {', '.join(low_names)} with low-risk experiments to round out readiness."
        ),
        "insights": "Use identity as anchor, connection for accountability, and vitality to power consistent small moves.",
        "why_now": "Transitions stick when started early and practiced in small cycles you can keep.",
        "future_snapshot": (
            f"Hi {first_name or 'there'} — a month from now you have one weekly social anchor, "
            "a learning block you enjoy, and a small way you contribute that feels useful."
        ),
        "signature_strengths": ["Reliability","Discernment","Boundary sense","Follow-through"],
        "energizers": ["Meaningful 1:1 connections","Short focused sessions","Clear weekly anchors"],
        "drainers": ["Vague commitments","Overscheduling","Low-meaning social time"],
        "hidden_tensions": ["Freedom vs structure","Helping vs overcommitting","Comfort vs growth"],
        "watchout": "Don’t let calm become avoidance of tiny useful risks.",
        "actions": [
            "Pick two weekly anchors: one social, one learning.",
            "Choose one micro-contribution (30–60 min).",
            "Name two identities to strengthen; schedule one small rep."
        ],
        "if_then": [
            "If a request feels fuzzy, then ask for a clear why/when before yes.",
            "If energy dips, then shorten the session and finish with a visible win.",
            "If you skip a day, then restart with your smallest anchor next morning."
        ],
        "one_week_plan": [
            "Day 1: Draft your ideal post-work day; pick anchors.",
            "Day 2: Schedule the first anchor; invite one person.",
            "Day 3: Add a 30-minute learning block.",
            "Day 4: Do a micro-contribution; note how it felt.",
            "Day 5: Light exploration (new place/group) for 30 minutes.",
            "Day 6: Review energy; tweak anchors.",
            "Day 7: Celebrate a small win; set next week."
        ],
        "balancing_opportunity": f"Lift {', '.join(low_names)} with tiny, low-cost experiments aligned to your values.",
        "keep_in_view": ["One-sentence mission","Top 3 values","Morning ritual","One true yes","Boundary checklist","Weekly review"],
        "signature_week": [
            {"day":"Monday","focus":"Health + Connection","plan":"Morning walk, midday call; evening light reading."},
            {"day":"Tuesday","focus":"Learning","plan":"30-minute short course or book; try a new healthy recipe."},
            {"day":"Wednesday","focus":"Purpose Project","plan":"90 minutes on a hands-on project tied to identity."},
            {"day":"Thursday","focus":"Social","plan":"Attend a local class/group; introduce yourself to one person."},
            {"day":"Friday","focus":"Restorative","plan":"Gentle movement + intentional call with family/friend."},
            {"day":"Saturday","focus":"Adventure","plan":"Half-day outing: hike, museum, nearby town."},
            {"day":"Sunday","focus":"Reflection & Planning","plan":"Short journaling; plan next week’s small goals."}
        ],
        "tiny_progress_tracker": [
            {"metric":"Minutes of movement per day","target":"20–40"},
            {"metric":"Social touchpoints per week","target":"2"},
            {"metric":"Learning sessions per week","target":"3 × 30 minutes"},
            {"metric":"Micro-adventures per month","target":"1"},
            {"metric":"Daily mood rating","target":"1–5 (note one quick reason)"},
            {"metric":"One purposeful accomplishment per week","target":"1 (small project or meaningful outreach)"}
        ]
    }

# ------------------------------ Normalizers & PDF tools ------------------------------
LOGO_PATH = "Life-Minus-Work-Logo.webp"  # expected in app working dir

def _as_text(x) -> str:
    if x is None: return ""
    if isinstance(x, (list, tuple)): return "\n".join(f"• {str(item)}" for item in x if item is not None)
    if isinstance(x, dict):
        try: return json.dumps(x, ensure_ascii=False, indent=2)
        except Exception: return str(x)
    return str(x)

def to_latin1(s) -> str:
    s = _as_text(s)
    if not s: return ""
    rep = {"—":"-", "–":"-", "-":"-", "“":'"', "”":'"', "‘":"'", "’":"'", "…":"...", "•":"- ", "\xa0":" ", "→":"->"}
    for a, b in rep.items(): s = s.replace(a, b)
    return s.encode("latin-1", "ignore").decode("latin-1")

def normalize_report(data: dict) -> dict:
    defaults = {
        "archetype":"", "core_need":"", "signature_metaphor":"", "signature_sentence":"",
        "top_themes":[], "theme_snapshot":{},
        "from_your_words":"", "what_this_says":"",
        "insights":"", "why_now":"", "future_snapshot":"",
        "signature_strengths":[], "energizers":[], "drainers":[], "hidden_tensions":[],
        "watchout":"", "actions":[], "if_then":[], "one_week_plan":[],
        "balancing_opportunity":"", "keep_in_view":[], "signature_week":[], "tiny_progress_tracker":[]
    }
    out = defaults.copy()
    if isinstance(data, dict): out.update({k:v for k,v in data.items() if k in out})
    # keep list items as-is (don’t stringify dicts; we have custom renderers)
    for k in ["top_themes","signature_strengths","energizers","drainers","hidden_tensions",
              "actions","if_then","one_week_plan","keep_in_view","signature_week","tiny_progress_tracker"]:
        v = out.get(k, [])
        if isinstance(v, str): out[k] = [v]
        elif isinstance(v, (list, tuple)): out[k] = list(v)
        else: out[k] = []
    # allow strings OR lists (renderer handles both)
    for k in ["archetype","core_need","signature_metaphor","signature_sentence",
              "from_your_words","what_this_says","insights","why_now","future_snapshot",
              "watchout","balancing_opportunity"]:
        if out.get(k) is None: out[k] = ""
    # snapshot dict
    ts = out.get("theme_snapshot", {})
    if not isinstance(ts, dict): ts = {}
    out["theme_snapshot"] = {str(k): int(v) if isinstance(v, (int,float)) else v for k,v in ts.items()}
    return out

class PDF(FPDF):
    def header(self):
        # Small logo at top-left on first page
        if getattr(self, "_on_first_page", True):
            try:
                if os.path.exists(LOGO_PATH):
                    with Image.open(LOGO_PATH) as im:
                        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                        im.convert("RGBA").save(tmp.name, format="PNG")
                        self.image(tmp.name, x=10, y=8, w=24)  # smaller, left
            except Exception:
                pass
            self._on_first_page = False
        # Title (centered)
        self.set_y(8)
        self.set_font("Helvetica","B",16)
        self.cell(0,10,to_latin1("Life Minus Work — Retirement Readiness Report"),ln=1,align="C")

    def footer(self):
        self.set_y(-18)
        self.set_font("Helvetica","",7)
        disclaimer = "Life Minus Work • This report is a starting point for reflection. Nothing here is medical or financial advice."
        self.multi_cell(0,4,to_latin1(disclaimer), align="C")
        self.set_y(-10)
        self.set_font("Helvetica","",8)
        self.cell(0,8,to_latin1("© Life Minus Work • lifeminuswork.com"),align="C")

def _p(pdf, text, size=11, style=""):
    pdf.set_font("Helvetica", style, size)
    pdf.multi_cell(0, 6, to_latin1(text))

def sec(pdf, title, body):
    pdf.set_font("Helvetica","B",13)
    pdf.cell(0, 8, to_latin1(title), ln=1)
    _p(pdf, body, 11)

def list_block(pdf, title, items):
    if not items: return
    if not isinstance(items, (list, tuple)): items = [items]
    pdf.set_font("Helvetica","B",13)
    pdf.cell(0, 8, to_latin1(title), ln=1)
    for it in items: _p(pdf, f"• {it}", 11)

def _write_if_then(pdf, item):
    # Accept dict {'if':..., 'then':...} or a string
    if isinstance(item, dict):
        if_text = str(item.get("if","")).strip()
        then_text = str(item.get("then","")).strip()
        s = f"If {if_text} then {then_text}"
    else:
        s = str(item or "")
    low = s.lower()
    if not low.startswith("if "):
        _p(pdf, f"• {s}", 11)
        return
    idx = low.find(" then ")
    if idx == -1:
        pdf.set_font("Helvetica","",11)
        pdf.cell(5,6,to_latin1("• "), ln=0)
        pdf.set_font("Helvetica","B",11); pdf.write(6, to_latin1("If"))
        pdf.set_font("Helvetica","",11); pdf.write(6, to_latin1(s[2:]))
        pdf.ln(6); return
    before = s[3:idx]; after = s[idx+6:]
    pdf.set_font("Helvetica","",11); pdf.cell(5,6,to_latin1("• "), ln=0)
    pdf.set_font("Helvetica","B",11); pdf.write(6, to_latin1("If"))
    pdf.set_font("Helvetica","",11); pdf.write(6, to_latin1(" " + before + " "))
    pdf.set_font("Helvetica","B",11); pdf.write(6, to_latin1("Then"))
    pdf.set_font("Helvetica","",11); pdf.write(6, to_latin1(" " + after))
    pdf.ln(6)

def list_block_if_then(pdf, title, items):
    if not items: return
    if not isinstance(items, (list, tuple)): items = [items]
    pdf.set_font("Helvetica","B",13)
    pdf.cell(0, 8, to_latin1(title), ln=1)
    for it in items: _write_if_then(pdf, it)

def list_block_signature_week(pdf, title, items):
    if not items: return
    if not isinstance(items, (list, tuple)): items = [items]
    pdf.set_font("Helvetica","B",13); pdf.cell(0,8,to_latin1(title), ln=1)
    for it in items:
        if isinstance(it, dict):
            day = it.get("day",""); focus = it.get("focus",""); plan = it.get("plan","")
            _p(pdf, f"• {day} — {focus}: {plan}", 11)
        else:
            _p(pdf, f"• {it}", 11)

def list_block_progress_tracker(pdf, title, items):
    if not items: return
    if not isinstance(items, (list, tuple)): items = [items]
    pdf.set_font("Helvetica","B",13); pdf.cell(0,8,to_latin1(title), ln=1)
    for it in items:
        if isinstance(it, dict):
            m = it.get("metric",""); t = it.get("target","")
            _p(pdf, f"• {m} — {t}", 11)
        else:
            _p(pdf, f"• {it}", 11)

def _scores_chart_png(theme_scores: Dict[str,int]) -> str:
    labels = list(theme_scores.keys()); values = [theme_scores[k] for k in labels]
    fig, ax = plt.subplots(figsize=(4.0,1.6), dpi=140)
    ax.barh(labels, values)
    ax.set_xlim(0,10); ax.grid(axis="x", alpha=0.3)
    for spine in ["top","right"]: ax.spines[spine].set_visible(False)
    ax.set_title("Theme Snapshot"); plt.tight_layout()
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    fig.savefig(tmp.name, bbox_inches="tight", dpi=140); plt.close(fig)
    return tmp.name

def build_pdf(first_name: str, scores: dict, overall_score: int, data:dict) -> bytes:
    data = normalize_report(data)
    pdf=PDF(); pdf.set_auto_page_break(True,18); pdf.add_page()
    pdf.set_y(42)  # <-- start body lower so nothing overlaps the logo/title

    _p(pdf, f"Hi {first_name or 'there'},",12)
    _p(pdf, "Here’s a calm snapshot of your emotional and mental readiness for life after work.",11)
    pdf.ln(2)

    sec(pdf, "Archetype", data["archetype"])
    sec(pdf, "Core Need", data["core_need"])
    sec(pdf, "Signature Metaphor", data["signature_metaphor"])
    sec(pdf, "Signature Sentence", data["signature_sentence"])

    pdf.ln(1); pdf.set_font("Helvetica","B",13); pdf.cell(0,8,to_latin1("Scores at a glance"),ln=1)
    _p(pdf, f"Overall readiness: {overall_score}/10",11)
    for k,v in scores.items(): _p(pdf, f"{LABELS.get(k,k)}: {v}/10",11)

    try:
        snap = {LABELS.get(k,k): v for k,v in scores.items()}
        png = _scores_chart_png(snap)
        if png and os.path.exists(png):
            pdf.ln(1); pdf.image(png, w=160)
    except Exception:
        pass

    if data.get("from_your_words"): sec(pdf, "From your words", data["from_your_words"])
    if data.get("what_this_says"):  sec(pdf, "What this really says about you", data["what_this_says"])

    sec(pdf, "Insights", data["insights"])
    sec(pdf, "Why Now", data["why_now"])
    sec(pdf, "Future Snapshot (1 month)", data["future_snapshot"])

    list_block(pdf, "Signature Strengths", data["signature_strengths"])
    list_block(pdf, "Energizers", data["energizers"])
    list_block(pdf, "Drainers", data["drainers"])
    list_block(pdf, "Hidden Tensions", data["hidden_tensions"])
    sec(pdf, "Watch-out (gentle blind spot)", data["watchout"])

    list_block(pdf, "3 Next-step Actions (7 days)", data["actions"])
    list_block_if_then(pdf, "Implementation Intentions (If–Then)", data["if_then"])
    list_block(pdf, "1-Week Gentle Plan", data["one_week_plan"])

    if data.get("balancing_opportunity"):
        sec(pdf, "Balancing Opportunity", data["balancing_opportunity"])
    list_block(pdf, "Keep This In View", data["keep_in_view"])
    list_block_signature_week(pdf, "Signature Week — At a glance", data["signature_week"])
    list_block_progress_tracker(pdf, "Tiny Progress Tracker", data["tiny_progress_tracker"])

    return pdf.output(dest="S").encode("latin-1")

# ------------------------------ UI ------------------------------
st.title("Life Minus Work — Retirement Readiness (Non-Financial)")
st.caption("A warm, practical check on identity, connection, vitality, learning, adventure, and giving back — no money math.")

first_name = st.text_input("Your first name (used to personalize your report)")
user_words = st.text_area("In your own words (optional): What matters to you about life after work?", height=80)

if "answers" not in st.session_state:
    st.session_state.answers = {t:[5]*len(QUESTIONS[t]) for t in THEMES}

for t in THEMES:
    st.subheader(t)
    for i,q in enumerate(QUESTIONS[t]):
        st.session_state.answers[t][i] = st.slider(q,0,10,st.session_state.answers[t][i],1, key=f"{t}:{i}")

scores = compute_scores(st.session_state.answers); total = overall(scores)

# Mini — compact horizontal bar chart
st.divider()
st.subheader("Your Mini Report (Preview)")
top3 = [k for k,_ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:3]]
st.caption("Top strengths right now: " + ", ".join(LABELS.get(k,k) for k in top3))

fig, ax = plt.subplots(figsize=(3.2,1.6), dpi=120)
vals = [scores.get(k,0) for k in THEMES]; labs = [LABELS.get(k,k) for k in THEMES]
ax.barh(labs, vals); ax.set_xlim(0,10); ax.grid(axis="x", alpha=0.3)
for spine in ["top","right"]: ax.spines[spine].set_visible(False)
ax.set_title("Theme Snapshot")
st.pyplot(fig, use_container_width=False)

mini = build_mini_copy(first_name, scores)
lft, rgt = st.columns([1.2, 1])
with lft:
    st.markdown("**Tiny actions to try this week:**")
    for b in mini["tiny_actions"]: st.write(f"- {b}")
    st.markdown("**Your next 7 days (teaser):**")
    for b in mini["teaser"]: st.write(f"- {b}")
with rgt:
    st.markdown("**What you’ll unlock with the full report:**")
    for b in mini["unlock"]: st.write(f"- {b}")

# Verify + unlock
st.divider()
st.header("Unlock your complete Retirement Readiness Report")
st.caption("We’ll email a 6-digit code to verify it’s really you. No spam—ever.")
st.caption("Heads up: generating your full report is intensive and may take up to a minute.")
email = st.text_input("Your email", placeholder="you@example.com")
if "sent_code" not in st.session_state: st.session_state.sent_code=""
if "verified" not in st.session_state: st.session_state.verified=False

cA,cB = st.columns(2)
with cA:
    if st.button("Email me a 6-digit code"):
        e=(email or "").strip()
        if not e or "@" not in e: st.error("Please enter a valid email.")
        else:
            code="".join(str(random.randint(0,9)) for _ in range(6))
            st.session_state.sent_code=code
            try:
                send_verification_code(e, code, first_name=first_name)
                log_email_capture(e, first_name, scores, total, source="request-code", note=user_words[:120])
                st.success(f"We’ve emailed a code to {e}.")
            except Exception as ex:
                st.error(f"Could not send email: {ex}")
with cB:
    v=st.text_input("Verification code", max_chars=6)
    if st.button("Verify"):
        if v.strip()==st.session_state.sent_code:
            st.session_state.verified=True
            log_email_capture(email, first_name, scores, total, source="verify", note=user_words[:120])
            st.success("Verified!")
        else:
            st.error("That code doesn’t match.")

# Full report
if st.session_state.verified:
    ai_data = ai_full_report(first_name, scores, total, user_words) if _HAS_OPENAI else {}
    if not ai_data:
        ai_data = rule_based_full_report(first_name, scores, total, user_words)
    pdf_bytes = build_pdf(first_name, scores, total, ai_data)
    st.download_button("📄 Download your Retirement Readiness Report (PDF)", data=pdf_bytes,
                       file_name="LMW_Retirement_Readiness_Report.pdf", mime="application/pdf")
    if st.button("Email me the PDF"):
        try:
            send_pdf(email, pdf_bytes, "LMW_Retirement_Readiness_Report.pdf", first_name=first_name)
            st.success("Sent! Check your inbox.")
        except Exception as ex:
            st.error(f"Could not send PDF: {ex}")
