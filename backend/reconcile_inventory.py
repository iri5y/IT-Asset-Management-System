"""只读检查固定资产与消耗品分类边界及库房数量守恒。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from category_policy import ASSET_CATEGORY_NAMES, CONSUMABLE_CATEGORY_NAMES
from database import SessionLocal
from models import Asset, WarehouseAsset


def _print_issues(title, items, formatter):
    print(f"\n{title}: {len(items)} 条")
    for item in items:
        print(f"  - {formatter(item)}")


def reconcile():
    """执行只读检查；两个数据域独立，不进行跨表数量比较或修改。"""
    db = SessionLocal()
    try:
        assets = db.query(Asset).filter(Asset.is_deleted.is_(False)).all()
        warehouse_items = db.query(WarehouseAsset).all()
        fixed_names = set(ASSET_CATEGORY_NAMES.values())

        invalid_assets = [item for item in assets if item.category not in fixed_names]
        invalid_warehouse = [
            item for item in warehouse_items
            if item.category not in CONSUMABLE_CATEGORY_NAMES
        ]
        quantity_issues = [
            item for item in warehouse_items
            if any(value is None or value < 0 for value in (
                item.total_quantity, item.available_quantity, item.allocated_quantity
            )) or (item.total_quantity or 0) != (
                (item.available_quantity or 0) + (item.allocated_quantity or 0)
            )
        ]

        print("\nIT资产分类与库存完整性检查")
        print("固定资产允许品类：" + "、".join(sorted(fixed_names)))
        print("消耗品允许品类：" + "、".join(sorted(CONSUMABLE_CATEGORY_NAMES)))
        _print_issues("固定资产非法分类", invalid_assets, lambda x: f"{x.asset_tag}: {x.category}")
        _print_issues("消耗品非法分类", invalid_warehouse, lambda x: f"ID={x.id} {x.name}: {x.category}")
        _print_issues("库房数量异常", quantity_issues, lambda x: (
            f"ID={x.id} {x.name}: total={x.total_quantity}, "
            f"available={x.available_quantity}, allocated={x.allocated_quantity}"
        ))
        total_issues = len(invalid_assets) + len(invalid_warehouse) + len(quantity_issues)
        print(f"\n检查完成：共发现 {total_issues} 项问题；本脚本未修改任何数据。\n")
    finally:
        db.close()


if __name__ == "__main__":
    reconcile()
