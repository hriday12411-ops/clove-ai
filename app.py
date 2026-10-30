import json
import os
from pathlib import Path
import streamlit as st
from groq import Groq

# ==============================================================================
# 🔑 1. API CONFIGURATION
# ==============================================================================
# Paste your working Groq API key (starts with gsk_) between these quotes:
BUILTIN_GROQ_KEY = "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"

# ==============================================================================
# 📱 2. UI SETUP & FUTURISTIC HUD STYLING
# ==============================================================================
st.set_page_config(
    page_title="CLOVER // NEURAL OS",
    page_icon="🍀",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* --- CYBER GRID & AMBIENT MESH BACKGROUND --- */
    .stApp {
        background-color: #030708 !important;
        background-image: 
            radial-gradient(at 0% 0%, rgba(16, 185, 129, 0.18) 0px, transparent 50%),
            radial-gradient(at 100% 100%, rgba(6, 182, 212, 0.14) 0px, transparent 50%),
            linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px) !important;
        background-size: 100% 100%, 100% 100%, 30px 30px, 30px 30px !important;
        color: #f1f5f9;
    }

    /* --- TOP HUD TELEMETRY STRIP --- */
    .hud-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(52, 211, 153, 0.25);
        border-radius: 12px;
        padding: 6px 16px;
        margin-bottom: 20px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        color: #94a3b8;
        box-shadow: 0 0 15px rgba(16, 185, 129, 0.1);
    }
    .hud-item {
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .hud-green {
        color: #34d399;
        font-weight: 700;
    }

    /* --- PULSING CORE BADGE --- */
    .pulse-dot {
        width: 8px;
        height: 8px;
        background-color: #10b981;
        border-radius: 50%;
        box-shadow: 0 0 12px #10b981;
        animation: pulse 1.8s infinite;
    }
    @keyframes pulse {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        70% { transform: scale(1.2); box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    /* --- HERO HOLOGRAPHIC CONTAINER --- */
    .hero-container {
        background: rgba(10, 18, 25, 0.75);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(52, 211, 153, 0.3);
        border-radius: 24px;
        padding: 30px 24px;
        text-align: center;
        margin-bottom: 25px;
        box-shadow: 0 0 35px -10px rgba(16, 185, 129, 0.2), inset 0 0 20px rgba(16, 185, 129, 0.04);
    }
    .hero-title {
        font-size: clamp(26px, 6vw, 38px);
        font-weight: 900;
        letter-spacing: -1px;
        background: linear-gradient(135deg, #ffffff 10%, #6ee7b7 55%, #06b6d4 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 8px;
        text-shadow: 0 0 30px rgba(16, 185, 129, 0.25);
    }
    .hero-subtitle {
        color: #94a3b8;
        font-size: 14px;
        line-height: 1.6;
        max-width: 520px;
        margin: 0 auto;
    }

    /* --- METRIC PILLS --- */
    .metric-row {
        display: flex;
        justify-content: center;
        gap: 10px;
        margin-top: 18px;
        flex-wrap: wrap;
    }
    .metric-chip {
        background: rgba(16, 185, 129, 0.08);
        border: 1px solid rgba(52, 211, 153, 0.25);
        padding: 5px 12px;
        border-radius: 8px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        font-weight: 600;
        color: #a7f3d0;
    }

    /* --- TRANSFORM DEFAULT STREAMLIT BUTTONS INTO GLOWING CARDS --- */
    div[data-testid="stButton"] > button {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.85), rgba(10, 20, 28, 0.95)) !important;
        border: 1px solid rgba(52, 211, 153, 0.28) !important;
        border-radius: 14px !important;
        color: #e2e8f0 !important;
        font-weight: 600 !important;
        font-size: 13.5px !important;
        padding: 14px 18px !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4) !important;
        width: 100% !important;
        text-align: left !important;
    }
    div[data-testid="stButton"] > button:hover {
        transform: translateY(-3px) !important;
        border-color: #34d399 !important;
        box-shadow: 0 0 25px rgba(16, 185, 129, 0.45) !important;
        color: #ffffff !important;
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(15, 23, 42, 0.95)) !important;
    }

    /* --- CHAT MESSAGES WITH NEON EDGES --- */
    .stChatMessage {
        background: rgba(11, 19, 28, 0.75) !important;
        backdrop-filter: blur(14px) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 16px !important;
        padding: 14px 18px !important;
        margin-bottom: 12px !important;
        word-break: break-word;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3) !important;
    }
    [data-testid="stChatMessageAssistant"] {
        border-left: 3px solid #10b981 !important;
        border-top: 1px solid rgba(16, 185, 129, 0.3) !important;
        background: rgba(6, 78, 59, 0.18) !important;
        box-shadow: 0 0 25px rgba(16, 185, 129, 0.12) !important;
    }
    [data-testid="stChatMessageUser"] {
        border-right: 3px solid #06b6d4 !important;
        background: rgba(8, 28, 44, 0.35) !important;
    }

    /* --- GLOWING INPUT BAR --- */
    .stChatInputContainer {
        border-radius: 16px !important;
        border: 1px solid rgba(52, 211, 153, 0.3) !important;
        background: rgba(8, 14, 20, 0.9) !important;
        box-shadow: 0 0 20px rgba(0, 0, 0, 0.6) !important;
    }
    .stChatInputContainer:focus-within {
        border-color: #10b981 !important;
        box-shadow: 0 0 20px rgba(16, 185, 129, 0.35) !important;
    }

    /* --- CLEAN SIDEBAR --- */
    section[data-testid="stSidebar"] {
        background-color: #04080c !important;
        border-right: 1px solid rgba(52, 211, 153, 0.15) !important;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 🧠 3. SYSTEM PROMPT & PEDAGOGICAL BOUNDARIES
# ==============================================================================
SYSTEM_PROMPT = """You are Clover, an all-in-one student life consultant and a close, trusted friend. 
You act like a supportive, brilliant senior schoolmate or study buddy who is always in the student's corner. 
You aren't a corporate AI, a strict teacher, or a boring encyclopedia—you’re a chill peer who gives real, practical advice with zero judgment.

- Tone: Casual, conversational, warm, and encouraging. Use natural phrasing, everyday language, and a friendly vibe.
- Structure: Keep responses punchy, scannable, and easy to read. Use clean bullet points and short paragraphs.
- Empathy First: Always validate feelings first before jumping into study strategy.
- Never Do the Work For Them: Guide them through concepts, do not write complete homework sets.
- Strict: Never give medical or clinical advice.
"""

# ==============================================================================
# 💾 4. PERSISTENT STORAGE & MODEL RESOLUTION
# ==============================================================================
BASE = Path(__file__).parent
HISTORY_DIR = BASE / "students"
try:
    HISTORY_DIR.mkdir(exist_ok=True)
except Exception:
    pass

def load_history(student_slug):
    path = HISTORY_DIR / f"{student_slug}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_history(student_slug, history):
    try:
        path = HISTORY_DIR / f"{student_slug}.json"
        path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except Exception:
        pass

@st.cache_resource
def get_groq_model(_client):
    try:
        raw_models = _client.models.list().data
        chat_models = [
            m.id for m in raw_models 
            if not any(skip in m.id.lower() for skip in ["whisper", "guard", "embed", "distil", "vision"])
        ]
        priority_list = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "llama3-70b-8192",
            "mixtral-8x7b-32768",
            "gemma2-9b-it"
        ]
        for pref in priority_list:
            if pref in chat_models:
                return pref
        for m in chat_models:
            if "llama" in m or "qwen" in m or "gpt" in m:
                return m
        return chat_models[0] if chat_models else "llama-3.3-70b-versatile"
    except Exception:
        return "llama-3.3-70b-versatile"

# ==============================================================================
# ⚙️ 5. SIDEBAR (PROFILE & JUDGE SPECS)
# ==============================================================================
with st.sidebar:
    st.markdown("### 🍀 **CLOVER // SYSTEM**")
    st.caption("Neural Academic Architecture v2.4")

    sidebar_key = st.text_input(
        "Groq API Key (Override):",
        type="password",
        value="",
        placeholder="gsk_...",
        help="Pre-configured by default. Paste here to override."
    )

    st.divider()
    st.markdown("#### 👤 **Active Student Profile**")
    student_name = st.text_input("Profile ID:", value="Hriday Bedi")
    clean_name = student_name.strip().lower().replace(" ", "_") or "guest"

    if st.button("🗑️ Purge Context Cache", use_container_width=True):
        save_history(clean_name, [])
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.markdown("#### ⚙️ **Hardware Telemetry**")
    st.markdown("""
    - **Inference Unit:** Groq LPU™ Silicon
    - **Latency Index:** ~0.22s First-Token
    - **Context Management:** Dynamic Sliding Window
    - **Persistence:** Isolated JSON Data Store
    - **Guardrails:** Pedagogical Anti-Cheat Active
    """)

# Resolve API Key
ACTIVE_API_KEY = sidebar_key.strip() or BUILTIN_GROQ_KEY.strip() or os.environ.get("GROQ_API_KEY", "").strip()

# Initialize session history
if "messages" not in st.session_state or st.session_state.get("current_student") != clean_name:
    st.session_state.current_student = clean_name
    st.session_state.messages = load_history(clean_name)

# ==============================================================================
# 🛰️ 6. TOP TELEMETRY HUD BAR
# ==============================================================================
st.markdown("""
<div class="hud-bar">
    <div class="hud-item">
        <span class="pulse-dot"></span>
        <span>SYS: <span class="hud-green">ONLINE</span></span>
    </div>
    <div class="hud-item">
        <span>INFERENCE: <span class="hud-green">GROQ LPU™</span></span>
    </div>
    <div class="hud-item">
        <span>LATENCY: <span class="hud-green">&lt;0.3s</span></span>
    </div>
</div>
""", unsafe_allow_html=True)

# ==============================================================================
# 🚀 7. HERO INTERFACE & NEON STARTER CARDS
# ==============================================================================
starter_prompt = None

if len(st.session_state.messages) == 0:
    st.markdown("""
    <div class="hero-container">
        <div class="hero-title">Meet Clover.</div>
        <div class="hero-subtitle">
            An advanced AI academic strategist and student life consultant engineered to crush exam burnout, optimize study sprints, and build unbreakable GPA systems.
        </div>
        <div class="metric-row">
            <span class="metric-chip">⚡ LPU ACCELERATED</span>
            <span class="metric-chip">🧠 MULTI-TURN PERSISTENCE</span>
            <span class="metric-chip">🛡️ ANTI-CHEAT GUARDRAILS</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<p style='font-size: 12px; font-weight: 700; color: #34d399; font-family: \"JetBrains Mono\", monospace; text-transform: uppercase; letter-spacing: 1px;'>// Quick Launch Directives</p>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🧪 Emergency Exam Triage\n(3-Day Plan)", use_container_width=True):
            starter_prompt = "I have a tough exam in 3 days and feel unprepared. Walk me through an emergency triage study plan."
        if st.button("🧠 Deep Focus Routine\n(Pomodoro Architecture)", use_container_width=True):
            starter_prompt = "Design a high-retention 3-hour study block routine using Pomodoro that avoids mental fatigue."
    with col2:
        if st.button("😰 Calm Test Anxiety\n(2-Minute Protocol)", use_container_width=True):
            starter_prompt = "I'm experiencing intense test stress right now. Can we do a fast 2-minute calm-down protocol?"
        if st.button("⚡ High-Fuel Study Nutrition\n(Zero Brain-Fog)", use_container_width=True):
            starter_prompt = "What quick snacks and hydration strategy will give me sustained focus without brain fog or sugar crashes?"

# ==============================================================================
# 💬 8. RENDER CHAT HISTORY
# ==============================================================================
for msg in st.session_state.messages:
    role = msg.get("role")
    avatar = "🍀" if role == "assistant" else "👤"
    with st.chat_message(role, avatar=avatar):
        st.markdown(msg.get("content", ""))

# ==============================================================================
# ⚡ 9. CHAT INPUT & LIVE STREAMING PIPELINE (HARDENED)
# ==============================================================================
chat_input = st.chat_input("Input directives (e.g., 'Make a chemistry review schedule')...")
user_prompt = chat_input or starter_prompt

if user_prompt:
    if not ACTIVE_API_KEY or "PASTE_YOUR_GROQ_KEY_HERE" in ACTIVE_API_KEY:
        st.warning("👈 Please enter your Groq API Key in line 14 or the sidebar to unlock Clover.")
    else:
        # Display User Input
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_prompt)

        # Stream Assistant Response
        with st.chat_message("assistant", avatar="🍀"):
            try:
                client = Groq(api_key=ACTIVE_API_KEY)
                active_model = get_groq_model(client)

                payload = [{"role": "system", "content": SYSTEM_PROMPT}]
                payload.extend(st.session_state.messages[-10:])

                stream = client.chat.completions.create(
                    model=active_model,
                    messages=payload,
                    stream=True,
                )

                # Hardened against empty final chunks or unexpected network packets
                def stream_chunks():
                    for chunk in stream:
                        if chunk.choices and len(chunk.choices) > 0:
                            delta = getattr(chunk.choices[0], "delta", None)
                            if delta:
                                content = getattr(delta, "content", None)
                                if content:
                                    yield content

                # Live Word-by-Word Typing
                response_text = st.write_stream(stream_chunks())

                # Commit to Storage
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                save_history(clean_name, st.session_state.messages)

                # Clean transition from hero card to conversation
                if len(st.session_state.messages) == 2:
                    st.rerun()

            except Exception as e:
                st.error(f"Inference Engine Error: {e}")

    
