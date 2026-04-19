import os
import shutil
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

# --- XÓA HUGGINGFACE, DÙNG GOOGLE ---
from langchain_google_genai import GoogleGenerativeAIEmbeddings

DOCS = "documents"
DB = "vector_db"

def main():
    # 1. Kiểm tra thư mục đầu vào
    if not os.path.exists(DOCS):
        print(f" ❌  Thư mục {DOCS} không tồn tại!")
        return

    print(" 📂  Đang quét các file trong:", DOCS)
    all_files = os.listdir(DOCS)
    print(" 📋  Danh sách file:", all_files)
    raw_documents = []
    
    for file in all_files:
        path = os.path.join(DOCS, file)
        loaded_docs = []
        try:
            # HỖ TRỢ ĐỌC CẢ PDF VÀ TXT (FAQ)
            if file.endswith(".pdf"):
                loader = PyPDFLoader(path)
                loaded_docs = loader.load()
            elif file.endswith(".txt"):
                loader = TextLoader(path, encoding="utf-8")
                loaded_docs = loader.load()
            else:
                continue # Bỏ qua các file không phải pdf hoặc txt

            # --- QUAN TRỌNG: Làm sạch Metadata để Phân quyền ---
            for doc in loaded_docs:
                # Chỉ lấy tên file (ví dụ: 'noiquy.pdf', 'FAQ_1.txt') thay vì cả đường dẫn
                doc.metadata["source"] = file

            raw_documents.extend(loaded_docs)
            print(f" ✅  Đã nạp: {file}")
        except Exception as e:
            print(f" ❌  Lỗi khi đọc file {file}: {e}")
            
    if not raw_documents:
        print(" ❌  Không tìm thấy nội dung hợp lệ nào để nạp!")
        return
        
    # 2. Chia nhỏ tài liệu (Chunking)
    print(" ✂️  Đang chia nhỏ tài liệu...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=600, # Chuẩn vàng để tiết kiệm Token
        chunk_overlap=100
    )
    docs = splitter.split_documents(raw_documents)
    print(f" 📦  Tổng số đoạn (chunks) tạo ra: {len(docs)}")
    
    # 3. Xóa Vector DB cũ để làm mới hoàn toàn
    if os.path.exists(DB):
        print(" 🗑 ️ Đang xóa Vector DB cũ để cập nhật dữ liệu mới...")
        shutil.rmtree(DB)
        
    # 4. Khởi tạo Embedding (DÙNG GOOGLE API)
    print("🧠 Đang khởi tạo mô hình Embedding Google (Siêu nhẹ)...")
    api_key = os.environ.get("GEMINI_API_KEY_1") or os.environ.get("GEMINI_API_KEY")
    embedding = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004", 
        google_api_key=api_key
    )
    
    # 5. Lưu vào ChromaDB
    print(" 💾  Đang lưu dữ liệu vào ChromaDB...")
    db = Chroma.from_documents(
        documents=docs,
        embedding=embedding,
        persist_directory=DB
    )

    print(" ✨  CHÚC MỪNG SẾP! Hệ thống đã nạp xong tri thức mới.")
    print(f" 🚀  Vector DB hiện đã sẵn sàng tại thư mục: {DB}")

if __name__ == "__main__":
    main()