"""
迁移脚本：为 warehouse_locations 和 office_locations 表添加 description 列

运行方式：
    cd backend && python migrate_location_description.py
"""

from database import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        # 检查并添加 warehouse_locations.description
        try:
            conn.execute(text("ALTER TABLE warehouse_locations ADD COLUMN description VARCHAR"))
            print("✅ warehouse_locations.description 列已添加")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("⏭  warehouse_locations.description 列已存在，跳过")
            else:
                print(f"❌ warehouse_locations 迁移失败: {e}")

        # 检查并添加 office_locations.description
        try:
            conn.execute(text("ALTER TABLE office_locations ADD COLUMN description VARCHAR(255)"))
            print("✅ office_locations.description 列已添加")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("⏭  office_locations.description 列已存在，跳过")
            else:
                print(f"❌ office_locations 迁移失败: {e}")

        conn.commit()
    print("迁移完成")

if __name__ == "__main__":
    migrate()
