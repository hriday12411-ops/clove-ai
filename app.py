import hashlib
import html
import inspect
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from groq import Groq

# ==============================================================================
# 🔑 1. API CONFIGURATION
# ==============================================================================
# Put GROQ_API_KEY in .streamlit/secrets.toml (safe for GitHub), or paste it in the sidebar.
# NEVER paste a real key here if the code goes online. The old key was exposed: revoke it.
BUILTIN_GROQ_KEY = "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"

st.set_page_config(
    page_title="CLOVER STUDIO // NEURAL FOUNDRY",
    page_icon="🍀",
    layout="centered",
    initial_sidebar_state="auto",
)

ss = st.session_state
ss.setdefault("docs", {})            # attached notes: {filename: text}
ss.setdefault("dismissed", set())    # removed attachments (so the fallback uploader won't re-add them)
ss.setdefault("pending", False)      # a user message is waiting for an AI reply
ss.setdefault("queued_prompt", None)
ss.setdefault("studio", {})          # generated Studio outputs
ss.setdefault("studio_active", None)
ss.setdefault("last_audio_hash", None)
ss.setdefault("messages", [])        # messages of the chat that is open right now
ss.setdefault("chat_id", None)       # None = brand-new chat (saved on the first message)
ss.setdefault("chat_title", "")
ss.setdefault("confirm_del", None)   # chat id waiting for delete confirmation

TEXT_TYPES = ["txt", "md", "py", "json", "csv", "pdf"]
MAX_DOC_CHARS = 6000
MAX_DOCS = 5


# ==============================================================================
# 🧰 2. HELPERS
# ==============================================================================
def get_secret_key():
    try:
        return str(st.secrets.get("GROQ_API_KEY", "")).strip()
    except Exception:
        return ""


def auto_scroll():
    """Scrolls to the newest message (works on old and new Streamlit layouts)."""
    components.html(
        """
        <script>
            setTimeout(function () {
                const doc = window.parent.document;
                const main = doc.querySelector('[data-testid="stMain"]') || doc.querySelector('section.main');
                if (main) { main.scrollTo({ top: main.scrollHeight, behavior: 'smooth' }); }
            }, 150);
        </script>
        """,
        height=0,
    )


def get_live_weather(query_text):
    weather_keywords = ["weather", "temperature", "rain", "forecast", "climate",
                        "hot outside", "cold outside", "umbrella", "sunny"]
    if not any(k in query_text.lower() for k in weather_keywords):
        return None
    try:
        city = "Delhi"
        match = re.search(r"\bin\s+([A-Za-z]+)", query_text, re.IGNORECASE)
        if match and match.group(1).lower() not in {"the", "my", "this", "that", "a", "an", "our"}:
            city = match.group(1).strip()
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=%C+%t+(Humidity:+%h,+Wind:+%w)"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = resp.read().decode("utf-8").strip()
            return f"LIVE SATELLITE WEATHER FOR {city.upper()}: {data}"
    except Exception:
        return None


BASE = Path(__file__).parent
HISTORY_DIR = BASE / "students"
try:
    HISTORY_DIR.mkdir(exist_ok=True)
except Exception:
    pass


# ---------- multi-chat storage: one JSON file per chat in students/chats/ ----------
CHATS_DIR = HISTORY_DIR / "chats"
try:
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
_ID_OK = re.compile(r"^[0-9A-Za-z_-]+$")


def _trim(text, n):
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _chat_path(cid):
    return CHATS_DIR / f"{cid}.json" if _ID_OK.match(str(cid or "")) else None


def _new_id():
    return time.strftime("%Y%m%d-%H%M%S") + "-" + hashlib.md5(os.urandom(8)).hexdigest()[:4]


def _make_title(first_text):
    focus = ss.get("lib_focus")
    if focus and focus.get("prompt") == first_text and focus.get("chapter"):
        return f"{focus.get('subject')} · {focus.get('chapter')}"
    return _trim(first_text, 48) or "New chat"


def save_chat():
    """Saves the open chat. Empty chats are never kept (no clutter in the history list)."""
    if not ss.messages:
        path = _chat_path(ss.chat_id)
        if path:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        ss.chat_id, ss.chat_title = None, ""
        return
    if not ss.chat_id:
        ss.chat_id = _new_id()
        first_user = next((m.get("content", "") for m in ss.messages if m.get("role") == "user"), "")
        ss.chat_title = _make_title(first_user)
    path = _chat_path(ss.chat_id)
    if not path:
        return
    data = {"id": ss.chat_id, "title": ss.chat_title or "Chat", "avatar": ai_avatar,
            "updated": time.time(), "messages": ss.messages}
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def list_chats(limit=60):
    try:
        files = sorted(CHATS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
    except Exception:
        return []
    out = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and isinstance(d.get("messages"), list) and d["messages"]:
            out.append({"id": f.stem, "title": d.get("title") or "Chat", "avatar": d.get("avatar") or "",
                        "updated": d.get("updated") or f.stat().st_mtime})
    return out


def migrate_old_histories():
    """One-time: turns the old per-persona history files into entries in the new chat list."""
    try:
        for f in list(HISTORY_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                data = None
            if isinstance(data, list) and any(m.get("role") == "user" for m in data if isinstance(m, dict)):
                first = next(m.get("content", "") for m in data if m.get("role") == "user")
                cid = _new_id()
                (CHATS_DIR / f"{cid}.json").write_text(json.dumps(
                    {"id": cid, "title": _trim(first, 48) or "Old chat", "avatar": "",
                     "updated": f.stat().st_mtime, "messages": data}, ensure_ascii=False, indent=1), encoding="utf-8")
            f.rename(f.with_suffix(".json.bak"))
    except Exception:
        pass


def new_chat():
    ss.chat_id = None
    ss.chat_title = ""
    ss.messages = []
    ss.pending = False
    ss.studio = {}
    ss.studio_active = None
    ss.confirm_del = None
    ss["mode"] = "💬 Chat"


def open_chat(cid):
    path = _chat_path(cid)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        msgs = data["messages"]
        assert isinstance(msgs, list)
    except Exception:
        st.toast("Couldn't open that chat.", icon="⚠️")
        return
    ss.chat_id = cid
    ss.chat_title = data.get("title") or "Chat"
    ss.messages = msgs
    ss.pending = False
    ss.studio = {}
    ss.studio_active = None
    ss.confirm_del = None
    ss["mode"] = "💬 Chat"


def ask_delete(cid):
    ss.confirm_del = cid


def cancel_delete():
    ss.confirm_del = None


def delete_chat(cid):
    path = _chat_path(cid)
    if path:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
    ss.confirm_del = None
    if cid == ss.chat_id:
        new_chat()


def delete_current_chat():
    if ss.chat_id:
        delete_chat(ss.chat_id)
    else:
        new_chat()


def group_label(ts):
    try:
        days = (date.today() - datetime.fromtimestamp(ts).date()).days
    except Exception:
        return "Older"
    return "Today" if days <= 0 else "Yesterday" if days == 1 else "Previous 7 days" if days <= 7 else "Older"


if not ss.get("migrated"):
    migrate_old_histories()
    ss.migrated = True


@st.cache_resource
def get_groq_model(_client):
    try:
        raw = _client.models.list().data
        skip_words = ["whisper", "guard", "embed", "distil", "vision", "tts", "playai"]
        chats = [m.id for m in raw if not any(s in m.id.lower() for s in skip_words)]
        priority = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-70b-8192",
                    "mixtral-8x7b-32768", "gemma2-9b-it"]
        for p in priority:
            if p in chats:
                return p
        for m in chats:
            if "llama" in m or "qwen" in m or "gpt" in m:
                return m
        return chats[0] if chats else "llama-3.3-70b-versatile"
    except Exception:
        return "llama-3.3-70b-versatile"


def read_upload(f):
    """Turns an uploaded file into plain text (txt/md/py/json/csv, and pdf if pypdf is installed)."""
    name = f.name
    data = f.getvalue()
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext == "pdf":
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:15])
        except Exception:
            return ""
    else:
        text = data.decode("utf-8", errors="ignore")
    return text.strip()[:MAX_DOC_CHARS]


def add_docs(files, force=False):
    added = []
    for f in files or []:
        try:
            key = f"{f.name}:{getattr(f, 'size', 0)}"
            if not force and key in ss.dismissed:
                continue
            ss.dismissed.discard(key)
            if f.name in ss.docs:
                continue
            if len(ss.docs) >= MAX_DOCS:
                st.toast(f"Max {MAX_DOCS} attachments. Remove one first.", icon="⚠️")
                break
            text = read_upload(f)
            if text:
                ss.docs[f.name] = text
                ss.docs_keys = {**ss.get("docs_keys", {}), f.name: key}
                added.append(f.name)
            else:
                st.toast(f"Couldn't read {f.name}", icon="⚠️")
        except Exception:
            st.toast("Couldn't read that file.", icon="⚠️")
    if added:
        st.toast(f"Attached: {', '.join(added)}", icon="📎")
    return added


def remove_doc(name):
    key = ss.get("docs_keys", {}).get(name)
    if key:
        ss.dismissed.add(key)
    ss.docs.pop(name, None)


def queue_prompt(p):
    ss.queued_prompt = p


def transcribe(api_key, audio_bytes):
    client = Groq(api_key=api_key)
    result = client.audio.transcriptions.create(
        file=("audio.wav", audio_bytes, "audio/wav"),
        model="whisper-large-v3",
    )
    return (result.text or "").strip()


def unpack_chat_value(value):
    """chat_input returns a plain string or a dict-like object (text / files / audio)."""
    if value is None:
        return "", [], None
    if isinstance(value, str):
        return value, [], None

    def grab(key):
        try:
            return value[key]
        except Exception:
            return getattr(value, key, None)

    files = grab("files") or []
    if not isinstance(files, (list, tuple)):
        files = [files]
    return (grab("text") or ""), list(files), grab("audio")


# ==============================================================================
# 📚 2B. NCERT CLASS 11 LIBRARY (textbooks + previous-year papers)
# ==============================================================================
# Put the free NCERT PDFs (ncert.nic.in) in  library/<subject>/  and past papers /
# sample papers in  pyq/<subject>/ . You can also upload them from the Library screen.
LIB_DIR = BASE / "library"
PYQ_DIR = BASE / "pyq"

CHAPTERS = {
    "Physics": [
        "Units and Measurements", "Motion in a Straight Line", "Motion in a Plane", "Laws of Motion",
        "Work, Energy and Power", "System of Particles and Rotational Motion", "Gravitation",
        "Mechanical Properties of Solids", "Mechanical Properties of Fluids",
        "Thermal Properties of Matter", "Thermodynamics", "Kinetic Theory", "Oscillations", "Waves",
    ],
    "Chemistry": [
        "Some Basic Concepts of Chemistry", "Structure of Atom",
        "Classification of Elements and Periodicity in Properties",
        "Chemical Bonding and Molecular Structure", "Thermodynamics", "Equilibrium", "Redox Reactions",
        "Organic Chemistry: Some Basic Principles and Techniques", "Hydrocarbons",
    ],
    "Biology": [
        "The Living World", "Biological Classification", "Plant Kingdom", "Animal Kingdom",
        "Morphology of Flowering Plants", "Anatomy of Flowering Plants",
        "Structural Organisation in Animals", "Cell: The Unit of Life", "Biomolecules",
        "Cell Cycle and Cell Division", "Photosynthesis in Higher Plants", "Respiration in Plants",
        "Plant Growth and Development", "Breathing and Exchange of Gases",
        "Body Fluids and Circulation", "Excretory Products and their Elimination",
        "Locomotion and Movement", "Neural Control and Coordination",
        "Chemical Coordination and Integration",
    ],
    "Maths": [
        "Sets", "Relations and Functions", "Trigonometric Functions",
        "Complex Numbers and Quadratic Equations", "Linear Inequalities",
        "Permutations and Combinations", "Binomial Theorem", "Sequences and Series", "Straight Lines",
        "Conic Sections", "Introduction to Three Dimensional Geometry", "Limits and Derivatives",
        "Statistics", "Probability",
    ],
    "English": [
        "Hornbill - The Portrait of a Lady", "Hornbill - We're Not Afraid to Die",
        "Hornbill - Discovering Tut: the Saga Continues", "Hornbill - Landscape of the Soul",
        "Hornbill - The Ailing Planet", "Hornbill - The Browning Version", "Hornbill - The Adventure",
        "Hornbill - Silk Road",
        "Hornbill Poems - A Photograph / The Laburnum Top / The Voice of the Rain / Childhood / Father to Son",
        "Snapshots - The Summer of the Beautiful White Horse", "Snapshots - The Address",
        "Snapshots - Ranga's Marriage", "Snapshots - Albert Einstein at School",
        "Snapshots - Mother's Day", "Snapshots - The Ghat of the Only World", "Snapshots - Birth",
        "Snapshots - The Tale of Melon City",
    ],
}

for _folder in (LIB_DIR, PYQ_DIR):
    for _s in CHAPTERS:
        try:
            (_folder / _s.lower()).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass


@st.cache_data(show_spinner=False)
def _pdf_chunks(path_str, mtime):
    try:
        from pypdf import PdfReader
        reader = PdfReader(path_str)
    except Exception:
        return []
    chunks = []
    for pno, page in enumerate(reader.pages, 1):
        try:
            text = re.sub(r"\s+", " ", page.extract_text() or "").strip()
        except Exception:
            continue
        for i in range(0, len(text), 1100):
            piece = text[i:i + 1200]
            if len(piece) > 150:
                chunks.append((pno, piece))
    return chunks


def _lib_files(folder, subject=None):
    subs = [subject.lower()] if subject else [s.lower() for s in CHAPTERS]
    out = []
    for s in subs:
        d = folder / s
        if d.exists():
            out += sorted(d.glob("*.pdf"))
    return out


STOP = set("""about above after again also because been before being between both could does doing done
down during each from give have having here into just like make more most much need only other over same
should some such than that their them then there these they this those through under until very want what
when where which while will with would your explain simply chapter class ncert important things exams exam
question questions answer answers tell please help quick revision sheet page quiz wait next""".split())


def retrieve(query, subject=None, folder=None, k=4, max_chars=3500, boost=""):
    """Best-matching passages from your PDFs (simple keyword scoring)."""
    folder = folder or LIB_DIR
    weights = {}
    for w in re.findall(r"[a-zA-Z]{4,}", query.lower()):
        if w not in STOP:
            weights[w] = 1
    for w in re.findall(r"[a-zA-Z]{4,}", (boost or "").lower()):
        if w not in STOP:
            weights[w] = 3
    if not weights:
        return ""
    scored = []
    for f in _lib_files(folder, subject):
        for pno, text in _pdf_chunks(str(f), f.stat().st_mtime):
            low = text.lower()
            score = sum(low.count(w) * wt for w, wt in weights.items())
            if score:
                scored.append((score, f.name, pno, text))
    scored.sort(reverse=True)
    parts, total = [], 0
    for _, name, pno, text in scored[:k]:
        if total + len(text) > max_chars:
            break
        parts.append(f"[{name} p.{pno}] {text}")
        total += len(text)
    return "\n\n".join(parts)


def library_context(query, focus=None):
    """Extra system-prompt text so answers come from the textbooks / PYQ style.
    focus = {"subject":..., "chapter":...} when the message came from a Library button."""
    subject = focus.get("subject") if focus else None
    boost = focus.get("chapter") if focus else ""
    book = retrieve(query, subject, LIB_DIR, boost=boost)
    pyq = retrieve(query, subject, PYQ_DIR, k=2, max_chars=1500, boost=boost)
    out = ""
    if book:
        out += ("\n\nTEXTBOOK EXCERPTS (NCERT Class 11). Treat these as the source of truth and mention "
                "which book/page you used:\n" + book)
    if pyq:
        out += "\n\nPREVIOUS-YEAR QUESTION STYLE REFERENCE:\n" + pyq
    return out


def go_chat_with(prompt, subject=None, chapter=None):
    ss.queued_prompt = prompt
    ss.lib_focus = {"prompt": prompt, "subject": subject, "chapter": chapter}
    ss["mode"] = "💬 Chat"


def render_library():
    st.markdown('<div class="studio-head">// NCERT CLASS 11 · LIBRARY</div>', unsafe_allow_html=True)
    subject = st.selectbox("Subject", list(CHAPTERS), key="lib_subject")
    chapter = st.selectbox("Chapter", CHAPTERS[subject], key="lib_chapter")

    n_books = len(_lib_files(LIB_DIR, subject))
    n_pyq = len(_lib_files(PYQ_DIR, subject))
    st.caption(f"📚 {n_books} textbook PDF(s) · 📝 {n_pyq} PYQ PDF(s) loaded for {subject}")
    if not n_books:
        st.info(f"Add the NCERT {subject} PDFs below (free at ncert.nic.in) so answers use the real book text.")

    ctx = f"NCERT Class 11 {subject}, chapter '{chapter}'"
    c1, c2 = st.columns(2)
    with c1:
        st.button("📖 Explain chapter", key="lib_b1", use_container_width=True, on_click=go_chat_with, args=(
            f"Explain {ctx} simply: key ideas, formulas/definitions, and the 5 most important things for exams.",
            subject, chapter))
        st.button("🧠 Quick revision", key="lib_b2", use_container_width=True, on_click=go_chat_with, args=(
            f"Give me a 1-page quick revision sheet for {ctx}.", subject, chapter))
    with c2:
        st.button("📝 PYQ-style practice", key="lib_b3", use_container_width=True, on_click=go_chat_with, args=(
            f"Give me 8 exam-style questions for {ctx} in the CBSE school-exam pattern "
            "(3 MCQ x1 mark, 3 short x2-3 marks, 2 long x5 marks). Do not give answers yet; "
            "I'll attempt them and you check.", subject, chapter))
        st.button("✅ Test me", key="lib_b4", use_container_width=True, on_click=go_chat_with, args=(
            f"Quiz me one question at a time on {ctx}. Wait for my answer before the next.", subject, chapter))

    with st.expander("➕ Add textbook / PYQ PDFs"):
        kind = st.radio("Type", ["Textbook", "PYQ / Sample paper"], horizontal=True, key="lib_kind")
        ups = st.file_uploader("PDFs", type=["pdf"], accept_multiple_files=True,
                               key=f"lib_up_{ss.get('lib_up_n', 0)}")
        if ups and st.button("Save to library", use_container_width=True, key="lib_save"):
            dest = (LIB_DIR if kind == "Textbook" else PYQ_DIR) / subject.lower()
            dest.mkdir(parents=True, exist_ok=True)
            for u in ups:
                (dest / Path(u.name).name).write_bytes(u.getvalue())
            st.toast(f"Saved {len(ups)} file(s) to {subject}", icon="📚")
            ss.lib_up_n = ss.get("lib_up_n", 0) + 1
            st.rerun()


# ==============================================================================
# ⚙️ 3. SIDEBAR (persona, exam, key)
# ==============================================================================
with st.sidebar:
    history_slot = st.empty()   # chat history list, filled at the end so it is never stale
    st.divider()
    st.markdown("""
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
        <span style="font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:700;color:#94a3b8;letter-spacing:1px;">// CONTROL MATRIX</span>
        <span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#10b981;font-weight:700;">● SENSORS: ONLINE</span>
    </div>
    """, unsafe_allow_html=True)

    persona_mode = st.selectbox(
        "AI Archetype Core:",
        [
            "🍀 Clover (Chill Peer / Study Buddy)",
            "⚡ Titan (Discipline & Drill Coach)",
            "🌙 Luna (Calm & Mindfulness Guide)",
            "⚙️ Custom Agent Studio",
        ],
    )

    if "Clover" in persona_mode:
        ai_name, ai_avatar = "Clover", "🍀"
        ai_tagline = "Chill senior schoolmate and practical study buddy."
        custom_instructions = ("You are Clover, a casual, smart, and friendly senior student. Answer questions "
                               "directly, casually, and with simple analogies. Never sound like a corporate robot.")
        theme = {
            "primary": "#10b981", "accent": "#34d399", "ambient1": "rgba(16, 185, 129, 0.22)",
            "ambient2": "rgba(6, 182, 212, 0.14)", "assistant_bg": "rgba(6, 78, 59, 0.22)",
            "title_grad": "linear-gradient(135deg, #ffffff 10%, #6ee7b7 55%, #06b6d4 100%)",
            "glow_rgba": "rgba(16, 185, 129, 0.45)",
        }
    elif "Titan" in persona_mode:
        ai_name, ai_avatar = "Titan", "⚡"
        ai_tagline = "High-accountability, zero-excuses exam drill coach."
        custom_instructions = ("You are Titan, an intense, direct academic coach. Push back against procrastination, "
                               "demand sharp focus, but answer questions directly and concisely.")
        theme = {
            "primary": "#ef4444", "accent": "#f87171", "ambient1": "rgba(239, 68, 68, 0.25)",
            "ambient2": "rgba(249, 115, 22, 0.16)", "assistant_bg": "rgba(127, 29, 29, 0.25)",
            "title_grad": "linear-gradient(135deg, #ffffff 10%, #fca5a5 50%, #f97316 100%)",
            "glow_rgba": "rgba(239, 68, 68, 0.45)",
        }
    elif "Luna" in persona_mode:
        ai_name, ai_avatar = "Luna", "🌙"
        ai_tagline = "Calming mindfulness guide for test anxiety."
        custom_instructions = ("You are Luna, a gentle, soothing study companion. Help students stay grounded and "
                               "answer their questions calmly without inducing any panic.")
        theme = {
            "primary": "#3b82f6", "accent": "#60a5fa", "ambient1": "rgba(37, 99, 235, 0.26)",
            "ambient2": "rgba(30, 58, 138, 0.40)", "assistant_bg": "rgba(30, 58, 138, 0.28)",
            "title_grad": "linear-gradient(135deg, #ffffff 10%, #93c5fd 50%, #3b82f6 100%)",
            "glow_rgba": "rgba(59, 130, 246, 0.45)",
        }
    else:
        st.markdown("##### 🎨 **Design Your Custom Agent:**")
        ai_name = st.text_input("Agent Codename:", value="Athena").strip() or "CustomAI"
        raw_avatar = st.text_input("Agent Avatar Emoji:", value="🦉").strip()
        ai_avatar = raw_avatar if (raw_avatar and len(raw_avatar) <= 2) else "🤖"
        ai_tagline = st.text_input("Agent Purpose:", value="Strategic logic mentor for advanced problem-solving.").strip()
        custom_instructions = st.text_area(
            "Persona & Tone Directives:",
            value="You are Athena, a sharp intellectual mentor who explains concepts clearly using logical reasoning.",
        )
        theme = {
            "primary": "#a855f7", "accent": "#c084fc", "ambient1": "rgba(168, 85, 247, 0.25)",
            "ambient2": "rgba(236, 72, 153, 0.16)", "assistant_bg": "rgba(88, 28, 135, 0.25)",
            "title_grad": "linear-gradient(135deg, #ffffff 10%, #d8b4fe 50%, #ec4899 100%)",
            "glow_rgba": "rgba(168, 85, 247, 0.45)",
        }

    st.divider()
    st.markdown(f"""
    <div style="background:rgba(15,23,42,0.7);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:12px;margin-bottom:12px;">
        <div style="font-size:10px;font-family:'JetBrains Mono',monospace;color:#94a3b8;">STUDENT IDENTITY</div>
        <div style="font-size:14px;font-weight:700;color:#f8fafc;margin-top:2px;">Hriday Bedi</div>
        <div style="font-size:11px;color:{theme['accent']};font-family:'JetBrains Mono',monospace;margin-top:4px;">● PROFILE AUTHENTICATED</div>
    </div>
    """, unsafe_allow_html=True)

    student_name = "Hriday Bedi"
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", f"hriday_bedi_{ai_name.lower()}")

    enable_exam_context = st.checkbox("🎯 Set Active Exam Deadline", value=False)
    if enable_exam_context:
        col_a, col_b = st.columns(2)
        with col_a:
            raw_target = st.text_input("Subject:", value="Chemistry")
            safe_exam_target = re.sub(r"[^\w\s-]", "", raw_target).strip() or "Exams"
        with col_b:
            exam_days = st.number_input("Days Left:", min_value=1, max_value=365, value=3)
    else:
        safe_exam_target = "General"
        exam_days = None

    st.divider()
    docs_slot = st.empty()      # filled after input is processed (so it is never stale)
    st.divider()
    st.markdown(f"""
    <div style="background:rgba(10,15,22,0.6);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:12px;margin-bottom:14px;font-family:'JetBrains Mono',monospace;font-size:10px;line-height:1.8;color:#94a3b8;">
        <div>INFERENCE: <span style="color:{theme['accent']};font-weight:700;">GROQ LPU™ SILICON</span></div>
        <div>WHISPER CORE: <span style="color:#f1f5f9;">v3 LARGE AUDIO</span></div>
        <div>WEATHER HOOK: <span style="color:#f1f5f9;">LIVE SATELLITE</span></div>
        <div>LIBRARY: <span style="color:#f1f5f9;">NCERT CLASS 11</span></div>
        <div>GUARDRAILS: <span style="color:{theme['primary']};font-weight:700;">ANTI-CHEAT ACTIVE</span></div>
    </div>
    """, unsafe_allow_html=True)
    export_slot = st.empty()    # export + reset, filled at the very end
    st.divider()
    sidebar_key = st.text_input("Groq API Key (Override):", type="password", value="", placeholder="gsk_...")

ACTIVE_API_KEY = (sidebar_key.strip() or BUILTIN_GROQ_KEY.strip()
                  or get_secret_key() or os.environ.get("GROQ_API_KEY", "").strip())
KEY_OK = bool(ACTIVE_API_KEY)

# ==============================================================================
# 🎨 4. THEME + ROUNDED RGB/HDR CHAT BAR
# ==============================================================================
raw_css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');

    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    code, pre { font-family: 'JetBrains Mono', monospace !important; }

    :root {
        --rgb-stops: #ff2a6d, #ff9a00, #ffe600, #2dff8f, #00d4ff, #7a5cff, #ff2bd6, #ff2a6d;
    }
    /* HDR / wide-gamut screens get richer colours */
    @media (color-gamut: p3) {
        :root {
            --rgb-stops: color(display-p3 1 0.1 0.4), color(display-p3 1 0.62 0), color(display-p3 1 0.95 0),
                         color(display-p3 0.1 1 0.58), color(display-p3 0 0.85 1), color(display-p3 0.5 0.35 1),
                         color(display-p3 1 0.15 0.85), color(display-p3 1 0.1 0.4);
        }
    }

    @property --angle { syntax: '<angle>'; initial-value: 0deg; inherits: true; }
    @keyframes rgbSpin { to { --angle: 360deg; } }

    .stApp {
        background-color: #030708 !important;
        background-image:
            radial-gradient(at 0% 0%, __AMBIENT1__ 0px, transparent 50%),
            radial-gradient(at 100% 100%, __AMBIENT2__ 0px, transparent 50%),
            linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px) !important;
        background-size: 100% 100%, 100% 100%, 30px 30px, 30px 30px !important;
        color: #f1f5f9;
    }

    .hud-bar {
        position: relative; overflow: hidden; display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;
        background: rgba(15,23,42,0.7); border: 1px solid __PRIMARY__; border-radius: 10px;
        padding: 5px 14px; margin-bottom: 14px; font-family: 'JetBrains Mono', monospace; font-size: 10.5px;
        color: #94a3b8; box-shadow: 0 0 14px __AMBIENT1__;
    }
    .hud-bar::after {
        content: ''; position: absolute; top: 0; left: -100%; width: 40%; height: 100%;
        background: linear-gradient(90deg, transparent, __PRIMARY__, transparent);
        opacity: 0.25; animation: laserScan 8s infinite linear; pointer-events: none;
    }
    @keyframes laserScan { 0% { left: -100%; } 100% { left: 200%; } }
    .hud-item { display: flex; align-items: center; gap: 6px; z-index: 2; }
    .hud-accent { color: __ACCENT__; font-weight: 700; }
    .pulse-dot { width: 7px; height: 7px; background-color: __PRIMARY__; border-radius: 50%;
        box-shadow: 0 0 10px __PRIMARY__; animation: pulse 1.8s infinite; }
    @keyframes pulse { 0% { opacity: 0.8; } 50% { opacity: 1; } 100% { opacity: 0.8; } }

    .hero-container {
        background: rgba(10,18,25,0.75); backdrop-filter: blur(16px);
        border: 1px solid __PRIMARY__; border-radius: 16px; padding: 14px 12px;
        text-align: center; margin-bottom: 12px; animation: neonGlow 4s infinite ease-in-out;
    }
    @keyframes neonGlow { 0%, 100% { box-shadow: 0 0 18px -8px __GLOW__; } 50% { box-shadow: 0 0 30px 0px __GLOW__; } }
    .hero-title { font-size: clamp(20px, 5vw, 26px); font-weight: 800; letter-spacing: -0.5px;
        background: __TITLE_GRAD__; -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 2px; }
    .hero-subtitle { color: #94a3b8; font-size: 12px; line-height: 1.4; max-width: 440px; margin: 0 auto; }

    div[data-testid="stButton"] > button, div[data-testid="stDownloadButton"] > button {
        background: rgba(15,23,42,0.85) !important; border: 1px solid __PRIMARY__ !important;
        border-radius: 999px !important; color: #cbd5e1 !important; font-weight: 500 !important;
        font-size: 12px !important; padding: 5px 12px !important; min-height: 30px !important;
        line-height: 1.2 !important; box-shadow: none !important; width: 100% !important; margin-bottom: 2px !important;
    }
    div[data-testid="stButton"] > button:hover, div[data-testid="stDownloadButton"] > button:hover {
        border-color: __ACCENT__ !important; color: #ffffff !important; background: __ASSISTANT_BG__ !important;
    }

    .stChatMessage {
        background: rgba(11,19,28,0.75) !important; backdrop-filter: blur(14px) !important;
        border: 1px solid rgba(255,255,255,0.08) !important; border-radius: 14px !important;
        padding: 12px 16px !important; margin-bottom: 10px !important; word-break: break-word;
    }
    [data-testid="stChatMessageAssistant"] { border-left: 3px solid __PRIMARY__ !important; background: __ASSISTANT_BG__ !important; }
    [data-testid="stChatMessageUser"] { border-right: 3px solid #64748b !important; background: rgba(15,23,42,0.4) !important; }

    .telemetry-chip {
        display: inline-flex; align-items: center; gap: 6px; background: rgba(15,23,42,0.9);
        border: 1px solid __PRIMARY__; padding: 2px 8px; border-radius: 5px;
        font-family: 'JetBrains Mono', monospace; font-size: 9.5px; font-weight: 600; color: __ACCENT__; margin-top: 6px;
    }

    .studio-head { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #94a3b8; letter-spacing: 1px; margin: 4px 0 8px; }

    /* ---------- ROUNDED CHAT BAR WITH SPINNING RGB RING ---------- */
    [data-testid="stBottom"], [data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] {
        background: transparent !important;
    }
    [data-testid="stBottomBlockContainer"] { padding-bottom: 1.4rem !important; }

    [data-testid="stChatInput"] {
        position: relative;
        border: 2px solid transparent !important;
        border-radius: 34px !important;
        background:
            linear-gradient(#0a1016, #0a1016) padding-box,
            conic-gradient(from var(--angle), var(--rgb-stops)) border-box !important;
        animation: rgbSpin 4s linear infinite;
        box-shadow: none !important;
    }
    /* soft HDR glow that sits behind the bar */
    [data-testid="stChatInput"]::before {
        content: ""; position: absolute; inset: -5px; border-radius: 40px; z-index: -1; pointer-events: none;
        background: conic-gradient(from var(--angle), var(--rgb-stops));
        filter: blur(16px) saturate(1.6); opacity: 0.6;
    }
    [data-testid="stChatInput"] > div,
    [data-testid="stChatInput"] div[data-baseweb],
    [data-testid="stChatInput"] div[data-baseweb] > div {
        background: transparent !important; border: none !important; box-shadow: none !important;
        border-radius: 32px !important;
    }
    [data-testid="stChatInput"] textarea { background: transparent !important; color: #f1f5f9 !important; caret-color: __ACCENT__; }
    [data-testid="stChatInput"] button { border-radius: 50% !important; }
    [data-testid="stChatInput"] button:hover { background: __ASSISTANT_BG__ !important; }
    [data-testid="stChatInput"] button svg { color: __ACCENT__ !important; }

    section[data-testid="stSidebar"] { background-color: #04080c !important; border-right: 1px solid __PRIMARY__ !important; }

    /* ---------- SMOOTHNESS LAYER ---------- */
    * { -webkit-font-smoothing: antialiased; }
    div[data-testid="stButton"] > button, div[data-testid="stDownloadButton"] > button {
        transition: background-color .2s ease, border-color .2s ease, color .2s ease, transform .15s ease;
    }
    .stChatMessage { line-height: 1.65; }
    .stChatMessage p { margin-bottom: .6rem; }
    /* chat bar and page share the same width so they line up */
    [data-testid="stMainBlockContainer"], .block-container, [data-testid="stBottomBlockContainer"] { max-width: 760px !important; }
    /* keep the status bar clear of Streamlit's fixed top header (this was hiding it) */
    [data-testid="stMainBlockContainer"], .block-container { padding-top: 4.5rem !important; }
    [data-testid="stHeader"] { background: rgba(3,7,8,0.65) !important; backdrop-filter: blur(10px); }
    .hud-bar { position: relative; z-index: 1; }
    /* mode switch wraps cleanly on small screens */
    [data-testid="stRadio"] [role="radiogroup"] { gap: .4rem .9rem; flex-wrap: wrap; }
    /* the invisible auto-scroll helper must not leave a blank gap */
    div[data-testid="stElementContainer"]:has(iframe[height="0"]),
    .element-container:has(iframe[height="0"]) { position: absolute !important; height: 0 !important; margin: 0 !important; overflow: hidden !important; }
    @media (max-width: 520px) { .hud-bar .hud-item:last-child { display: none; } }
    div[data-testid="stButton"] > button:hover { transform: translateY(-1px); }
    div[data-testid="stButton"] > button:active { transform: scale(.98); }
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-thumb { background: rgba(148,163,184,.25); border-radius: 8px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(148,163,184,.45); }

    @media (prefers-reduced-motion: reduce) {
        [data-testid="stChatInput"], .hud-bar::after, .hero-container { animation: none !important; }
        div[data-testid="stButton"] > button { transition: none !important; }
    }
</style>
"""

st.markdown(
    raw_css.replace("__PRIMARY__", theme["primary"])
    .replace("__ACCENT__", theme["accent"])
    .replace("__AMBIENT1__", theme["ambient1"])
    .replace("__AMBIENT2__", theme["ambient2"])
    .replace("__ASSISTANT_BG__", theme["assistant_bg"])
    .replace("__TITLE_GRAD__", theme["title_grad"])
    .replace("__GLOW__", theme["glow_rgba"]),
    unsafe_allow_html=True,
)

safe_ai_name = ai_name.replace("<", "").replace(">", "")
safe_ai_tagline = ai_tagline.replace("<", "").replace(">", "")

# ==============================================================================
# 🛰️ 5. HUD BAR + MODE SWITCH
# ==============================================================================
hud_exam_text = f"{safe_exam_target.upper()} ({exam_days}D)" if (enable_exam_context and exam_days) else "STANDBY"
st.markdown(f"""
<div class="hud-bar">
    <div class="hud-item"><span class="pulse-dot"></span><span>CORE: <span class="hud-accent">{html.escape(safe_ai_name.upper())}</span></span></div>
    <div class="hud-item"><span>STATUS: <span class="hud-accent">{html.escape(hud_exam_text)}</span></span></div>
    <div class="hud-item"><span>INFERENCE: <span class="hud-accent">GROQ LPU™</span></span></div>
</div>
""", unsafe_allow_html=True)

mode = st.radio("View", ["💬 Chat", "📚 Library", "🗺️ Studio"], horizontal=True,
                label_visibility="collapsed", key="mode")

# ==============================================================================
# 📎 6. INPUT HANDLING (voice + files live inside the chat bar)
# ==============================================================================
chat_params = inspect.signature(st.chat_input).parameters
NATIVE_FILE = "accept_file" in chat_params
NATIVE_AUDIO = "accept_audio" in chat_params

user_text = ""
if ss.queued_prompt:
    user_text, ss.queued_prompt = ss.queued_prompt, None

if mode == "💬 Chat":
    # Fallback for older Streamlit versions: attach + mic in a popover right above the bar
    if not (NATIVE_FILE and NATIVE_AUDIO):
        with st.popover("📎 Attach notes  •  🎙️ Voice"):
            if not NATIVE_FILE:
                fb_files = st.file_uploader("Attach notes", type=TEXT_TYPES, accept_multiple_files=True,
                                            key="fb_files")
                add_docs(fb_files)
            if not NATIVE_AUDIO and hasattr(st, "audio_input"):
                fb_audio = st.audio_input("Record your voice", key="fb_audio")
                if fb_audio is not None:
                    audio_bytes = fb_audio.getvalue()
                    h = hashlib.md5(audio_bytes).hexdigest()
                    if h != ss.last_audio_hash:
                        ss.last_audio_hash = h
                        if KEY_OK:
                            with st.spinner("Transcribing..."):
                                try:
                                    user_text = (user_text + " " + transcribe(ACTIVE_API_KEY, audio_bytes)).strip()
                                except Exception as err:
                                    st.error(f"Voice Transcription Error: {err}")
                        else:
                            st.warning("Add your Groq API key to use voice.")

    kwargs = {}
    if NATIVE_FILE:
        kwargs["accept_file"] = "multiple"
        kwargs["file_type"] = TEXT_TYPES
    if NATIVE_AUDIO:
        kwargs["accept_audio"] = True

    try:
        chat_value = st.chat_input(f"Message {safe_ai_name}...", **kwargs)
    except TypeError:
        chat_value = st.chat_input(f"Message {safe_ai_name}...")

    c_text, c_files, c_audio = unpack_chat_value(chat_value)
    if c_files:
        add_docs(c_files, force=True)
    if c_audio is not None:
        if KEY_OK:
            try:
                with st.spinner("Transcribing..."):
                    spoken = transcribe(ACTIVE_API_KEY, c_audio.getvalue())
                c_text = (c_text + " " + spoken).strip()
            except Exception as err:
                st.error(f"Voice Transcription Error: {err}")
        else:
            st.warning("Add your Groq API key to use voice.")
    if c_text.strip():
        user_text = c_text.strip()

    if user_text.strip():
        if not KEY_OK:
            st.warning(f"👈 Please paste your Groq API Key in the sidebar to unlock {safe_ai_name}.")
        else:
            ss.messages.append({"role": "user", "content": user_text.strip()})
            save_chat()
            ss.pending = True

# Sidebar attachment list (rendered AFTER input handling so it is always current)
with docs_slot.container():
    st.markdown("#### 📁 **Attached Notes**")
    if ss.docs:
        for i, dname in enumerate(list(ss.docs.keys())):
            c1, c2 = st.columns([5, 1])
            c1.caption(f"📄 {dname} · {len(ss.docs[dname].split())} words")
            c2.button("✕", key=f"rm_{i}_{dname}", on_click=remove_doc, args=(dname,))
    else:
        st.caption("Use the 📎 in the chat bar to attach notes (.txt .md .py .json .csv .pdf).")

# ==============================================================================
# 🧠 7. SYSTEM PROMPT
# ==============================================================================
if enable_exam_context and exam_days:
    exam_note = (f"Context: The student has an upcoming {safe_exam_target} test in {exam_days} days. "
                 "Only reference this timeline if they ask about schedules or planning.")
else:
    exam_note = "Context: General academic and study support."

file_injection = ""
if ss.docs:
    blocks = "\n".join(f'<document name="{n}">\n{t}\n</document>' for n, t in ss.docs.items())
    file_injection = f"\nATTACHED NOTES FOR THIS SESSION (use them when relevant):\n{blocks[:12000]}\n"

SYSTEM_PROMPT = f"""You are {ai_name}, an intelligent, casual student peer and study consultant.
{custom_instructions}

{exam_note}
{file_injection}

The student is in CBSE Class 11 (subjects: Physics, Chemistry, Biology, Maths, English) following NCERT textbooks.
When textbook excerpts are provided, base your answer on them and name the book/page.

STRICT CONVERSATION RULES:
1. ANSWER DIRECTLY: Explain concepts simply and casually. If live weather telemetry is provided in context, share the weather directly and accurately!
2. NO ROBOTIC SLOGANS: NEVER say generic hype lines like "Let's prepare for it!", "Let's do this!", or "Time to gear up!". Speak naturally like a real 11th-grade friend.
3. ANTI-CHEAT: Explain concepts, methods, and outlines. Do not complete entire graded assignments or write long essays for them.
"""

# ==============================================================================
# 🗺️ 8. STUDIO (NotebookLM-style roadmap + study tools)
# ==============================================================================
BRANCH_COLORS = ["#34d399", "#60a5fa", "#f472b6", "#fbbf24", "#a78bfa", "#fb923c"]


def llm(system, user, json_mode=False, max_tokens=1800):
    client = Groq(api_key=ACTIVE_API_KEY)
    model = get_groq_model(client)
    kw = dict(model=model, temperature=0.4, max_tokens=max_tokens,
              messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    if json_mode:
        kw["response_format"] = {"type": "json_object"}
    try:
        r = client.chat.completions.create(**kw)
    except Exception:
        if not json_mode:
            raise
        kw.pop("response_format", None)
        r = client.chat.completions.create(**kw)
    return (r.choices[0].message.content or "").strip()


def build_source():
    parts = []
    if enable_exam_context and exam_days:
        parts.append(f"Student's focus subject: {safe_exam_target} (exam in {exam_days} days)")
    for n, t in ss.docs.items():
        parts.append(f"[NOTES: {n}]\n{t}")
    convo = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in ss.messages[-16:]
                      if str(m.get("content", "")).strip())
    if convo:
        parts.append(f"[CONVERSATION]\n{convo}")
    return "\n\n".join(parts)[:9000]


def parse_json(text):
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def clean_roadmap(data):
    if not isinstance(data, dict):
        return None
    branches = []
    for b in (data.get("branches") or [])[:6]:
        if not isinstance(b, dict) or not str(b.get("name", "")).strip():
            continue
        kids = [str(k).strip() for k in (b.get("children") or []) if str(k).strip()][:4]
        branches.append({"name": str(b["name"]).strip(), "children": kids})
    if not branches:
        return None
    return {"title": str(data.get("title") or "Study Roadmap").strip(), "branches": branches}


def short(s, n):
    s = str(s)
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def roadmap_svg(data):
    row, pad = 40, 26
    rows = sum(max(1, len(b["children"])) for b in data["branches"])
    H = rows * row + pad * 2
    W = 980
    cy = H / 2
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
           f'style="width:100%;min-width:720px;height:auto;display:block">']
    # root
    out.append(f'<rect x="14" y="{cy-32}" width="220" height="64" rx="32" fill="#0b1520" stroke="{theme["primary"]}" stroke-width="2"/>')
    out.append(f'<text x="124" y="{cy+5}" text-anchor="middle" fill="#f8fafc" font-size="14" font-weight="700">{html.escape(short(data["title"], 22))}</text>')
    y = pad
    for bi, b in enumerate(data["branches"]):
        color = BRANCH_COLORS[bi % len(BRANCH_COLORS)]
        n = max(1, len(b["children"]))
        by = y + n * row / 2
        out.append(f'<path d="M234 {cy} C 280 {cy}, 270 {by}, 316 {by}" fill="none" stroke="{color}" stroke-width="2.2" opacity="0.85"/>')
        out.append(f'<rect x="316" y="{by-21}" width="260" height="42" rx="21" fill="#0b1520" stroke="{color}" stroke-width="2"/>')
        out.append(f'<circle cx="341" cy="{by}" r="12" fill="{color}"/>')
        out.append(f'<text x="341" y="{by+4.5}" text-anchor="middle" fill="#04080c" font-size="12" font-weight="800">{bi+1}</text>')
        out.append(f'<text x="360" y="{by+4.5}" fill="#f1f5f9" font-size="13" font-weight="600">{html.escape(short(b["name"], 24))}</text>')
        for ci, kid in enumerate(b["children"]):
            ky = y + ci * row + row / 2
            out.append(f'<path d="M576 {by} C 610 {by}, 604 {ky}, 640 {ky}" fill="none" stroke="{color}" stroke-width="1.6" opacity="0.7"/>')
            out.append(f'<rect x="640" y="{ky-16}" width="326" height="32" rx="16" fill="rgba(15,23,42,0.9)" stroke="{color}" stroke-opacity="0.6"/>')
            out.append(f'<text x="656" y="{ky+4}" fill="#cbd5e1" font-size="12">{html.escape(short(kid, 42))}</text>')
        y += n * row
    out.append("</svg>")
    return (
        '<html><body style="margin:0;background:transparent;font-family:Plus Jakarta Sans,Segoe UI,sans-serif;'
        'overflow-x:auto">' + "".join(out) + "</body></html>"
    ), H


def roadmap_markdown(data):
    lines = [f"# {data['title']}", ""]
    for i, b in enumerate(data["branches"], 1):
        lines.append(f"## {i}. {b['name']}")
        lines += [f"- {k}" for k in b["children"]]
        lines.append("")
    return "\n".join(lines)


STUDIO_SYS = ("You are a study-material generator for a school student. Base everything on the provided notes and "
              "conversation. If the material is thin, use well-established knowledge of the topic it mentions. "
              "Be accurate, concise and student-friendly.")


def generate_studio(kind):
    source = build_source()
    if not source.strip():
        st.info("Chat with me or attach notes first. Studio builds from those.")
        return
    try:
        with st.spinner("Building..."):
            if kind == "roadmap":
                raw = llm(
                    STUDIO_SYS,
                    "Create a study ROADMAP as JSON only, exactly in this shape:\n"
                    '{"title": "short topic title", "branches": [{"name": "step or theme", "children": ["sub-point", "sub-point"]}]}\n'
                    "Rules: 4 to 6 branches ordered as a logical learning path; 2 to 4 children each; every label under 40 characters.\n\n"
                    f"MATERIAL:\n{source}",
                    json_mode=True, max_tokens=1200,
                )
                data = clean_roadmap(parse_json(raw))
                if not data:
                    st.error("Couldn't build the roadmap. Try again.")
                    return
                ss.studio["roadmap"] = data
            else:
                prompts = {
                    "guide": "Write a concise STUDY GUIDE in markdown: key ideas, definitions, and 5 common mistakes.",
                    "cards": "Write 10 FLASHCARDS in markdown. Format each as **Q:** question then **A:** answer.",
                    "quiz": "Write a 6-question multiple-choice QUIZ in markdown with options A-D, then an answer key at the end.",
                }
                ss.studio[kind] = llm(STUDIO_SYS, f"{prompts[kind]}\n\nMATERIAL:\n{source}", max_tokens=1600)
        ss.studio_active = kind
    except Exception as e:
        st.error(f"Studio Error: {e}")


if mode == "📚 Library":
    render_library()

if mode == "🗺️ Studio":
    if not KEY_OK:
        st.warning("Add your Groq API key in the sidebar to use Studio.")
    st.markdown('<div class="studio-head">// STUDIO · BUILT FROM YOUR CHAT + NOTES</div>', unsafe_allow_html=True)
    s1, s2 = st.columns(2)
    with s1:
        go_road = st.button("🗺️ Roadmap", key="st_road", use_container_width=True, disabled=not KEY_OK)
        go_cards = st.button("🃏 Flashcards", key="st_cards", use_container_width=True, disabled=not KEY_OK)
    with s2:
        go_guide = st.button("📘 Study Guide", key="st_guide", use_container_width=True, disabled=not KEY_OK)
        go_quiz = st.button("❓ Quiz", key="st_quiz", use_container_width=True, disabled=not KEY_OK)

    for flag, kind in [(go_road, "roadmap"), (go_cards, "cards"), (go_guide, "guide"), (go_quiz, "quiz")]:
        if flag:
            generate_studio(kind)

    active = ss.studio_active
    if active == "roadmap" and ss.studio.get("roadmap"):
        data = ss.studio["roadmap"]
        page, height = roadmap_svg(data)
        components.html(page, height=int(height * 0.78) + 24, scrolling=True)
        st.download_button("📥 Download roadmap (.md)", roadmap_markdown(data),
                           file_name=f"{clean_name}_roadmap.md", mime="text/markdown", use_container_width=True)
    elif active in ("guide", "cards", "quiz") and ss.studio.get(active):
        st.markdown(ss.studio[active])
    else:
        st.caption("Pick a tool above. The Roadmap turns your chat and notes into a visual mind map.")

# ==============================================================================
# 🚀 9. CHAT VIEW
# ==============================================================================
if mode == "💬 Chat":
    if ss.messages:
        st.button("➕ New chat", key="new_chat_top", on_click=new_chat)
    if len(ss.messages) == 0 and not ss.pending:
        st.markdown(f"""
        <div class="hero-container">
            <div class="hero-title">Meet {html.escape(safe_ai_name)}.</div>
            <div class="hero-subtitle">{html.escape(safe_ai_tagline)}</div>
        </div>
        """, unsafe_allow_html=True)
        st.caption("✨ **Quick Directives (Optional):**")
        col1, col2 = st.columns(2)
        with col1:
            st.button("🧪 3-Day Triage Plan", key="q1", use_container_width=True, on_click=queue_prompt,
                      args=("Can you help me organize a realistic 3-day triage study plan without burning out?",))
            st.button("🧠 Focus & Pomodoro", key="q2", use_container_width=True, on_click=queue_prompt,
                      args=("What is a practical Pomodoro routine for a 2-hour study session?",))
        with col2:
            st.button("😰 Calm Test Anxiety", key="q3", use_container_width=True, on_click=queue_prompt,
                      args=("I'm feeling really stressed about exams right now. Can we do a quick calm-down routine?",))
            st.button("🍎 Smart Study Fuel", key="q4", use_container_width=True, on_click=queue_prompt,
                      args=("What are the best snacks to avoid brain fog during long revision sessions?",))

    for msg in ss.messages:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        with st.chat_message(role, avatar=ai_avatar if role == "assistant" else "👤"):
            st.markdown(msg.get("content", ""))
            if msg.get("telemetry"):
                st.markdown(f'<div class="telemetry-chip">{msg["telemetry"]}</div>', unsafe_allow_html=True)

    # Generate the reply for the message that was just added
    if ss.pending and ss.messages and ss.messages[-1].get("role") == "user":
        with st.chat_message("assistant", avatar=ai_avatar):
            try:
                client = Groq(api_key=ACTIVE_API_KEY)
                active_model = get_groq_model(client)

                dynamic_system = SYSTEM_PROMPT
                last_q = ss.messages[-1]["content"]

                weather = get_live_weather(last_q)
                if weather:
                    dynamic_system += (f"\n\n[REAL-TIME DATA INJECTION]: {weather}. "
                                       "Use this live data to answer the user's weather question accurately!")

                # NCERT textbook + PYQ passages from the Library folders
                focus = ss.get("lib_focus")
                if focus and focus.get("prompt") != last_q:
                    focus = None
                with st.spinner("Checking your textbooks..."):
                    dynamic_system += library_context(last_q, focus)

                clean_history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in ss.messages[-12:]
                    if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()
                ]
                payload = [{"role": "system", "content": dynamic_system}] + clean_history

                start_time = time.time()
                stream = client.chat.completions.create(model=active_model, messages=payload, stream=True)

                def stream_chunks():
                    for chunk in stream:
                        if chunk.choices:
                            delta = getattr(chunk.choices[0], "delta", None)
                            content = getattr(delta, "content", None) if delta else None
                            if content:
                                yield content

                response_text = st.write_stream(stream_chunks())
                if not isinstance(response_text, str):
                    response_text = "".join(str(x) for x in response_text)
                if not response_text.strip():
                    raise RuntimeError("The model returned an empty reply. Try again.")

                elapsed = max(time.time() - start_time, 0.05)
                est_tokens = max(int(len(response_text.split()) * 1.33), 1)
                telemetry_str = f"⚡ {elapsed:.2f}s LATENCY &bull; ~{int(est_tokens / elapsed)} TOK/S &bull; GROQ LPU™ HARDWARE"
                st.markdown(f'<div class="telemetry-chip">{telemetry_str}</div>', unsafe_allow_html=True)

                ss.messages.append({"role": "assistant", "content": response_text, "telemetry": telemetry_str})
                save_chat()
                ss.pending = False
            except Exception as e:
                ss.pending = False
                if ss.messages and ss.messages[-1].get("role") == "user":
                    ss.messages.pop()
                    save_chat()
                st.error(f"Inference Engine Error: {e}")

    if ss.messages:
        auto_scroll()

# ==============================================================================
# 💾 10. SIDEBAR EXPORT / RESET (filled last so it always matches the chat)
# ==============================================================================
with export_slot.container():
    if ss.messages:
        export_text = f"CLOVER OS // STUDY ROADMAP\nStudent: {student_name}\nAgent: {ai_name}\n" + "=" * 40 + "\n\n"
        for m in ss.messages:
            sender = student_name if m.get("role") == "user" else ai_name
            export_text += f"[{sender}]:\n{m.get('content', '')}\n\n"
        st.download_button("📥 Export Session (.txt)", export_text, file_name=f"{clean_name}_study_roadmap.txt",
                           mime="text/plain", use_container_width=True)
    if ss.messages:
        st.button("🗑️ Delete this chat", key="del_current", use_container_width=True, on_click=delete_current_chat)


def render_history():
    st.button("➕ New chat", key="new_chat_side", use_container_width=True, on_click=new_chat)
    chats = list_chats()
    if not chats:
        st.caption("No saved chats yet. Your conversations will show up here.")
        return
    try:
        box = st.container(height=340) if len(chats) > 7 else st.container()
    except TypeError:
        box = st.container()
    with box:
        last_group = None
        for c in chats:
            grp = group_label(c["updated"])
            if grp != last_group:
                st.caption(grp.upper())
                last_group = grp
            cid = c["id"]
            if ss.get("confirm_del") == cid:
                st.caption(f"Delete “{_trim(c['title'], 28)}”?")
                y, n = st.columns(2)
                y.button("Delete", key=f"yes_{cid}", on_click=delete_chat, args=(cid,))
                n.button("Cancel", key=f"no_{cid}", on_click=cancel_delete)
            else:
                a, b = st.columns([5, 1])
                label = ("● " if cid == ss.chat_id else "") + _trim(c["title"], 26)
                a.button(label, key=f"open_{cid}", on_click=open_chat, args=(cid,), help=c["title"])
                b.button("🗑", key=f"del_{cid}", on_click=ask_delete, args=(cid,), help="Delete chat")


with history_slot.container():
    render_history()

