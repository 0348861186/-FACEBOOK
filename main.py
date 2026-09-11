import streamlit as st
import sqlite3
import os
import json
import base64
import hashlib
import requests
import random
import time
from pathlib import Path
from datetime import datetime

from google import genai
from google.genai import types
from PIL import Image


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Poster Studio",
    page_icon="🎨",
    layout="wide"
)

DB_FILE = "poster.db"
POSTER_DIR = Path("generated_posters")
POSTER_DIR.mkdir(exist_ok=True)

GEMINI_MODEL = "gemini-2.5-flash-image"


# ============================================================
# SECRETS
# ============================================================

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "")


# ============================================================
# DATABASE
# ============================================================

def db():
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_database():

    conn = db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            content_hash TEXT,
            created_at TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS posters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_id INTEGER,
            version INTEGER,
            image_path TEXT,
            style TEXT,
            telegram_message_id TEXT,
            approved INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY(ad_id) REFERENCES ads(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poster_id INTEGER,
            request TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


init_database()


# ============================================================
# DATABASE FUNCTIONS
# ============================================================

def save_ad(content):

    content_hash = hashlib.sha256(
        content.strip().encode("utf-8")
    ).hexdigest()

    conn = db()

    cur = conn.execute(
        """
        INSERT INTO ads
        (content, content_hash, created_at)
        VALUES (?, ?, ?)
        """,
        (
            content.strip(),
            content_hash,
            datetime.now().isoformat()
        )
    )

    ad_id = cur.lastrowid

    conn.commit()
    conn.close()

    return ad_id


def get_latest_ad():

    conn = db()

    row = conn.execute(
        """
        SELECT *
        FROM ads
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    conn.close()

    return row


def get_latest_poster():

    conn = db()

    row = conn.execute(
        """
        SELECT *
        FROM posters
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    conn.close()

    return row


def get_poster(poster_id):

    conn = db()

    row = conn.execute(
        """
        SELECT *
        FROM posters
        WHERE id = ?
        """,
        (poster_id,)
    ).fetchone()

    conn.close()

    return row


def get_next_version(ad_id):

    conn = db()

    row = conn.execute(
        """
        SELECT MAX(version) AS version
        FROM posters
        WHERE ad_id = ?
        """,
        (ad_id,)
    ).fetchone()

    conn.close()

    if row["version"] is None:
        return 1

    return row["version"] + 1


def get_styles(ad_id):

    conn = db()

    rows = conn.execute(
        """
        SELECT style
        FROM posters
        WHERE ad_id = ?
        ORDER BY id DESC
        LIMIT 20
        """,
        (ad_id,)
    ).fetchall()

    conn.close()

    return [
        r["style"]
        for r in rows
        if r["style"]
    ]


def save_poster(
    ad_id,
    version,
    image_path,
    style
):

    conn = db()

    cur = conn.execute(
        """
        INSERT INTO posters
        (
            ad_id,
            version,
            image_path,
            style,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            ad_id,
            version,
            str(image_path),
            style,
            datetime.now().isoformat()
        )
    )

    poster_id = cur.lastrowid

    conn.commit()
    conn.close()

    return poster_id


def save_revision(
    poster_id,
    request
):

    conn = db()

    conn.execute(
        """
        INSERT INTO revisions
        (
            poster_id,
            request,
            created_at
        )
        VALUES (?, ?, ?)
        """,
        (
            poster_id,
            request,
            datetime.now().isoformat()
        )
    )

    conn.commit()
    conn.close()


def approve_poster(poster_id):

    conn = db()

    conn.execute(
        """
        UPDATE posters
        SET approved = 1
        WHERE id = ?
        """,
        (poster_id,)
    )

    conn.commit()
    conn.close()


# ============================================================
# GEMINI
# ============================================================

def gemini_client():

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "Chưa cấu hình GEMINI_API_KEY."
        )

    os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
    return genai.Client()


def create_design_prompt(
    content,
    previous_styles=None,
    revision=None
):

    previous_styles = previous_styles or []

    styles_text = "\n".join(
        f"- {x}"
        for x in previous_styles
    )

    if not styles_text:
        styles_text = "Chưa có poster trước đó."

    prompt = f"""
Bạn là một Art Director chuyên nghiệp,
chuyên thiết kế poster quảng cáo và tuyển dụng.

Hãy tạo một poster quảng cáo cực kỳ bắt mắt,
hiện đại, chuyên nghiệp, cao cấp và có khả năng
thu hút người xem ngay trong 2-3 giây đầu tiên.

==================================================
NỘI DUNG QUẢNG CÁO
==================================================

{content}

==================================================
YÊU CẦU THIẾT KẾ
==================================================

- Giữ chính xác nội dung quan trọng.
- Không tự ý bịa thông tin.
- Không tự thêm số điện thoại.
- Không tự thêm mức lương.
- Không tự thêm địa chỉ.
- Không làm sai tên công ty.
- Tiếng Việt phải có dấu chính xác.
- Tiêu đề chính cực kỳ nổi bật.
- Thông tin phụ dễ đọc.
- Typography chuyên nghiệp.
- Bố cục rõ ràng.
- Tối ưu hiển thị trên điện thoại.
- Có hình ảnh minh họa phù hợp.
- Hình ảnh phải tự nhiên.
- Không watermark.
- Không logo giả.
- Không làm poster quá nhiều chữ.
- Không làm bố cục lộn xộn.

==================================================
PHONG CÁCH
==================================================

Premium
Modern
Dynamic
Commercial
Professional
High visual impact
Mobile friendly

==================================================
CÁC THIẾT KẾ ĐÃ TỪNG DÙNG
==================================================

{styles_text}

TUYỆT ĐỐI không lặp lại thiết kế cũ.

Hãy thay đổi đáng kể:
- bố cục
- màu sắc
- hình ảnh
- typography
- composition
- vị trí tiêu đề
- background
- visual hierarchy

"""

    if revision:

        prompt += f"""

==================================================
YÊU CẦU CHỈNH SỬA
==================================================

{revision}

Hãy chỉnh sửa poster theo yêu cầu trên.

Giữ lại các thông tin chính.
Không thay đổi thông tin quảng cáo
nếu người dùng không yêu cầu.

"""

    return prompt


def generate_image(
    content,
    output_path,
    previous_styles=None,
    revision=None,
    previous_image=None
):

    client = gemini_client()

    prompt = create_design_prompt(
        content,
        previous_styles,
        revision
    )

    contents = [prompt]

    if previous_image:

        with open(
            previous_image,
            "rb"
        ) as f:

            image_bytes = f.read()

        contents.append(
            types.Part.from_bytes(
                data=image_bytes,
                mime_type="image/png"
            )
        )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=[
                "TEXT",
                "IMAGE"
            ]
        )
    )

    image_saved = False

    for part in response.candidates[0].content.parts:

        if part.inline_data:

            image_bytes = part.inline_data.data

            with open(
                output_path,
                "wb"
            ) as f:

                f.write(image_bytes)

            image_saved = True

            break

    if not image_saved:

        raise RuntimeError(
            "Gemini không trả về hình ảnh."
        )

    return output_path


# ============================================================
# TELEGRAM
# ============================================================

def telegram_api(method):

    return (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/"
        f"{method}"
    )


def telegram_send_message(
    text
):

    if not TELEGRAM_BOT_TOKEN:
        return None

    response = requests.post(
        telegram_api("sendMessage"),
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text
        },
        timeout=60
    )

    response.raise_for_status()

    return response.json()


def telegram_send_photo(
    image_path,
    caption,
    poster_id
):

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ ƯNG Ý",
                    "callback_data":
                        f"approve:{poster_id}"
                },
                {
                    "text": "✏️ CẦN SỬA",
                    "callback_data":
                        f"revise:{poster_id}"
                }
            ],
            [
                {
                    "text": "🔄 THIẾT KẾ KHÁC",
                    "callback_data":
                        f"newdesign:{poster_id}"
                }
            ]
        ]
    }

    with open(
        image_path,
        "rb"
    ) as photo:

        response = requests.post(
            telegram_api("sendPhoto"),
            data={
                "chat_id":
                    TELEGRAM_CHAT_ID,

                "caption":
                    caption,

                "reply_markup":
                    json.dumps(keyboard)
            },
            files={
                "photo": photo
            },
            timeout=120
        )

    response.raise_for_status()

    return response.json()


# ============================================================
# CREATE POSTER
# ============================================================

def create_poster(
    content,
    send_to_telegram=True,
    revision=None,
    previous_poster=None
):

    # Nếu nội dung mới
    if content.strip():

        ad_id = save_ad(
            content
        )

    else:

        latest = get_latest_ad()

        if not latest:
            raise RuntimeError(
                "Chưa có nội dung quảng cáo."
            )

        ad_id = latest["id"]

        content = latest["content"]

    version = get_next_version(
        ad_id
    )

    styles = get_styles(
        ad_id
    )

    # Tạo style ngẫu nhiên để tránh lặp
    style_variations = [
        "Corporate",
        "Japanese modern",
        "Premium recruitment",
        "Dynamic industrial",
        "Minimal luxury",
        "Bold typography",
        "Modern gradient",
        "Editorial",
        "Clean professional",
        "High energy advertising"
    ]

    style = random.choice(
        style_variations
    )

    styles.append(style)

    output_path = (
        POSTER_DIR /
        f"poster_{ad_id}_v{version}.png"
    )

    previous_image = None

    if previous_poster:

        previous_image = (
            previous_poster["image_path"]
        )

        if not os.path.exists(
            previous_image
        ):
            previous_image = None

    generate_image(
        content=content,
        output_path=output_path,
        previous_styles=styles,
        revision=revision,
        previous_image=previous_image
    )

    poster_id = save_poster(
        ad_id=ad_id,
        version=version,
        image_path=output_path,
        style=style
    )

    if revision:

        save_revision(
            poster_id,
            revision
        )

    # Telegram
    telegram_result = None

    if send_to_telegram:

        caption = (
            "🎨 AI POSTER\n\n"
            f"Version: {version}\n\n"
            "Bạn thấy poster thế nào?\n\n"
            "✅ ƯNG Ý\n"
            "✏️ CẦN SỬA\n"
            "🔄 THIẾT KẾ KHÁC\n\n"
            "Bạn cũng có thể nhắn trực tiếp "
            "yêu cầu chỉnh sửa."
        )

        telegram_result = telegram_send_photo(
            output_path,
            caption,
            poster_id
        )

    return {
        "poster_id": poster_id,
        "path": str(output_path),
        "version": version,
        "telegram": telegram_result
    }


# ============================================================
# TELEGRAM UPDATE PROCESSOR
# ============================================================

def get_telegram_updates():

    response = requests.get(
        telegram_api("getUpdates"),
        params={
            "timeout": 5
        },
        timeout=15
    )

    response.raise_for_status()

    return response.json().get(
        "result",
        []
    )


def answer_callback(
    callback_id,
    text
):

    requests.post(
        telegram_api(
            "answerCallbackQuery"
        ),
        json={
            "callback_query_id":
                callback_id,

            "text":
                text
        },
        timeout=30
    )


def process_telegram_updates():

    updates = get_telegram_updates()

    processed = []

    for update in updates:

        processed.append(
            update.get("update_id")
        )

        # ============================
        # BUTTON
        # ============================

        callback = update.get(
            "callback_query"
        )

        if callback:

            data = callback.get(
                "data",
                ""
            )

            callback_id = callback.get(
                "id"
            )

            if data.startswith(
                "approve:"
            ):

                poster_id = int(
                    data.split(":")[1]
                )

                approve_poster(
                    poster_id
                )

                answer_callback(
                    callback_id,
                    "✅ Poster đã được duyệt!"
                )

                telegram_send_message(
                    "✅ Poster đã được duyệt."
                )

            elif data.startswith(
                "revise:"
            ):

                poster_id = int(
                    data.split(":")[1]
                )

                answer_callback(
                    callback_id,
                    "✏️ Hãy gửi yêu cầu chỉnh sửa."
                )

                telegram_send_message(
                    "✏️ Hãy gửi yêu cầu chỉnh sửa.\n\n"
                    "Ví dụ:\n"
                    "• Đổi nền thành xanh\n"
                    "• Tiêu đề lớn hơn\n"
                    "• Thêm hình công nhân\n"
                    "• Làm chuyên nghiệp hơn"
                )

                st.session_state[
                    "telegram_waiting_revision"
                ] = poster_id

            elif data.startswith(
                "newdesign:"
            ):

                poster_id = int(
                    data.split(":")[1]
                )

                old_poster = get_poster(
                    poster_id
                )

                if old_poster:

                    ad = get_latest_ad()

                    if ad:

                        result = create_poster(
                            content=ad["content"],
                            send_to_telegram=True,
                            previous_poster=None
                        )

                        answer_callback(
                            callback_id,
                            "🔄 Đã tạo thiết kế mới."
                        )

            continue

        # ============================
        # MESSAGE
        # ============================

        message = update.get(
            "message"
        )

        if not message:
            continue

        text = message.get(
            "text",
            ""
        ).strip()

        if not text:
            continue

        waiting = st.session_state.get(
            "telegram_waiting_revision"
        )

        if waiting:

            poster = get_poster(
                waiting
            )

            if poster:

                ad = get_latest_ad()

                if ad:

                    result = create_poster(
                        content=ad["content"],
                        send_to_telegram=True,
                        revision=text,
                        previous_poster=poster
                    )

                    telegram_send_message(
                        "🔄 Đã xử lý yêu cầu chỉnh sửa."
                    )

            st.session_state[
                "telegram_waiting_revision"
            ] = None

    return processed


# ============================================================
# DAILY POSTER
# ============================================================

def generate_daily_poster():

    latest = get_latest_ad()

    if not latest:

        telegram_send_message(
            "⚠️ Chưa có nội dung quảng cáo."
        )

        return

    result = create_poster(
        content=latest["content"],
        send_to_telegram=True
    )

    return result


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size: 42px;
        font-weight: 800;
        text-align: center;
        margin-bottom: 5px;
    }

    .subtitle {
        text-align: center;
        color: #777;
        margin-bottom: 30px;
    }

    .status-box {
        padding: 15px;
        border-radius: 12px;
        background: rgba(100,100,100,0.08);
        margin-bottom: 15px;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="main-title">🎨 AI POSTER STUDIO</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">'
    'Gemini AI + Telegram Automation'
    '</div>',
    unsafe_allow_html=True
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ HỆ THỐNG")

    if GEMINI_API_KEY:
        st.success(
            "🟢 Gemini API"
        )
    else:
        st.error(
            "🔴 Chưa có Gemini API"
        )

    if TELEGRAM_BOT_TOKEN:
        st.success(
            "🟢 Telegram Bot"
        )
    else:
        st.error(
            "🔴 Chưa có Telegram Bot"
        )

    st.divider()

    st.info(
        "⏰ Poster tự động:\n"
        "10:00 mỗi ngày"
    )

    st.divider()

    st.caption(
        "Mỗi lần tạo poster mới, "
        "AI sẽ cố gắng thay đổi "
        "bố cục và phong cách."
    )


# ============================================================
# CONTENT INPUT
# ============================================================

latest_ad = get_latest_ad()

default_text = ""

if latest_ad:
    default_text = latest_ad["content"]


st.subheader(
    "📝 NỘI DUNG QUẢNG CÁO"
)

content = st.text_area(
    "Dán nội dung quảng cáo",
    value=default_text,
    height=280,
    placeholder=(
        "Dán nội dung quảng cáo "
        "của bạn vào đây..."
    )
)


# ============================================================
# BUTTON
# ============================================================

col1, col2 = st.columns(
    [3, 1]
)

with col1:

    create_button = st.button(
        "🎨 TẠO POSTER NGAY",
        type="primary",
        use_container_width=True
    )

with col2:

    telegram_button = st.button(
        "📱 TEST TELEGRAM",
        use_container_width=True
    )


# ============================================================
# CREATE
# ============================================================

if create_button:

    if not content.strip():

        st.error(
            "Hãy nhập nội dung quảng cáo."
        )

    else:

        with st.spinner(
            "🤖 Gemini đang thiết kế poster..."
        ):

            try:

                result = create_poster(
                    content=content,
                    send_to_telegram=True
                )

                st.session_state[
                    "current_poster"
                ] = result["path"]

                st.session_state[
                    "current_poster_id"
                ] = result["poster_id"]

                st.success(
                    f"🎉 Đã tạo poster V"
                    f"{result['version']}"
                )

            except Exception as e:

                st.error(
                    f"Lỗi: {e}"
                )


# ============================================================
# TELEGRAM TEST
# ============================================================

if telegram_button:

    try:

        telegram_send_message(
            "🟢 AI Poster Studio kết nối Telegram thành công!"
        )

        st.success(
            "Đã gửi tin nhắn test."
        )

    except Exception as e:

        st.error(
            f"Lỗi Telegram: {e}"
        )


# ============================================================
# SHOW POSTER
# ============================================================

current = st.session_state.get(
    "current_poster"
)

if current and os.path.exists(current):

    st.divider()

    st.subheader(
        "🖼️ POSTER"
    )

    left, center, right = st.columns(
        [1, 2, 1]
    )

    with center:

        st.image(
            current,
            use_container_width=True
        )

        with open(
            current,
            "rb"
        ) as f:

            poster_bytes = f.read()

        st.download_button(
            "⬇️ DOWNLOAD POSTER",
            poster_bytes,
            file_name="AI_poster.png",
            mime="image/png",
            use_container_width=True
        )


# ============================================================
# HISTORY
# ============================================================

st.divider()

st.subheader(
    "📚 LỊCH SỬ POSTER"
)

conn = db()

history = conn.execute(
    """
    SELECT *
    FROM posters
    ORDER BY id DESC
    LIMIT 20
    """
).fetchall()

conn.close()

if history:

    for poster in history:

        c1, c2, c3 = st.columns(
            [1, 3, 1]
        )

        with c1:

            if os.path.exists(
                poster["image_path"]
            ):

                st.image(
                    poster["image_path"],
                    width=120
                )

        with c2:

            st.write(
                f"**Poster V{poster['version']}**"
            )

            st.caption(
                poster["created_at"]
            )

            st.write(
                f"Style: {poster['style']}"
            )

            if poster["approved"]:

                st.success(
                    "✅ Đã duyệt"
                )

        with c3:

            if os.path.exists(
                poster["image_path"]
            ):

                with open(
                    poster["image_path"],
                    "rb"
                ) as f:

                    data = f.read()

                st.download_button(
                    "⬇️",
                    data,
                    file_name=(
                        f"poster_v"
                        f"{poster['version']}.png"
                    ),
                    mime="image/png",
                    key=f"download_{poster['id']}"
                )

        st.divider()


# ============================================================
# TELEGRAM UPDATE
# ============================================================

st.subheader(
    "🤖 TELEGRAM CONTROL"
)

if st.button(
    "🔄 KIỂM TRA COMMENT TELEGRAM",
    use_container_width=True
):

    try:

        updates = process_telegram_updates()

        st.success(
            f"Đã kiểm tra {len(updates)} update."
        )

    except Exception as e:

        st.error(
            f"Lỗi Telegram: {e}"
        )


# ============================================================
# MANUAL DAILY
# ============================================================

st.divider()

st.subheader(
    "☀️ POSTER HÀNG NGÀY"
)

if st.button(
    "🚀 TẠO POSTER HÀNG NGÀY NGAY",
    use_container_width=True
):

    try:

        with st.spinner(
            "Đang tạo poster hàng ngày..."
        ):

            result = generate_daily_poster()

        st.success(
            "Đã tạo và gửi poster hàng ngày."
        )

        if result:

            st.session_state[
                "current_poster"
            ] = result["path"]

            st.rerun()

    except Exception as e:

        st.error(
            f"Lỗi: {e}"
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "AI Poster Studio • Gemini AI • Telegram"
)
