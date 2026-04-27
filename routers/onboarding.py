import os
import psycopg2
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()
# --- HÀM KẾT NỐI DATABASE CHUẨN ---
def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    return psycopg2.connect(db_url, keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5)
# --- 1. ĐỊNH NGHĨA SCHEMA ---
class OnboardingTask(BaseModel):
    day: int
    title: str
    message: str
    action_required: bool = True # Yêu cầu người dùng phải bấm xác nhận
    suggested_prompt: str  # <--- Câu lệnh mồi để ép chatbot RAG trả lời


# --- 2. DỮ LIỆU MẪU (Nên chuyển vào Database thực tế) ---
# FIX 1: Đã đưa dòng này ra sát lề trái, xóa thụt lề sai
ONBOARDING_SCENARIOS = {
    1: OnboardingTask(
        day=1, 
        title="Giới thiệu Văn hóa & Sơ đồ tổ chức", 
        message="Chào mừng gia nhập công ty! Dưới đây là sơ đồ tổ chức và tầm nhìn cốt lõi. Hãy bấm 'Học ngay' để AI hướng dẫn nhé.",
        suggested_prompt="Hãy giới thiệu ngắn gọn về văn hóa cốt lõi và sơ đồ tổ chức của công ty." 
    ),
    2: OnboardingTask(
        day=2, 
        title="Quy trình & Nội quy", 
        message="Hôm nay tìm hiểu về quy trình xin nghỉ phép và hệ thống nội bộ.",
        suggested_prompt="Hãy hướng dẫn chi tiết quy trình xin nghỉ phép của công ty từng bước một." 
    ),
    3: OnboardingTask(
        day=3, 
        title="Tài liệu chuyên môn", 
        message="Đây là kho tài liệu dành riêng cho phòng ban của nhân viên. Hãy dành thời gian nghiên cứu các SOP (Quy trình chuẩn) này.",
        # FIX 2: Thêm dấu phẩy ở dòng trên và đổi lại câu mồi cho đúng nội dung SOP
        suggested_prompt="Hãy tóm tắt các quy trình chuẩn (SOP) quan trọng nhất mà nhân viên mới cần nắm rõ." 
    )
}

# Giả lập Database lưu trữ tiến độ của nhân viên
user_progress_db = {
    "EMP001": {"current_day": 1, "completed_days": [], "is_fully_completed": False}
}

# --- 3. API ENDPOINTS ---

@router.get("/api/onboarding/{user_id}")
async def get_onboarding_status(user_id: str):
    """Lấy trạng thái hội nhập trực tiếp từ Supabase"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        # Kiểm tra cột is_onboarded trong bảng users
        c.execute("SELECT is_onboarded FROM users WHERE username = %s", (user_id,))
        result = c.fetchone()
        c.close()
        conn.close()
        
        # Nếu không tìm thấy user hoặc is_onboarded = True -> Đã hoàn thành
        if not result or result[0] == True:
            return {"status": "completed", "is_completed": True, "message": "Đã hoàn thành lộ trình hội nhập."}
            
        # Nếu is_onboarded = False -> Trả về kịch bản Ngày 1
        task = ONBOARDING_SCENARIOS.get(1)
        return {
            "status": "in_progress",
            "is_completed": False,
            "current_task": task.dict() if task else None
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/api/onboarding/{user_id}/complete")
async def complete_onboarding_task(user_id: str):
    """Đánh dấu hoàn thành vĩnh viễn trên Supabase"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        # Lưu vào Supabase: Cập nhật is_onboarded thành TRUE
        c.execute("UPDATE users SET is_onboarded = TRUE WHERE username = %s", (user_id,))
        conn.commit()
        c.close()
        conn.close()
        return {"status": "success", "message": "Đã lưu trạng thái hoàn thành vào Database"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))