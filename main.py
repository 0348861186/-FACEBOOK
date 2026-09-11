import io
import os
import time
from datetime import datetime
import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types

# --- CẤU HÌNH API & TELEGRAM (Lấy từ Streamlit Secrets khi lên Cloud) ---
# Trên Streamlit Cloud, hãy cấu hình trong mục Settings > Secrets:
# GEMINI_API_KEY = "..."
# TELEGRAM_TOKEN = "..."
# TELEGRAM_CHAT_ID = "..."

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "THAY_API_KEY_CUA_BAN")
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "THAY_TELEGRAM_TOKEN_CUA_BAN")
TELEGRAM_CHAT_ID = st.secrets.get(
    "TELEGRAM_CHAT_ID", "THAY_TELEGRAM_CHAT_ID_CUA_BAN"
)

# Khởi tạo client Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# File lưu trạng thái nội dung cũ & lịch sử
STATE_FILE = "last_content.txt"
HISTORY_FILE = "history_posters.txt"


def get_last_content():
  if os.path.exists(STATE_FILE):
    with open(STATE_FILE, "r", encoding="utf-8") as f:
      return f.read().strip()
  return "Chương trình khuyến mãi đặc biệt: Giảm giá 50% toàn bộ sản phẩm trong tuần lễ vàng! Mua ngay kẻo lỡ."


def save_content(content):
  with open(STATE_FILE, "w", encoding="utf-8") as f:
    f.write(content)


# --- HÀM TẠO POSTER BẰNG PIL (Tạo ảnh bắt mắt, chuyên nghiệp) ---
def generate_poster_image(headline, subtext, variation_seed=1):
  # Kích thước poster chuẩn mạng xã hội (Instagram/Facebook: 1080x1080)
  width, height = 1080, 1080

  # Đổi màu nền dựa trên variation_seed để không bị trùng lặp khi chạy tự động
  bg_colors = [
      (20, 30, 48),
      (40, 20, 60),
      (10, 50, 40),
      (60, 30, 20),
      (30, 40, 60),
  ]
  bg_color = bg_colors[variation_seed % len(bg_colors)]

  img = Image.new("RGB", (width, height), color=bg_color)
  draw = ImageDraw.Draw(img)

  # Vẽ một vài hoạ tiết trang trí sinh động, chuyên nghiệp
  for i in range(5):
    offset = i * 40 + (variation_seed * 10) % 50
    draw.rectangle(
        [
            50 + offset,
            50 + offset,
            width - 50 - offset,
            height - 50 - offset,
        ],
        outline=(255, 255, 255, 30 + i * 20),
        width=3,
    )

  # Sử dụng font mặc định hoặc load font chữ (trên Cloud thường dùng font hệ thống)
  try:
    title_font = ImageFont.truetype("arial.ttf", 60)
    sub_font = ImageFont.truetype("arial.ttf", 40)
  except:
    title_font = ImageFont.load_default()
    sub_font = ImageFont.load_default()

  # Vẽ chữ lên poster (Cơ bản căn chỉnh)
  draw.text(
      (100, 200),
      "QUẢNG CÁO ĐẶC BIỆT",
      fill=(255, 215, 0),
      font=title_font,
  )

  # Tự động ngắt dòng chữ quảng cáo dài
  margin = 100
  max_width = width - 200
  lines = []
  words = headline.split()
  current_line = ""
  for word in words:
    test_line = current_line + " " + word if current_line else word
    # Đo kích thước chữ (đơn giản hoá)
    if len(test_line) > 30:
      lines.append(current_line)
      current_line = word
    else:
      current_line = test_line
  if current_line:
    lines.append(current_line)

  y_text = 350
  for line in lines:
    draw.text((margin, y_text), line, fill=(255, 255, 255), font=sub_font)
    y_text += 60

  draw.text(
      (margin, height - 150),
      f"Mã phiên bản: #{variation_seed} | Hotline: 1900 xxxx",
      fill=(200, 200, 200),
      font=sub_font,
  )

  # Lưu vào BytesIO để tải xuống hoặc gửi Telegram
  img_byte_arr = io.BytesIO()
  img.save(img_byte_arr, format="PNG")
  img_byte_arr.seek(0)
  return img_byte_arr


# --- GỬI ẢNH LÊN TELEGRAM ---
def send_telegram_photo(image_bytes, caption):
  if (
      TELEGRAM_TOKEN == "THAY_TELEGRAM_TOKEN_CUA_BAN"
      or not TELEGRAM_TOKEN
      or not TELEGRAM_CHAT_ID
  ):
    return "Chưa cấu hình Telegram Token hoặc Chat ID."

  url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
  files = {"photo": ("poster.png", image_bytes, "image/png")}
  data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
  response = requests.post(url, data=data, files=files)
  return response.json()


# --- GIAO DIỆN STREAMLIT (DASHBOARD) ---
st.set_page_config(
    page_title="AI Poster Creator & Telegram Bot", layout="centered"
)

st.title("🎨 AI Poster Creator & Telegram Automation")
st.write(
    "Biến nội dung chữ thành poster chuyên nghiệp, tự động đẩy lên Telegram và"
    " hỗ trợ tương tác phản hồi."
)

# Khởi tạo session state
if "poster_bytes" not in st.session_state:
  st.session_state["poster_bytes"] = None
if "seed" not in st.session_state:
  st.session_state["seed"] = 1
if "current_content" not in st.session_state:
  st.session_state["current_content"] = get_last_content()

# 1) Ô để dán nội dung cần tạo poster
ad_content = st.text_area(
    "Dán nội dung quảng cáo của bạn vào đây:",
    value=st.session_state["current_content"],
    height=150,
)

col1, col2 = st.columns(2)

with col1:
  # 6) Nút nhấn "tạo poster" ngay
  if st.button("🚀 Tạo Poster Ngay", use_container_width=True):
    if not ad_content.strip():
      # Yêu cầu 5: Nếu không dán nội dung mới thì lấy nội dung cũ nhưng đổi biến số để không trùng lặp
      ad_content = get_last_content()
      st.info("Sử dụng nội dung cũ trước đó với mẫu thiết kế mới.")

    save_content(ad_content)
    st.session_state["seed"] += 1  # Tăng seed để không trùng lặp poster

    # Dùng Gemini AI để tinh chỉnh lại nội dung cho hấp dẫn hơn trước khi đưa lên poster
    try:
      response = client.models.generate_content(
          model="gemini-2.5-flash",
          contents=(
              "Hãy cô đọng nội dung quảng cáo sau thành một tiêu đề ngắn gọn"
              f" hấp dẫn (dưới 15 từ): {ad_content}"
          ),
      )
      headline = response.text
    except Exception:
      headline = ad_content[:50]

    # Tạo poster
    poster_io = generate_poster_image(
        headline, ad_content, st.session_state["seed"]
    )
    st.session_state["poster_bytes"] = poster_io

    st.success("Đã tạo poster thành công!")

with col2:
  # 2) Nút download poster khi tạo xong
  if st.session_state["poster_bytes"] is not None:
    st.download_button(
        label="📥 Tải Poster Xuống",
        data=st.session_state["poster_bytes"],
        file_name=f"poster_{st.session_state['seed']}.png",
        mime="image/png",
        use_container_width=True,
    )

# Hiển thị poster nếu đã được tạo
if st.session_state["poster_bytes"] is not None:
  st.image(
      st.session_state["poster_bytes"],
      caption=f"Poster bản #{st.session_state['seed']}",
      use_column_width=True,
  )

  # 3) Đem lên telegram
  if st.button("📤 Gửi Poster lên Telegram để duyệt", use_container_width=True):
    st.session_state["poster_bytes"].seek(0)
    caption = (
        "🤖 *Poster Mới Được Tạo*\nNội dung: "
        f"{ad_content[:100]}...\n*(Hãy phản hồi nếu cần sửa đổi)*"
    )
    res = send_telegram_photo(st.session_state["poster_bytes"], caption)
    if isinstance(res, dict) and res.get("ok"):
      st.success("Đã gửi poster lên Telegram thành công!")
    else:
      st.error(f"Lỗi gửi Telegram: {res}")

st.markdown("---")
st.markdown("### 💡 Hướng dẫn tính năng Tự động hàng ngày (Yêu cầu 4)")
st.info(
    "Để hệ thống tự động gửi lúc 10h sáng hàng ngày (Yêu cầu 4), bạn có thể"
    " sử dụng các dịch vụ Cloud Scheduler (như GitHub Actions, Cron-job.org"
    " hoặc Render Cron) để gọi trực tiếp endpoint hoặc hàm tự động kích hoạt"
    " script chạy nền mỗi ngày."
)
