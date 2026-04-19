import sqlite3

def setup_permissions():
    print("⏳ Đang kết nối Database...")
    conn = sqlite3.connect('enterprise.db')
    c = conn.cursor()

    # =======================================================
    # 1. TẠO TÀI KHOẢN ADMIN MẶC ĐỊNH (CHỐNG MẤT QUYỀN)
    # =======================================================
    print("⏳ Đang thiết lập tài khoản Admin...")
    # Đảm bảo bảng users tồn tại
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    ''')
    
    # Xóa tài khoản admin cũ (nếu có bị kẹt) để tạo mới hoàn toàn
    c.execute("DELETE FROM users WHERE username = 'admin'")
    
    # Bơm tài khoản Giám đốc vào Database
    # LƯU Ý: Đang để mật khẩu thuần là '123456'
    c.execute("INSERT INTO users (username, password, role) VALUES ('admin', '123456', 'admin')")
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