"""为仓储库存表补齐低库存阈值字段。

运行方式：python migrate_warehouse_low_stock_threshold.py
该迁移幂等，仅在字段不存在时添加，不删除或改写现有库存数量。
"""
from sqlalchemy import inspect, text

from database import engine


def migrate():
    inspector = inspect(engine)
    if "warehouse_assets" not in inspector.get_table_names():
        raise RuntimeError("warehouse_assets 表不存在，请先初始化数据库表")

    columns = {
        column["name"] for column in inspector.get_columns("warehouse_assets")
    }
    if "low_stock_threshold" in columns:
        print("low_stock_threshold 字段已存在，无需迁移")
        return

    with engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE warehouse_assets "
            "ADD COLUMN low_stock_threshold INTEGER NOT NULL DEFAULT 0"
        ))
    print("已添加 warehouse_assets.low_stock_threshold 字段，默认值为 0")


if __name__ == "__main__":
    migrate()
