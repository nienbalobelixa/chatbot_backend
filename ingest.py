import os
import shutil
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

DOCS = "documents"
DB = "vector_db"

def main():
    # 1. Kiểm tra thư mục đầu vào
    if not os.path.exists(DOCS):
        print(f"❌ Thư mục {DOCS} không tồn tại!")
        return
        
    print("📂 Đang quét các file trong:", DOCS)
    all_files = os.listdir(DOCS)
    print("📋 Danh sách file:", all_files)

    raw_documents = []
    for file in all_files:
        if file.endswith(".pdf"):
            try:
                path = os.path.join(DOCS, file)
                loader = PyPDFLoader(path)
                # Load tài liệu
                loaded_docs = loader.load()
                
                # --- QUAN TRỌNG: Làm sạch Metadata để Phân quyền ---
                for doc in loaded_docs:
                    # Chỉ lấy tên file (ví dụ: 'noiquy.pdf') thay vì cả đường dẫn
                    doc.metadata["source"] = file 
                
                raw_documents.extend(loaded_docs)
                print(f"✅ Đã nạp: {file}")
            except Exception as e:
                print(f"❌ Lỗi khi đọc file {file}: {e}")

    if not raw_documents:
        print("❌ Không tìm thấy nội dung PDF nào để nạp!")
        return

    # 2. Chia nhỏ tài liệu (Chunking)
    print("✂️ Đang chia nhỏ tài liệu...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=600, # Tăng lên một chút để Gemini có nhiều ngữ cảnh hơn
        chunk_overlap=100
    )
    docs = splitter.split_documents(raw_documents)
    print(f"📦 Tổng số đoạn (chunks) tạo ra: {len(docs)}")

    # 3. Xóa Vector DB cũ để làm mới hoàn toàn
    if os.path.exists(DB):
        print("🗑️ Đang xóa Vector DB cũ để cập nhật phân quyền...")
        shutil.rmtree(DB)

    # 4. Khởi tạo Embedding
    print("🧠 Đang khởi tạo mô hình Embedding (Vui lòng đợi)...")
    embedding = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )

    # 5. Lưu vào ChromaDB
    print("💾 Đang lưu dữ liệu vào ChromaDB...")
    db = Chroma.from_documents(
        documents=docs,
        embedding=embedding,
        persist_directory=DB
    )
    
    # Lưu ý: Trong các phiên bản LangChain mới, persist() tự động chạy khi khởi tạo
    # Nhưng gọi lại cũng không sao để đảm bảo an toàn.
    print("✨ CHÚC MỪNG NIÊN! Hệ thống đã nạp xong tri thức mới.")
    print(f"🚀 Vector DB hiện đã sẵn sàng tại thư mục: {DB}")

if __name__ == "__main__":
    main()