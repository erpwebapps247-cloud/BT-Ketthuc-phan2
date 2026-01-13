import os
import sys
import streamlit as st
from PIL import Image
import pytesseract
from openai import OpenAI
import io

# Thử import pdf2image; nếu thiếu thì chỉ tắt chức năng xử lý PDF thay vì làm sập app
try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    convert_from_bytes = None
    PDF2IMAGE_AVAILABLE = False

# ========================================================================================
# CẤU HÌNH TRANG & DỊCH VỤ
# ========================================================================================
# Cấu hình đường dẫn Tesseract cho Windows (dùng biến môi trường nếu được cung cấp)
tesseract_cmd = os.environ.get("TESSERACT_CMD") or os.environ.get("TESSERACT_PATH")
if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

st.set_page_config(
    page_title="Trợ lý OCR Thông minh",
    page_icon="📄",
    layout="wide"
)

# Khởi tạo session state cho API key nếu chưa có
if 'openai_api_key' not in st.session_state:
    # Ưu tiên lấy từ biến môi trường, nếu không có thì để trống
    st.session_state.openai_api_key = os.environ.get("OPENAI_API_KEY", "")

# Khởi tạo client OpenAI từ session state hoặc biến môi trường
def get_openai_client():
    """Lấy OpenAI client từ API key trong session state hoặc biến môi trường"""
    api_key = st.session_state.get('openai_api_key', '') or os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        try:
            return OpenAI(api_key=api_key)
        except Exception:
            return None
    return None

openai_client = get_openai_client()

# ========================================================================================
# HÀM HỖ TRỢ (LOGIC XỬ LÝ)
# ========================================================================================

@st.cache_data  # Sử dụng cache để không xử lý lại file đã xử lý
def process_file(file_bytes, file_extension, lang_choice: str):
    """
    Hàm trung tâm xử lý file đầu vào (ảnh hoặc PDF) và trả về văn bản được trích xuất.
    Mặc định sử dụng chế độ song ngữ Việt + Anh.
    """
    # Ngôn ngữ xử lý: cho phép chọn trong giao diện
    lang_code = lang_choice
    
    extracted_text = ""
    try:
        if file_extension == 'pdf':
            if not PDF2IMAGE_AVAILABLE:
                return None, (
                    "Thư viện 'pdf2image' chưa được cài đặt trong môi trường hiện tại.\n"
                    "- Vui lòng cài bằng lệnh: pip install pdf2image\n"
                    "- Sau đó chạy lại ứng dụng.\n\n"
                    "Bạn vẫn có thể xử lý file ảnh (PNG/JPG/JPEG) bình thường."
                )

            images = convert_from_bytes(file_bytes)
            all_text = []
            progress_bar = st.progress(0, text="Đang xử lý file PDF...")
            for i, img in enumerate(images):
                all_text.append(
                    pytesseract.image_to_string(
                        img,
                        lang=lang_code,
                        config="--oem 1 --psm 6"
                    )
                )
                progress_bar.progress((i + 1) / len(images))
            extracted_text = "\n\n--- Hết trang ---\n\n".join(all_text)
        elif file_extension in ['png', 'jpg', 'jpeg']:
            image = Image.open(io.BytesIO(file_bytes))
            extracted_text = pytesseract.image_to_string(
                image,
                lang=lang_code,
                config="--oem 1 --psm 6"
            )
        return extracted_text, None
    except Exception as e:
        return None, f"Đã xảy ra lỗi trong quá trình xử lý: {e}"


def enhance_with_openai(raw_text: str, lang_code: str, model: str = "gpt-4o-mini", enhancement_level: str = "medium", client=None):
    """
    Dùng OpenAI để sửa lỗi chính tả, dấu tiếng Việt và định dạng văn bản OCR với độ chính xác cao.
    
    Args:
        raw_text: Văn bản gốc từ OCR
        lang_code: Mã ngôn ngữ (vie, eng, vie+eng)
        model: Model OpenAI sử dụng (gpt-4o-mini hoặc gpt-4o)
        enhancement_level: Mức độ cải thiện (light, medium, strong)
        client: OpenAI client (nếu None sẽ tự lấy từ session)
    """
    if not raw_text.strip():
        return raw_text, None

    # Lấy client từ tham số hoặc từ session state
    if client is None:
        client = get_openai_client()
    
    if client is None:
        return None, (
            "Chưa cấu hình OpenAI API Key. "
            "Vui lòng nhập API Key trong phần cấu hình ở trên."
        )

    # Xác định ngôn ngữ chính để tối ưu prompt
    is_vietnamese = "vie" in lang_code.lower()
    is_english = "eng" in lang_code.lower()
    
    # Prompt system message chi tiết và chính xác hơn
    system_prompt = """Bạn là chuyên gia xử lý văn bản OCR với độ chính xác cao. Nhiệm vụ của bạn:

1. **Sửa lỗi OCR phổ biến:**
   - Thiếu dấu tiếng Việt (ă, â, ê, ô, ơ, ư, đ)
   - Nhầm lẫn ký tự (0/O, 1/l/I, 5/S, 8/B, v/u, n/h)
   - Khoảng trắng sai vị trí
   - Xuống dòng không hợp lý

2. **Sửa chính tả và ngữ pháp:**
   - Sửa từ sai chính tả
   - Điều chỉnh ngữ pháp nếu cần thiết
   - Giữ nguyên thuật ngữ chuyên ngành, tên riêng, số liệu

3. **Định dạng văn bản:**
   - Giữ nguyên cấu trúc đoạn văn
   - Xuống dòng hợp lý giữa các đoạn
   - Giữ nguyên định dạng số, ngày tháng, địa chỉ

**QUAN TRỌNG:**
- KHÔNG thêm bớt nội dung, không tóm tắt, không diễn giải lại
- KHÔNG thay đổi ý nghĩa gốc
- Giữ nguyên số liệu, ngày tháng, tên riêng chính xác
- Chỉ sửa những lỗi rõ ràng do OCR, không đoán mò"""

    # User prompt tùy theo mức độ cải thiện
    enhancement_instructions = {
        "light": "Chỉ sửa những lỗi rõ ràng nhất (thiếu dấu, nhầm ký tự dễ nhận biết). Giữ nguyên phần lớn văn bản.",
        "medium": "Sửa lỗi OCR và chính tả phổ biến. Điều chỉnh định dạng nhẹ nhàng. Đây là mức khuyên dùng.",
        "strong": "Sửa toàn diện: lỗi OCR, chính tả, ngữ pháp và định dạng. Tối ưu hóa văn bản để dễ đọc nhất."
    }
    
    user_prompt = f"""Đây là văn bản được trích xuất từ OCR (nhận dạng ký tự quang học).

**Ngôn ngữ:** {'Tiếng Việt' if is_vietnamese and not is_english else 'Tiếng Anh' if is_english and not is_vietnamese else 'Tiếng Việt và Tiếng Anh (song ngữ)'}

**Yêu cầu:** {enhancement_instructions.get(enhancement_level, enhancement_instructions['medium'])}

**Văn bản gốc từ OCR:**
```
{raw_text}
```

Hãy trả về phiên bản đã được chỉnh sửa và cải thiện, giữ nguyên cấu trúc và nội dung gốc."""

    try:
        # Điều chỉnh temperature theo mức độ cải thiện
        temperature_map = {
            "light": 0.1,   # Rất thấp để giữ nguyên tối đa
            "medium": 0.2,  # Thấp để cân bằng
            "strong": 0.3   # Vừa phải để có thể cải thiện nhiều hơn
        }
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature_map.get(enhancement_level, 0.2),
            max_tokens=4000,  # Đủ cho văn bản dài
        )
        improved = response.choices[0].message.content.strip()
        
        # Loại bỏ markdown code block nếu có (một số model tự thêm)
        if improved.startswith("```"):
            lines = improved.split("\n")
            if lines[0].startswith("```"):
                improved = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
        
        return improved, None
    except Exception as e:
        return None, f"Lỗi khi gọi OpenAI: {e}"

# ========================================================================================
# GIAO DIỆN CHÍNH CỦA ỨNG DỤNG
# ========================================================================================

st.title("📄 Trợ lý OCR Thông minh")
st.write("Trích xuất văn bản từ file ảnh hoặc PDF. Hỗ trợ Tiếng Việt, Tiếng Anh hoặc song ngữ.")

# Cột cho phần tải lên, thiết lập và hướng dẫn
col1, col2 = st.columns([2, 1])

with col1:
    # Chọn ngôn ngữ nhận dạng
    lang_display = st.selectbox(
        "Ngôn ngữ nhận dạng",
        options=[
            ("Tiếng Việt + Tiếng Anh (khuyên dùng)", "vie+eng"),
            ("Chỉ Tiếng Việt", "vie"),
            ("Chỉ Tiếng Anh", "eng"),
        ],
        format_func=lambda x: x[0],
        index=0,
    )
    lang_code = lang_display[1]

    # Tuỳ chọn dùng OpenAI để cải thiện văn bản
    use_openai = st.checkbox(
        "✨ Sử dụng OpenAI để cải thiện độ chính xác",
        value=False,
        help="Nhập API Key trong phần cấu hình ở cột bên phải để sử dụng tính năng này."
    )
    
    # Các tùy chọn nâng cao cho OpenAI (chỉ hiện khi bật OpenAI)
    if use_openai:
        col_model, col_level = st.columns(2)
        with col_model:
            openai_model = st.selectbox(
                "Model OpenAI",
                options=["gpt-4o-mini", "gpt-4o"],
                index=0,
                help="gpt-4o-mini: Nhanh và tiết kiệm. gpt-4o: Chính xác hơn nhưng tốn phí hơn."
            )
        with col_level:
            enhancement_level = st.selectbox(
                "Mức độ cải thiện",
                options=[
                    ("Nhẹ (chỉ sửa lỗi rõ ràng)", "light"),
                    ("Vừa (khuyên dùng)", "medium"),
                    ("Mạnh (tối ưu toàn diện)", "strong"),
                ],
                format_func=lambda x: x[0],
                index=1,
                help="Nhẹ: Giữ nguyên tối đa. Vừa: Cân bằng. Mạnh: Cải thiện nhiều nhất."
            )
            enhancement_level = enhancement_level[1]
    else:
        openai_model = "gpt-4o-mini"
        enhancement_level = "medium"

    # Tiện ích tải file đã được đơn giản hóa
    uploaded_files = st.file_uploader(
        "Tải lên MỘT hoặc NHIỀU file...",
        type=['pdf', 'png', 'jpg', 'jpeg'],
        accept_multiple_files=True
    )

with col2:
    # Khung cấu hình OpenAI API Key
    with st.expander("🔑 Cấu hình OpenAI API Key", expanded=False):
        st.info("💡 Nhập API Key của bạn để sử dụng tính năng cải thiện văn bản bằng AI.")
        
        api_key_input = st.text_input(
            "OpenAI API Key",
            value=st.session_state.openai_api_key if st.session_state.openai_api_key else "",
            type="password",
            help="Nhập API Key từ https://platform.openai.com/api-keys",
            key="api_key_input"
        )
        
        if api_key_input:
            # Cập nhật session state
            st.session_state.openai_api_key = api_key_input
            # Kiểm tra API key có hợp lệ không
            try:
                test_client = OpenAI(api_key=api_key_input)
                st.success("✅ API Key đã được lưu!")
            except Exception as e:
                st.error(f"❌ API Key không hợp lệ: {str(e)}")
        elif st.session_state.openai_api_key:
            st.info("✅ Đang sử dụng API Key đã lưu.")
        else:
            st.warning("⚠️ Chưa có API Key. Vui lòng nhập để sử dụng tính năng OpenAI.")
        
        if st.button("🗑️ Xóa API Key", use_container_width=True):
            st.session_state.openai_api_key = ""
            st.rerun()
    
    # Khung thông tin / mẹo sử dụng
    with st.expander("💡 Mẹo sử dụng", expanded=True):
        st.info("""
        **OCR (Nhận dạng văn bản):**
        - Ứng dụng được tối ưu để nhận dạng tài liệu có cả Tiếng Việt và Tiếng Anh.
        - Bạn có thể kéo thả nhiều file vào đây cùng một lúc.
        - Để có kết quả tốt nhất, hãy sử dụng ảnh rõ nét, chữ không bị mờ.
        
        **✨ Cải thiện bằng OpenAI:**
        - Tự động sửa lỗi thiếu dấu tiếng Việt
        - Sửa chính tả và ngữ pháp
        - Định dạng lại văn bản cho dễ đọc
        - Chọn mức độ cải thiện phù hợp với nhu cầu
        - So sánh trực quan giữa văn bản gốc và đã cải thiện
        """)

    # Khung chẩn đoán môi trường giúp tránh lỗi cài gói sai nơi
    with st.expander("🛠 Thông tin môi trường (chẩn đoán lỗi)", expanded=False):
        st.write(f"**Python đang dùng:** `{sys.executable}`")
        st.write(f"**pdf2image khả dụng:** {'✅ Có' if PDF2IMAGE_AVAILABLE else '❌ Không'}")
        
        # Kiểm tra OpenAI từ session state
        current_openai_status = get_openai_client() is not None
        st.write(f"**OpenAI đã cấu hình:** {'✅ Có' if current_openai_status else '❌ Chưa'}")
        if not current_openai_status:
            st.caption("💡 Nhập API Key trong phần '🔑 Cấu hình OpenAI API Key' ở trên để kích hoạt.")

        if ".venv" not in sys.executable.replace("\\", "/"):
            st.warning(
                "Có vẻ bạn **không chạy ứng dụng bằng môi trường `.venv` trong dự án**.\n\n"
                "Hãy dùng lệnh sau trong PowerShell tại thư mục dự án:\n"
                "`.\.venv\\Scripts\\streamlit run app.py`"
            )

# Xử lý nếu người dùng đã tải file lên
if uploaded_files:
    st.markdown("---")
    st.header("Kết quả trích xuất")

    for uploaded_file in uploaded_files:
        with st.expander(f"Kết quả cho file: {uploaded_file.name}", expanded=True):
            with st.spinner(f"Đang xử lý '{uploaded_file.name}'..."):
                file_bytes = uploaded_file.getvalue()
                file_extension = uploaded_file.name.split('.')[-1].lower()
                
                # Gọi hàm xử lý đã được đơn giản hóa
                text, error = process_file(file_bytes, file_extension, lang_code)

            if error:
                st.error(error)
            else:
                # Nếu bật OpenAI, gọi thêm bước hậu xử lý
                improved_text = None
                openai_error = None
                if use_openai:
                    # Lấy client mới từ session state
                    current_client = get_openai_client()
                    if current_client is None:
                        openai_error = "Chưa cấu hình OpenAI API Key. Vui lòng nhập API Key trong phần cấu hình ở trên."
                    else:
                        with st.spinner(f"Đang cải thiện văn bản bằng OpenAI ({openai_model})..."):
                            improved_text, openai_error = enhance_with_openai(
                                text, 
                                lang_code, 
                                model=openai_model,
                                enhancement_level=enhancement_level,
                                client=current_client
                            )

                # Hiển thị kết quả trong các tab
                if use_openai and not openai_error and improved_text:
                    # Thống kê so sánh
                    col_stat1, col_stat2, col_stat3 = st.columns(3)
                    with col_stat1:
                        st.metric("Độ dài gốc", f"{len(text):,} ký tự")
                    with col_stat2:
                        st.metric("Độ dài sau cải thiện", f"{len(improved_text):,} ký tự")
                    with col_stat3:
                        diff = len(improved_text) - len(text)
                        st.metric("Thay đổi", f"{diff:+,} ký tự", delta=f"{diff/len(text)*100:.1f}%" if len(text) > 0 else "0%")
                    
                    tab1, tab2, tab3 = st.tabs([
                        "📝 Văn bản gốc (Tesseract)", 
                        "✨ Văn bản đã cải thiện (OpenAI)",
                        "🔍 So sánh"
                    ])
                    
                    with tab1:
                        st.text_area(
                            "Văn bản gốc từ OCR:",
                            text,
                            height=300,
                            key=f"text_raw_{uploaded_file.name}",
                            help="Văn bản được trích xuất trực tiếp từ Tesseract OCR"
                        )
                        st.caption(f"📊 {len(text.split())} từ | {len(text)} ký tự")
                    
                    with tab2:
                        st.text_area(
                            "Văn bản đã được cải thiện:",
                            improved_text,
                            height=300,
                            key=f"text_improved_{uploaded_file.name}",
                            help=f"Văn bản đã được OpenAI ({openai_model}) xử lý với mức độ {enhancement_level}"
                        )
                        st.caption(f"📊 {len(improved_text.split())} từ | {len(improved_text)} ký tự")
                        st.success("✅ Văn bản đã được cải thiện về chính tả, dấu và định dạng!")
                    
                    with tab3:
                        st.subheader("So sánh trực quan")
                        st.write("**Văn bản gốc:**")
                        st.code(text[:500] + ("..." if len(text) > 500 else ""), language=None)
                        st.write("**Văn bản đã cải thiện:**")
                        st.code(improved_text[:500] + ("..." if len(improved_text) > 500 else ""), language=None)
                        st.info("💡 Tip: So sánh hai phiên bản để thấy những cải thiện về dấu, chính tả và định dạng.")

                    # Cho phép tải cả 2 phiên bản
                    col_dl1, col_dl2 = st.columns(2)
                    with col_dl1:
                        st.download_button(
                            label="📥 Tải văn bản gốc",
                            data=text.encode('utf-8'),
                            file_name=f"ket_qua_goc_{uploaded_file.name}.txt",
                            mime="text/plain",
                            key=f"download_raw_{uploaded_file.name}",
                            use_container_width=True,
                        )
                    with col_dl2:
                        st.download_button(
                            label="📥 Tải văn bản đã cải thiện",
                            data=improved_text.encode('utf-8'),
                            file_name=f"ket_qua_cai_thien_{uploaded_file.name}.txt",
                            mime="text/plain",
                            key=f"download_improved_{uploaded_file.name}",
                            use_container_width=True,
                        )

                else:
                    # Nếu không dùng OpenAI hoặc có lỗi khi gọi OpenAI
                    if use_openai and openai_error:
                        st.warning(openai_error)

                    st.text_area(
                        "Văn bản:",
                        text,
                        height=300,
                        key=f"text_{uploaded_file.name}",
                    )
                    st.download_button(
                        label="📥 Tải kết quả này",
                        data=text.encode('utf-8'),
                        file_name=f"ket_qua_{uploaded_file.name}.txt",
                        mime="text/plain",
                        key=f"download_{uploaded_file.name}",
                    )
