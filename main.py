# ==============================================================================
# DỰ ÁN: PIPELINE TỰ ĐỘNG HÓA TẠO POSTER TUYỂN DỤNG TỪ NỘI DUNG VĂN BẢN
# QUY TRÌNH:
#   1. NỘI DUNG TUYỂN DỤNG (JD thô)
#   2. GEMINI PHÂN TÍCH TEXT -> JSON (RecruitmentData)
#   3. GEMINI IMAGE AI (Imagen 3) TẠO BACKGROUND CHUYÊN NGHIỆP
#   4. PYTHON / PILLOW GHÉP TYPOGRAPHY CHUẨN TIẾNG VIỆT
#   5. XUẤT POSTER FINAL -> DOWNLOAD / TELEGRAM BOT / VÒNG LẶP CHỈNH SỬA
# ==============================================================================
# HƯỚNG DẪN CÀI ĐẶT THƯ VIỆN:
#   pip install google-genai pillow pydantic requests python-dotenv
# ==============================================================================

import io
import os
import json
from typing import List, Optional
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont
import requests

from google import genai
from google.genai import types

# ------------------------------------------------------------------------------
# 1. KHỞI TẠO CLIENT
# ------------------------------------------------------------------------------
# Yêu cầu cài biến môi trường: export GEMINI_API_KEY="your_api_key_here"
# Hoặc truyền trực tiếp: client = genai.Client(api_key="...")
client = genai.Client()

# ------------------------------------------------------------------------------
# 2. SCHEMA DỮ LIỆU CẤU TRÚC (Pydantic Model)
# ------------------------------------------------------------------------------
class RecruitmentData(BaseModel):
    job_title: str = Field(description="Vị trí tuyển dụng chính (IN HOA, súc tích)")
    company_name: str = Field(description="Tên công ty hoặc thương hiệu tuyển dụng")
    salary_range: str = Field(description="Mức lương hoặc chế độ đãi ngộ hấp dẫn nhất")
    requirements: List[str] = Field(description="Danh sách 3-4 gạch đầu dòng yêu cầu cốt lõi")
    contact_info: str = Field(description="Email nộp CV, số hotline hoặc Zalo liên hệ")
    visual_theme_prompt: str = Field(
        description="Prompt tiếng Anh mô tả ảnh nền phù hợp ngành nghề, phong cách hiện đại, chừa nhiều khoảng trống negative space"
    )

# ------------------------------------------------------------------------------
# 3. GEMINI PHÂN TÍCH VĂN BẢN THÔ RA JSON
# ------------------------------------------------------------------------------
def extract_recruitment_info(raw_text: str) -> RecruitmentData:
    """
    Sử dụng mô hình Gemini để đọc hiểu và chuẩn hóa văn bản tuyển dụng thành cấu trúc JSON.
    """
    prompt = (
        "Bạn là chuyên gia thiết kế truyền thông và nhân sự. "
        "Hãy đọc tin tuyển dụng dưới đây và trích xuất các trường thông tin chuẩn xác, "
        "đồng thời tạo một prompt tiếng Anh tạo ảnh nền phù hợp nhất:

"
        f"{raw_text}"
    )
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RecruitmentData,
            temperature=0.2,
        ),
    )
    return RecruitmentData.model_validate_json(response.text)

# ------------------------------------------------------------------------------
# 4. GEMINI IMAGE AI TẠO BACKGROUND
# ------------------------------------------------------------------------------
def generate_background_image(theme_prompt: str) -> Image.Image:
    """
    Sử dụng mô hình Imagen 3 để sinh nền poster chuẩn tỉ lệ 3:4 với không gian trống chèn chữ.
    """
    refined_prompt = (
        f"{theme_prompt}, modern aesthetic, clean minimalist design, corporate poster background, "
        f"lots of negative space in the center and lower-middle, cinematic lighting, 8k, no text, no letters"
    )
    
    result = client.models.generate_images(
        model="imagen-3.0-generate-002",
        prompt=refined_prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="3:4",  # Tỉ lệ poster dọc chuẩn cho mạng xã hội
            output_mime_type="image/png"
        )
    )
    image_bytes = result.generated_images[0].image.image_bytes
    return Image.open(io.BytesIO(image_bytes)).convert("RGBA")

# ------------------------------------------------------------------------------
# 5. PYTHON / PILLOW: RENDER TYPOGRAPHY CHUẨN ĐẸP LÊN POSTER
# ------------------------------------------------------------------------------
def render_poster(bg_image: Image.Image, data: RecruitmentData) -> Image.Image:
    """
    Tạo poster 1080x1440, phủ layer làm dịu nền và căn chỉnh typography chuẩn.
    """
    # Chuẩn hóa độ phân giải poster
    poster = bg_image.resize((1080, 1440))
    overlay = Image.new("RGBA", poster.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Khung nền mờ màu đen sẫm (Slate Dark bán trong suốt) để chữ luôn sắc nét
    draw.rectangle([(60, 240), (1020, 1380)], fill=(15, 23, 42, 215))

    # Font chữ (tìm font hỗ trợ tiếng Việt trên hệ thống)
    font_candidates = [
        "Roboto-Bold.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", 
        "segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    font_path = None
    for f in font_candidates:
        if os.path.exists(f):
            font_path = f
            break

    try:
        if font_path:
            font_company = ImageFont.truetype(font_path, 34)
            font_badge = ImageFont.truetype(font_path, 38)
            font_title = ImageFont.truetype(font_path, 58)
            font_salary = ImageFont.truetype(font_path, 36)
            font_section = ImageFont.truetype(font_path, 36)
            font_body = ImageFont.truetype(font_path, 28)
            font_footer = ImageFont.truetype(font_path, 26)
        else:
            raise IOError("No TTF found")
    except IOError:
        font_company = font_badge = font_title = font_salary = font_section = font_body = font_footer = ImageFont.load_default()

    # 1. Tên công ty & Badge tuyển dụng
    draw.text((100, 280), data.company_name.upper(), font=font_company, fill="#94A3B8")
    draw.text((100, 335), "● WE ARE HIRING", font=font_badge, fill="#38BDF8")
    
    # 2. Vị trí ứng tuyển
    draw.text((100, 410), data.job_title, font=font_title, fill="#FFFFFF")
    
    # 3. Hộp mức lương nổi bật (Accent Box)
    draw.rectangle([(100, 505), (650, 575)], fill="#F59E0B")
    draw.text((120, 520), f"LƯƠNG: {data.salary_range}", font=font_salary, fill="#0F172A")

    # 4. Yêu cầu công việc
    draw.text((100, 625), "YÊU CẦU ỨNG VIÊN:", font=font_section, fill="#F8FAFC")
    y_offset = 690
    for req in data.requirements:
        draw.text((120, y_offset), f"✔  {req}", font=font_body, fill="#E2E8F0")
        y_offset += 65

    # 5. Đường kẻ chia và Thông tin liên hệ
    draw.line([(100, 1230), (980, 1230)], fill="#475569", width=2)
    draw.text((100, 1260), f"Ứng tuyển ngay: {data.contact_info}", font=font_footer, fill="#38BDF8")

    # Gộp layer ảnh gốc và layer đồ họa text
    final_poster = Image.alpha_composite(poster, overlay)
    return final_poster.convert("RGB")

# -------------------------------------------------------------
# 6. DISPATCH: GỬI POSTER QUA TELEGRAM BOT
# -------------------------------------------------------------
def send_to_telegram(image: Image.Image, caption: str, bot_token: str, chat_id: str):
    """
    Gửi ảnh poster trực tiếp đến kênh/nhóm Telegram bằng Bot API.
    """
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='JPEG', quality=95)
    img_byte_arr.seek(0)
    
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    files = {'photo': ('poster.jpg', img_byte_arr, 'image/jpeg')}
    data = {'chat_id': chat_id, 'caption': caption}
    
    try:
        response = requests.post(url, files=files, data=data, timeout=30)
        return response.json()
    except Exception as e:
        print(f"Lỗi khi gửi Telegram: {e}")
        return None

# -------------------------------------------------------------
# 7. CHỈNH SỬA POSTER BẰNG GEMINI AI (VÒNG LẶP CHỈNH SỬA)
# -------------------------------------------------------------
def refine_recruitment_data(current_data: RecruitmentData, feedback: str) -> RecruitmentData:
    """
    Cho phép người dùng đưa ra feedback chỉnh sửa để Gemini cập nhật lại JSON.
    """
    prompt = (
        f"Dưới đây là thông tin tuyển dụng hiện tại:
{current_data.model_dump_json(indent=2)}

"
        f"Yêu cầu chỉnh sửa từ người dùng: {feedback}
"
        f"Hãy cập nhật lại dữ liệu tuyển dụng theo đúng yêu cầu trên."
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RecruitmentData,
            temperature=0.2,
        ),
    )
    return RecruitmentData.model_validate_json(response.text)

# -------------------------------------------------------------
# 8. HÀM ĐIỀU PHỐI PIPELINE CHÍNH
# -------------------------------------------------------------
def execute_pipeline(raw_jd_text: str, telegram_token: str = None, chat_id: str = None, output_filename: str = "poster_final.jpg"):
    print("=" * 60)
    print("BƯỚC 1: Đang phân tích nội dung JD bằng Gemini 2.5...")
    data = extract_recruitment_info(raw_jd_text)
    print(f"-> Vị trí tuyển: {data.job_title}")
    print(f"-> Công ty: {data.company_name}")
    print(f"-> Lương: {data.salary_range}")

    print("
BƯỚC 2: Đang tạo ảnh nền với Gemini Image AI (Imagen 3)...")
    bg_img = generate_background_image(data.visual_theme_prompt)

    print("
BƯỚC 3: Đang ghép bố cục Typography với Pillow...")
    final_poster = render_poster(bg_img, data)
    
    # Tải / Lưu file poster
    final_poster.save(output_filename, quality=95)
    print(f"-> Đã lưu poster thành công: {output_filename}")

    # Gửi qua Telegram nếu có cấu hình token
    if telegram_token and chat_id:
        print("
BƯỚC 4: Đang dispatch gửi poster qua Telegram...")
        caption = f"🚀 Tuyển dụng: {data.job_title} - {data.company_name}
💰 Lương: {data.salary_range}
📩 Liên hệ: {data.contact_info}"
        send_to_telegram(final_poster, caption, telegram_token, chat_id)
        print("-> Đã gửi thành công qua Telegram!")

    print("=" * 60)
    print("HOÀN THÀNH TOÀN BỘ QUY TRÌNH!")
    return final_poster, data

# -------------------------------------------------------------
# ĐOẠN CODE TEST THỰC NGHIỆM
# -------------------------------------------------------------
if __name__ == "__main__":
    sample_jd = """
    Công ty Cổ phần Công nghệ TechNova tuyển dụng gấp vị trí:
    Senior Python Backend Developer (Làm việc tại Quận 1, TP.HCM hoặc Remote).
    Mức thu nhập: 35.000.000 - 55.000.000 VNĐ + Thưởng dự án và tháng 13.
    Mô tả yêu cầu:
    - Trên 3 năm kinh nghiệm lập trình Python với FastAPI hoặc Django.
    - Làm chủ kiến trúc Microservices, hệ cơ sở dữ liệu PostgreSQL và Redis Cache.
    - Có kỹ năng triển khai Docker, Kubernetes và thiết lập CI/CD.
    - Kỹ năng giao tiếp và làm việc nhóm tốt, tư duy phản biện.
    Hồ sơ CV gửi về email: careers@technova.vn hoặc liên hệ Hotline/Zalo: 0912.345.678
    """
    
    # Chạy quy trình:
    # execute_pipeline(
    #     raw_jd_text=sample_jd,
    #     telegram_token=os.getenv("TELEGRAM_BOT_TOKEN"),
    #     chat_id=os.getenv("TELEGRAM_CHAT_ID"),
    #     output_filename="poster_final.jpg"
    # )
