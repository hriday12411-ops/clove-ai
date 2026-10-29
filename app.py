import json
from pathlib import Path
import streamlit as st
from groq import Groq

# Put your Groq key (starts with gsk_) right here:
API_KEY = "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"

SYSTEM_PROMPT = """You are Clover, an all-in-one student life consultant and a close, trusted friend. 
You act like a supportive, brilliant senior schoolmate or study buddy who is always in the student's corner. 
You aren't a corporate AI, a strict teacher, or a boring encyclopedia—you’re a chill peer who gives real, practical advice with zero judgment.

- Tone: Casual, conversational, warm, and encouraging.
- Structure: Keep responses punchy, scannable, and easy to read. Use bullet points and short paragraphs.
- Empathy First: Always validate the student's feelings first before jumping into solutions.
- Never Do the Work For Them: Guide them through concepts, do not write complete homework sets.
- Strict: Never give medical or clinical advice.
"""

BASE = Path(__file__).parent
HISTORY_DIR = BASE / "students"
HISTORY_DIR.mkdir(exist_ok=True)


def load_history(student):
    path = HISTORY_DIR / f"{student}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_history(student, history):
    path = HISTORY_DIR / f"{student}.json"
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")


# Automatically finds the active online model from Groq
@st.cache_resource
def get_groq_model(_client):
    try:
        models = [m.id for m in _client.models.list().data if "whisper" not in m.id.lower()]
        for pref in ["gpt-oss", "qwen", "llama"]:
            for m in models:
                if pref in m:
                    return m
        return models[0]
    except Exception:
        return "openai/gpt-oss-20b"


# --- PAGE SETUP ---
st.set_page_config(page_title="Clover - Student AI Consultant", page_icon="🍀", layout="centered")

st.title("🍀 Clover: Your AI Study & Life Consultant")
st.caption("A chill, judgment-free AI consultant to help you navigate school, stress, and study plans.")

# Initialize client
client = Groq(api_key=API_KEY)
active_model = get_groq_model(client)

# --- SIDEBAR (Student Profile) ---
with st.sidebar:
    st.header("👤 Student Profile")
    student_name = st.text_input("Enter your name:", value="Hriday Bedi")
    clean_name = student_name.strip().lower().replace(" ", "_") or "guest"
    st.info(f"Connected to model: `{active_model}`")
    
    if st.button("🗑️ Reset My Chat History"):
        save_history(clean_name, [])
        st.session_state.messages = []
        st.rerun()

# Initialize session messages
if "messages" not in st.session_state or st.session_state.get("current_student") != clean_name:
    st.session_state.current_student = clean_name
    st.session_state.messages = load_history(clean_name)

# Display chat history on screen
for msg in st.session_state.messages:
    role = msg.get("role")
    avatar = "🍀" if role == "assistant" else "👤"
    with st.chat_message(role, avatar=avatar):
        st.markdown(msg.get("content", ""))

# --- CHAT INPUT BAR ---
user_input = st.chat_input("Ask Clover about study tips, exam stress, routines...")

if user_input:
    # 1. Display user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)

    # 2. Call Groq
    messages_payload = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages_payload.extend(st.session_state.messages[-10:])

    with st.chat_message("assistant", avatar="🍀"):
        with st.spinner("Clover is thinking..."):
            try:
                response = client.chat.completions.create(
                    model=active_model,
                    messages=messages_payload,
                )
                answer = response.choices[0].message.content
                st.markdown(answer)
                
                # 3. Save to history
                st.session_state.messages.append({"role": "assistant", "content": answer})
                save_history(clean_name, st.session_state.messages)
            except Exception as e:
                st.error(f"Something went wrong: {e}")