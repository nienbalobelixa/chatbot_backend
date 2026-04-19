import sqlite3

def setup_permissions():
    print("⏳ Đang kết nối Database...")
    conn = sqlite3.connect('enterprise.db')
    c = conn.cursor()

    # =======================================================
    # =======================================================
    # 1. TẠO TÀI KHOẢN ADMIN MẶC ĐỊNH (CHUẨN BẢO MẬT SHA-256)
    # =======================================================
    print("⏳ Đang thiết lập tài khoản Admin...")
    # Bổ sung thêm cột is_onboarded để khớp với app.py
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            is_onboarded INTEGER DEFAULT 0
        )
    ''')
    
    c.execute("DELETE FROM users WHERE username = 'admin'")
    
    # Chuỗi loằng ngoằng dưới đây chính là chữ "123456" đã được băm bằng SHA-256
    c.execute("INSERT INTO users (username, password, role, is_onboarded) VALUES ('admin', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', 'admin', 1)")
    print("✅ Đã tạo tài khoản Giám đốc: [User: admin] - [Pass: 123456]")

    # =======================================================
    # 2. CẤU HÌNH BẢNG CÂU HỎI & QUYỀN TÀI LIỆU (Giữ nguyên của sếp)
    # =======================================================
    c.execute("CREATE TABLE IF NOT EXISTS unanswered_questions (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, username TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS document_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT UNIQUE,
            required_role TEXT
        )
    ''')

    c.execute("DELETE FROM document_permissions")

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

    try:
        c.executemany("INSERT INTO document_permissions (file_name, required_role) VALUES (?, ?)", danh_sach_file)
        conn.commit()
        print(f"✅ Đã cấp quyền thành công cho {len(danh_sach_file)} file!")
        print("🚀 HOÀN TẤT SETUP KHỞI ĐỘNG!")
    except Exception as e:
        print(f"❌ Có lỗi xảy ra: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    setup_permissions()
    # Day la ban cap nhat tai khoan Admin