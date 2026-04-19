import sqlite3
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# ---------------------------------------------------------
# TỐI ƯU HIỆU SUẤT: Singleton Pattern & Lazy Loading
# ---------------------------------------------------------
_db_instance = None
_embedding_instance = None

def get_vector_db():
    """Chỉ khởi tạo mô hình nặng 1 lần duy nhất, các lần sau dùng lại luôn"""
    global _db_instance, _embedding_instance
    
    if _db_instance is None:
        print("🧠 Đang tải mô hình Embedding vào RAM (Chỉ chạy 1 lần duy nhất)...")
        _embedding_instance = HuggingFaceEmbeddings(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        print("✅ Kết nối Vector DB thành công!")
        _db_instance = Chroma(persist_directory="vector_db", embedding_function=_embedding_instance)
        
    return _db_instance

# ---------------------------------------------------------

def get_allowed_files(user_role):
    """Lấy danh sách các file mà Role này được phép xem từ SQLite"""
    try:
        conn = sqlite3.connect('enterprise.db')
        c = conn.cursor()
        
        if user_role == 'admin':
            c.execute("SELECT file_name FROM document_permissions")
        else:
            c.execute("SELECT file_name FROM document_permissions WHERE required_role = 'staff'")
        
        # Làm sạch tên file (xóa khoảng trắng thừa) để đảm bảo khớp 100% với ChromaDB
        files = [row[0].strip() for row in c.fetchall() if row[0]]
        conn.close()
        
        return files
    except Exception as e:
        print(f"❌ [Lỗi SQLite] Không thể lấy danh sách file: {e}")
        return []

def search_docs(query, user_role='staff'):
    """Tìm kiếm tài liệu có lọc theo quyền truy cập (RBAC)"""
    print(f"\n🔍 [Câu hỏi mới] '{query}' | Từ Role: '{user_role}'")
    
    # Bước 1: Xác định vùng dữ liệu được phép
    allowed_files = get_allowed_files(user_role)
    
    if not allowed_files:
        print("⚠️ [Bị chặn] User không có quyền xem bất kỳ file nào!")
        return {
            "answer": "Bạn chưa được cấp quyền truy cập vào tài liệu nội bộ để trả lời câu hỏi này.",
            "sources": []
        }

    # Bước 2: Tạo bộ lọc Metadata Filter cho ChromaDB
    search_filter = {"source": {"$in": allowed_files}}
    print(f"⚙️ [Bộ lọc Chroma] Đang quét trên {len(allowed_files)} tài liệu...")
    
    try:
        # Bước 3: Tìm kiếm (Sử dụng hàm get_vector_db để gọi DB từ RAM)
        db = get_vector_db()
        docs = db.similarity_search(query, k=2, filter=search_filter)
        print(f"📄 [Kết quả] Lấy ra được {len(docs)} đoạn văn bản khớp nhất.")

        if not docs:
            print("⚠️ [Trống] Không tìm thấy nội dung nào liên quan câu hỏi.")
            return {
                "answer": "Tài liệu nội bộ không có thông tin về vấn đề này.",
                "sources": []
            }

        # Bước 4: Tổng hợp kết quả (Dán thêm tên file vào trước đoạn văn để AI dễ hiểu)
        context = "\n\n".join([f"--- Trích từ file {d.metadata.get('source', 'Nguồn ẩn')} ---\n{d.page_content}" for d in docs])
        sources = list(set([d.metadata.get("source", "Nguồn ẩn") for d in docs]))

        print(f"✅ [Thành công] Tốc độ trích xuất tối ưu. Nguồn: {sources}")
        return {
            "answer": context,
            "sources": sources
        }
        
    except Exception as e:
        print(f"❌ [Lỗi ChromaDB] Lỗi trong quá trình tìm kiếm: {e}")
        return {
            "answer": "Lỗi hệ thống khi truy xuất dữ liệu Vector.",
            "sources": []
        }

def check_exact_faq_match(query, user_role='staff'):
    """Quét FAQ và trả về cả Câu trả lời + Tên file thật để mở được trích dẫn"""
    print(f"\n⚡ [Semantic Cache] Đang kiểm tra câu hỏi: '{query}'")
    
    allowed_files = get_allowed_files(user_role)
    # Lọc ra chỉ tìm trong các file FAQ (Do Admin trả lời)
    faq_files = [f for f in allowed_files if f.startswith("FAQ_")]
    
    if not faq_files:
        return None

    search_filter = {"source": {"$in": faq_files}}
    
    try:
        db = get_vector_db()
        results = db.similarity_search_with_score(query, k=1, filter=search_filter)
        
        if results:
            doc, score = results[0]
            print(f"🎯 [Semantic Cache] Điểm tương đồng: {score:.3f} (Nguồn: {doc.metadata.get('source')})")
            
            # Điểm < 0.25 là cực kỳ giống nhau
            if score < 0.25:
                content = doc.page_content
                if "Câu trả lời:" in content:
                    answer = content.split("Câu trả lời:")[1].strip()
                    print("✅ BẮT ĐƯỢC FAQ! ĐÃ CHẶN ĐỨNG LUỒNG GỌI GEMINI!")
                    # TRẢ VỀ CẢ CÂU TRẢ LỜI VÀ TÊN FILE
                    return answer, doc.metadata.get("source")
    except Exception as e:
        print(f"❌ [Lỗi Semantic Cache]: {e}")
        
    return None