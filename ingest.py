import os
import shutil
from supabase import create_client, Client
# 💡 ĐÃ THÊM: Docx2txtLoader để đọc file Word
from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings

DOCS = "documents"
DB = "vector_db"

# Khai báo Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def sync_files_from_supabase():
    """Hàm phép thuật: Tải toàn bộ file từ Supabase Storage về máy chủ Render"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️ Thiếu biến môi trường Supabase.")
        return
        
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    if not os.path.exists(DOCS):
        os.makedirs(DOCS)
        
    print("☁️ Đang đồng bộ tài liệu từ Supabase Storage xuống máy chủ...")
    try:
        # Lấy danh sách file trên bucket 'documents'
        files = supabase.storage.from_("documents").list()
        downloaded_count = 0
        for f in files:
            file_name = f['name']
            if file_name == '.emptyFolderPlaceholder' or not file_name: continue
            
            file_path = os.path.join(DOCS, file_name)
            
            # Tải file về
            res = supabase.storage.from_("documents").download(file_name)
            with open(file_path, 'wb') as f_out:
                f_out.write(res)
            downloaded_count += 1
            
        print(f"✅ Đã kéo {downloaded_count} file từ Supabase về thành công!")
    except Exception as e:
        print(f"❌ Lỗi đồng bộ Supabase: {e}")

def main():
    # 1. ĐỒNG BỘ FILE TỪ CLOUD VỀ TRƯỚC TIÊN
    sync_files_from_supabase()

    # 2. Xử lý như bình thường
    if not os.path.exists(DOCS) or not os.listdir(DOCS):
        print(" ❌ Không có file nào trong thư mục!")
        return
        
    print(" 📂 Đang quét các file trong:", DOCS)
    all_files = os.listdir(DOCS)
    raw_documents = []
    
    for file in all_files:
        path = os.path.join(DOCS, file)
        loaded_docs = []
        try:
            if file.endswith(".pdf"):
                loaded_docs = PyPDFLoader(path).load()
            elif file.endswith(".txt"):
                loaded_docs = TextLoader(path, encoding="utf-8").load()
            # 🌟 ĐÃ THÊM: Xử lý file Word
            elif file.endswith(".docx") or file.endswith(".doc"):
                loaded_docs = Docx2txtLoader(path).load()
            else:
                continue
                
            for doc in loaded_docs:
                doc.metadata["source"] = file
                
            raw_documents.extend(loaded_docs)
        except Exception as e:
            print(f"Lỗi khi đọc file {file}: {e}")
            
    if not raw_documents: return
        
    print(" ✂️ Đang chia nhỏ tài liệu...")
    splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)
    docs = splitter.split_documents(raw_documents)
    
    # 3. LÀM MỚI VECTOR DB CHUẨN ENTERPRISE (CHỐNG XUNG ĐỘT)
    print("🧠 Đang khởi tạo mô hình Embedding...")
    api_key = os.environ.get("GEMINI_API_KEY_1") or os.environ.get("GEMINI_API_KEY")
    embedding = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=api_key)

    # KHÔNG dùng shutil.rmtree nữa. Chúng ta kết nối vào DB và xóa sạch dữ liệu bên trong.
    print(" 🗑️ Đang dọn dẹp bộ nhớ cũ một cách an toàn...")
    if os.path.exists(DB):
        try:
            db_old = Chroma(persist_directory=DB, embedding_function=embedding)
            db_old.delete_collection() # Lệnh này chỉ xóa dữ liệu, giữ nguyên file vật lý nên không bao giờ bị lỗi khóa ổ cứng
            print(" ✅ Đã dọn dẹp xong dữ liệu cũ!")
        except Exception as e:
            print(f" ⚠️ Collection trống hoặc chưa tạo: {e}")

    # 4. Lưu dữ liệu mới
    print(" 💾 Đang nạp kiến thức mới vào ChromaDB...")
    Chroma.from_documents(
        documents=docs,
        embedding=embedding,
        persist_directory=DB
    )
    
    print(" ✨ CHÚC MỪNG SẾP! Hệ thống đã nạp xong tri thức mới.")

if __name__ == "__main__":
    main()