"""
初始化管理员账号脚本
运行: python init_admin.py
"""
from database import SessionLocal, engine
import models
from auth import get_password_hash
from datetime import datetime, timezone, timedelta

def china_now():
    """返回中国时区的当前时间，但以naive datetime存储（数据库会按本地时区处理）"""
    # 获取当前UTC时间，然后转换为中国时区，最后移除时区信息
    utc_now = datetime.now(timezone.utc)
    china_time = utc_now.astimezone(timezone(timedelta(hours=8)))
    return china_time.replace(tzinfo=None)  # 移除时区信息，让数据库按本地时区处理

def init_admin():
    # 确保表已创建
    models.Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # 检查是否已存在管理员
        existing_admin = db.query(models.User).filter(models.User.username == "admin").first()
        if existing_admin:
            print("管理员账号已存在")
            return
        
        # 创建默认管理员账号
        admin = models.User(
            username="admin",
            email="admin@zingsemi.com",
            full_name="系统管理员",
            hashed_password=get_password_hash("admin123"),  # 默认密码，请立即修改
            role="admin",
            is_active=True,
            must_change_password=False,  # 默认管理员不强制修改密码
            password_changed_at=china_now()
        )
        db.add(admin)
        db.commit()
        
        print("=" * 50)
        print("管理员账号创建成功!")
        print("=" * 50)
        print(f"用户名: admin")
        print(f"密码: admin123")
        print("=" * 50)
        print("⚠️  请立即登录并修改默认密码!")
        print("=" * 50)
        
    finally:
        db.close()

if __name__ == "__main__":
    init_admin()
