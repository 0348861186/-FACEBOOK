import os
import io
import time
import random
import logging
import urllib.parse
import requests
import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from google import genai

# Cấu hình hiển thị log hoạt động trên Terminal
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================================
# 1. CẤU HÌNH TOKEN, KEY & CHAT ID
# ==================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8915690207:AAH0k4A2Ro59aYgK2YaTN51kYUymS9LAKwY")
MY_TELEGRAM_CHAT_ID = int(os.getenv("MY_TELEGRAM_CHAT_ID", "7654812561"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6KKqFNcTY5oTboA2_TKSK-X7dvKh3WrBUytZArd0xcjJw")

FB_PAGE_ID = os.getenv("FB_PAGE_ID", "THAY_PAGE_ID_CUA_BAN")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "THAY_PAGE_TOKEN_CUA_BAN")

# Khởi tạo Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# ==================================
# 2. NỘI DUNG TUYỂN DỤNG CỐ ĐỊNH TRONG CODE
# ==================================
RECRUITMENT_CONTENT = """CN CÔNG TY TNHH DAISSHO VN
Địa chỉ: KCN Kim Huy, Bình Dương
TUYỂN GẤP CÔNG NHÂN CHÍNH THỨC VÀ THỜI VỤ

📌 LƯƠNG THỬ VIỆC: 7.200.000đ (LCB 6.000.000 + 1.200.000 PC)
📌 LƯƠNG CHÍNH THỨC: 7.500.000đ (LCB 6.000.000 + 1.500.000 PC)

🔹 YÊU CẦU:
- Nam Nữ biết đọc viết
- Chịu khó siêng năng
- Làm việc ca 12 tiếng xoay ca ngày đêm

🎁 CHẾ ĐỘ & QUYỀN LỢI:
- Ngoài lương ra có: thưởng tuần, thưởng tháng, thưởng chủ nhật
- Công ty bao cơm

💰 THU NHẬP 26 CÔNG TỪ: 13.000.000đ - 15.000.000đ

📞 LIÊN HỆ NGAY: 0348861186"""


# ==================================
# 3. TẠO POSTER AI KHÔNG TRÙNG LẶP
# ==================================
def tao_anh_ai_mien_phi(prompt_en: str):
    seed = random.randint(1, 999999)
    encoded_prompt = urllib.parse.quote(prompt_en)
    # Tỷ lệ 4:5 hoặc 1:1 phù hợp làm poster quảng cáo
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1280&nologo=true&seed={seed}"
    
    try:
        response = requests.get(image_url, timeout=45)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        logger.error(f"Lỗi tải ảnh poster: {e}")
    return None

async def tao_cac_poster_tuyen_dung():
    """Gemini AI tạo ra các ý tưởng thiết kế poster hoàn toàn khác biệt, không bị trùng lặp"""
    prompt_gen = f"""
    Dựa vào thông tin tuyển dụng công nhân của công ty Daissho VN:
    "{RECRUITMENT_CONTENT}"
    
    Hãy viết 3 đoạn mô tả (Prompts) bằng tiếng Anh cực kỳ chuyên nghiệp, sáng tạo, sắc nét để tạo ra 3 mẫu **Poster quảng cáo tuyển dụng việc làm** khác nhau hoàn toàn về phong cách, bố cục và màu sắc (Đảm bảo các poster KHÔNG ĐƯỢC PHÉP TRÙNG NHAU):
    1. Poster 1: Phong cách thiết kế đồ họa hiện đại, phẳng (Modern Flat Graphic Design), màu sắc chủ đạo xanh dương/trắng chuyên nghiệp, có không gian trống để hiển thị thông tin tuyển dụng, biểu tượng nhà xưởng công nghệ cao.
    2. Poster 2: Phong cách poster thương mại nổi bật (Vibrant Commercial Advertising Poster), tông màu cam/vàng năng động, hình ảnh minh họa công nhân làm việc vui vẻ, chuyên nghiệp, hiện đại.
    3. Poster 3: Phong cách tối giản cao cấp (High-end Minimalist Corporate Poster), kết hợp giữa công nghiệp thông minh và con người, màu xanh lá/xám sang trọng, bố cục sạch sẽ.

    Yêu cầu trả về đúng 3 dòng, mỗi dòng là 1 prompt tiếng Anh chi tiết, không kèm số thứ tự hay văn bản thừa.
    """
    
    try:
        res = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_gen
        )
        prompts = [p.strip() for p in res.text.strip().split("\n") if p.strip()][:3]
    except Exception as e:
        logger.error(f"Lỗi sinh prompt poster từ Gemini: {e}")
        prompts = []
    
    # Dự phòng nếu lỗi API
    fallback_prompts = [
        "Professional recruitment poster design for manufacturing company, modern blue and white corporate style, clean typography layout, 8k resolution",
        "Vibrant job hiring advertisement poster, energetic orange and yellow theme, happy industrial workers, modern factory background, high quality",
        "Minimalist corporate recruitment banner design, green and gray professional tones, smart factory concept, sleek graphic layout"
    ]
    
    while len(prompts) < 3:
        prompts.append(fallback_prompts[len(prompts)])

    list_images = []
    for idx, p in enumerate(prompts):
        # Đảm bảo mỗi poster có biến thể ngẫu nhiên riêng biệt
        unique_prompt = f"{p}, unique variation style {random.randint(100, 999)}"
        img_bytes = tao_anh_ai_mien_phi(unique_prompt)
        if img_bytes:
            list_images.append(img_bytes)
        time.sleep(0.8)
        
    return list_images


# ==================================
# 4. TIẾN TRÌNH TẠO & GỬI DUYỆT
# ==================================
async def auto_generate_and_send_review(app_context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    await app_context.bot.send_message(
        chat_id=chat_id, 
        text="⏰ **[HỆ THỐNG TẠO POSTER TUYỂN DỤNG]**\n\n*Đang yêu cầu AI thiết kế bộ 3 mẫu poster độc quyền, không trùng lặp cho Daissho VN...*"
    )

    try:
        # 1. Sinh 3 poster AI độc đáo
        images_list = await tao_cac_poster_tuyen_dung()

        if not images_list:
            await app_context.bot.send_message(chat_id=chat_id, text="❌ Lỗi: Không thể khởi tạo poster AI!")
            return

        # Lưu dữ liệu bài viết và poster vào bot_data để xử lý duyệt/sửa
        app_context.bot_data['pending_post'] = {
            'text': RECRUITMENT_CONTENT,
            'images': images_list
        }

        # 2. Gửi 3 poster lên Telegram dưới dạng Album
        media_group = [InputMediaPhoto(media=io.BytesIO(img)) for img in images_list]
        await app_context.bot.send_media_group(chat_id=chat_id, media=media_group)

        # 3. Gửi nội dung kèm các nút thao tác duyệt
        action_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🟢 Duyệt & Đăng Facebook", callback_data="btn_approve_post"),
                InlineKeyboardButton("🔄 Tạo lại bộ poster mới", callback_data="btn_regen_post")
            ],
            [
                InlineKeyboardButton("🔴 Hủy bỏ", callback_data="btn_cancel_post")
            ]
        ])

        await app_context.bot.send_message(
            chat_id=chat_id,
            text=f"📝 **NỘI DUNG BÀI ĐĂNG TUYỂN DỤNG:**\n\n{RECRUITMENT_CONTENT}\n\n💡 *Mẹo: Nếu bạn muốn thay đổi nội dung hoặc yêu cầu đổi kiểu poster, hãy nhắn tin trực tiếp vào đây (Ví dụ: 'Sửa lại phần lương nổi bật hơn' hoặc 'Tạo lại poster phong cách tối giản hơn')*",
            reply_markup=action_keyboard
        )

    except Exception as e:
        logger.error(f"Lỗi tiến trình tạo poster: {e}")
        await app_context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi trong quá trình tạo poster: {e}")


# ==================================
# 5. XỬ LÝ NHẮN TIN TRỰC TIẾP ĐỂ SỬA (COMMENT)
# ==================================
async def handle_user_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    pending_post = context.bot_data.get('pending_post')

    if not pending_post:
        await update.message.reply_text("💡 Chưa có bài viết nào đang chờ duyệt. Gõ lệnh `/runnow` để bắt đầu tạo poster tuyển dụng nhé!")
        return

    await update.message.reply_text(f"🔄 **Đang xử lý yêu cầu chỉnh sửa của bạn:**\n👉 *\"{user_text}\"*")

    try:
        # Dùng Gemini thông minh để hiểu yêu cầu sửa nội dung hoặc thay đổi ý tưởng thiết kế
        prompt_edit = f"""
        Đây là nội dung tuyển dụng hiện tại:
