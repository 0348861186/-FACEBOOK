import os
import io
import json
import base64
import random
from datetime import datetime
from typing import Optional, List

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
from pydantic import BaseModel, Field
from google import genai


APP_TITLE = "AI Recruitment Poster Studio"
TEXT_MODEL = "gemini-3.1-flash-lite"
IMAGE_MODEL = "gemini-3.1-flash-image"

POSTER_WIDTH = 1080
POSTER_HEIGHT = 1350
MAX_TEXT_LENGTH = 12000


st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-title {
        font-size: 34px;
        font-weight: 800;
        margin-bottom: 4px;
    }
    .sub-title {
        color: #64748b;
        font-size: 16px;
        margin-bottom: 25px;
    }
    .step-card {
        padding: 16px;
        border-radius: 14px;
        border: 1px solid #e2e8f0;
        background: #ffffff;
        margin-bottom: 12px;
    }
    .success-box {
        padding: 14px;
        border-radius: 12px;
        background: #ecfdf5;
        border: 1px solid #a7f3d0;
    }
    .warning-box {
        padding: 14px;
        border-radius: 12px;
        background: #fffbeb;
        border: 1px solid #fde68a;
    }
    .flow-box {
        padding: 12px;
        border-radius: 12px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        text-align: center;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


class RecruitmentData(BaseModel):
    company: str = ""
    location: str = ""
    title: str = ""
    salary: str = ""
    salary_details: str = ""
    requirements: List[str] = Field(default_factory=list)
    benefits: List[str] = Field(default_factory=list)
    schedule: str = ""
    income: str = ""
    contact: str = ""
    other: List[str] = Field(default_factory=list)


defaults = {
    "raw_text": "",
    "parsed_data": None,
    "poster_bytes": None,
    "background_bytes": None,
    "last_prompt": "",
    "revision_history": [],
    "telegram_message_id": None,
    "last_generated_at": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)


def get_gemini_client():
    api_key = get_secret("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Chưa tìm thấy GEMINI_API_KEY. "
            "Hãy thêm GEMINI_API_KEY vào Streamlit Secrets."
        )
    return genai.Client(api_key=api_key)


def clean_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def parse_recruitment_content(raw_text: str) -> RecruitmentData:
    client = get_gemini_client()

    prompt = f"""
Bạn là chuyên gia phân tích nội dung tuyển dụng tại Việt Nam.

Hãy đọc nội dung tuyển dụng dưới đây và trích xuất thông tin
để dùng cho việc thiết kế poster.

QUY TẮC:
1. Không được tự bịa thông tin.
2. Nếu không có thông tin thì để chuỗi rỗng.
3. Giữ nguyên số tiền, số điện thoại, địa chỉ, tên công ty.
4. Không đổi 13.000.000 thành 13 triệu nếu dữ liệu gốc là 13.000.000.
5. Requirements là danh sách yêu cầu.
6. Benefits là danh sách quyền lợi.
7. Salary là mức lương nổi bật nhất.
8. Contact phải giữ nguyên số điện thoại/Zalo/email nếu có.
9. Title phải ngắn gọn, phù hợp làm tiêu đề poster.
10. Chỉ trả về JSON theo schema được yêu cầu.

NỘI DUNG:
{raw_text}
"""

    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": RecruitmentData,
        },
    )

    if not response.text:
        raise RuntimeError("Gemini không trả về dữ liệu phân tích.")

    try:
        return RecruitmentData.model_validate_json(response.text)
    except Exception:
        cleaned = clean_json_text(response.text)
        try:
            return RecruitmentData.model_validate(json.loads(cleaned))
        except Exception as exc:
            raise RuntimeError(f"Không thể đọc JSON từ Gemini: {exc}") from exc


def build_visual_prompt(
    data: RecruitmentData,
    variation_seed: int,
    style: str,
) -> str:

    visual_themes = {
        "Công nghiệp mạnh mẽ": """
modern industrial recruitment advertising,
Vietnam factory environment,
professional Vietnamese manufacturing workers,
dynamic lighting,
strong depth,
clean corporate visual,
high contrast,
premium commercial photography,
red and dark blue visual accents,
""",
        "Hiện đại chuyên nghiệp": """
modern corporate recruitment advertising,
professional Vietnamese workers,
clean office and industrial visual language,
premium commercial photography,
minimal but energetic composition,
blue and white visual accents,
""",
        "Trẻ trung nổi bật": """
young energetic recruitment advertising,
Vietnamese workers,
dynamic commercial photography,
bright energetic atmosphere,
modern social media advertising,
bold visual composition,
orange, blue and dark tones,
""",
        "Tối giản cao cấp": """
premium minimalist recruitment advertising,
professional Vietnamese workforce,
clean composition,
luxury corporate design,
soft dramatic lighting,
large negative space,
deep blue and white tones,
""",
    }

    theme = visual_themes.get(
        style,
        visual_themes["Công nghiệp mạnh mẽ"],
    )

    return f"""
Create ONLY the visual background/image for a professional
Vietnamese recruitment poster.

IMPORTANT:
- Do NOT render any text.
- Do NOT render letters.
- Do NOT render numbers.
- Do NOT render logos.
- Leave clear empty areas for text overlays.
- The final image will have text added separately by software.
- Vertical poster composition.
- Aspect ratio approximately 4:5.
- Professional commercial advertising quality.
- Realistic people and workplace.
- Avoid distorted hands and faces.
- Avoid fake writing.
- Avoid random symbols.

STYLE:
{theme}

RECRUITMENT CONTEXT:
Company: {data.company}
Job title: {data.title}
Location: {data.location}
Salary: {data.salary}

Variation seed: {variation_seed}

Create a visually striking background suitable for a
Facebook/Zalo recruitment poster.
"""


def generate_background(
    data: RecruitmentData,
    style: str,
    variation_seed: int,
) -> bytes:

    client = get_gemini_client()

    prompt = build_visual_prompt(
        data,
        variation_seed,
        style,
    )

    interaction = client.interactions.create(
        model=IMAGE_MODEL,
        input=prompt,
        response_format={
            "type": "image",
            "mime_type": "image/png",
            "aspect_ratio": "4:5",
            "image_size": "2K",
        },
    )

    image_data = None

    if getattr(interaction, "output_image", None):
        image_data = interaction.output_image.data

    if not image_data:
        steps = getattr(interaction, "steps", []) or []
        for step in steps:
            if getattr(step, "type", "") != "model_output":
                continue
            content = getattr(step, "content", []) or []
            for block in content:
                if getattr(block, "type", "") == "image":
                    image_data = getattr(block, "data", None)
                    if image_data:
                        break
            if image_data:
                break

    if not image_data:
        raise RuntimeError(
            "Gemini đã chạy nhưng không trả về ảnh."
        )

    if isinstance(image_data, str):
        return base64.b64decode(image_data)

    return bytes(image_data)


def find_font(size: int, bold: bool = False):
    candidates = []

    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/Arial Bold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/Arial.ttf",
        ]

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass

    return ImageFont.load_default()


def rounded_rectangle(
    draw,
    xy,
    radius,
    fill,
    outline=None,
    width=1,
):
    draw.rounded_rectangle(
        xy,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width,
    )


def fit_background(image_bytes: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    target_ratio = POSTER_WIDTH / POSTER_HEIGHT
    source_ratio = image.width / image.height

    if source_ratio > target_ratio:
        new_width = int(image.height * target_ratio)
        left = (image.width - new_width) // 2
        image = image.crop(
            (left, 0, left + new_width, image.height)
        )
    else:
        new_height = int(image.width / target_ratio)
        top = (image.height - new_height) // 2
        image = image.crop(
            (0, top, image.width, top + new_height)
        )

    return image.resize(
        (POSTER_WIDTH, POSTER_HEIGHT),
        Image.Resampling.LANCZOS,
    )


def add_dark_gradient(image: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for y in range(image.height):
        ratio = y / image.height
        alpha = int(35 + ratio * 135)
        draw.line(
            [(0, y), (image.width, y)],
            fill=(0, 0, 0, alpha),
        )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    ).convert("RGB")


def add_top_gradient(image: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    top_height = int(image.height * 0.43)

    for y in range(top_height):
        ratio = y / max(top_height, 1)
        alpha = int(190 * (1 - ratio))
        draw.line(
            [(0, y), (image.width, y)],
            fill=(0, 0, 0, alpha),
        )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    ).convert("RGB")


def draw_wrapped_text(
    draw,
    text,
    font,
    x,
    y,
    max_width,
    fill,
    spacing=8,
    anchor="la",
):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = word if not current else current + " " + word
        bbox = draw.textbbox((0, 0), test, font=font)
        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    current_y = y

    for line in lines:
        draw.text(
            (x, current_y),
            line,
            font=font,
            fill=fill,
            anchor=anchor,
        )

        bbox = draw.textbbox(
            (x, current_y),
            line,
            font=font,
            anchor=anchor,
        )

        line_height = bbox[3] - bbox[1]
        current_y += line_height + spacing

    return current_y


def draw_icon_circle(
    draw,
    center,
    radius,
    fill,
    symbol,
    symbol_font,
):
    x, y = center

    draw.ellipse(
        (
            x - radius,
            y - radius,
            x + radius,
            y + radius,
        ),
        fill=fill,
    )

    draw.text(
        (x, y),
        symbol,
        font=symbol_font,
        fill=(255, 255, 255),
        anchor="mm",
    )


def render_poster(
    background_bytes: bytes,
    data: RecruitmentData,
    style: str,
    variation_seed: int,
) -> bytes:

    image = fit_background(background_bytes)
    image = ImageEnhance.Color(image).enhance(1.15)
    image = ImageEnhance.Contrast(image).enhance(1.08)
    image = add_dark_gradient(image)
    image = add_top_gradient(image)

    draw = ImageDraw.Draw(image)

    if style == "Tối giản cao cấp":
        accent = (37, 99, 235)
        accent2 = (59, 130, 246)
    elif style == "Trẻ trung nổi bật":
        accent = (249, 115, 22)
        accent2 = (234, 88, 12)
    else:
        accent = (220, 38, 38)
        accent2 = (185, 28, 28)

    white = (255, 255, 255)
    dark = (15, 23, 42)
    gray = (71, 85, 105)

    company_font = find_font(35, True)
    title_font = find_font(70, True)
    salary_font = find_font(58, True)
    section_font = find_font(31, True)
    body_font = find_font(27, False)
    contact_font = find_font(34, True)
    icon_font = find_font(28, True)

    x_margin = 70

    company = data.company.strip()

    if company:
        draw.text(
            (x_margin, 60),
            company.upper(),
            font=company_font,
            fill=white,
        )

    title = data.title or "TUYỂN DỤNG"

    draw_wrapped_text(
        draw,
        title.upper(),
        title_font,
        x_margin,
        145,
        POSTER_WIDTH - 140,
        white,
        spacing=5,
    )

    salary = data.salary or data.income

    if salary:
        badge_y = 335

        rounded_rectangle(
            draw,
            (
                x_margin,
                badge_y,
                POSTER_WIDTH - x_margin,
                badge_y + 125,
            ),
            28,
            fill=accent,
        )

        draw.text(
            (POSTER_WIDTH // 2, badge_y + 63),
            salary,
            font=salary_font,
            fill=white,
            anchor="mm",
        )

    card_top = 510
    card_bottom = 1075

    shadow = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    shadow_draw = ImageDraw.Draw(shadow)

    shadow_draw.rounded_rectangle(
        (
            x_margin + 8,
            card_top + 10,
            POSTER_WIDTH - x_margin + 8,
            card_bottom + 10,
        ),
        radius=34,
        fill=(0, 0, 0, 80),
    )

    shadow = shadow.filter(ImageFilter.GaussianBlur(12))

    image = Image.alpha_composite(
        image.convert("RGBA"),
        shadow,
    ).convert("RGB")

    draw = ImageDraw.Draw(image)

    rounded_rectangle(
        draw,
        (
            x_margin,
            card_top,
            POSTER_WIDTH - x_margin,
            card_bottom,
        ),
        34,
        fill=(255, 255, 255),
    )

    y = card_top + 45

    if data.location:
        draw_icon_circle(
            draw,
            (x_margin + 48, y + 20),
            24,
            accent,
            "L",
            icon_font,
        )

        draw.text(
            (x_margin + 90, y),
            "ĐỊA ĐIỂM",
            font=section_font,
            fill=dark,
        )

        y = draw_wrapped_text(
            draw,
            data.location,
            body_font,
            x_margin + 90,
            y + 45,
            POSTER_WIDTH - x_margin * 2 - 120,
            gray,
            spacing=5,
        )

        y += 25

    if data.schedule:
        draw_icon_circle(
            draw,
            (x_margin + 48, y + 20),
            24,
            accent2,
            "T",
            icon_font,
        )

        draw.text(
            (x_margin + 90, y),
            "THỜI GIAN",
            font=section_font,
            fill=dark,
        )

        y = draw_wrapped_text(
            draw,
            data.schedule,
            body_font,
            x_margin + 90,
            y + 45,
            POSTER_WIDTH - x_margin * 2 - 120,
            gray,
            spacing=5,
        )

        y += 25

    if data.requirements:
        draw.text(
            (x_margin + 40, y),
            "YÊU CẦU",
            font=section_font,
            fill=dark,
        )

        y += 52

        for item in data.requirements[:5]:
            draw.ellipse(
                (
                    x_margin + 42,
                    y + 9,
                    x_margin + 54,
                    y + 21,
                ),
                fill=accent,
            )

            y = draw_wrapped_text(
                draw,
                item,
                body_font,
                x_margin + 75,
                y,
                POSTER_WIDTH - x_margin * 2 - 110,
                gray,
                spacing=3,
            )

            y += 8

    if data.benefits and y < card_bottom - 120:
        draw.text(
            (x_margin + 40, y),
            "QUYỀN LỢI",
            font=section_font,
            fill=dark,
        )

        y += 52

        for item in data.benefits[:4]:
            draw.ellipse(
                (
                    x_margin + 42,
                    y + 9,
                    x_margin + 54,
                    y + 21,
                ),
                fill=accent2,
            )

            y = draw_wrapped_text(
                draw,
                item,
                body_font,
                x_margin + 75,
                y,
                POSTER_WIDTH - x_margin * 2 - 110,
                gray,
                spacing=3,
            )

            y += 8

    if data.income:
        draw.text(
            (POSTER_WIDTH // 2, card_bottom - 115),
            data.income,
            font=section_font,
            fill=accent,
            anchor="ma",
        )

    contact = data.contact.strip()

    footer_top = 1120
    footer_bottom = 1290

    rounded_rectangle(
        draw,
        (
            x_margin,
            footer_top,
            POSTER_WIDTH - x_margin,
            footer_bottom,
        ),
        32,
        fill=accent,
    )

    draw.text(
        (POSTER_WIDTH // 2, footer_top + 47),
        "ỨNG TUYỂN NGAY",
        font=contact_font,
        fill=white,
        anchor="mm",
    )

    draw.text(
        (POSTER_WIDTH // 2, footer_top + 105),
        contact if contact else "Liên hệ để biết thêm thông tin",
        font=body_font,
        fill=white,
        anchor="mm",
    )

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)

    return output.getvalue()


def send_telegram_photo(
    image_bytes: bytes,
    caption: str,
) -> dict:

    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")

    if not bot_token:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN.")

    if not chat_id:
        raise RuntimeError("Thiếu TELEGRAM_CHAT_ID.")

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"

    files = {
        "photo": ("poster.png", image_bytes, "image/png")
    }

    data = {
        "chat_id": chat_id,
        "caption": caption[:1024],
    }

    response = requests.post(
        url,
        data=data,
        files=files,
        timeout=60,
    )

    response.raise_for_status()
    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            result.get("description", "Telegram error")
        )

    return result


def apply_revision(
    data: RecruitmentData,
    revision_request: str,
) -> RecruitmentData:

    client = get_gemini_client()

    prompt = f"""
Bạn là AI chuyên chỉnh sửa dữ liệu poster tuyển dụng.

DỮ LIỆU HIỆN TẠI:
{data.model_dump_json(indent=2)}

YÊU CẦU CHỈNH SỬA:
{revision_request}

QUY TẮC:
- Chỉ thay đổi những phần mà người dùng yêu cầu.
- Không tự bịa số điện thoại.
- Không tự bịa mức lương.
- Không tự bịa địa chỉ.
- Không tự bịa quyền lợi.
- Giữ nguyên các thông tin không được yêu cầu thay đổi.
- Trả về JSON đúng schema.
"""

    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": RecruitmentData,
        },
    )

    if not response.text:
        raise RuntimeError(
            "Gemini không trả về dữ liệu sửa đổi."
        )

    try:
        return RecruitmentData.model_validate_json(
            response.text
        )
    except Exception:
        cleaned = clean_json_text(response.text)
        try:
            return RecruitmentData.model_validate(
                json.loads(cleaned)
            )
        except Exception as exc:
            raise RuntimeError(
                f"Lỗi đọc dữ liệu chỉnh sửa: {exc}"
            ) from exc


def build_telegram_caption(
    data: RecruitmentData,
) -> str:

    title = data.title or "POSTER TUYỂN DỤNG"
    salary = data.salary or data.income

    return (
        f"🎨 {title}\n\n"
        f"🏢 {data.company}\n"
        f"📍 {data.location}\n"
        f"💰 {salary}\n\n"
        "Gửi yêu cầu chỉnh sửa nếu cần.\n"
        "Ví dụ:\n"
        "• Làm mức lương nổi bật hơn\n"
        "• Đổi màu sang xanh\n"
        "• Thêm hình công nhân\n"
        "• Làm poster trẻ trung hơn"
    )


with st.sidebar:
    st.markdown("## ⚙️ Cấu hình")

    style = st.selectbox(
        "Phong cách poster",
        [
            "Công nghiệp mạnh mẽ",
            "Hiện đại chuyên nghiệp",
            "Trẻ trung nổi bật",
            "Tối giản cao cấp",
        ],
    )

    variation = st.slider(
        "Độ biến đổi mẫu",
        min_value=1,
        max_value=100,
        value=50,
    )

    st.markdown("---")
    st.markdown("### 🔐 Kiểm tra API")

    gemini_exists = bool(get_secret("GEMINI_API_KEY"))
    telegram_exists = bool(get_secret("TELEGRAM_BOT_TOKEN"))
    chat_exists = bool(get_secret("TELEGRAM_CHAT_ID"))

    if gemini_exists:
        st.success("Gemini API Key: OK")
    else:
        st.error("Gemini API Key: CHƯA CÓ")

    if telegram_exists and chat_exists:
        st.success("Telegram: OK")
    else:
        st.warning("Telegram: chưa cấu hình đầy đủ")

    st.markdown("---")
    st.caption("AI Recruitment Poster Studio")


st.markdown(
    '<div class="main-title">🎨 AI Recruitment Poster Studio</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="sub-title">'
    "Từ nội dung tuyển dụng → AI phân tích → tạo visual → "
    "render chữ chính xác → poster chuyên nghiệp"
    "</div>",
    unsafe_allow_html=True,
)

flow_cols = st.columns(7)

flow = [
    "📝 Nội dung",
    "🧠 AI phân tích",
    "📦 JSON",
    "🎨 Visual AI",
    "🖼️ Render",
    "📱 Telegram",
    "✏️ Sửa AI",
]

for col, item in zip(flow_cols, flow):
    with col:
        st.markdown(
            f'<div class="flow-box">{item}</div>',
            unsafe_allow_html=True,
        )

st.markdown("---")

left, right = st.columns([1, 1], gap="large")

with left:
    st.subheader("1️⃣ Nội dung tuyển dụng")

    raw_text = st.text_area(
        "Dán nội dung tuyển dụng vào đây",
        value=st.session_state.raw_text,
        height=390,
        max_chars=MAX_TEXT_LENGTH,
        placeholder=(
            "Ví dụ:\n\n"
            "CN CÔNG TY TNHH DAISSHO VN\n"
            "KCN Kim Huy, Bình Dương\n\n"
            "TUYỂN GẤP CÔNG NHÂN\n"
            "Lương 13.000.000 - 15.000.000đ\n"
            "Nam/Nữ..."
        ),
    )

    st.session_state.raw_text = raw_text

    col1, col2 = st.columns(2)

    with col1:
        analyze_button = st.button(
            "🧠 Phân tích nội dung",
            use_container_width=True,
        )

    with col2:
        generate_button = st.button(
            "🎨 TẠO POSTER",
            type="primary",
            use_container_width=True,
        )


if analyze_button:
    if not raw_text.strip():
        st.error("Vui lòng nhập nội dung tuyển dụng.")
    else:
        try:
            with st.spinner("Gemini đang phân tích nội dung..."):
                parsed = parse_recruitment_content(raw_text)

            st.session_state.parsed_data = parsed
            st.success("Đã phân tích nội dung thành công.")

        except Exception as exc:
            st.error(f"Lỗi phân tích Gemini: {exc}")


if generate_button:
    if not raw_text.strip():
        st.error("Vui lòng nhập nội dung tuyển dụng.")
    else:
        try:
            with st.spinner("Bước 1/4: AI phân tích nội dung..."):
                parsed = parse_recruitment_content(raw_text)
                st.session_state.parsed_data = parsed

            seed = (
                variation
                + random.randint(1, 999999)
                + int(datetime.now().timestamp())
            )

            with st.spinner("Bước 2/4: AI đang tạo visual..."):
                background = generate_background(
                    parsed,
                    style,
                    seed,
                )
                st.session_state.background_bytes = background

            with st.spinner("Bước 3/4: Đang render poster..."):
                poster = render_poster(
                    background,
                    parsed,
                    style,
                    seed,
                )
                st.session_state.poster_bytes = poster

            st.session_state.last_generated_at = (
                datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            )

            st.session_state.last_prompt = (
                f"{style} / seed={seed}"
            )

            st.session_state.revision_history.append(
                {
                    "time": st.session_state.last_generated_at,
                    "type": "generate",
                    "request": "Tạo poster mới",
                }
            )

            st.success("✅ Đã tạo poster thành công!")

        except Exception as exc:
            st.error("❌ Không thể tạo poster.")
            st.exception(exc)


with right:
    st.subheader("2️⃣ Dữ liệu AI đã phân tích")

    data = st.session_state.parsed_data

    if data:
        st.write(f"**Công ty:** {data.company}")
        st.write(f"**Tiêu đề:** {data.title}")
        st.write(f"**Lương:** {data.salary}")
        st.write(f"**Địa điểm:** {data.location}")
        st.write(f"**Thời gian:** {data.schedule}")

        if data.requirements:
            st.markdown("**Yêu cầu:**")
            for item in data.requirements:
                st.markdown(f"- {item}")

        if data.benefits:
            st.markdown("**Quyền lợi:**")
            for item in data.benefits:
                st.markdown(f"- {item}")

        st.write(f"**Thu nhập:** {data.income}")
        st.write(f"**Liên hệ:** {data.contact}")

        with st.expander("Xem JSON"):
            st.code(
                data.model_dump_json(
                    indent=2,
                    ensure_ascii=False,
                ),
                language="json",
            )
    else:
        st.info(
            "Chưa có dữ liệu. Hãy bấm 'Phân tích nội dung' "
            "hoặc 'TẠO POSTER'."
        )


if st.session_state.poster_bytes:
    st.markdown("---")
    st.subheader("3️⃣ Poster kết quả")

    poster_cols = st.columns([1, 1], gap="large")

    with poster_cols[0]:
        st.image(
            st.session_state.poster_bytes,
            caption="Poster AI",
            use_container_width=True,
        )

    with poster_cols[1]:
        st.markdown(
            '<div class="success-box">'
            "<b>Poster đã sẵn sàng.</b><br>"
            "Các thông tin quan trọng được render "
            "bằng Python để hạn chế lỗi chữ."
            "</div>",
            unsafe_allow_html=True,
        )

        st.download_button(
            "⬇️ Tải poster PNG",
            data=st.session_state.poster_bytes,
            file_name=(
                "poster_tuyen_dung_"
                + datetime.now().strftime("%Y%m%d_%H%M%S")
                + ".png"
            ),
            mime="image/png",
            use_container_width=True,
        )

        st.markdown("---")

        send_telegram_button = st.button(
            "📱 Gửi poster vào Telegram",
            use_container_width=True,
        )

        if send_telegram_button:
            try:
                if not st.session_state.parsed_data:
                    raise RuntimeError(
                        "Chưa có dữ liệu tuyển dụng."
                    )

                caption = build_telegram_caption(
                    st.session_state.parsed_data
                )

                with st.spinner("Đang gửi Telegram..."):
                    result = send_telegram_photo(
                        st.session_state.poster_bytes,
                        caption,
                    )

                message_id = (
                    result.get("result", {}).get("message_id")
                )

                st.session_state.telegram_message_id = message_id

                st.success("✅ Đã gửi poster vào Telegram.")

            except Exception as exc:
                st.error(f"Lỗi Telegram: {exc}")


if st.session_state.parsed_data:
    st.markdown("---")
    st.subheader("4️⃣ Yêu cầu AI chỉnh sửa poster")

    revision = st.text_area(
        "Bạn muốn thay đổi gì?",
        height=120,
        placeholder=(
            "Ví dụ:\n"
            "- Làm poster nổi bật hơn\n"
            "- Đổi phong cách sang xanh dương\n"
            "- Làm mức lương lớn hơn\n"
            "- Thêm quyền lợi thưởng\n"
            "- Đổi tiêu đề thành TUYỂN GẤP CÔNG NHÂN"
        ),
    )

    revise_button = st.button(
        "✏️ AI CHỈNH SỬA & TẠO LẠI",
        type="primary",
        use_container_width=True,
    )

    if revise_button:
        if not revision.strip():
            st.warning("Hãy nhập yêu cầu chỉnh sửa.")
        else:
            try:
                with st.spinner(
                    "AI đang hiểu yêu cầu chỉnh sửa..."
                ):
                    updated_data = apply_revision(
                        st.session_state.parsed_data,
                        revision,
                    )

                seed = (
                    random.randint(1, 999999)
                    + int(datetime.now().timestamp())
                )

                with st.spinner("AI đang tạo lại visual..."):
                    background = generate_background(
                        updated_data,
                        style,
                        seed,
                    )

                with st.spinner("Đang render phiên bản mới..."):
                    poster = render_poster(
                        background,
                        updated_data,
                        style,
                        seed,
                    )

                st.session_state.parsed_data = updated_data
                st.session_state.background_bytes = background
                st.session_state.poster_bytes = poster

                revision_time = datetime.now().strftime(
                    "%d/%m/%Y %H:%M:%S"
                )

                st.session_state.revision_history.append(
                    {
                        "time": revision_time,
                        "type": "revision",
                        "request": revision,
                    }
                )

                st.success("✅ Đã tạo phiên bản mới.")
                st.rerun()

            except Exception as exc:
                st.error(f"Lỗi chỉnh sửa: {exc}")


with st.expander("📱 Hướng dẫn cấu hình Telegram"):
    st.markdown(
        """
### 1. Tạo Telegram Bot

Mở Telegram và tìm **@BotFather**.

Dùng:

`/newbot`

Sau đó lấy Bot Token.

### 2. Lấy Chat ID

Gửi một tin nhắn cho bot rồi lấy `chat_id`.

### 3. Thêm vào Streamlit Secrets

```toml
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
```

Không đưa các key này trực tiếp vào code.
        """
    )


if st.session_state.revision_history:
    with st.expander("📋 Lịch sử tạo / chỉnh sửa"):
        for item in reversed(
            st.session_state.revision_history[-10:]
        ):
            st.write(
                f"**{item['time']}** — {item['type']}"
            )
            if item.get("request"):
                st.caption(item["request"])
