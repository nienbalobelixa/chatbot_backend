import sqlite3

def setup_permissions():
    print("⏳ Đang kết nối Database...")
    conn = sqlite3.connect('enterprise.db')
    c = conn.cursor()
    conn.execute("CREATE TABLE IF NOT EXISTS unanswered_questions (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, username TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
    # 1. Đảm bảo bảng tồn tại đúng cấu trúc
    c.execute('''
        CREATE TABLE IF NOT EXISTS document_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT UNIQUE,
            required_role TEXT
        )
    ''')

    # 2. Xóa dữ liệu cũ (nếu có) để làm mới hoàn toàn
    c.execute("DELETE FROM document_permissions")

    # 3. Danh sách file và quyền (Chuẩn theo hình của con)
    danh_sach_file = [
        # File bảo mật (Chỉ Admin)
        ("Bảng điểm toàn khóa.pdf", "admin"), 
        ("Chính sách Bảo mật CNTT.pdf", "staff"),           
        
        # File phổ thông (Staff và Admin đều xem được)
        ("Quy chế Nhân sự  Phúc lợi.pdf", "staff"), 
        ("chinhsachnhansu.pdf", "staff"),        
        ("Tóm tắt điều hành của công ty.pdf", "staff"),              
        ("pdf_hr_company.pdf", "staff")          
    ]

    # 4. Bơm dữ liệu vào SQLite
    try:
        c.executemany("INSERT INTO document_permissions (file_name, required_role) VALUES (?, ?)", danh_sach_file)
        conn.commit()
        print(f"✅ Đã cấp quyền thành công cho {len(danh_sach_file)} file!")
    except Exception as e:
        print(f"❌ Có lỗi xảy ra: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    setup_permissions()