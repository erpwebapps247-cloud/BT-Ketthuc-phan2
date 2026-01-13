# Trợ lý OCR Thông minh

Ứng dụng Streamlit trích xuất văn bản từ ảnh/PDF bằng Tesseract + pdf2image.

## Cách chạy nhanh
1) Tạo môi trường (khuyến nghị):
```
python -m venv .venv
.venv\Scripts\activate
```
2) Cài phụ thuộc Python:
```
pip install -r requirements.txt
```
3) Cài Tesseract & Poppler:
- Windows: cài `Tesseract-OCR` (ví dụ tại `C:\Program Files\Tesseract-OCR\tesseract.exe`) và Poppler (tải bản Windows và thêm `bin` vào PATH).
- Debian/Ubuntu: `sudo apt-get install tesseract-ocr tesseract-ocr-vie tesseract-ocr-eng poppler-utils`
4) Khai báo đường dẫn Tesseract nếu không tự nhận (Windows):
```
setx TESSERACT_CMD "C:\Program Files\Tesseract-OCR\tesseract.exe"
```
5) (Tuỳ chọn) Cấu hình OpenAI để cải thiện văn bản OCR:
```powershell
setx OPENAI_API_KEY "sk-..."
```
Khởi động lại terminal sau khi đặt biến môi trường.

6) Chạy ứng dụng:
```
streamlit run app.py
```

## Ghi chú
- `pdf2image` cần Poppler để chuyển PDF sang ảnh.
- Nếu gặp lỗi thiếu `pytesseract`, hãy chắc chắn đã cài bằng `pip install -r requirements.txt`.
- Nếu bật tuỳ chọn **Sử dụng OpenAI**, ứng dụng sẽ gửi văn bản OCR sang OpenAI để tự động sửa dấu / chính tả và trả về bản đã cải thiện.