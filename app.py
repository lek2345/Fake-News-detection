import os
import base64
import urllib.parse
from datetime import datetime, timedelta
import streamlit as st
import joblib
import requests
import feedparser
import pandas as pd
import wikipedia
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from googletrans import Translator
import speech_recognition as sr   # ⭐ ADDED

# -------------------------------------------------------
# PAGE SETTINGS
# -------------------------------------------------------
st.set_page_config(page_title="Fake News Detector", page_icon="📰", layout="wide")

# -------------------------------------------------------
# ANIMATED THEME CSS
# -------------------------------------------------------
st.markdown("""
<style>

.stApp {
    background: radial-gradient(circle at top left, #1e293b 0%, #111827 100%);
    color: #f9fafb;
    font-family: 'Inter', sans-serif;
    overflow-x: hidden;
}

/* Fade-in animations */
@keyframes fadeIn { from { opacity:0; transform:translateY(25px);} to { opacity:1; transform:translateY(0);} }
@keyframes fadePop {0%{opacity:0; transform:scale(0.92) translateY(40px);} 100%{opacity:1; transform:scale(1) translateY(0);} }
@keyframes glowPulse {0%{box-shadow:0 0 0px rgba(255,255,255,0);} 100%{box-shadow:0 0 22px rgba(255,255,255,0.3);} }

/* Card styling */
.card {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.12);
    backdrop-filter: blur(14px);
    border-radius: 18px;
    padding: 24px;
    margin-bottom: 20px;
    animation: fadePop 0.9s ease forwards;
}

.result { border-top: 4px solid #22c55e; animation: glowPulse 1.4s ease; }
.related { border-top: 4px solid #eab308; animation: glowPulse 1.4s ease; }
.unverified { border-top: 4px solid #ef4444; animation: glowPulse 1.4s ease; }

/* Badge */
.badge {
    display: inline-block;
    padding: 6px 16px;
    border-radius: 999px;
    font-weight: 600;
    color: white;
    margin-bottom: 12px;
    font-size: 0.9rem;
    animation: fadeIn 1s ease;
}
.badge.green { background:#22c55e; }
.badge.amber { background:#fbbf24; }
.badge.red { background:#ef4444; }

/* Title */
h1.title {
    text-align:center;
    font-size:2.7rem;
    font-weight:700;
    background:linear-gradient(90deg,#60a5fa,#a78bfa);
    -webkit-text-fill-color:transparent;
    -webkit-background-clip:text;
    margin-bottom:0.5rem;
    animation:fadeIn 1.2s ease;
}

/* Buttons */
div.stButton > button {
    background: linear-gradient(90deg,#6366f1,#8b5cf6);
    color:white;
    font-weight:600;
    border-radius: 50px;
    padding: 0.6rem 1.5rem;
    transition:0.3s ease;
    box-shadow:0 4px 16px rgba(99,102,241,0.4);
    animation: fadeIn 1.1s ease;
}

div.stButton > button:hover {
    transform: translateY(-3px) scale(1.03);
    background: linear-gradient(90deg,#8b5cf6,#6366f1);
}

div.stButton > button:active {
    transform: scale(0.96);
    box-shadow:0 0 0 4px rgba(139,92,246,0.4);
}

/* Text area */
textarea {
    background:#ffffff !important;
    color:#000000 !important;
    border:1px solid rgba(255,255,255,0.25) !important;
    border-radius:14px !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background:rgba(17,24,39,0.75);
    border-right:1px solid rgba(255,255,255,0.1);
    backdrop-filter:blur(12px);
    animation:fadeIn 1.1s ease;
}

.footer {
    text-align:center;
    color:#94a3b8;
    margin-top:25px;
    animation:fadeIn 1.2s ease;
}

</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------
# LOAD MODELS
# -------------------------------------------------------
API_KEY = "59cb2b160a264c0a8b2bd742805b09bf"
model = joblib.load("model.pkl")
vectorizer = joblib.load("vectorizer.pkl")
translator = Translator()

if "history" not in st.session_state:
    st.session_state.history = []

if "speech_text" not in st.session_state:
    st.session_state.speech_text = ""

# -------------------------------------------------------
# SPEECH TO TEXT
# -------------------------------------------------------
def convert_speech_to_text():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        st.info("🎙️ Listening... speak now.")
        audio = recognizer.listen(source)
    try:
        text = recognizer.recognize_google(audio)
        st.success("Converted successfully!")
        return text
    except:
        st.error("Could not recognize speech")
        return ""

# -------------------------------------------------------
# KEYWORD EXTRACTION
# -------------------------------------------------------
def extract_keywords(text):
    words = text.lower().split()
    return " ".join([w for w in words if w not in ENGLISH_STOP_WORDS])

# -------------------------------------------------------
# SEARCH FUNCTIONS
# -------------------------------------------------------
def search_newsapi_today(query):
    now = datetime.utcnow()
    last24 = now - timedelta(hours=24)
    url = (
        f"https://newsapi.org/v2/everything?q={query}"
        f"&language=en&from={last24.isoformat()}&to={now.isoformat()}"
        f"&sortBy=publishedAt&apiKey={API_KEY}"
    )
    return requests.get(url).json()

def search_newsapi_all(query):
    url = (
        f"https://newsapi.org/v2/everything?q={query}"
        f"&language=en&sortBy=relevancy&apiKey={API_KEY}"
    )
    return requests.get(url).json()

def search_google_news(query):
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}"
    return feedparser.parse(url).entries

def is_google_news_today(entry):
    try:
        pub = entry.published_parsed
        pub_dt = datetime(*pub[:6])
        return (datetime.utcnow() - pub_dt) < timedelta(hours=24)
    except:
        return False

def fact_check_wikipedia(text):
    try:
        return wikipedia.summary(text, sentences=2)
    except:
        return None

# -------------------------------------------------------
# SAVE TO EXCEL
# -------------------------------------------------------
def save_result_to_excel(text, status, title, url):

    df = pd.DataFrame([{
        "Text": text,
        "Status": status,
        "Headline": title,
        "URL": url,
        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }])

    try:
        old = pd.read_excel("results.xlsx")

        cols_to_drop = ["Confidence", "confidence", "CONFIDENCE"]
        for c in cols_to_drop:
            if c in old.columns:
                old = old.drop(columns=[c], errors="ignore")

        df = pd.concat([old, df], ignore_index=True)

    except:
        pass

    df.to_excel("results.xlsx", index=False)

def download_excel_button():
    if os.path.exists("results.xlsx"):
        with open("results.xlsx","rb") as f:
            data=f.read()
        b64 = base64.b64encode(data).decode()
        st.markdown(
            f'<a href="data:application/octet-stream;base64,{b64}" download="results.xlsx">📥 Download Excel Results</a>',
            unsafe_allow_html=True
        )

# -------------------------------------------------------
# MAIN CHECK FUNCTION
# -------------------------------------------------------
def check_news(text):

    original = text

    # Language detection
    try:
        lang = translator.detect(text).lang
    except:
        lang = "en"

    if lang != "en":
        try:
            text = translator.translate(text, dest="en").text
        except:
            pass

    query = extract_keywords(text)

    # --- NewsAPI Today ---
    today = search_newsapi_today(query)
    today_found = today.get("totalResults",0) > 0

    # --- Google RSS ---
    google = search_google_news(query)
    google_today = [g for g in google if is_google_news_today(g)]
    google_today_found = len(google_today) > 0

    # CASE 1 — NewsAPI Found
    if today_found:
        titles = [a.get("title","") for a in today["articles"]]

        user_vec = vectorizer.transform([text])

        best_score = 0
        best_t, best_u = "", ""

        for a in today["articles"]:
            t = a.get("title","")
            u = a.get("url","")
            score = cosine_similarity(user_vec, vectorizer.transform([t]))[0][0]

            if score > best_score:
                best_score = score
                best_t = t
                best_u = u

        st.markdown('<div class="card result">', unsafe_allow_html=True)
        st.markdown('<span class="badge green">REAL — Found Today</span>', unsafe_allow_html=True)

        st.write("### 🔹 Fresh Headline")
        st.write(best_t)
        st.write(f"[Open Article]({best_u})")

        st.progress(best_score)
        st.write(f"**{round(best_score*100,2)}%**")

        st.markdown("</div>", unsafe_allow_html=True)

        save_result_to_excel(original,"REAL TODAY",best_t,best_u)
        return

    # CASE 2 — Google News Today
    if google_today:
        st.markdown('<div class="card related">', unsafe_allow_html=True)
        st.markdown('<span class="badge amber">REAL : News Found Today</span>', unsafe_allow_html=True)

        for g in google_today[:5]:
            st.write("🔹", g.title)
            st.write("🔗", g.link)

        st.markdown("</div>", unsafe_allow_html=True)

        save_result_to_excel(original, "RELATED TODAY", google_today[0].title, google_today[0].link)
        return

    # CASE 3 — No news found
    st.markdown('<div class="card related">', unsafe_allow_html=True)
    st.markdown('<span class="badge amber">FAKE : No News Found</span>', unsafe_allow_html=True)
    st.write("This topic did NOT appear in any trusted news source today.")
    st.markdown("</div>", unsafe_allow_html=True)

    save_result_to_excel(original,"FAKE TODAY","","")

# -------------------------------------------------------
# UI
# -------------------------------------------------------
st.markdown("<h1 class='title'>📰 Real-Time Fake News Detector</h1>", unsafe_allow_html=True)

st.markdown('<div class="card">', unsafe_allow_html=True)

text_input = st.text_area("Enter News Text", value=st.session_state.speech_text, height=140)

# ⭐ MIC BUTTON — FIXED rerun
if st.button("🎤 Speak"):
    spoken_text = convert_speech_to_text()
    if spoken_text:
        st.session_state.speech_text = spoken_text
        st.rerun()   # ⭐ FIXED

st.markdown('</div>', unsafe_allow_html=True)

mid = st.columns([1,1,1])[1]
with mid:
    run_check = st.button("🔍 Check Now", use_container_width=True)

if run_check:
    if text_input.strip():
        st.session_state.history.append(text_input.strip())
        with st.spinner("Analyzing..."):
            check_news(text_input.strip())
    else:
        st.error("Enter news text")

# History
with st.expander("📜 Search History"):
    for h in reversed(st.session_state.history[-12:]):
        if st.button(f"🔁 {h}"):
            check_news(h)

# Sidebar
with st.sidebar:
    st.header("💾 Export")
    download_excel_button()

st.markdown("<div class='footer'></div>", unsafe_allow_html=True)
