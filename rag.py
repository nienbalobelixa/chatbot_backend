import os
import psycopg2
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings

def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    # Thêm các tham số keepalives để chống rớt mạng SSL đột ngột
    return psycopg2.connect(
        db_url,
        keepalives=1,
        keepalives_idle=30,      # Ping sau mỗi 30s không hoạt động
        keepalives_interval=10,  # Nếu không thấy phản hồi, ping lại sau 10s
        keepalives_count=5       # Thử tối đa 5 lần trước khi báo lỗi thực sự
    )
def get_vector_db():
    """Luôn đọc trực tiếp từ ổ cứng, KHÔNG lưu RAM. 
       Đảm bảo AI luôn thấy file mới nhất ngay sau khi Admin upload!"""
    try:
        api_key = os.environ.get("GEMINI_API_KEY_1") or os.environ.get("GEMINI_API_KEY")
        embedding = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001", 
            google_api_key=api_key
        )
        # Bắt buộc khởi tạo lại Chroma để nhận thư mục vector_db mới nhất
        db = Chroma(persist_directory="vector_db", embedding_function=embedding)
        return db
    except Exception as e:
        print(f"❌ Lỗi khởi tạo ChromaDB: {e}")
        return None

def get_allowed_files(user_role):
    """Lấy danh sách các file mà Role này được phép xem từ Supabase"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        if user_role == 'admin':
            c.execute("SELECT file_name FROM document_permissions")
        else:
            # Ép về chữ thường hết để so sánh, không lo bị gõ lệch chữ HOA/thường
            c.execute("SELECT file_name FROM document_permissions WHERE LOWER(required_role) = LOWER(%s)", (user_role,))
            
        # Làm sạch tên file (xóa khoảng trắng thừa) để đảm bảo khớp 100% với ChromaDB
        files = [row[0].strip() for row in c.fetchall() if row[0]]
        
        c.close()
        conn.close()
        return files
    except Exception as e:
        print(f"  ❌  [Lỗi Supabase] Không thể lấy danh sách file: {e}")
        return []

def search_docs(query, user_role='staff'):
    """Tìm kiếm tài liệu có lọc theo quyền truy cập (RBAC)"""
    print(f"\n  🔍  [Câu hỏi mới] '{query}' | Từ Role: '{user_role}'")
    
    # Bước 1: Xác định vùng dữ liệu được phép
    allowed_files = get_allowed_files(user_role)
    
    if not allowed_files:
        print("  ⚠️  [Bị chặn] User không có quyền xem bất kỳ file nào!")
        return {
            "answer": "Bạn chưa được cấp quyền truy cập vào tài liệu nội bộ để trả lời câu hỏi này.",
            "sources": []
        }
        
    # Bước 2: Tạo bộ lọc Metadata Filter cho ChromaDB
    search_filter = {"source": {"$in": allowed_files}}
    print(f"  ⚙️  [Bộ lọc Chroma] Đang quét trên {len(allowed_files)} tài liệu...")
    
    try:
        # Bước 3: Tìm kiếm (Gọi DB trực tiếp từ ổ cứng)
        db = get_vector_db()
        if db is None:
             return {"answer": "Lỗi kết nối Vector DB cục bộ.", "sources": []}
             
        docs = db.similarity_search(query, k=2, filter=search_filter)
        print(f"  📄  [Kết quả] Lấy ra được {len(docs)} đoạn văn bản khớp nhất.")
        
        if not docs:
            print("  ⚠️  [Trống] Không tìm thấy nội dung nào liên quan câu hỏi.")
            return {
                "answer": "Tài liệu nội bộ không có thông tin về vấn đề này.",
                "sources": []
            }
            
        # Bước 4: Tổng hợp kết quả (Dán thêm tên file vào trước đoạn văn để AI dễ hiểu)
        context = "\n\n".join([f"--- Trích từ file {d.metadata.get('source', 'Nguồn ẩn')} ---\n{d.page_content}" for d in docs])
        sources = list(set([d.metadata.get("source", "Nguồn ẩn") for d in docs]))
        print(f"  ✅  [Thành công] Tốc độ trích xuất tối ưu. Nguồn: {sources}")
        
        return {
            "answer": context,
            "sources": sources
        }
    except Exception as e:
        print(f"  ❌  [Lỗi ChromaDB] Lỗi trong quá trình tìm kiếm: {e}")
        return {
            "answer": "Lỗi hệ thống khi truy xuất dữ liệu Vector.",
            "sources": []
        }

def check_exact_faq_match(query, user_role='staff'):
    """🔥 Quét FAQ từ DATABASE (Supabase) và trả về Câu trả lời trực tiếp nếu khớp"""
    from difflib import SequenceMatcher
    
    print(f"\n  ⚡  [FAQ Lookup] Đang kiểm tra câu hỏi trong kho: '{query}'")
    
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Lấy tất cả FAQ từ database
        c.execute("SELECT id, question, answer FROM faqs ORDER BY updated_at DESC")
        faqs = c.fetchall()
        c.close()
        conn.close()
        
        if not faqs:
            print("  📭 [Kho FAQ] Chưa có câu hỏi nào được admin trả lời")
            return None
        
        # So sánh độ tương đồng với từng FAQ
        best_match = None
        best_score = 0
        
        query_lower = query.lower().strip()
        
        for faq_id, faq_question, faq_answer in faqs:
            faq_q_lower = faq_question.lower().strip()
            
            # So sánh độ giống nhau (0.0 - 1.0)
            similarity = SequenceMatcher(None, query_lower, faq_q_lower).ratio()
            
            if similarity > best_score:
                best_score = similarity
                best_match = (faq_id, faq_question, faq_answer, similarity)
        
        # Nếu độ giống nhau >= 70%, trả về câu trả lời admin
        if best_match and best_score >= 0.70:
            faq_id, faq_q, faq_ans, score = best_match
            print(f"  ✅ [FAQ HIT] Khớp với FAQ #{faq_id} - Độ tương đồng: {score:.1%}")
            print(f"     📝 Câu gốc: {faq_q}")
            print(f"     👉 Trả lời từ Kho: {faq_ans[:100]}...")
            return faq_ans
        else:
            if best_match:
                print(f"  ⚠️  [Gần như] Câu hỏi gần giống (~{best_score:.1%}) nhưng chưa đủ tin cậy, gọi AI")
            else:
                print(f"  📭 [Không tìm] Không có FAQ tương tự, sẽ hỏi AI")
            
    except Exception as e:
        print(f"  ❌  [Lỗi FAQ Lookup]: {e}")
        
    return None