import psycopg
from dotenv import load_dotenv
import os

load_dotenv()

# 从 DATABASE_URL 中提取信息
db_url = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:password@localhost:5432/it_assets")
# 解析连接字符串
parts = db_url.replace("postgresql+psycopg://", "").split("@")
user_pass = parts[0].split(":")
user = user_pass[0]
password = user_pass[1] if len(user_pass) > 1 else ""
host_db = parts[1].split("/")
host_port = host_db[0].split(":")
host = host_port[0]
port = host_port[1] if len(host_port) > 1 else "5432"
dbname = host_db[1]

print(f"尝试连接到 PostgreSQL 服务器...")
print(f"主机: {host}, 端口: {port}, 用户: {user}")

try:
    # 连接到默认的 postgres 数据库
    conn = psycopg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname="postgres",
        autocommit=True
    )
    
    cursor = conn.cursor()
    
    # 检查数据库是否存在
    cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{dbname}'")
    exists = cursor.fetchone()
    
    if exists:
        print(f"✅ 数据库 '{dbname}' 已存在")
    else:
        # 创建数据库
        cursor.execute(f"CREATE DATABASE {dbname}")
        print(f"✅ 成功创建数据库 '{dbname}'")
    
    cursor.close()
    conn.close()
    
except psycopg.OperationalError as e:
    print(f"❌ 连接失败: {e}")
    print("\n请检查:")
    print("1. PostgreSQL 服务是否正在运行")
    print("2. .env 文件中的用户名和密码是否正确")
    print("3. PostgreSQL 是否监听在 localhost:5432")
except Exception as e:
    print(f"❌ 错误: {e}")
