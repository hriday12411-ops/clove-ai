import json
import os
import re
import time
from pathlib import Path
import streamlit as st
from groq import Groq

# ==============================================================================
# 🔑 1. API CONFIGURATION
# ==============================================================================
# Paste your working Groq API key (starts with gsk_) between these quotes:
BUILTIN_GROQ_KEY = "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"

# Page Initialization (Must be first Streamlit command)
st.set_page_config(
    page_title="CLOVER STUDIO // NEURAL FOUNDRY",
    page_icon="🍀",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ==============================================================================
# 💾 2. CORE STORAGE & MODEL AUTO-DETECTION
# ==============================================================================
BASE = Path(__file__).parent
HISTORY_DIR = BASE / "students"
try:
    HISTORY_DIR.mkdir(exist_ok=True)
except Exception:
    pass

def load_history(slug):
    path = HISTORY_DIR / f"{slug}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_history(slug, history):
    try:
        path = HISTORY_DIR / f"{slug}.json"
        path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except Exception:
        pass

@st.cache_resource
def get_groq_model(_client):
    try:
        raw = _client.models.list().data
        chats = [
            m.id for m in raw 
            if not any(skip in m.id.lower() for skip in ["whisper", "guard", "embed", "distil", "vision"])
        ]
        priority = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-70b-8192", "mixtral-8x7b-32768", "gemma2-9b-it"]
        for p in priority:
            if p in chats:
                return p
        for m in chats:
            if "llama" in m or "qwen" in m or "gpt" in m:
                return m
        return chats[0] if chats else "llama-3.3-70b-versatile"
    except Exception:
        return "llama-3.3-70b-versatile"

# ==============================================================================
# ⚙️ 3. SIDEBAR: AGENT STUDIO & COUNTDOWN ENGINE
# ==============================================================================
with st.sidebar:
    st.markdown("### 🛠️ **AGENT STUDIO**")
    st.caption("Autonomous AI Customization Engine")

    persona_mode = st.selectbox(
        "Select AI Archetype:",
        [
            "🍀 Clover (Chill Peer / Anti-Burnout)",
            "⚡ Titan (Discipline & Drill Coach)",
            "🌙 Luna (Calm & Mindfulness Guide)",
            "⚙️ Custom Agent Studio"
        ]
    )

    # Dynamic Persona & Theme Mapping
    if "Clover" in persona_mode:
        ai_name = "Clover"
        ai_avatar = "🍀"
        ai_tagline = "Your chill senior schoolmate and anti-burnout study buddy."
        custom_instructions = "You are Clover, a casual, friendly, empathetic senior student. Use warm phrasing, validate emotions first, and make realistic 3-day recovery study plans."
        theme = {
            "primary": "#10b981",          # Emerald Green
            "accent": "#34d399",
            "ambient1": "rgba(16, 185, 129, 0.22)",
            "ambient2": "rgba(6, 182, 212, 0.14)",
            "assistant_bg": "rgba(6, 78, 59, 0.22)",
            "title_grad": "linear-gradient(135deg, #ffffff 10%, #6ee7b7 55%, #06b6d4 100%)",
            "glow_rgba": "rgba(16, 185, 129, 0.45)"
        }
    elif "Titan" in persona_mode:
        ai_name = "Titan"
        ai_avatar = "⚡"
        ai_tagline = "High-accountability, zero-excuses exam drill coach."
        custom_instructions = "You are Titan, an intense, direct, laser-focused academic drill coach for competitive exams. Push back against procrastination, demand rigorous Pomodoro sprints, and give sharp, bulletproof schedules."
        theme = {
            "primary": "#ef4444",          # Crimson Red
            "accent": "#f87171",
            "ambient1": "rgba(239, 68, 68, 0.25)",
            "ambient2": "rgba(249, 115, 22, 0.16)",
            "assistant_bg": "rgba(127, 29, 29, 0.25)",
            "title_grad": "linear-gradient(135deg, #ffffff 10%, #fca5a5 50%, #f97316 100%)",
            "glow_rgba": "rgba(239, 68, 68, 0.45)"
        }
    elif "Luna" in persona_mode:
        ai_name = "Luna"
        ai_avatar = "🌙"
        ai_tagline = "Calming mindfulness guide for acute test anxiety."
        custom_instructions = "You are Luna, a gentle, soothing, mindfulness-focused study companion. Help students take deep breaths, un-clench their jaws, ground their focus, and approach topics with zero panic."
        theme = {
            "primary": "#3b82f6",          # Sapphire Navy
            "accent": "#60a5fa",
            "ambient1": "rgba(37, 99, 235, 0.26)",
            "ambient2": "rgba(30, 58, 138, 0.40)",
            "assistant_bg": "rgba(30, 58, 138, 0.28)",
            "title_grad": "linear-gradient(135deg, #ffffff 10%, #93c5fd 50%, #3b82f6 100%)",
            "glow_rgba": "rgba(59, 130, 246, 0.45)"
        }
    else:
        st.markdown("##### 🎨 **Design Your Custom Agent:**")
        ai_name = st.text_input("Agent Codename:", value="Athena").strip() or "CustomAI"
        raw_avatar = st.text_input("Agent Avatar Emoji:", value="🦉").strip()
        ai_avatar = raw_avatar if (raw_avatar and len(raw_avatar) <= 2) else "🤖"
        ai_tagline = st.text_input("Agent Purpose:", value="Strategic logic mentor for advanced problem-solving.").strip()
        custom_instructions = st.text_area(
            "Persona & Tone Directives:",
            value="You are Athena, a sharp intellectual mentor who explains tough science topics using historical examples and clear logical deductions."
        )
        theme = {
            "primary": "#a855f7",          # Electric Violet
            "accent": "#c084fc",
            "ambient1": "rgba(168, 85, 247, 0.25)",
            "ambient2": "rgba(236, 72, 153, 0.16)",
            "assistant_bg": "rgba(88, 28, 135, 0.25)",
            "title_grad": "linear-gradient(135deg, #ffffff 10%, #d8b4fe 50%, #ec4899 100%)",
            "glow_rgba": "rgba(168, 85, 247, 0.45)"
        }

    st.divider()
    st.markdown("#### 👤 **Student Workspace**")
    student_name = st.text_input("Active Profile ID:", value="Hriday Bedi")

    # Exam Countdown Tracker
    st.markdown("##### 🎯 **Exam Countdown Tracker**")
    col_a, col_b = st.columns(2)
    with col_a:
        raw_target = st.text_input("Target Exam:", value="Chemistry")
        safe_exam_target = re.sub(r'[^\w\s-]', '', raw_target).strip() or "Exams"
    with col_b:
        exam_days = st.number_input("Days Left:", min_value=1, max_value=365, value=3)

    raw_slug = f"{student_name.strip().lower()}_{ai_name.lower()}"
    clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', raw_slug)

    # Session Utilities & Export
    st.divider()
    st.markdown("#### 📥 **Session Utilities**")
    
    # Initialize session history
    if "messages" not in st.session_state or st.session_state.get("current_profile") != clean_name:
        st.session_state.current_profile = clean_name
        st.session_state.messages = load_history(clean_name)

    if st.session_state.messages:
        export_text = f"=====================================================\n"
        export_text += f"CLOVER OS // EXAM STRATEGY & STUDY ROADMAP\n"
        export_text += f"Student: {student_name}\n"
        export_text += f"Target Subject: {safe_exam_target} (Deadline: {exam_days} Days Remaining)\n"
        export_text += f"Consultant Engine: {ai_name} Core\n"
        export_text += f"=====================================================\n\n"
        for m in st.session_state.messages:
            sender = student_name if m.get("role") == "user" else ai_name
            export_text += f"[{sender}]:\n{m.get('content', '')}\n\n"

        st.download_button(
            label="📥 Download Study Plan (.txt)",
            data=export_text,
            file_name=f"{clean_name}_study_roadmap.txt",
            mime="text/plain",
            use_container_width=True
        )
    else:
        st.caption("💬 Chat with the AI to generate an exportable study roadmap.")

    if st.button("🗑️ Reset Chat History", use_container_width=True):
        save_history(clean_name, [])
        st.session_state.messages = []
        st.rerun()

    st.divider()
    sidebar_key = st.text_input("Groq API Key (Override):", type="password", value="", placeholder="gsk_...")

# ==============================================================================
# 🎨 4. DYNAMIC THEME & MOVING SCANNER LIGHT INJECTION
# ==============================================================================
raw_css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Ambient Dynamic Mesh */
    .stApp {
        background-color: #030708 !important;
        background-image: 
            radial-gradient(at 0% 0%, __AMBIENT1__ 0px, transparent 50%),
            radial-gradient(at 100% 100%, __AMBIENT2__ 0px, transparent 50%),
            linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px) !important;
        background-size: 100% 100%, 100% 100%, 30px 30px, 30px 30px !important;
        color: #f1f5f9;
    }

    /* Top Telemetry HUD Strip with MOVING SCANNER LIGHT */
    .hud-bar {
        position: relative;
        overflow: hidden;
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid __PRIMARY__;
        border-radius: 12px;
        padding: 6px 16px;
        margin-bottom: 20px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        color: #94a3b8;
        box-shadow: 0 0 16px __AMBIENT1__;
    }
    .hud-bar::after {
        content: '';
        position: absolute;
        top: 0; left: -100%; width: 40%; height: 100%;
        background: linear-gradient(90deg, transparent, __PRIMARY__, transparent);
        opacity: 0.45;
        animation: laserScan 3.5s infinite linear;
    }
    @keyframes laserScan {
        0% { left: -100%; }
        100% { left: 200%; }
    }

    .hud-item {
        display: flex;
        align-items: center;
        gap: 6px;
        z-index: 2;
    }
    .hud-accent {
        color: __ACCENT__;
        font-weight: 700;
    }

    /* Pulsing Core Badge */
    .pulse-dot {
        width: 8px;
        height: 8px;
        background-color: __PRIMARY__;
        border-radius: 50%;
        box-shadow: 0 0 12px __PRIMARY__;
        animation: pulse 1.8s infinite;
    }
    @keyframes pulse {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 __AMBIENT1__; }
        70% { transform: scale(1.2); box-shadow: 0 0 0 8px transparent; }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 transparent; }
    }

    /* Hero Container with Neon Pulse */
    .hero-container {
        background: rgba(10, 18, 25, 0.75);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid __PRIMARY__;
        border-radius: 24px;
        padding: 26px 20px;
        text-align: center;
        margin-bottom: 22px;
        animation: neonGlow 4s infinite ease-in-out;
    }
    @keyframes neonGlow {
        0%, 100% { box-shadow: 0 0 25px -8px __GLOW__; }
        50% { box-shadow: 0 0 45px 2px __GLOW__; }
    }

    .hero-title {
        font-size: clamp(24px, 6vw, 36px);
        font-weight: 900;
        letter-spacing: -1px;
        background: __TITLE_GRAD__;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 8px;
    }
    .hero-subtitle {
        color: #94a3b8;
        font-size: 13.5px;
        line-height: 1.6;
        max-width: 520px;
        margin: 0 auto;
    }

    /* Metric Chips */
    .metric-row {
        display: flex;
        justify-content: center;
        gap: 8px;
        margin-top: 14px;
        flex-wrap: wrap;
    }
    .metric-chip {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid __PRIMARY__;
        padding: 4px 10px;
        border-radius: 8px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        font-weight: 600;
        color: __ACCENT__;
    }

    /* Glowing Prompt Cards */
    div[data-testid="stButton"] > button {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.85), rgba(10, 20, 28, 0.95)) !important;
        border: 1px solid __PRIMARY__ !important;
        border-radius: 14px !important;
        color: #e2e8f0 !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        padding: 12px 16px !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4) !important;
        width: 100% !important;
    }
    div[data-testid="stButton"] > button:hover {
        transform: translateY(-2px) !important;
        border-color: __ACCENT__ !important;
        box-shadow: 0 0 22px __GLOW__ !important;
        color: #ffffff !important;
    }

    /* Chat Messages */
    .stChatMessage {
        background: rgba(11, 19, 28, 0.75) !important;
        backdrop-filter: blur(14px) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 16px !important;
        padding: 14px 18px !important;
        margin-bottom: 12px !important;
        word-break: break-word;
    }
    [data-testid="stChatMessageAssistant"] {
        border-left: 3px solid __PRIMARY__ !important;
        background: __ASSISTANT_BG__ !important;
    }
    [data-testid="stChatMessageUser"] {
        border-right: 3px solid #64748b !important;
        background: rgba(15, 23, 42, 0.4) !important;
    }

    /* Telemetry Chip */
    .telemetry-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(15, 23, 42, 0.9);
        border: 1px solid __PRIMARY__;
        padding: 3px 10px;
        border-radius: 6px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        font-weight: 600;
        color: __ACCENT__;
        margin-top: 8px;
        box-shadow: 0 0 10px __AMBIENT1__;
    }

    /* Glowing Input Bar */
    .stChatInputContainer {
        border-radius: 16px !important;
        border: 1px solid __PRIMARY__ !important;
        background: rgba(8, 14, 20, 0.9) !important;
    }
    .stChatInputContainer:focus-within {
        border-color: __ACCENT__ !important;
        box-shadow: 0 0 20px __GLOW__ !important;
    }

    section[data-testid="stSidebar"] {
        background-color: #04080c !important;
        border-right: 1px solid __PRIMARY__ !important;
    }
</style>
"""

styled_css = (
    raw_css
    .replace("__PRIMARY__", theme["primary"])
    .replace("__ACCENT__", theme["accent"])
    .replace("__AMBIENT1__", theme["ambient1"])
    .replace("__AMBIENT2__", theme["ambient2"])
    .replace("__ASSISTANT_BG__", theme["assistant_bg"])
    .replace("__TITLE_GRAD__", theme["title_grad"])
    .replace("__GLOW__", theme["glow_rgba"])
)
st.markdown(styled_css, unsafe_allow_html=True)

# Master System Prompt with Countdown Context & Permanent Guardrails
SYSTEM_PROMPT = f"""You are {ai_name}, an AI student academic companion.
{custom_instructions}

SITUATIONAL AWARENESS:
The student is actively preparing for an upcoming '{safe_exam_target}' exam in exactly {exam_days} days.
Tailor all study timelines, triage steps, active recall recommendations, and urgency strictly to this {exam_days}-day window!

MANDATORY PEDAGOGICAL GUARDRAILS (NEVER VIOLATE):
1. Never Do The Work For Them: Do not write essays, complete assignments, or solve test questions directly. Guide their thought process, give outlines, and explain concepts.
2. No Medical/Clinical Advice: Keep stress advice educational and practical.
3. Keep responses punchy, scannable, and formatted with clean bullet points.
"""

ACTIVE_API_KEY = sidebar_key.strip() or BUILTIN_GROQ_KEY.strip() or os.environ.get("GROQ_API_KEY", "").strip()

safe_ai_name = ai_name.replace("<", "").replace(">", "")
safe_ai_tagline = ai_tagline.replace("<", "").replace(">", "")

# ==============================================================================
# 🛰️ 5. TELEMETRY HUD BAR (WITH SCANNER LIGHT)
# ==============================================================================
st.markdown(f"""
<div class="hud-bar">
    <div class="hud-item">
        <span class="pulse-dot"></span>
        <span>CORE: <span class="hud-accent">{safe_ai_name.upper()}</span></span>
    </div>
    <div class="hud-item">
        <span>EXAM: <span class="hud-accent">{safe_exam_target.upper()} ({exam_days}D)</span></span>
    </div>
    <div class="hud-item">
        <span>INFERENCE: <span class="hud-accent">GROQ LPU™</span></span>
    </div>
</div>
""", unsafe_allow_html=True)

# ==============================================================================
# 🚀 6. DYNAMIC HERO CARD & STARTER PROMPTS
# ==============================================================================
starter_prompt = None

if len(st.session_state.messages) == 0:
    st.markdown(f"""
    <div class="hero-container">
        <div class="hero-title">Meet {safe_ai_name}.</div>
        <div class="hero-subtitle">{safe_ai_tagline}</div>
        <div class="metric-row">
            <span class="metric-chip">⚡ LPU ACCELERATED</span>
            <span class="metric-chip">🎯 {safe_exam_target.upper()} TARGET: {exam_days} DAYS</span>
            <span class="metric-chip">🛡️ ANTI-CHEAT GUARDRAILS</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<p style='font-size: 11px; font-weight: 700; color: #94a3b8; font-family: \"JetBrains Mono\", monospace; text-transform: uppercase;'>// Quick Directives</p>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"🧪 Emergency {safe_exam_target} Triage", use_container_width=True):
            starter_prompt = f"I have my {safe_exam_target} exam in {exam_days} days and feel unprepared. Walk me through an emergency triage study plan."
        if st.button("🧠 Deep Focus Pomodoro Setup", use_container_width=True):
            starter_prompt = "Design a high-retention 3-hour study block routine using Pomodoro that avoids mental fatigue."
    with col2:
        if st.button("😰 Calm Test Anxiety Protocol", use_container_width=True):
            starter_prompt = "I'm experiencing intense test stress right now. Can we do a fast 2-minute calm-down protocol?"
        if st.button("⚡ High-Fuel Study Nutrition", use_container_width=True):
            starter_prompt = "What quick snacks and hydration strategy will give me sustained focus without brain fog or sugar crashes?"

# ==============================================================================
# 💬 7. CHAT HISTORY DISPLAY (WITH BENCHMARK CHIPS)
# ==============================================================================
for msg in st.session_state.messages:
    role = msg.get("role")
    avatar = ai_avatar if role == "assistant" else "👤"
    with st.chat_message(role, avatar=avatar):
        st.markdown(msg.get("content", ""))
        if msg.get("telemetry"):
            st.markdown(f'<div class="telemetry-chip">{msg["telemetry"]}</div>', unsafe_allow_html=True)

# ==============================================================================
# ⚡ 8. CHAT INPUT & LIVE STREAMING PIPELINE (HARDENED)
# ==============================================================================
chat_input = st.chat_input(f"Message {safe_ai_name} (Target: {safe_exam_target} in {exam_days} days)...")
user_prompt = chat_input or starter_prompt

if user_prompt:
    if not ACTIVE_API_KEY or "PASTE_YOUR_GROQ_KEY_HERE" in ACTIVE_API_KEY:
        st.warning(f"👈 Please paste your Groq API Key in line 16 or the sidebar to unlock {safe_ai_name}.")
    else:
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_prompt)

        with st.chat_message("assistant", avatar=ai_avatar):
            try:
                client = Groq(api_key=ACTIVE_API_KEY)
                active_model = get_groq_model(client)

                # AIRTIGHT PAYLOAD SANITIZER:
                # 1. Strips away any 'telemetry' or extra keys
                # 2. Ensures only valid 'role' and non-empty 'content' strings reach Groq
                clean_history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[-10:]
                    if m.get("role") in ["user", "assistant"] and str(m.get("content", "")).strip()
                ]
                payload = [{"role": "system", "content": SYSTEM_PROMPT}] + clean_history

                start_time = time.time()

                stream = client.chat.completions.create(
                    model=active_model,
                    messages=payload,
                    stream=True,
                )

                def stream_chunks():
                    for chunk in stream:
                        if chunk.choices and len(chunk.choices) > 0:
                            delta = getattr(chunk.choices[0], "delta", None)
                            if delta:
                                content = getattr(delta, "content", None)
                                if content:
                                    yield content

                response_text = st.write_stream(stream_chunks())
                
                # Hardware benchmark telemetry
                elapsed = max(time.time() - start_time, 0.05)
                est_tokens = max(int(len(response_text.split()) * 1.33), 1)
                tps = int(est_tokens / elapsed)
                telemetry_str = f"⚡ {elapsed:.2f}s LATENCY &bull; ~{tps} TOK/S &bull; GROQ LPU™ HARDWARE"
                
                st.markdown(f'<div class="telemetry-chip">{telemetry_str}</div>', unsafe_allow_html=True)

                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": response_text,
                    "telemetry": telemetry_str
                })
                save_history(clean_name, st.session_state.messages)

                if len(st.session_state.messages) == 2:
                    st.rerun()

            except Exception as e:
                # If an error ever occurs, roll back the un-replied prompt so history isn't poisoned!
                if st.session_state.messages and st.session_state.messages[-1].get("role") == "user":
                    st.session_state.messages.pop()
                st.error(f"Inference Engine Error: {e}")

    
