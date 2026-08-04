"""补齐固定资产受控入库字段。

运行方式：python migrate_asset_fixed_identifiers.py
仅添加缺失的可空字段，不修改既有资产记录。
"""
from sqlalchemy import inspect, text

from database import engine

COLUMNS = {
    "asset_category_code": "VARCHAR(2)",
    "inbound_source": "VARCHAR(16)",
    "terminal_inventory_id": "INTEGER",
}


def migrate():
    inspector = inspect(engine)
    if "assets" not in inspector.get_table_names():
        raise RuntimeError("assets 表不存在，请先初始化数据库表")

    existing = {column["name"] for column in inspector.get_columns("assets")}
    added = []
    with engine.begin() as connection:
        for name, definition in COLUMNS.items():
            if name not in existing:
                connection.execute(text(
                    f"ALTER TABLE assets ADD COLUMN {name} {definition}"
                ))
                added.append(name)

    if added:
        print(f"已添加 assets 字段：{', '.join(added)}")
    else:
        print("固定资产受控字段已存在，无需迁移")


if __name__ == "__main__":
    migrate()
