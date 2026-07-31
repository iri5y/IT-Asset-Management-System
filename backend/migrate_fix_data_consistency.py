"""
数据一致性修复迁移脚本
======================
修复对账脚本发现的历史数据问题：
1. 清除闲置资产上残留的员工绑定信息
2. 修复 warehouse_assets 中 total_quantity ≠ available_quantity + allocated_quantity 的记录

使用方式：
  cd backend && python migrate_fix_data_consistency.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Asset, WarehouseAsset, AssetLog, WarehouseAssetLog, china_now


def migrate():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("  数据一致性修复迁移")
        print("=" * 60)

        # ── 1. 清除闲置资产上残留的员工绑定信息 ──────────────────────

        print("\n[1/2] 修复闲置资产的员工绑定信息...")

        idle_with_employee = (
            db.query(Asset)
            .filter(
                Asset.status == "闲置",
                Asset.is_deleted == False,
                Asset.employee_name != None,
                Asset.employee_name != "",
            )
            .all()
        )

        fixed_employee_count = 0
        for asset in idle_with_employee:
            old_info = (
                f"工号={asset.employee_id or '(空)'}, "
                f"使用人={asset.employee_name or '(空)'}, "
                f"部门={asset.department or '(空)'}, "
                f"直属领导={asset.supervisor or '(空)'}"
            )
            print(f"  修复 {asset.asset_tag}: 清除 {old_info}")

            asset.employee_id = None
            asset.employee_name = None
            asset.department = None
            asset.supervisor = None

            # 记录操作日志
            log = AssetLog(
                asset_id=asset.id,
                action="数据修复",
                description=f"迁移脚本自动清除闲置资产的员工绑定信息: {old_info}",
                operator="系统迁移",
            )
            db.add(log)
            fixed_employee_count += 1

        db.commit()
        print(f"  ✅ 已修复 {fixed_employee_count} 条闲置资产的员工绑定")

        # ── 2. 修复 warehouse_assets 数量守恒 ────────────────────────

        print("\n[2/2] 修复库房资产数量守恒...")

        all_wh = db.query(WarehouseAsset).all()
        fixed_qty_count = 0

        for item in all_wh:
            expected_total = item.available_quantity + item.allocated_quantity
            if item.total_quantity != expected_total:
                old_total = item.total_quantity
                print(
                    f"  修复 ID={item.id} {item.name}: "
                    f"total {old_total} → {expected_total} "
                    f"(available={item.available_quantity} + allocated={item.allocated_quantity})"
                )
                item.total_quantity = expected_total

                wh_log = WarehouseAssetLog(
                    asset_id=item.id,
                    action="数据修复",
                    description=(
                        f"迁移脚本修复数量守恒: "
                        f"总数量 {old_total} → {expected_total} "
                        f"(可用={item.available_quantity} + 已分配={item.allocated_quantity})"
                    ),
                    operator="系统迁移",
                )
                db.add(wh_log)
                fixed_qty_count += 1

        db.commit()
        print(f"  ✅ 已修复 {fixed_qty_count} 条库房资产的数量守恒")

        # ── 汇总 ─────────────────────────────────────────────────────

        print("\n" + "=" * 60)
        print("  迁移完成")
        print(f"  - 清除员工绑定: {fixed_employee_count} 条")
        print(f"  - 修复数量守恒: {fixed_qty_count} 条")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"\n❌ 迁移失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
