import os
import psycopg2
from psycopg2 import IntegrityError
import shutil
import hashlib
import uuid
import ast
import subprocess
from datetime import datetime, timedelta
from typing import Optional
import re 
import json
import threading
import time
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from rag import search_docs, check_exact_faq_match
from routers.onboarding import router as onboarding_router
import logging 
from dotenv import load_dotenv
import PyPDF2
import io
import PIL.Image
from fastapi import BackgroundTasks 

app = FastAPI()
load_dotenv()

os.makedirs("documents", exist_ok=True)
os.makedirs("avatars", exist_ok=True)
os.makedirs("vector_db", exist_ok=True)

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "/notifications/" in msg or "/admin/unanswered" in msg:
            return False
        return True

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.include_router(onboarding_router)

DOCS_DIR = "documents"
AVATARS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "avatars")
app.mount("/avatars", StaticFiles(directory=AVATARS_DIR), name="avatars")
app.mount("/files", StaticFiles(directory=DOCS_DIR), name="files")

# =====================================================================
# 🛠️ KẾT NỐI DATABASE SUPABASE (POSTGRESQL)
# =====================================================================

def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    return psycopg2.connect(db_url)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT, 
        role TEXT DEFAULT 'staff', is_onboarded BOOLEAN DEFAULT false, avatar TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS document_permissions (
        file_name TEXT PRIMARY KEY, required_role TEXT DEFAULT 'staff')''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS chat_sessions (
        id TEXT PRIMARY KEY, username TEXT, title TEXT, last_active TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history (
        id SERIAL PRIMARY KEY, session_id TEXT, username TEXT, role TEXT, 
        content TEXT, sources TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS unanswered_questions (
        id SERIAL PRIMARY KEY, question TEXT, username TEXT, session_id TEXT, 
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS feedbacks (
        id SERIAL PRIMARY KEY, session_id TEXT, username TEXT, bot_response TEXT, 
        rating TEXT, reason TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id SERIAL PRIMARY KEY, username TEXT, session_id TEXT, message TEXT, 
        is_read BOOLEAN DEFAULT false, is_trashed BOOLEAN DEFAULT false, 
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS reminders (
        id SERIAL PRIMARY KEY, username TEXT, task TEXT, remind_at TIMESTAMP, 
        is_done BOOLEAN DEFAULT false, is_notified BOOLEAN DEFAULT false)''')

    # Tự động cấy Admin mới (Username: admin1 | Pass: 123456)
    admin_hashed = hashlib.sha256("123456".encode()).hexdigest()
    c.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING", 
              ("admin1", admin_hashed, "admin"))

    conn.commit()
    c.close()
    conn.close()

init_db()

# =====================================================================
# 🚀 HỆ THỐNG QUẢN LÝ API AI (FALLBACK THÔNG MINH)
# =====================================================================

# =====================================================================
# 🚀 HỆ THỐNG QUẢN LÝ BĂNG ĐẠN API VÀ FALLBACK THÔNG MINH
# =====================================================================

raw_keys_dict = {
    "Key Mặc định": os.getenv("GEMINI_API_KEY"),
    "Key 1": os.getenv("GEMINI_API_KEY_1"),
    "Key 2": os.getenv("GEMINI_API_KEY_2"),
    "Key 3": os.getenv("GEMINI_API_KEY_3"),
    "Key 4": os.getenv("GEMINI_API_KEY_4"),
    "Key 5": os.getenv("GEMINI_API_KEY_5")
}

VALID_KEYS = [(name, key) for name, key in raw_keys_dict.items() if key]
print(f" 🚀  Băng đạn đã nạp: {len(VALID_KEYS)} API Keys")

current_key_idx = 0

def get_optimized_models():
    """
    Cập nhật danh sách "Đội hình ra sân" khớp 100% với tài khoản của sếp:
    - Tiên phong: gemini-3-flash-preview (Dùng 20 lượt VIP đầu tiên).
    - Đánh chính : gemini-3.1-flash-lite-preview (dùng 15 lượt VIP đầu tiên).
    - Chủ lực gánh team: gemma-3-27b-it (Thông minh nhất dòng Gemma, bao trọn 14.400 lượt).
    - Dự phòng: gemma-3-12b-it (Đề phòng con 27B bị lỗi mạng).
    """
    return [
        "gemini-3-flash-preview", 
        "gemini-3.1-flash-lite-preview",
        "gemma-3-27b-it",    # Bản 27 Tỷ tham số chuyên dùng để Chat (it = instruction tuned)
        "gemma-3-12b-it"     
    ]

def generate_content_with_fallback(prompt) -> str:
    global current_key_idx
    if not VALID_KEYS:
        return "Lỗi Server: Không tìm thấy API Key nào trong file .env!"

    models = get_optimized_models()

    # Vòng lặp 1: Quét qua từng API Key trong băng đạn
    for attempt in range(len(VALID_KEYS)):
        key_name, current_key = VALID_KEYS[current_key_idx]
        genai.configure(api_key=current_key)

        # Vòng lặp 2: Quét qua từng mô hình AI
        for model_name in models:
            print(f"  🔄  Đang xử lý... | Dùng: [{key_name}] | Mô hình: [{model_name}]")
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                print(f"  ✅  THÀNH CÔNG   | Đã trả lời bằng [{key_name}] - [{model_name}]")
                return response.text

            except ResourceExhausted:
                # Nếu model này hết Token, KHÔNG break vội!
                # Có thể gemini-2.5-flash hết 20 lượt, nhưng gemini-1.5-flash vẫn còn 1500 lượt.
                print(f"  ⚠️  HẾT HẠN MỨC  | [{model_name}] kiệt sức. Chuyển model khác...")
                continue

            except Exception as e:
                error_msg = str(e).lower()
                print(f"  ❌  LỖI KHÁC     | [{key_name}] - [{model_name}]: {error_msg[:50]}...")
                
                # PHANH KHẨN CẤP: Chống Spam API của Google nếu nội dung vi phạm
                if "400" in error_msg or "safety" in error_msg:
                    return "Câu hỏi vi phạm chính sách an toàn hoặc quá phức tạp. Vui lòng thử lại!"
                
                continue # Lỗi mạng bình thường thì thử tiếp

        # Nếu chạy hết tất cả các model mà vẫn không có kết quả -> Key này đã cạn kiệt hoàn toàn
        print(f"  🚨  CHUYỂN KEY   | [{key_name}] đã hết sạch Token. Nạp súng mới!")
        current_key_idx = (current_key_idx + 1) % len(VALID_KEYS)

    print("  🚨  BÁO ĐỘNG ĐỎ  | Toàn bộ hệ thống API Key đã cạn kiệt!")
    return "Hệ thống AI hiện đang quá tải do hết sạch Token trên tất cả các Key. Vui lòng đợi hoặc nạp thêm Key."
# =====================================================================
# 📡 ENDPOINTS
# =====================================================================

class User(BaseModel): username: str; password: str
class Question(BaseModel): question: str; session_id: Optional[str] = None
class RenameRequest(BaseModel): title: str
class FeedbackReq(BaseModel): session_id: str; bot_response: str; rating: str; reason: str = ""
class UpdateRoleReq(BaseModel): role: str
class AnswerReq(BaseModel): question: str; answer: str
class EditFaqReq(BaseModel): question: str; answer: str
class BroadcastReq(BaseModel): message: str; admin_username: str = None

@app.post("/feedback")
def save_feedback(req: FeedbackReq, username: str = "guest"):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO feedbacks (session_id, username, bot_response, rating, reason) VALUES (%s, %s, %s, %s, %s)", 
              (req.session_id, username, req.bot_response, req.rating, req.reason))
    conn.commit()
    c.close()
    conn.close()
    return {"status": "success"}

@app.get("/sessions/{username}")
async def get_sessions(username: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, title, last_active FROM chat_sessions WHERE username = %s ORDER BY last_active DESC", (username,))
    rows = c.fetchall()
    c.close()
    conn.close()
    return [{"id": r[0], "title": r[1], "last_active": r[2]} for r in rows]

@app.get("/history/{session_id}")
async def get_chat_history(session_id: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT role, content, sources, timestamp FROM chat_history WHERE session_id = %s ORDER BY timestamp ASC", (session_id,))
    rows = c.fetchall()
    c.close()
    conn.close()
    history = []
    for r in rows:
        try: sources = ast.literal_eval(r[2]) if r[2] else []
        except: sources = []
        history.append({"role": r[0], "text": r[1], "sources": sources, "time": r[3]})
    return history

def rewrite_query(original_query: str, history_text: str = "") -> str:
    try:
        prompt = f"Hệ thống tối ưu truy vấn...\n[LỊCH SỬ]: {history_text}\n[CÂU HỎI]: {original_query}\n[TRUY VẤN VIẾT LẠI]:"
        return generate_content_with_fallback(prompt).strip()
    except Exception: return original_query

@app.post("/ask")
def ask_ai(data: Question, username: str = "guest"):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT role FROM users WHERE username = %s", (username,))
        row = c.fetchone()
        user_role = row[0] if row else 'staff'

        s_id = data.session_id
        is_new_session = False
        if not s_id or s_id == "null" or s_id == "":
            s_id = str(uuid.uuid4())
            is_new_session = True
        
        history_text = ""
        if not is_new_session:
            c.execute("SELECT role, content FROM chat_history WHERE session_id = %s ORDER BY id DESC LIMIT 4", (s_id,))
            raw_history = c.fetchall()
            raw_history.reverse()
            for r, text_content in raw_history:
                prefix = "Nhân viên" if r == "user" else "AI"
                history_text += f"{prefix}: {text_content[:500]}...\n"
        
        optimized_query = data.question
        direct_answer = check_exact_faq_match(optimized_query, user_role=user_role)

        if direct_answer:
            ai_answer = direct_answer
            sources = ["Giải đáp trực tiếp từ Admin"]
            follow_ups = []
            ai_answer_raw = ai_answer
        else:
            rag_res = search_docs(optimized_query, user_role=user_role)
            context = rag_res.get("answer", "")
            raw_sources = rag_res.get("sources", [])
            sources = [f"Tài liệu: {s}" for s in raw_sources]
            
            if user_role == 'admin':
                prompt = f"""Bạn là Trợ lý Hành chính & Nhân sự (HR Copilot) cấp cao của ABC TECH.
Nhiệm vụ: LÊN DÀN Ý, SOẠN THẢO VĂN BẢN, VIẾT EMAIL, THÔNG BÁO. Hành văn lịch sự.
[TÀI LIỆU NỘI BỘ]: {context}
[QUY TẮC NHẮC VIỆC]:
Nếu Giám đốc yêu cầu nhắc nhở, thêm chính xác: [[REMINDER: {{"task": "nội dung ngắn gọn", "time": "YYYY-MM-DD HH:MM:SS"}}]]
[YÊU CẦU TỪ GIÁM ĐỐC]: {data.question}"""
            else:
                prompt = f"""Bạn là Trợ lý AI Nội bộ của ABC TECH. KHÔNG PHẢI chatbot tâm sự.
[QUY TẮC SINH TỬ]:
1. CHỈ ĐƯỢC PHÉP trả lời dựa trên [TÀI LIỆU NỘI BỘ]. KHÔNG bịa câu trả lời.
2. Nếu KHÔNG CÓ THÔNG TIN, PHẢI TỪ CHỐI bằng câu: "Tôi chưa được cập nhật thông tin này."
[LỊCH SỬ CHAT]: {history_text}
[TÀI LIỆU NỘI BỘ]: {context}
[CÂU HỎI MỚI]: {data.question}
[YÊU CẦU ĐẶC BIỆT]: Gợi ý 3 câu hỏi tiếp theo đặt dưới ký hiệu ---SUGGESTIONS---"""

            ai_answer_raw = generate_content_with_fallback(prompt)
            ai_answer = ai_answer_raw
            follow_ups = []

        current_time = datetime.now()
        
        if "[[REMINDER:" in ai_answer_raw:
            try:
                sources = [] 
                reminder_part = ai_answer_raw.split("[[REMINDER:")[1].split("]]")[0].strip()
                rem_data = json.loads(reminder_part)
                c.execute("INSERT INTO reminders (username, task, remind_at) VALUES (%s, %s, %s)", (username, rem_data['task'], rem_data['time']))
                ai_answer_raw = ai_answer_raw.split("[[REMINDER:")[0].strip()
                ai_answer = ai_answer_raw
            except Exception as e: print(f"Lỗi phân tích JSON nhắc việc: {e}")
            
        if "---SUGGESTIONS---" in ai_answer_raw:
            parts = ai_answer_raw.split("---SUGGESTIONS---")
            ai_answer = parts[0].strip()
            follow_ups = re.findall(r'^\d+\.\s*(.+)', parts[1].strip(), re.MULTILINE)
            
        lower_answer = ai_answer.lower()
        if user_role != 'admin' and ("chưa được cập nhật" in lower_answer or "không có thông tin" in lower_answer):
            sources = []
            try: c.execute("INSERT INTO unanswered_questions (question, username, session_id) VALUES (%s, %s, %s)", (data.question, username, s_id))
            except: pass
            
        if is_new_session:
            title = data.question[:30] + "..."
            c.execute("INSERT INTO chat_sessions (id, username, title, last_active) VALUES (%s, %s, %s, %s)", (s_id, username, title, current_time))
            c.execute("INSERT INTO chat_history (session_id, username, role, content, sources) VALUES (%s, %s, %s, %s, %s)", (s_id, username, "user", data.question, "[]"))
            
        c.execute("INSERT INTO chat_history (session_id, username, role, content, sources) VALUES (%s, %s, %s, %s, %s)", (s_id, username, "bot", ai_answer, str(sources)))
        c.execute("UPDATE chat_sessions SET last_active = %s WHERE id = %s", (current_time, s_id))

        conn.commit()
        c.close()
        conn.close()
        return { "answer": ai_answer, "sources": sources, "follow_ups": follow_ups, "session_id": s_id, "time": current_time.strftime("%H:%M - %d/%m/%Y") }
    except Exception as e:
        return {"answer": f"Lỗi hệ thống AI: {str(e)}", "status": "error"}

@app.post("/ask_with_file")
async def ask_with_file(username: str, role: str = 'staff', question: str = Form(""), session_id: str = Form(""), file: UploadFile = File(...)):
    try:
        s_id = session_id or str(uuid.uuid4())
        is_new_session = not session_id
            
        conn = get_db_connection()
        c = conn.cursor()
        history_text = ""
        if not is_new_session:
            c.execute("SELECT role, content FROM chat_history WHERE session_id = %s ORDER BY id DESC LIMIT 4", (s_id,))
            raw_history = c.fetchall()
            raw_history.reverse()
            for r, text_content in raw_history:
                prefix = "Nhân viên" if r == "user" else "AI"
                history_text += f"{prefix}: {text_content[:500]}...\n"
                
        file_extension = file.filename.split('.')[-1].lower()
        ai_prompt_data = None
        extracted_text = ""
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if file_extension in ['jpg', 'jpeg', 'png']:
            image_bytes = await file.read()
            img = PIL.Image.open(io.BytesIO(image_bytes))
            system_prompt = f"""Bạn là trợ lý AI thông minh của ABC TECH.
Câu hỏi: "{question}"
Lịch sử: {history_text}
Hãy quan sát kỹ bức ảnh và trả lời. Thêm tag [[REMINDER: {{"task": "...", "time": "YYYY-MM-DD HH:MM:SS"}}]] nếu cần."""
            ai_prompt_data = [img, system_prompt]
        else:
            if file_extension == 'pdf':
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(await file.read()))
                for page in pdf_reader.pages: extracted_text += page.extract_text() or ""
            elif file_extension == 'txt':
                extracted_text = (await file.read()).decode('utf-8')
            else:
                return {"answer": f"Định dạng {file_extension} hiện chưa hỗ trợ."}
                
            system_prompt = f"""Bạn là trợ lý AI. Nội dung tệp: {extracted_text[:2500]}...
Câu hỏi: "{question}"
Lịch sử: {history_text}"""
            ai_prompt_data = system_prompt
            
        ai_answer_raw = generate_content_with_fallback(ai_prompt_data)
        current_time = datetime.now()
        ai_answer = ai_answer_raw
        follow_ups = []
        
        if "[[REMINDER:" in ai_answer_raw:
            try:
                reminder_part = ai_answer_raw.split("[[REMINDER:")[1].split("]]")[0].strip()
                rem_data = json.loads(reminder_part)
                c.execute("INSERT INTO reminders (username, task, remind_at) VALUES (%s, %s, %s)", (username, rem_data['task'], rem_data['time']))
                ai_answer_raw = ai_answer_raw.split("[[REMINDER:")[0].strip()
                ai_answer = ai_answer_raw
            except Exception as e: print(f"Lỗi phân tích JSON: {e}")
            
        if "---SUGGESTIONS---" in ai_answer_raw:
            parts = ai_answer_raw.split("---SUGGESTIONS---")
            ai_answer = parts[0].strip()
            follow_ups = re.findall(r'^\d+\.\s*(.+)', parts[1].strip(), re.MULTILINE)
            
        if is_new_session:
            title = (question if question.strip() else f"Gửi tệp {file.filename}")[:30] + "..."
            c.execute("INSERT INTO chat_sessions (id, username, title, last_active) VALUES (%s, %s, %s, %s)", (s_id, username, title, current_time))
            user_content = question if question.strip() else f"[Đã đính kèm tệp: {file.filename}]"
            c.execute("INSERT INTO chat_history (session_id, username, role, content, sources) VALUES (%s, %s, %s, %s, %s)", (s_id, username, "user", user_content, "[]"))
            
        c.execute("INSERT INTO chat_history (session_id, username, role, content, sources) VALUES (%s, %s, %s, %s, %s)", (s_id, username, "bot", ai_answer, str([file.filename])))
        c.execute("UPDATE chat_sessions SET last_active = %s WHERE id = %s", (current_time, s_id))

        conn.commit()
        c.close()
        conn.close()
        return { "answer": ai_answer, "sources": [file.filename], "follow_ups": follow_ups, "session_id": s_id, "time": current_time.strftime("%H:%M - %d/%m/%Y") }
    except Exception as e:
        return {"answer": f"Lỗi xử lý tệp Backend: {str(e)}", "status": "error"}

@app.post("/register")
async def register(user: User):
    username = user.username.strip()
    password = user.password.strip()
    if len(username) < 3: return {"status": "error", "message": "Tên đăng nhập phải có ít nhất 3 ký tự!"}
    if len(password) < 6: return {"status": "error", "message": "Mật khẩu phải có ít nhất 6 ký tự!"}
    if not username.isalnum(): return {"status": "error", "message": "Tên không chứa ký tự đặc biệt!"}
    
    hashed = hashlib.sha256(password.encode()).hexdigest()
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, 'staff')", (username, hashed))
        conn.commit()
        c.close()
        conn.close()
        return {"status": "success", "message": "Đăng ký tài khoản thành công!"}
    except IntegrityError:
        return {"status": "error", "message": "Tên đăng nhập này đã tồn tại. Vui lòng chọn tên khác!"}
    except Exception as e:
        return {"status": "error", "message": f"Lỗi hệ thống: {str(e)}"}

@app.post("/login")
async def login(user: User):
    username = user.username.strip()
    password = user.password.strip()
    if not username or not password: return {"status": "error", "message": "Vui lòng nhập đầy đủ!"}
    
    hashed = hashlib.sha256(password.encode()).hexdigest()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT username, role, is_onboarded FROM users WHERE username = %s AND password = %s", (username, hashed))
    record = c.fetchone()
    c.close()
    conn.close()

    if record:
        return {"status": "success", "username": record[0], "role": record[1], "is_onboarded": bool(record[2]), "message": "Thành công!"}
    return {"status": "error", "message": "Sai tên đăng nhập hoặc mật khẩu!"}

@app.put("/users/{username}/onboarded")
def complete_onboarding(username: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET is_onboarded = true WHERE username = %s", (username,))
    conn.commit()
    c.close()
    conn.close()
    return {"status": "success"}

@app.put("/sessions/{session_id}/rename")
def rename_session(session_id: str, req: RenameRequest):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE chat_sessions SET title = %s WHERE id = %s", (req.title, session_id))
    conn.commit()
    c.close()
    conn.close()
    return {"message": "Đã đổi tên thành công"}

@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM chat_sessions WHERE id = %s", (session_id,))
    c.execute("DELETE FROM chat_history WHERE session_id = %s", (session_id,))
    conn.commit()
    c.close()
    conn.close()
    return {"message": "Đã xóa thành công"}

@app.get("/sessions/{session_id}/summarize")
def summarize_session(session_id: str):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT role, content FROM chat_history WHERE session_id = %s ORDER BY timestamp ASC", (session_id,))
        rows = c.fetchall()
        c.close()
        conn.close()
        if not rows: return {"summary": "Chưa có nội dung."}
        chat_text = "\n".join([f"{r[0]}: {r[1]}" for r in rows])
        prompt = f"Tóm tắt ngắn gọn 1-2 câu:\n\n{chat_text}"
        summary_text = generate_content_with_fallback(prompt)
        return {"summary": summary_text}
    except Exception: return {"summary": "Lỗi hệ thống."}

@app.get("/notifications/{username}")
def get_notifications(username: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, session_id, message, is_read, timestamp FROM notifications WHERE username = %s AND is_trashed = false ORDER BY timestamp DESC", (username,))
    rows = c.fetchall()
    c.close()
    conn.close()
    return [{"id": r[0], "session_id": r[1], "message": r[2], "is_read": bool(r[3]), "time": r[4]} for r in rows]

@app.get("/notifications/{username}/trash")
def get_trashed_notifications(username: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, session_id, message, is_read, timestamp FROM notifications WHERE username = %s AND is_trashed = true ORDER BY timestamp DESC", (username,))
    rows = c.fetchall()
    c.close()
    conn.close()
    return [{"id": r[0], "session_id": r[1], "message": r[2], "is_read": bool(r[3]), "time": r[4]} for r in rows]

@app.put("/notifications/{notif_id}/trash")
def trash_notification(notif_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE notifications SET is_trashed = true WHERE id = %s", (notif_id,))
    conn.commit()
    c.close()
    conn.close()
    return {"status": "success"}

@app.put("/notifications/{notif_id}/restore")
def restore_notification(notif_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE notifications SET is_trashed = false WHERE id = %s", (notif_id,))
    conn.commit()
    c.close()
    conn.close()
    return {"status": "success"}

@app.put("/notifications/{notif_id}/read")
def mark_notif_read(notif_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE notifications SET is_read = true WHERE id = %s", (notif_id,))
    conn.commit()
    c.close()
    conn.close()
    return {"status": "success"}

@app.delete("/notifications/{notif_id}")
def delete_notification(notif_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM notifications WHERE id = %s", (notif_id,))
    conn.commit()
    c.close()
    conn.close()
    return {"status": "success"}

@app.post("/admin/answer_unanswered/{q_id}")
def answer_unanswered_question(q_id: int, req: AnswerReq):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT session_id, question, username FROM unanswered_questions WHERE id = %s", (q_id,))
        row = c.fetchone()
        if not row: return {"status": "error", "message": "Không tìm thấy câu hỏi"}

        session_id, question, username = row
        current_time = datetime.now()
        filename = f"FAQ_{q_id}_{current_time.strftime('%Y%m%d%H%M%S')}.txt"
        filepath = os.path.join(DOCS_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f: f.write(f"Câu hỏi: {question}\nCâu trả lời: {req.answer}\n")

        c.execute("INSERT INTO document_permissions (file_name, required_role) VALUES (%s, 'staff') ON CONFLICT (file_name) DO UPDATE SET required_role = 'staff'", (filename,))

        if session_id:
            notification_msg = f" 🔔  **[Cập nhật từ Quản trị viên]**\n\n* 📝  Câu hỏi: {question}*\n\n** 👉  Trả lời:** {req.answer}"
            c.execute("INSERT INTO chat_history (session_id, username, role, content, sources) VALUES (%s, %s, %s, %s, %s)", (session_id, username, "bot", notification_msg, "['Phản hồi từ Admin']"))
            c.execute("UPDATE chat_sessions SET last_active = %s WHERE id = %s", (current_time, session_id))
            short_msg = f"Admin đã giải đáp: '{question[:25]}...'"
            c.execute("INSERT INTO notifications (username, session_id, message, timestamp) VALUES (%s, %s, %s, %s)", (username, session_id, short_msg, current_time))
        
        c.execute("DELETE FROM unanswered_questions WHERE id = %s", (q_id,))
        conn.commit()
        return {"status": "success"}
    except Exception as e: return {"status": "error", "message": str(e)}
    finally:
        c.close()
        conn.close()

@app.post("/admin/upload")
async def upload_document(file: UploadFile = File(...), role: str = Form(...)):
    try:
        file_path = os.path.join(DOCS_DIR, file.filename)
        with open(file_path, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO document_permissions (file_name, required_role) VALUES (%s, %s) ON CONFLICT (file_name) DO UPDATE SET required_role = EXCLUDED.required_role", (file.filename, role))
        conn.commit()
        c.close()
        conn.close()
        subprocess.run(["python", "ingest.py"])
        return {"message": f"Đã tải lên và nạp {file.filename} thành công!"}
    except Exception as e: return {"error": str(e)}

@app.get("/admin/documents")
def get_documents():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT file_name, file_name, required_role FROM document_permissions WHERE file_name NOT LIKE 'FAQ_%'")
    docs = [{"id": r[0], "file_name": r[1], "role": r[2]} for r in c.fetchall()]
    c.close()
    conn.close()
    return docs

@app.get("/admin/faqs")
def get_faqs():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT file_name FROM document_permissions WHERE file_name LIKE 'FAQ_%'")
    db_faqs = c.fetchall()
    c.close()
    conn.close()
    faqs = []
    for r in db_faqs:
        file_name = r[0]
        filepath = os.path.join(DOCS_DIR, file_name)
        question, answer = "", ""
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                if "Câu hỏi: " in content and "Câu trả lời: " in content:
                    parts = content.split("\nCâu trả lời: ")
                    if len(parts) >= 2:
                        question = parts[0].replace("Câu hỏi: ", "").strip()
                        answer = parts[1].strip()
                else: question, answer = file_name, content
        faqs.append({"id": file_name, "file_name": file_name, "question": question, "answer": answer})
    return faqs

@app.put("/admin/faqs/{file_name}")
def update_faq(file_name: str, req: EditFaqReq):
    try:
        filepath = os.path.join(DOCS_DIR, file_name)
        if not os.path.exists(filepath): return {"status": "error", "message": "File không tồn tại"}
        old_question = ""
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            if "Câu hỏi: " in content and "Câu trả lời: " in content:
                old_question = content.split("Câu trả lời: ")[0].replace("Câu hỏi: ", "").strip()
        with open(filepath, "w", encoding="utf-8") as f: f.write(f"Câu hỏi: {req.question}\nCâu trả lời: {req.answer}\n")
        if old_question:
            conn = get_db_connection()
            c = conn.cursor()
            new_chat_content = f" 🔔  **[Cập nhật từ Quản trị viên]**\n\n* 📝  Câu hỏi: {req.question}*\n\n** 👉  Trả lời:** {req.answer}"
            c.execute("UPDATE chat_history SET content = %s WHERE role = 'bot' AND content LIKE %s", (new_chat_content, f"%{old_question[:20]}%"))
            short_msg = f"Admin đã CẬP NHẬT: '{req.question[:25]}...'"
            c.execute("UPDATE notifications SET message = %s, is_read = false, timestamp = CURRENT_TIMESTAMP WHERE message LIKE %s", (short_msg, f"%{old_question[:20]}%"))
            conn.commit()
            c.close()
            conn.close()
        return {"status": "success"}
    except Exception as e: return {"status": "error", "message": str(e)}

@app.delete("/admin/documents/{filename}")
def delete_document(filename: str, background_tasks: BackgroundTasks):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM document_permissions WHERE file_name = %s", (filename,))
    conn.commit()
    c.close()
    conn.close()
    file_path = os.path.join(DOCS_DIR, filename)
    if os.path.exists(file_path): os.remove(file_path)
    background_tasks.add_task(subprocess.run, ["python", "ingest.py"])
    return {"message": f"Đã xóa file {filename}. Đang cập nhật DB ngầm."}

@app.post("/admin/set-permission")
def set_document_permission(file_name: str, role: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE document_permissions SET required_role = %s WHERE file_name = %s", (role, file_name))
    conn.commit()
    c.close()
    conn.close()
    return {"status": "success", "message": f"Đã cập nhật quyền {file_name} thành {role}"}

@app.get("/admin/logs")
def get_system_logs():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT session_id, username, role, content, timestamp FROM chat_history ORDER BY timestamp DESC LIMIT 100")
    logs = [{"session_id": r[0], "username": r[1], "role": r[2], "content": r[3], "time": r[4]} for r in c.fetchall()]
    c.close()
    conn.close()
    return logs

@app.get("/admin/unanswered")
def get_unanswered():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, question, username, timestamp FROM unanswered_questions ORDER BY timestamp DESC")
    logs = [{"id": r[0], "question": r[1], "username": r[2], "time": r[3]} for r in c.fetchall()]
    c.close()
    conn.close()
    return logs

@app.get("/admin/stats")
def get_admin_stats():
    conn = get_db_connection()
    c = conn.cursor()
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")

    c.execute("SELECT COUNT(*) FROM chat_history WHERE CAST(timestamp AS TEXT) LIKE %s", (f"{today_str}%",))
    total_msgs = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM unanswered_questions")
    unanswered = c.fetchone()[0]

    last_7_days = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_db_str = day.strftime("%Y-%m-%d")
        display_day = day.strftime("%d/%m")
        c.execute("SELECT COUNT(*) FROM chat_history WHERE CAST(timestamp AS TEXT) LIKE %s", (f"{day_db_str}%",))
        count = c.fetchone()[0]
        last_7_days.append({"date": display_day, "count": count})

    c.execute("SELECT sources FROM chat_history WHERE role = 'bot' AND sources != '[]'")
    all_sources = c.fetchall()
    doc_counts = {}
    for row in all_sources:
        try:
            sources_list = ast.literal_eval(row[0])
            for doc in sources_list: doc_counts[doc] = doc_counts.get(doc, 0) + 1
        except: pass

    top_docs = sorted(doc_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    c.close()
    conn.close()
    return { "total_messages_today": total_msgs, "unanswered_count": unanswered, "top_docs": [{"name": k, "count": v} for k, v in top_docs], "last_7_days": last_7_days }

@app.get("/admin/users")
def get_users():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, username, role FROM users")
    users = [{"id": r[0], "username": r[1], "role": r[2]} for r in c.fetchall()]
    c.close()
    conn.close()
    return users

@app.put("/admin/users/{username}/role")
def update_user_role(username: str, req: UpdateRoleReq):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET role = %s WHERE username = %s", (req.role, username))
    conn.commit()
    c.close()
    conn.close()
    return {"status": "success"}

@app.delete("/admin/unanswered/{q_id}")
def delete_unanswered(q_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM unanswered_questions WHERE id = %s", (q_id,))
    conn.commit()
    c.close()
    conn.close()
    return {"status": "success"}

@app.post("/users/{username}/avatar")
async def upload_avatar(username: str, file: UploadFile = File(...)):
    try:
        ext = file.filename.split('.')[-1]
        new_filename = f"avatar_{username}.{ext}"
        filepath = os.path.join(AVATARS_DIR, new_filename)
        with open(filepath, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET avatar = %s WHERE username = %s", (new_filename, username))
        conn.commit()
        c.close()
        conn.close()
        return {"status": "success", "avatar_url": new_filename}
    except Exception as e: return {"status": "error", "message": str(e)}

@app.get("/users/{username}/avatar")
def get_avatar(username: str):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT avatar FROM users WHERE username = %s", (username,))
        row = c.fetchone()
        c.close()
        conn.close()
        if row and row[0]: return {"avatar_url": row[0]}
    except: pass
    return {"avatar_url": None}

@app.post("/admin/broadcast")
def broadcast_to_company(req: BroadcastReq):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE role != 'locked'")
        users = c.fetchall()
        current_time = datetime.now()
        final_message = f" 📢  **[THÔNG BÁO TỪ BAN GIÁM ĐỐC]**\n\n{req.message}"
        sent_count = 0
        for u in users:
            username = u[0]
            if req.admin_username and username == req.admin_username: continue
            c.execute("INSERT INTO notifications (username, message, is_read, session_id, timestamp) VALUES (%s, %s, false, 'broadcast', %s)",
                      (username, final_message, current_time))
            sent_count += 1
        conn.commit()
        c.close()
        conn.close()
        return {"status": "success", "total_sent": sent_count}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def check_reminders_loop():
    while True:
        try:
            conn = get_db_connection()
            c = conn.cursor()
            now = datetime.now()
            c.execute("SELECT id, username, task FROM reminders WHERE remind_at <= %s AND is_notified = false", (now,))
            pending = c.fetchall()

            for r_id, user, task in pending:
                msg = f"⏰ **[NHẮC NHỞ CÔNG VIỆC]**: Bạn có việc cần làm ngay bây giờ:\n\n 👉  **{task}**"
                c.execute("INSERT INTO notifications (username, message, is_read, session_id, timestamp) VALUES (%s, %s, false, 'broadcast', %s)",
                          (user, msg, now))
                c.execute("UPDATE reminders SET is_notified = true WHERE id = %s", (r_id,))

            conn.commit()
            c.close()
            conn.close()
        except Exception as e:
            print(f"Lỗi quét nhắc nhở: {e}")
        time.sleep(60)

threading.Thread(target=check_reminders_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)