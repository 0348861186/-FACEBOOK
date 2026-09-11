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
import threading

from google import genai
from google.genai import types
from PIL import Image
import io

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

# Sử dụng gemini-2.5-flash cho tác vụ sinh ảnh bằng text-to-image
GEMINI_MODEL = "gemini-2.5-flash" 

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
    content_hash = hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
    conn = db()
    cur = conn.execute(
        "INSERT INTO ads (content, content_hash, created_at) VALUES (?, ?, ?)",
        (content.strip(), content_hash, datetime.now().isoformat())
    )
    ad_id = cur.lastrowid
    conn.commit()
    conn.close()
    return ad_id

def get_latest_ad():
    conn = db()
    row = conn.execute("SELECT * FROM ads ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row

def get_latest_poster():
    conn = db()
    row = conn.execute("SELECT * FROM posters ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row

def get_poster(poster_id):
    conn = db()
    row = conn.execute("SELECT * FROM posters WHERE id = ?", (poster_id,)).fetchone()
    conn.close()
    return row

def get_next_version(ad_id):
    conn = db()
    row = conn.execute("SELECT MAX(version) AS version FROM posters WHERE ad_id = ?", (ad_id,)).fetchone()
    conn.close()
    if row["version"] is None:
        return 1
    return row["version"] + 1

def get_styles(ad_id):
    conn = db()
    rows = conn.execute(
        "SELECT style FROM posters WHERE ad_id = ? ORDER BY id DESC LIMIT 20",
        (ad_id,)
    ).fetchall()
    conn.close()
    return [r["style"] for r in rows if r["style"]]

def save_poster(ad_id, version, image_path, style):
    conn = db()
    cur = conn.execute(
        "INSERT INTO posters (ad_id, version, image_path, style, created_at) VALUES (?, ?, ?, ?, ?)",
        (ad_id, version, str(image_path), style, datetime.now().isoformat())
    )
    poster_id = cur.lastrowid
    conn.commit()
    conn.close()
    return poster_id

def save_revision(poster_id, request):
    conn = db()
    conn.execute(
        "INSERT INTO revisions (poster_id, request, created_at) VALUES (?, ?, ?)",
        (poster_id, request, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def update_poster_telegram_id(poster_id, msg_id):
    conn = db()
    conn.execute("UPDATE posters SET telegram_message_id = ? WHERE id = ?", (msg_id, poster_id))
    conn.commit()
    conn.close()

# ============================================================
# GEMINI AI (Sinh ảnh bằng Google GenAI SDK mới)
# ============================================================

import os

def gemini_client():
    if not GEMINI_API_KEY:
        raise RuntimeError("Chưa cấu hình GEMINI_API_KEY.")
    # Đảm bảo SDK mới nhận diện đúng API key thay vì OAuth
    os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
    return genai.Client()

def create_design_prompt(content, previous_styles=None, revision=None):
    previous_styles = previous_styles or []
    styles_text = "\n".join(f"- {x}" for x in previous_styles)
    if not styles_text:
        styles_text = "Chưa có poster trước đó."

    prompt = f"""
Bạn là một Art Director chuyên nghiệp, chuyên thiết kế poster quảng cáo và tuyển dụng.
Hãy tạo một bản mô tả phối cảnh/hình ảnh poster quảng cáo cực kỳ bắt mắt, hiện đại, chuyên nghiệp, cao cấp.

==================================================
NỘI DUNG QUẢNG CÁO GỐC
==================================================
{content}

==================================================
YÊU CẦU THIẾT KẾ
==================================================
- Giữ chính xác nội dung quan trọng. Tiếng Việt có dấu chính xác.
- Tiêu đề chính cực kỳ nổi bật, Typography chuyên nghiệp.
- Bố cục rõ ràng, tối ưu hiển thị trên điện thoại di động.

==================================================
CÁC PHONG CÁCH ĐÃ TỪNG DÙNG (TRÁNH TRÙNG LẶP)
==================================================
{styles_text}

TUYỆT ĐỐI không lặp lại thiết kế cũ. Hãy chọn một tone màu, bố cục, background, vị trí text và góc nhìn hoàn toàn mới.
"""
    if revision:
        prompt += f"\n\n==================================================\nYÊU CẦU CHỈNH SỬA TỪ KHÁCH HÀNG\n==================================================\n{revision}\nHãy áp dụng chỉnh sửa này một cách triệt để vào thiết kế mới."
    return prompt

def generate_image(content, output_path, previous_styles=None, revision=None, previous_image=None):
    client = gemini_client()
    
    # 1. Dùng Gemini Flash để tạo một Prompt mô tả hình ảnh tối ưu dựa trên nội dung quảng cáo
    meta_prompt = create_design_prompt(content, previous_styles, revision)
    meta_response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=meta_prompt
    )
    optimized_image_prompt = meta_response.text
    
    # Random style định danh để lưu vào DB tránh trùng lặp
    generated_style = f"Style-{random.randint(1000, 9999)}"
    
    # 2. Sử dụng API sinh ảnh Imagen thông qua SDK GenAI (Sử dụng model Imagen 3)
    result = client.models.generate_images(
        model='imagen-3.0-generate-002',
        prompt=optimized_image_prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="1:1", # Thiết kế poster dạng hình vuông mxh
            output_mime_type="image/png"
        )
    )
    
    # 3. Lưu ảnh được sinh ra về ổ đĩa
    for generated_image in result.generated_images:
        image_bytes = base64.b64decode(generated_image.image.image_bytes)
        image = Image.open(io.BytesIO(image_bytes))
        image.save(output_path)
        break
        
    return generated_style

# ============================================================
# TELEGRAM INTEGRATION
# ============================================================

def send_poster_to_telegram(image_path, caption):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(image_path, "rb") as img_file:
            files = {"photo": img_file}
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
            response = requests.post(url, files=files, data=data).json()
            if response.get("ok"):
                return response["result"]["message_id"]
    except Exception as e:
        print(f"Lỗi gửi Telegram: {e}")
    return None

def check_telegram_feedback():
    if not TELEGRAM_BOT_TOKEN:
        return None, None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        response = requests.get(url).json()
        if response.get("ok") and response.get("result"):
            # Duyệt từ dưới lên để tìm tin nhắn phản hồi (reply) mới nhất
            for update in reversed(response["result"]):
                message = update.get("message") or update.get("channel_post")
                if message and "reply_to_message" in message:
                    reply_to = message["reply_to_message"]
                    tg_msg_id = str(reply_to.get("message_id"))
                    text = message.get("text", "").strip()
                    
                    # Tìm xem tin nhắn được reply có khớp với poster nào trong DB không
                    conn = db()
                    poster = conn.execute("SELECT * FROM posters WHERE telegram_message_id = ?", (tg_msg_id,)).fetchone()
                    conn.close()
                    
                    if poster and text:
                        return poster, text
    except Exception as e:
        print(f"Lỗi đọc Telegram: {e}")
    return None, None

# ============================================================
# AUTOMATED CRON JOB (10:00 AM Hàng Ngày)
# ============================================================

def auto_cron_job():
    while True:
        now = datetime.now()
        # Chạy chính xác vào lúc 10h00 sáng
        if now.hour == 10 and now.minute == 0:
            latest_ad = get_latest_ad()
            content = "Ưu đãi đặc biệt ngày mới! Hãy trải nghiệm ngay dịch vụ đẳng cấp của chúng tôi."
            ad_id = None
            if latest_ad:
                content = latest_ad["content"]
                ad_id = latest_ad["id"]
            else:
                ad_id = save_ad(content)
            
            version = get_next_version(ad_id)
            filename = f"ad_{ad_id}v{version}{int(time.time())}.png"
            output_path = POSTER_DIR / filename
            previous_styles = get_styles(ad_id)
            try:
                style = generate_image(content, output_path, previous_styles=previous_styles)
                poster_id = save_poster(ad_id, version, output_path, style)
                caption = f"📢 [TỰ ĐỘNG 10H SÁNG]\nPoster cho chiến dịch quảng cáo mới.\n\nNếu muốn sửa đổi, hãy REPLY tin nhắn này và viết yêu cầu!"
                msg_id = send_poster_to_telegram(output_path, caption)
                if msg_id:
                    update_poster_telegram_id(poster_id, msg_id)
            except Exception as e:
                print(f"Lỗi Cron Job tự động sinh poster: {e}")
            
            time.sleep(60) # Ngủ 1 phút để không bị lặp lại trong cùng 1 phút 10h00
        time.sleep(30)

if "cron_started" not in st.session_state:
    st.session_state.cron_started = True
    threading.Thread(target=auto_cron_job, daemon=True).start()

# ============================================================
# STREAMLIT UI DASHBOARD
# ============================================================

st.title("🎨 AI Poster Studio & Automation Dashboard")
st.write("Giải pháp biến văn bản quảng cáo thô thành Poster chuyên nghiệp tự động gửi và duyệt qua Telegram.")

latest_ad = get_latest_ad()
default_text = latest_ad["content"] if latest_ad else ""

# 1) Dashboard có ô để dán nội dung quảng cáo
ad_content = st.text_area("✍️ Nhập hoặc dán nội dung quảng cáo tại đây:", value=default_text, height=150)

col_actions = st.columns([2, 2, 4])

with col_actions[0]:
    # 6) Dashboard có thêm nút nhấn "Tạo poster" ngay nếu cần
    btn_create = st.button("🚀 Tạo Poster Ngay", use_container_width=True, type="primary")

with col_actions[1]:
    btn_sync = st.button("🔄 Kiểm Tra Feedback Telegram", use_container_width=True)

# Kiểm tra và xử lý đồng bộ sửa poster từ Telegram tự động khi bấm nút
if btn_sync:
    poster_row, feedback_text = check_telegram_feedback()
    if poster_row and feedback_text:
        st.warning(f"Phát hiện yêu cầu chỉnh sửa từ Telegram cho Poster v{poster_row['version']}: \"{feedback_text}\"")
        with st.spinner("Gemini đang thiết kế lại dựa trên feedback của bạn..."):
            ad_id = poster_row["ad_id"]
            conn = db()
            ad_row = conn.execute("SELECT content FROM ads WHERE id = ?", (ad_id,)).fetchone()
            conn.close()
            
            new_version = get_next_version(ad_id)
            filename = f"ad_{ad_id}_v{new_version}rev{int(time.time())}.png"
            output_path = POSTER_DIR / filename
            previous_styles = get_styles(ad_id)
            try:
                style = generate_image(
                    content=ad_row["content"],
                    output_path=output_path,
                    previous_styles=previous_styles,
                    revision=feedback_text,
                    previous_image=poster_row["image_path"]
                )
                new_poster_id = save_poster(ad_id, new_version, output_path, style)
                save_revision(poster_row["id"], feedback_text)
                
                new_msg_id = send_poster_to_telegram(
                    output_path,
                    f"✨ Bản cập nhật Version {new_version} theo yêu cầu: \"{feedback_text}\"\n\nHãy REPLY tin nhắn này nếu cần sửa tiếp!"
                )
                if new_msg_id:
                    update_poster_telegram_id(new_poster_id, new_msg_id)
                st.success("Đã cập nhật bản thiết kế mới và gửi lại sang Telegram thành công!")
            except Exception as e:
                st.error(f"Lỗi khi sửa đổi ảnh: {e}")
    else:
        st.info("Không có yêu cầu chỉnh sửa mới nào được tìm thấy trên Telegram (Vui lòng đảm bảo bạn đã dùng chức năng 'Reply' chính xác ảnh poster trên Telegram).")

# Logic xử lý khi nhấn "Tạo Poster Ngay"
if btn_create:
    if not ad_content.strip():
        st.error("Vui lòng nhập nội dung quảng cáo trước khi tạo!")
    else:
        # 5) Nếu không dán nội dung mới (hoặc nội dung trùng cũ) thì lấy nội dung cũ, hệ thống vẫn xử lý tránh trùng lặp style nhờ DB
        current_ad_id = None
        if latest_ad and latest_ad["content"].strip() == ad_content.strip():
            current_ad_id = latest_ad["id"]
        else:
            current_ad_id = save_ad(ad_content)
        
        with st.spinner("Art Director Gemini đang sáng tạo Poster..."):
            version = get_next_version(current_ad_id)
            filename = f"ad_{current_ad_id}v{version}{int(time.time())}.png"
            output_path = POSTER_DIR / filename
            previous_styles = get_styles(current_ad_id)
            try:
                style = generate_image(ad_content, output_path, previous_styles=previous_styles)
                poster_id = save_poster(current_ad_id, version, output_path, style)
                
                # 3) Poster tạo xong thì bot đem lên Telegram để duyệt
                caption = f"🎨 Poster Mới Thiết Kế (V{version})\nNội dung: {ad_content[:50]}...\n\nNếu chưa ưng ý, hãy dùng tính năng REPLY tin nhắn này để gửi yêu cầu chỉnh sửa!"
                msg_id = send_poster_to_telegram(output_path, caption)
                if msg_id:
                    update_poster_telegram_id(poster_id, msg_id)
                
                st.success("Đã sinh Poster chuyên nghiệp thành công và gửi bản duyệt sang Telegram!")
            except Exception as e:
                st.error(f"Quá trình sinh ảnh gặp lỗi: {e}")

# Hiển thị khu vực Poster vừa tạo ra gần nhất
st.write("---")
st.subheader("🖼️ Trực quan hóa Poster mới nhất")

latest_poster_row = get_latest_poster()
if latest_poster_row and os.path.exists(latest_poster_row["image_path"]):
    col_view, col_info = st.columns([5, 3])
    with col_view:
        st.image(latest_poster_row["image_path"], use_container_width=True)
    with col_info:
        st.markdown(f"Thông tin thiết kế:")
        st.write(f"- Mã quảng cáo: #{latest_poster_row['ad_id']}")
        st.write(f"- Phiên bản: v{latest_poster_row['version']}")
        st.write(f"- Phong cách định danh: {latest_poster_row['style']}")
        st.write(f"- Thời gian tạo: {latest_poster_row['created_at']}")
        
        # 2) Có nút download poster khi tạo xong
        with open(latest_poster_row["image_path"], "rb") as file:
            btn_download = st.download_button(
                label="📥 Tải Poster Chất Lượng Cao Về Máy",
                data=file,
                file_name=f"poster_v{latest_poster_row['version']}.png",
                mime="image/png",
                use_container_width=True
            )
else:
    st.info("Chưa có poster nào được tạo. Hãy nhấn nút 'Tạo Poster Ngay' phía trên.")
