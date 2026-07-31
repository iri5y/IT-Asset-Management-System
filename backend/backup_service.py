import os
import subprocess
from datetime import datetime
import argparse 

#基础配置
DB_HOST = os.getenv("DB_HOST","localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "it_assets")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "51855700")

#备份文件存放目录
BACKUP_DIR = os.path.join(os.path.dirname(__file__),"backups")

def execute_backup(backup_dir=None):
    """执行 PostgresSQL 数据库备份"""
    target_dir = backup_dir if backup_dir else BACKUP_DIR
    target_dir = os.path.abspath(target_dir)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    #生成带时间戳的文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"asset_db_backup_{timestamp}.sql"
    backup_path = os.path.join(target_dir, filename)

    #复制当前环境变量，并注入PostgreSQL密码
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD

    #组装 pg_dump 命令(-F p代表导出为纯文本SQL格式)
    cmd = [
        "pg_dump",
        "-h", DB_HOST,
        "-p", DB_PORT,
        "-U", DB_USER,
        "-d", DB_NAME,
        "-F", "p",
        "-f", backup_path
    ]

    try:
        #执行命令
        result = subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
        print(f"【成功】数据库备份已完成！文件保存在：{backup_path}")
        return backup_path
    except subprocess.CalledProcessError as e:
        print(f"【失败】数据库备份期间发生错误：{e.stderr}")
        return None
    
if __name__=="__main__":
    parser = argparse.ArgumentParser(description="IT资产管理系统-数据库自动备份服务")
    parser.add_argument('--output', type=str, default=None, help='自定义备份文件存放目录')
    args = parser.parse_args()

    execute_backup(backup_dir=args.output)