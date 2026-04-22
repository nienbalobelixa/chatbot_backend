import os
import time
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma
from dotenv import load_dotenv

load_dotenv()

DOCS_DIR = "documents"
DB_DIR = "vector_db"

def optimize_ingest():
    print("🚀 Bắt đầu quét và nạp tài liệu tối ưu...")
    
    # 1. Khởi tạo model nhúng của Google
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001") 
    
    # 2. Kết nối vào ChromaDB
    vectordb = Chroma(persist_directory=DB_DIR, embedding_function=embeddings)
    
    # Lấy danh sách các file ĐÃ CÓ trong DB để không nạp lại
    existing_docs = []
    try:
        db_data = vectordb.get()
        if db_data and 'metadatas' in db_data:
            for meta in db_data['metadatas']:
                if meta and 'source' in meta:
                    existing_docs.append(meta['source'])
            existing_docs = list(set(existing_docs)) # Lọc trùng lặp
    except Exception as e:
        print("Chưa có DB cũ, sẽ tạo mới hoàn toàn.")

    # 3. Quét thư mục documents tìm file mới
    new_files_to_process = []
    if os.path.exists(DOCS_DIR):
        for filename in os.listdir(DOCS_DIR):
            if filename.endswith(".pdf"):
                filepath = os.path.join(DOCS_DIR, filename)
                # Chỉ nạp nếu file này chưa từng có trong ChromaDB
                if filepath not in existing_docs:
                    new_files_to_process.append(filepath)
    
    if not new_files_to_process:
        print("✅ Không có tài liệu mới nào. Tiết kiệm Token API!")
        return

    print(f"📦 Phát hiện {len(new_files_to_process)} tài liệu mới. Bắt đầu xử lý...")
    
    # 4. Xử lý file mới (Cắt nhỏ văn bản)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    
    for filepath in new_files_to_process:
        print(f"⏳ Đang nạp: {filepath}")
        try:
            loader = PyPDFLoader(filepath)
            docs = loader.load()
            splits = text_splitter.split_documents(docs)
            
            # Nạp vào DB
            vectordb.add_documents(splits)
            print(f"✔️ Đã nạp xong: {filepath}")
            
            # BÍ QUYẾT: Nghỉ 3 giây giữa mỗi file để không bị Google báo lỗi 429
            time.sleep(3)
        except Exception as e:
            print(f"❌ Lỗi khi nạp {filepath}: {e}")

    print("🎉 Hoàn tất cập nhật Vector Database!")

if __name__ == "__main__":
    optimize_ingest()