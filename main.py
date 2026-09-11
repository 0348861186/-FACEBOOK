from pathlib import Path
import re

src = Path("/mnt/data/Văn bản đã dán (1)(3).txt")
text = src.read_text(encoding="utf-8")

# Replace the Gemini SDK imports with REST-only dependencies.
text = text.replace(
    "from google import genai\nfrom google.genai import types\n",
    ""
)

# Replace the model line with the current stable image model.
text = text.replace(
    'GEMINI_MODEL = "gemini-2.5-flash-image"',
    'GEMINI_MODEL = "gemini-2.5-flash-image"\nGEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1/models/{GEMINI_MODEL}:generateContent"'
)

start = text.index("def gemini_client():")
end = text.index("\n\n# ============================================================\n# TELEGRAM", start)

new_gemini = r'''def gemini_headers():
    """Headers dùng API key trực tiếp, tránh SDK OAuth/AQ authentication."""
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "Chưa cấu hình GEMINI_API_KEY trong Streamlit Secrets."
        )

    return {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY.strip(),
    }


def _extract_gemini_image(response_json):
    """Lấy ảnh base64 từ response GenerateContent."""
    candidates = response_json.get("candidates", [])

    for candidate in candidates:
        content_obj = candidate.get("content", {})
        for part in content_obj.get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                return inline["data"], mime

    return None, None


def generate_image(
    content,
    output_path,
    previous_styles=None,
    revision=None,
    previous_image=None
):
    prompt = create_design_prompt(
        content,
        previous_styles,
        revision
    )

    # Gemini GenerateContent nhận text + ảnh cũ dưới dạng inline_data.
    parts = [
        {
            "text": prompt
        }
    ]

    if previous_image and os.path.exists(previous_image):
        with open(previous_image, "rb") as f:
            image_bytes = f.read()

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        parts.append({
            "inline_data": {
                "mime_type": "image/png",
                "data": image_b64
            }
        })

        # Khi chỉnh sửa ảnh cũ, nói rõ ảnh trước là nguồn tham chiếu.
        parts.insert(0, {
            "text": (
                "Đây là poster phiên bản trước được cung cấp ở ngay sau prompt. "
                "Hãy dùng nó làm ảnh tham chiếu khi chỉnh sửa. "
                "Nếu có yêu cầu chỉnh sửa, chỉ thay đổi những gì được yêu cầu "
                "và giữ nguyên các thông tin quảng cáo chính."
            )
        })

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": parts
            }
        ],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "responseFormat": {
                "image": {
                    "aspectRatio": "16:9"
                }
            }
        }
    }

    try:
        response = requests.post(
            GEMINI_API_URL,
            headers=gemini_headers(),
            json=payload,
            timeout=180
        )
    except requests.RequestException as e:
        raise RuntimeError(
            f"Không kết nối được Gemini API: {e}"
        ) from e

    if response.status_code != 200:
        try:
            error_data = response.json()
            error_message = error_data.get("error", {}).get(
                "message",
                response.text
            )
            error_status = error_data.get("error", {}).get(
                "status",
                ""
            )
            error_code = error_data.get("error", {}).get(
                "code",
                response.status_code
            )

            raise RuntimeError(
                f"Gemini API lỗi {error_code} {error_status}: "
                f"{error_message}"
            )
        except ValueError:
            raise RuntimeError(
                f"Gemini API lỗi HTTP {response.status_code}: "
                f"{response.text[:1000]}"
            )

    try:
        response_json = response.json()
    except ValueError as e:
        raise RuntimeError(
            "Gemini trả về dữ liệu không phải JSON."
        ) from e

    image_b64, mime_type = _extract_gemini_image(response_json)

    if not image_b64:
        # Trả lỗi dễ hiểu nếu model chỉ trả text hoặc bị safety block.
        block_reason = (
            response_json
            .get("promptFeedback", {})
            .get("blockReason")
        )

        finish_reason = None
        try:
            finish_reason = response_json["candidates"][0].get(
                "finishReason"
            )
        except (KeyError, IndexError, TypeError):
            pass

        raise RuntimeError(
            "Gemini không trả về hình ảnh. "
            f"blockReason={block_reason}, "
            f"finishReason={finish_reason}. "
            "Hãy thử nội dung/prompt khác."
        )

    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception as e:
        raise RuntimeError(
            "Không giải mã được ảnh base64 từ Gemini."
        ) from e

    # Gemini có thể trả PNG/JPEG; lưu đúng bytes.
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "wb") as f:
        f.write(image_bytes)

    return str(output_path)
'''

text = text[:start] + new_gemini + text[end:]

# Improve the "previous styles" bug: don't append the new random style
# to the list that is passed as "already used"; instead include it separately.
old = '''    styles = get_styles(
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

    styles.append(style)'''

new = '''    previous_styles = get_styles(ad_id)

    # Tạo style ngẫu nhiên để giảm khả năng lặp.
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

    unused_styles = [
        s for s in style_variations
        if s not in previous_styles
    ]

    style = random.choice(
        unused_styles or style_variations
    )'''

if old in text:
    text = text.replace(old, new)
    text = text.replace(
        "        previous_styles=styles,\n",
        "        previous_styles=previous_styles + [style],\n"
    )

# Add a visible API diagnostic button next to Telegram test.
old_button = '''with col2:

    telegram_button = st.button(
        "📱 TEST TELEGRAM",
        use_container_width=True
    )'''

new_button = '''with col2:

    telegram_button = st.button(
        "📱 TEST TELEGRAM",
        use_container_width=True
    )

col3 = st.columns(1)[0]

with col3:
    gemini_test_button = st.button(
        "🔑 TEST GEMINI",
        use_container_width=True
    )'''

if old_button in text:
    text = text.replace(old_button, new_button)

# Insert Gemini test handling before Telegram test.
marker = '''# ============================================================
# TELEGRAM TEST
# ============================================================'''

gemini_test_code = '''# ============================================================
# GEMINI TEST
# ============================================================

if "gemini_test_button" in locals() and gemini_test_button:

    try:
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "Chưa có GEMINI_API_KEY trong Streamlit Secrets."
            )

        test_response = requests.post(
            GEMINI_API_URL,
            headers=gemini_headers(),
            json={
                "contents": [{
                    "parts": [{
                        "text": "Create a simple professional abstract recruitment poster background."
                    }]
                }],
                "generationConfig": {
                    "responseModalities": ["IMAGE"],
                    "responseFormat": {
                        "image": {
                            "aspectRatio": "16:9"
                        }
                    }
                }
            },
            timeout=180
        )

        if test_response.status_code != 200:
            try:
                err = test_response.json().get("error", {})
                raise RuntimeError(
                    f"HTTP {err.get('code', test_response.status_code)}: "
                    f"{err.get('message', test_response.text[:1000])}"
                )
            except ValueError:
                raise RuntimeError(
                    f"HTTP {test_response.status_code}: "
                    f"{test_response.text[:1000]}"
                )

        data = test_response.json()
        image_b64, _ = _extract_gemini_image(data)

        if not image_b64:
            raise RuntimeError(
                "Gemini kết nối được nhưng không trả về ảnh."
            )

        st.success(
            "🟢 Gemini API hoạt động bình thường!"
        )

    except Exception as e:
        st.error(
            f"❌ Test Gemini thất bại: {e}"
        )


'''

if marker in text:
    text = text.replace(marker, gemini_test_code + marker)

# Add a small defensive check for Telegram token before API calls.
# (Don't alter behavior otherwise.)

out = Path("/mnt/data/app_fixed.py")
out.write_text(text, encoding="utf-8")

requirements = """streamlit>=1.40
requests>=2.31
Pillow>=10.0
"""
Path("/mnt/data/requirements.txt").write_text(requirements, encoding="utf-8")

secrets_example = """# .streamlit/secrets.toml
# KHÔNG dán key thật vào code/app.py

GEMINI_API_KEY = "YOUR_NEW_GEMINI_API_KEY"
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"
"""
Path("/mnt/data/secrets.toml.example").write_text(secrets_example, encoding="utf-8")

print(f"Đã tạo: {out}")
print("Đã tạo: /mnt/data/requirements.txt")
print("Đã tạo: /mnt/data/secrets.toml.example")
