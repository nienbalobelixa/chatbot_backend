import os
import shutil
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# ==============================
# 📂 PATH CHUẨN (ANTI LỖI WINDOWS)
# ==============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_PATH = os.path.join(BASE_DIR, "documents")
DB_PATH = os.path.join(BASE_DIR, "vector_db")

# ==============================
# 🧠 EMBEDDING
# ==============================
embedding = HuggingFaceEmbeddings(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    model_kwargs={"device": "cpu"}
)

# ==============================
# 📥 LOAD PDF & CLEAN METADATA
# ==============================
def load_documents():
    if not os.path.exists(DOCS_PATH):
        print(f"❌ Không tìm thấy thư mục: {DOCS_PATH}")
        return []

    print(f"📂 Đang quét file tại: {DOCS_PATH}")
    
    loader = DirectoryLoader(
        DOCS_PATH,
        glob="*.pdf",
        loader_cls=PyPDFLoader
    )

    documents = loader.load()

    # --- BƯỚC QUAN TRỌNG: FIX METADATA CHO PHÂN QUYỀN ---
    for doc in documents:
        # Lấy đường dẫn gốc (thường là đường dẫn dài loằng ngoằng)
        original_path = doc.metadata.get("source", "")
        # Chỉ lấy tên file cuối cùng (ví dụ: noiquy.pdf)
        clean_filename = os.path.basename(original_path)
        # Ghi đè lại vào metadata
        doc.metadata["source"] = clean_filename

    print(f"📄 Load được {len(documents)} trang từ PDF")
    return documents


# ==============================
# ✂️ SPLIT TEXT
# ==============================
def split_text(documents):
    # Tăng chunk_size lên 600 để nội dung đầy đủ hơn cho Gemini
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=100
    )

    chunks = splitter.split_documents(documents)
    print(f"✂️ Đã tạo {len(chunks)} đoạn văn bản nhỏ (chunks)")
    return chunks


# ==============================
# 💾 SAVE DB (XÓA CŨ - TẠO MỚI)
# ==============================
def save_db(chunks):
    # Xóa DB cũ trước khi lưu mới để tránh trùng lặp hoặc rác dữ liệu
    if os.path.exists(DB_PATH):
        print("🗑 Xoá DB cũ để cập nhật phân quyền...")
        shutil.rmtree(DB_PATH)

    db = Chroma.from_documents(
        documents=chunks,
        embedding=embedding,
        persist_directory=DB_PATH
    )
    
    # Ở phiên bản langchain_chroma mới, dữ liệu tự động lưu.
    print(f"💾 Đã lưu Vector DB thành công tại: {DB_PATH}")


# ==============================
# 🚀 MAIN
# ==============================
def main():
    print("\n🚀 BẮT ĐẦU QUÁ TRÌNH NẠP DỮ LIỆU (INGEST)...\n")

    # 1. Load file
    docs = load_documents()
    if not docs:
        print("❌ Không tìm thấy dữ liệu PDF nào!")
        return

    # 2. Cắt nhỏ
    chunks = split_text(docs)

    # 3. Lưu vào Chroma
    save_db(chunks)

    print("\n✅ HOÀN TẤT! Bây giờ hãy cập nhật bảng document_permissions trong SQLite nhé Niên.")


if __name__ == "__main__":
    main()