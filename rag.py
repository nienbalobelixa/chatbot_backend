import sqlite3
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# 1. Khởi tạo Embedding và Kết nối Database Vector
print("🧠 Đang khởi tạo mô hình Embedding...")
embedding = HuggingFaceEmbeddings(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

# Kết nối tới thư mục chứa dữ liệu đã nạp
db = Chroma(persist_directory="vector_db", embedding_function=embedding)
print("✅ Kết nối Vector DB thành công!")

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
        
        # IN RA TERMINAL ĐỂ KIỂM TRA
        print(f"🕵️ [Phân quyền] Role '{user_role}' được phép đọc: {files}")
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
    print(f"⚙️ [Bộ lọc Chroma] Áp dụng filter: {search_filter}")
    
    try:
        # Bước 3: Tìm kiếm
        docs = db.similarity_search(query, k=3, filter=search_filter)
        print(f"📄 [Kết quả] Lấy ra được {len(docs)} đoạn văn bản khớp nhất.")

        if not docs:
            print("⚠️ [Trống] Có quyền xem file, nhưng không tìm thấy nội dung nào liên quan câu hỏi.")
            return {
                "answer": "Tài liệu nội bộ không có thông tin về vấn đề này.",
                "sources": []
            }

        # Bước 4: Tổng hợp kết quả (Dán thêm tên file vào trước đoạn văn để AI dễ hiểu)
        context = "\n\n".join([f"--- Trích từ file {d.metadata.get('source', 'Nguồn ẩn')} ---\n{d.page_content}" for d in docs])
        sources = list(set([d.metadata.get("source", "Nguồn ẩn") for d in docs]))

        print(f"✅ [Thành công] Đã trích xuất ngữ cảnh từ: {sources}")
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