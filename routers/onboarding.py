from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

# --- 1. ĐỊNH NGHĨA SCHEMA ---
class OnboardingTask(BaseModel):
    day: int
    title: str
    message: str
    action_required: bool = True # Yêu cầu người dùng phải bấm xác nhận
    suggested_prompt: str  # <--- Câu lệnh mồi để ép chatbot RAG trả lời

class OnboardingProgress(BaseModel):
    user_id: str
    current_day: int
    completed_days: List[int]
    is_fully_completed: bool

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
    """Lấy nhiệm vụ hội nhập của ngày hiện tại cho nhân viên."""
    progress = user_progress_db.get(user_id)
    
    # 🌟 ĐÃ SỬA: Tự động khởi tạo cho nhân viên mới thay vì báo lỗi 404
    if not progress:
        progress = {"current_day": 1, "completed_days": [], "is_fully_completed": False}
        user_progress_db[user_id] = progress  # Lưu luôn vào Database giả lập
        
    if progress["is_fully_completed"]:
        return {"status": "completed", "message": "Đã hoàn thành toàn bộ lộ trình hội nhập."}
        
    current_day = progress["current_day"]
    task = ONBOARDING_SCENARIOS.get(current_day)
    
    return {
        "status": "in_progress",
        "progress": progress,
        "current_task": task.dict() if task else None
    }

@router.post("/api/onboarding/{user_id}/complete")
async def complete_onboarding_task(user_id: str, day: int):
    """Đánh dấu hoàn thành nhiệm vụ của một ngày cụ thể."""
    progress = user_progress_db.get(user_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin nhân viên")
        
    if day not in progress["completed_days"]:
        progress["completed_days"].append(day)
        
    # Chuyển sang ngày tiếp theo hoặc kết thúc
    next_day = day + 1
    if next_day > len(ONBOARDING_SCENARIOS):
        progress["is_fully_completed"] = True
    else:
        progress["current_day"] = next_day
        
    user_progress_db[user_id] = progress
    return {"message": f"Đã hoàn thành nhiệm vụ ngày {day}", "new_progress": progress}