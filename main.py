import os
import io
import time
import random
import logging
import urllib.parse
import requests
import gspread
import datetime
import pytz
from google.oauth2.service_account import Credentials
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

GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Content_Plan")

# Đường dẫn tuyệt đối chứa file credentials.json
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE", 
    os.path.join(BASE_DIR, "credentials.json")
)

# Khởi tạo Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)


# ==================================
# 2. KẾT NỐI GOOGLE SHEET
# ==================================
def connect_google_sheet():
    """Kết nối tới Google Sheet"""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open(GOOGLE_SHEET_NAME)
        return sh.sheet1
    except Exception as e:
        logger.error(f"❌ Lỗi kết nối Google Sheet: {e}")
        return None

def get_next_topic_from_sheet():
    """Tìm chủ đề tiếp theo chưa đăng trong Sheet"""
    sheet = connect_google_sheet()
    if not sheet:
        return None, None
    
    try:
        records = sheet.get_all_values()
        if len(records) <= 1:
            logger.warning("⚠️ Sheet rỗng hoặc chỉ có dòng tiêu đề!")
            return None, None

        for idx, row in enumerate(records[1:], start=2):
            topic = row[0].strip() if len(row) > 0 else ""
            status = row[1].strip().lower() if len(row) > 1 else ""
            
            if topic and status != "đã đăng":
                logger.info(f"📌 Đã tìm thấy chủ đề dòng {idx}: '{topic}' (Trạng thái: '{status}')")
                return idx, topic
    except Exception as e:
        logger.error(f"❌ Lỗi đọc dữ liệu Google Sheet: {e}")
        
    return None, None

def mark_topic_as_posted(row_index):
    """Cập nhật trạng thái 'Đã đăng' vào Google Sheet"""
    sheet = connect_google_sheet()
    if sheet and row_index:
        try:
            sheet.update_acell(f"B{row_index}", "Đã đăng")
            logger.info(f"✅ Đã cập nhật dòng {row_index} thành 'Đã đăng'")
        except Exception as e:
            logger.error(f"❌ Lỗi cập nhật trạng thái Google Sheet: {e}")


# ==================================
# 3. TẠO BỘ 4 ẢNH AI MIỄN PHÍ
# ==================================
def tao_anh_ai_mien_phi(prompt_en: str):
    seed = random.randint(1, 999999)
    encoded_prompt = urllib.parse.quote(prompt_en)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&seed={seed}"
    
    try:
        response = requests.get(image_url, timeout=45)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        logger.error(f"Lỗi tải ảnh: {e}")
    return None

async def tao_4_anh_ai_sinh_dong(chu_de: str):
    prompt_gen_prompts = f"""
    Dựa vào chủ đề: "{chu_de}", hãy viết 4 đoạn mô tả ảnh (Prompts) bằng tiếng Anh hoàn toàn khác nhau để vẽ ảnh sản phẩm/công nghệ cực kỳ sống động và bắt mắt.
    1. Ảnh 1: Ảnh chụp sản phẩm góc rộng hiện đại, banner thương mại chuyên nghiệp.
    2. Ảnh 2: Ảnh cận cảnh chi tiết linh kiện/công nghệ pin Lithium cao cấp.
    3. Ảnh 3: Ảnh ứng dụng thực tế trong đời sống hoặc hệ thống năng lượng mặt trời.
    4. Ảnh 4: Ảnh minh họa đồ họa 3D ấn tượng hoặc biểu tượng tương lai sinh động.

    Yêu cầu trả về đúng 4 dòng, mỗi dòng là 1 prompt tiếng Anh, không kèm số thứ tự hay văn bản thừa.
    """
    
    try:
        res = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_gen_prompts
        )
        prompts = [p.strip() for p in res.text.strip().split("\n") if p.strip()][:4]
    except Exception as e:
        logger.error(f"Lỗi sinh prompt ảnh Gemini: {e}")
        prompts = []
    
    while len(prompts) < 4:
        prompts.append(f"High quality modern commercial photo about {chu_de}, 8k resolution, cinematic lighting")

    list_images = []
    for p in prompts:
        img_bytes = tao_anh_ai_mien_phi(p)
        if img_bytes:
            list_images.append(img_bytes)
        time.sleep(0.5)
        
    return list_images


# ==================================
# 4. TIẾN TRÌNH SOẠN BÀI TỰ ĐỘNG
# ==================================
async def auto_generate_and_send_review(app_context: ContextTypes.DEFAULT_TYPE, chat_id: int, row_idx=None, topic=None):
    if not topic:
        row_idx, topic = get_next_topic_from_sheet()
    
    if not topic:
        await app_context.bot.send_message(
            chat_id=chat_id, 
            text="⚠️ **Google Sheet đã hết chủ đề chưa đăng!**\nVui lòng thêm nội dung mới vào Cột A của file `Content_Plan`."
        )
        return

    await app_context.bot.send_message(
        chat_id=chat_id, 
        text=f"⏰ **[TIẾN TRÌNH TẠO BÀI]**\n📌 Chủ đề (Dòng {row_idx}):\n👉 **{topic}**\n\n*Đang tiến hành viết nội dung & tạo 4 ảnh AI mới...*"
    )

    try:
        # 1. Viết bài bằng Gemini
        prompt_text = f"Viết 1 bài đăng Facebook marketing bán hàng tiếng Việt hấp dẫn, có tiêu đề sinh động, câu từ thu hút, hashtag, emoji phong phú, độ dài 150-200 từ về chủ đề: {topic}"
        res_text = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_text
        )
        bai_viet = res_text.text

        # 2. Sinh 4 ảnh AI
        images_list = await tao_4_anh_ai_sinh_dong(topic)

        if not images_list:
            await app_context.bot.send_message(chat_id=chat_id, text="❌ Lỗi: Không thể sinh ra ảnh AI nào!")
            return

        # Lưu dữ liệu bài viết hiện tại vào bot_data
        app_context.bot_data['pending_post'] = {
            'text': bai_viet,
            'images': images_list,
            'sheet_row': row_idx,
            'topic': topic
        }

        # 3. Gửi 4 ảnh lên Telegram dưới dạng Album
        media_group = [InputMediaPhoto(media=io.BytesIO(img)) for img in images_list]
        await app_context.bot.send_media_group(chat_id=chat_id, media=media_group)

        # 4. Gửi nội dung kèm nút thao tác
        action_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🟢 Duyệt & Đăng ngay", callback_data="btn_approve_post"),
                InlineKeyboardButton("🔄 Soạn lại toàn bộ", callback_data="btn_regen_post")
            ],
            [
                InlineKeyboardButton("🔴 Bỏ qua / Hủy", callback_data="btn_cancel_post")
            ]
        ])

        await app_context.bot.send_message(
            chat_id=chat_id,
            text=f"📝 **NỘI DUNG ĐÃ SOẠN (KÈM 4 ẢNH TRÊN):**\n\n{bai_viet}\n\n💡 *Mẹo: Bạn có thể nhắn tin trực tiếp để bảo Bot sửa bài này (Ví dụ: 'Sửa lại tiêu đề ngắn hơn')*",
            reply_markup=action_keyboard
        )

    except Exception as e:
        logger.error(f"Lỗi tiến trình soạn bài: {e}")
        await app_context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi trong quá trình soạn bài: {e}")


# ==================================
# 5. XỬ LÝ NHẮN TIN TRỰC TIẾP ĐỂ SỬA BÀI (TÍNH NĂNG 2)
# ==================================
async def handle_user_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    pending_post = context.bot_data.get('pending_post')

    if not pending_post:
        await update.message.reply_text("💡 Chưa có bài viết nào đang chờ duyệt. Hãy gõ `/runnow` để lấy bài từ Google Sheet nhé!")
        return

    await update.message.reply_text(f"🔄 **Đang chỉnh sửa lại bài viết theo yêu cầu:**\n👉 *\"{user_text}\"*")

    try:
        old_text = pending_post['text']
        topic = pending_post['topic']

        prompt_rewrite = f"""
        Dưới đây là bài đăng Facebook hiện tại về chủ đề '{topic}':
        ---
        {old_text}
        ---
        Yêu cầu chỉnh sửa từ người dùng: "{user_text}".

        Hãy viết lại bài đăng Facebook marketing này chuẩn chỉnh hơn theo đúng yêu cầu chỉnh sửa trên. Giữ nguyên định dạng bài đăng hấp dẫn, emoji và hashtag phù hợp.
        """

        res_text = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_rewrite
        )
        new_bai_viet = res_text.text

        # Cập nhật lại bài viết trong bộ nhớ
        pending_post['text'] = new_bai_viet
        context.bot_data['pending_post'] = pending_post

        action_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🟢 Duyệt & Đăng ngay", callback_data="btn_approve_post"),
                InlineKeyboardButton("🔄 Soạn lại toàn bộ", callback_data="btn_regen_post")
            ],
            [
                InlineKeyboardButton("🔴 Bỏ qua / Hủy", callback_data="btn_cancel_post")
            ]
        ])

        await update.message.reply_text(
            text=f"📝 **NỘI DUNG ĐÃ SỬA THEO YÊU CẦU:**\n\n{new_bai_viet}\n\n💡 *Nhắn tin tiếp nếu muốn chỉnh sửa thêm!*",
            reply_markup=action_keyboard
        )

    except Exception as e:
        logger.error(f"Lỗi sửa bài viết: {e}")
        await update.message.reply_text(f"❌ Lỗi khi sửa bài: {e}")


# ==================================
# 6. XỬ LÝ NÚT DUYỆT / SOẠN LẠI TỪ TELEGRAM
# ==================================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    pending_post = context.bot_data.get('pending_post')

    if data == "btn_approve_post":
        if not pending_post:
            await query.edit_message_text("❌ Không tìm thấy thông tin bài viết cần duyệt.")
            return

        await query.edit_message_text("⏳ **Đang tiến hành đăng bài viết kèm 4 ảnh lên Fanpage...**")

        success, msg = dang_album_len_facebook_fanpage(pending_post['text'], pending_post['images'])

        if success:
            mark_topic_as_posted(pending_post.get('sheet_row'))
            await query.edit_message_text(f"✅ **ĐÃ ĐĂNG BÀI THÀNH CÔNG LÊN FANPAGE!**\n\n{pending_post['text']}")
            context.bot_data.pop('pending_post', None)
        else:
            await query.edit_message_text(f"❌ **Đăng bài thất bại:** {msg}")

    elif data == "btn_regen_post":
        if not pending_post:
            await query.edit_message_text("❌ Không tìm thấy chủ đề để tạo lại.")
            return

        row_idx = pending_post.get('sheet_row')
        topic = pending_post.get('topic')
        
        await query.edit_message_text(f"🔄 **Đang tiến hành tạo lại nội dung & ảnh mới cho chủ đề:**\n👉 *{topic}*")
        await auto_generate_and_send_review(context, query.message.chat_id, row_idx=row_idx, topic=topic)

    elif data == "btn_cancel_post":
        context.bot_data.pop('pending_post', None)
        await query.edit_message_text("🚫 **Đã hủy bài viết này.** Google Sheet vẫn giữ nguyên trạng thái chưa đăng.")


# ==================================
# 7. ĐĂNG ALBUM ẢNH LÊN FACEBOOK FANPAGE
# ==================================
def dang_album_len_facebook_fanpage(text: str, images_bytes_list: list):
    if FB_PAGE_ID == "THAY_PAGE_ID_CUA_BAN" or FB_PAGE_ACCESS_TOKEN == "THAY_PAGE_TOKEN_CUA_BAN":
        return False, "Chưa thiết lập Access Token hoặc Page ID Facebook."

    attached_media = []

    try:
        for idx, img_bytes in enumerate(images_bytes_list):
            url_upload = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos"
            payload = {
                'published': 'false',
                'access_token': FB_PAGE_ACCESS_TOKEN
            }
            files = {'source': (f'image_{idx}.jpg', img_bytes, 'image/jpeg')}
            
            res = requests.post(url_upload, data=payload, files=files, timeout=30).json()
            if "id" in res:
                attached_media.append({"media_fbid": res["id"]})

        if not attached_media:
            return False, "Không thể upload ảnh lên Facebook."

        url_feed = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
        feed_payload = {
            'message': text,
            'access_token': FB_PAGE_ACCESS_TOKEN
        }
        
        for i, media in enumerate(attached_media):
            feed_payload[f'attached_media[{i}]'] = f'{{"media_fbid":"{media["media_fbid"]}"}}'

        res_post = requests.post(url_feed, data=payload, files=files, timeout=30).json() if False else requests.post(url_feed, data=feed_payload, timeout=30).json()
        
        if "id" in res_post:
            return True, res_post["id"]
        else:
            return False, res_post.get("error", {}).get("message", "Lỗi tạo bài đăng Feed")

    except Exception as e:
        return False, str(e)


# ==================================
# 8. LỆNH ĐIỀU KHIỂN & LẬP LỊCH CHẠY
# ==================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_chat_id = update.message.chat_id
    await update.message.reply_text(
        f"🚀 **Bot Auto Content Marketing Pro**\n\n"
        f"📌 **Chat ID của bạn:** `{user_chat_id}`\n\n"
        f"👉 Lệnh `/runnow`: Chạy thử ngay tiến trình soạn bài từ Google Sheet.",
        parse_mode="Markdown"
    )

async def run_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_generate_and_send_review(context, update.message.chat_id)

async def scheduled_job(context: ContextTypes.DEFAULT_TYPE):
    if MY_TELEGRAM_CHAT_ID != 123456789:
        await auto_generate_and_send_review(context, MY_TELEGRAM_CHAT_ID)


# ==================================
# 9. KHỞI CHẠY BOT
# ==================================
if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("runnow", run_now))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Bổ sung bộ xử lý tin nhắn chữ từ người dùng để sửa bài
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_user_text_message))

    tz = pytz.timezone('Asia/Ho_Chi_Minh')
    job_time = datetime.time(hour=8, minute=0, second=0, tzinfo=tz)
    app.job_queue.run_daily(scheduled_job, time=job_time)

    logger.info("🤖 Bot đang chạy và sẵn sàng nhận tin nhắn sửa bài...")
    app.run_polling()
