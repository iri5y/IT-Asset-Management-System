"""
迁移脚本：创建 asset_part_logs 表（资产配件更换/新增记录）

运行方式：
    cd backend && python migrate_asset_part_logs.py
"""

from database import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS asset_part_logs (
                    id SERIAL PRIMARY KEY,
                    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
                    warehouse_item_id INTEGER REFERENCES warehouse_assets(id) ON DELETE SET NULL,
                    warehouse_item_name VARCHAR NOT NULL,
                    action VARCHAR NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    notes TEXT,
                    operator VARCHAR,
                    created_at TIMESTAMP
                )
            """))
            conn.commit()
            print("✅ asset_part_logs 表已创建")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⏭  asset_part_logs 表已存在，跳过")
            else:
                print(f"❌ 迁移失败: {e}")
    print("迁移完成")


if __name__ == "__main__":
    migrate()
