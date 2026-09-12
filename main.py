import os
import json
import textwrap
from typing import List
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont
from google import genai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ================= CẤU HÌNH API KEYS =================
os.environ["GEMINI_API_KEY"] = "YOUR_GEMINI_API_KEY"
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

client = genai.Client()
user_posters = {}  # Lưu trạng thái chỉnh sửa theo từng user {chat_id: JobPosterData}

# ================= 1. SCHEMA DỮ LIỆU =================
class JobPosterData(BaseModel):
    title: str = Field(description="Vị trí tuyển dụng")
    salary: str = Field(description="Mức lương")
    location: str = Field(description="Địa điểm làm việc")
    requirements: List[str] = Field(description="Tối đa 3 yêu cầu cốt lõi, ngắn gọn")
    benefits: List[str] = Field(description="Tối đa 3 quyền lợi nổi bật")
    contact: str = Field(description="Thông tin liên hệ/email/sđt")
    
    # AI chọn phong cách/màu sắc
    primary_color: str = Field(default="#FFFFFF", description="Mã màu HEX tiêu đề")
    accent_color: str = Field(default="#38BDF8", description="Mã màu HEX điểm nhấn")
    bg_color: str = Field(default="#0F172A", description="Mã màu HEX nền poster")

# ================= 2. GEMINI AI PARSER =================
def extract_or_update_job(raw_text: str, current_data: JobPosterData = None) -> JobPosterData:
    if current_data is None:
        prompt = f"""
        Phân tích văn bản tuyển dụng sau và trích xuất thông tin theo cấu trúc JSON.
        Đồng thời chọn bộ màu sắc hiện đại, tương phản cao:
        
        NỘI DUNG:
        {raw_text}
        """
    else:
        prompt = f"""
        Dữ liệu hiện tại:
        {current_data.model_dump_json()}
        
        Yêu cầu chỉnh sửa:
        "{raw_text}"
        
        Hãy cập nhật thông tin và giữ nguyên các phần còn lại.
        """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": JobPosterData,
        },
    )
    return JobPosterData(**json.loads(response.text))

# ================= 3. RENDER POSTER (PIL) =================
def render_poster(data: JobPosterData, output_path: str):
    width, height = 1080, 1350
    image = Image.new("RGB", (width, height), color=data.bg_color)
    draw = ImageDraw.Draw(image)

    # Ưu tiên load font hệ thống hỗ trợ tiếng Việt
    try:
        font_title = ImageFont.truetype("arial.ttf", 56)
        font_header = ImageFont.truetype("arial.ttf", 34)
        font_body = ImageFont.truetype("arial.ttf", 28)
    except IOError:
        font_title = font_header = font_body = ImageFont.load_default()

    margin = 80
    cursor_y = 100

    # Header
    draw.text((margin, cursor_y), "TUYỂN DỤNG NHÂN SỰ", fill=data.accent_color, font=font_header)
    cursor_y += 70

    # Tiêu đề công việc (tự wrap dòng)
    for line in textwrap.wrap(data.title.upper(), width=24):
        draw.text((margin, cursor_y), line, fill=data.primary_color, font=font_title)
        cursor_y += 75
    cursor_y += 30

    # Box: Lương & Vị trí
    draw.rounded_rectangle([margin, cursor_y, width - margin, cursor_y + 120], radius=16, fill="#1E293B")
    draw.text((margin + 30, cursor_y + 20), f"💵 Thu nhập: {data.salary}", fill="#10B981", font=font_header)
    draw.text((margin + 30, cursor_y + 70), f"📍 Địa điểm: {data.location}", fill="#E2E8F0", font=font_body)
    cursor_y += 180

    # Yêu cầu công việc
    draw.text((margin, cursor_y), "YÊU CẦU:", fill=data.accent_color, font=font_header)
    cursor_y += 50
    for req in data.requirements:
        for line in textwrap.wrap(f"• {req}", width=45):
            draw.text((margin + 20, cursor_y), line, fill="#F8FAFC", font=font_body)
            cursor_y += 40
    cursor_y += 40

    # Quyền lợi
    draw.text((margin, cursor_y), "QUYỀN LỢI:", fill=data.accent_color, font=font_header)
    cursor_y += 50
    for ben in data.benefits:
        for line in textwrap.wrap(f"• {ben}", width=45):
            draw.text((margin + 20, cursor_y), line, fill="#F8FAFC", font=font_body)
            cursor_y += 40

    # Footer liên hệ
    draw.rectangle([0, height - 120, width, height], fill=data.accent_color)
    draw.text((margin, height - 80), f"LIÊN HỆ: {data.contact}", fill="#0F172A", font=font_header)

    image.save(output_path)

# ================= 4. TELEGRAM BOT HANDLER =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_input = update.message.text
    
    await update.message.reply_text("⏳ Gemini AI đang phân tích và render poster...")

    # Phân tích nội dung (mới hoặc chỉnh sửa tiếp theo luồng)
    previous_data = user_posters.get(chat_id)
    poster_data = extract_or_update_job(user_input, current_data=previous_data)
    user_posters[chat_id] = poster_data

    # Xuất ảnh
    output_filename = f"poster_{chat_id}.png"
    render_poster(poster_data, output_filename)

    # Gửi lại kết quả
    label = "Poster phiên bản 2 (Đã chỉnh sửa)" if previous_data else "Poster Final (Phiên bản đầu)"
    with open(output_filename, "rb") as photo:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=f"✅ **{label}**\n\nBạn có thể tải về trực tiếp hoặc nhắn nội dung cần sửa để AI điều chỉnh tiếp."
        )

# ================= 5. RUN SERVER =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🚀 Bot đã sẵn sàng nhận tin tuyển dụng...")
    app.run_polling()
