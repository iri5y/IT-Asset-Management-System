"""
迁移脚本：为 assets 表添加 condition 列（资产状况：可用 / 损坏 / 待报废）

运行方式：
    cd backend && python migrate_asset_condition.py
"""

from database import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE assets ADD COLUMN condition VARCHAR"))
            # 存量数据默认设为"可用"
            conn.execute(text("UPDATE assets SET condition = '可用' WHERE condition IS NULL"))
            conn.commit()
            print("✅ assets.condition 列已添加，存量数据已设为「可用」")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("⏭  assets.condition 列已存在，跳过")
            else:
                print(f"❌ 迁移失败: {e}")
    print("迁移完成")


if __name__ == "__main__":
    migrate()
