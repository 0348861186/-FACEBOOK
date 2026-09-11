import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
import requests
import io
import time
import schedule
import threading
import json
import os

# --- CẤU HÌNH API ---
# Trên Streamlit Cloud, hãy cấu hình các key này trong phần Settings -> Secrets
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "YOUR_GEMINI_KEY")
TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

DB_FILE = "poster_data.json"

# --- HÀM LƯU TRỮ DỮ LIỆU CŨ (Yêu cầu 5) ---
def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_content": "Ưu đãi sốc hôm nay!", "history_styles": []}

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

data_store = load_data()

# --- HÀM TẠO POSTER BẰNG PILLOW + GEMINI (Yêu cầu 2, 5) ---
def generate_poster_image(content, feedback=""):
    # Sử dụng Gemini để phân tích nội dung và đưa ra thiết kế (Màu sắc, Khẩu hiệu ngắn gọn)
    prompt = f"""
    Hãy phân tích nội dung quảng cáo sau: '{content}'. 
    Yêu cầu sửa đổi bổ sung (nếu có): '{feedback}'.
    Hãy rút gọn nó thành 1 tiêu đề chính (dưới 5 từ) và 1 thông điệp phụ (dưới 10 từ).
    Đồng thời gợi ý 1 mã màu nền (Hex) và 1 mã màu chữ tương phản phù hợp với ngành hàng.
    Trả về kết quả chính xác theo định dạng JSON sau:
    {{"headline": "TIÊU ĐỀ", "subtext": "Thông điệp phụ", "bg_color": "#HEX", "text_color": "#HEX"}}
    """
    try:
        response = model.generate_content(prompt)
        # Làm sạch chuỗi JSON từ phản hồi của Gemini
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        design = json.loads(clean_text)
    except Exception:
        # Dự phòng nếu Gemini lỗi định dạng
        design = {"headline": "QUẢNG CÁO HOT", "subtext": content[:20], "bg_color": "#FF4B4B", "text_color": "#FFFFFF"}

    # Đảm bảo không trùng lặp phong cách hoàn toàn nếu dùng lại nội dung cũ
    if design["bg_color"] in data_store["history_styles"]:
        design["bg_color"] = "#1E1E1E" # Đổi màu nền khác để tránh trùng lặp

    # Vẽ ảnh Poster (Kích thước chuẩn vuông 1080x1080 cho mạng xã hội)
    img = Image.new("RGB", (1080, 1080), color=design["bg_color"])
    draw = ImageDraw.Draw(img)
    
    # Cấu hình Font (Streamlit Cloud cần font mặc định hoặc tải font .ttf về thư mục app)
    try:
        font_title = ImageFont.truetype("Arial.ttf", 80)
        font_body = ImageFont.truetype("Arial.ttf", 45)
    except:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()

    # Vẽ chữ lên ảnh (Căn giữa cơ bản)
    draw.text((540, 400), design["headline"], fill=design["text_color"], font=font_title, anchor="mm")
    draw.text((540, 600), design["subtext"], fill=design["text_color"], font=font_body, anchor="mm")
    draw.text((540, 900), "Thiết kế bởi Gemini AI", fill=design["text_color"], font=font_body, anchor="mm")

    # Lưu lịch sử màu sắc để tránh trùng lặp lần sau
    data_store["history_styles"].append(design["bg_color"])
    if len(data_store["history_styles"]) > 10: data_store["history_styles"].pop(0)
    save_data(data_store)

    return img

# --- HÀM GỬI LÊN TELEGRAM (Yêu cầu 3, 4) ---
def send_poster_to_telegram(img, caption="Poster quảng cáo mới của bạn!"):
    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    url = f"https://telegram.org{TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {'photo': ('poster.png', bio, 'image/png')}
    data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
    res = requests.post(url, files=files, data=data)
    return res.json()

# --- HÀM KIỂM TRA PHẢN HỒI TỪ TELEGRAM (SỬA ĐỔI) (Yêu cầu 3) ---
def check_telegram_feedback():
    url = f"https://telegram.org{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        res = requests.get(url).json()
        if res.get("ok") and res.get("result"):
            # Lấy tin nhắn mới nhất
            last_update = res["result"][-1]
            message = last_update.get("message", {})
            text = message.get("text", "")
            # Nếu tin nhắn là một phản hồi (reply) hoặc bắt đầu bằng chữ "Sửa:"
            if text.lower().startswith("sửa:"):
                feedback = text[4:].strip()
                return feedback
    except:
        pass
    return None

# --- CHẠY TỰ ĐỘNG 10H SÁNG (Yêu cầu 4) ---
def daily_job():
    content = data_store["last_content"]
    img = generate_poster_image(content)
    send_poster_to_telegram(img, caption="[TỰ ĐỘNG 10H SÁNG] Poster hôm nay của bạn.")

def run_scheduler():
    schedule.every().day.at("10:00").do(daily_job)
    while True:
        schedule.run_pending()
        time.sleep(60)

# Khởi chạy luồng chạy ngầm cho Schedule nếu chưa có
if "scheduler_started" not in st.session_state:
    st.session_state.scheduler_started = True
    threading.Thread(target=run_scheduler, daemon=True).start()

# --- GIAO DIỆN STREAMLIT DASHBOARD ---
st.set_page_config(page_title="AI Poster Generator", layout="centered")
st.title("🎨 Hệ Thống Tạo Poster Tự Động Với Gemini AI")

# Ô dán nội dung (Yêu cầu 1)
user_content = st.text_area("1) Nhập hoặc dán nội dung quảng cáo tại đây:", value=data_store["last_content"])

# Nút bấm tạo ngay (Yêu cầu 6)
col1, col2 = st.columns(2)
with col1:
    btn_create = st.button("🚀 Tạo Poster Ngay")
with col2:
    btn_check_fb = st.button("🔄 Kiểm tra phản hồi từ Telegram")

# Xử lý Logic khi nhấn tạo poster
if btn_create:
    if user_content.strip():
        data_store["last_content"] = user_content
        save_data(data_store)
        
    st.info("Gemini đang thiết kế và phối màu...")
    poster_img = generate_poster_image(data_store["last_content"])
    st.session_state["current_poster"] = poster_img
    
    # Gửi lên telegram liền (Yêu cầu 3)
    st.info("Đang gửi bản nháp lên Telegram để bạn duyệt...")
    send_poster_to_telegram(poster_img, caption="Bản nháp poster mới. Nếu chưa ưng ý, hãy reply lại tin nhắn này với cú pháp: 'Sửa: [Nội dung cần sửa]'")
    st.success(" Đã gửi lên Telegram!")

# Kiểm tra phản hồi từ Telegram để sửa đổi (Yêu cầu 3)
if btn_check_fb:
    feedback = check_telegram_feedback()
    if feedback:
        st.warning(f"Phát hiện yêu cầu sửa từ Telegram: '{feedback}'")
        st.info("Gemini đang tiến hành sửa đổi lại poster...")
        poster_img = generate_poster_image(data_store["last_content"], feedback=feedback)
        st.session_state["current_poster"] = poster_img
        send_poster_to_telegram(poster_img, caption="Bản poster đã được sửa theo yêu cầu của bạn!")
        st.success("Đã cập nhật bản sửa đổi mới lên Telegram!")
    else:
        st.info("Chưa thấy yêu cầu sửa mới nào từ Telegram (Cú pháp đúng: 'Sửa: nội dung thay đổi')")

# Hiển thị Poster và nút Download (Yêu cầu 2)
if "current_poster" in st.session_state:
    st.markdown("### 🖼️ Kết quả Poster hiện tại:")
    st.image(st.session_state["current_poster"], use_column_width=True)
    
    # Chuyển đổi ảnh sang bytes để download
    buf = io.BytesIO()
    st.session_state["current_poster"].save(buf, format="PNG")
    byte_im = buf.getvalue()
    
    st.download_button(
        label="📥 Tải Poster Về Máy",
        data=byte_im,
        file_name="poster_chuyen_nghiep.png",
        mime="image/png"
    )
