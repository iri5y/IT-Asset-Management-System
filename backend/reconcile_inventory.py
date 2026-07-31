"""
数据对账脚本 (Inventory Reconciliation Script)
================================================
功能：
  1. 查询 assets 表中所有 status='闲置' 且未软删除的资产，按品类 (category) 计数
  2. 查询 warehouse_assets 表中各品类的 available_quantity 汇总
  3. 对比两者差额，输出详细的资产标签清单
  4. 分析逻辑漏洞可能出现在哪个 API 接口

使用方式：
  cd backend && python reconcile_inventory.py
"""

import sys
import os
from collections import defaultdict
from datetime import datetime

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Asset, WarehouseAsset


# ── 终端颜色辅助 ──────────────────────────────────────────────────────────

class Color:
    """简易终端颜色，Windows 终端不支持时自动降级为纯文本。"""
    try:
        os.system("")  # 启用 Windows ANSI 支持
        RED = "\033[91m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        CYAN = "\033[96m"
        BOLD = "\033[1m"
        RESET = "\033[0m"
    except Exception:
        RED = GREEN = YELLOW = CYAN = BOLD = RESET = ""


def print_header(title: str):
    width = 70
    print(f"\n{Color.CYAN}{'═' * width}")
    print(f"  {title}")
    print(f"{'═' * width}{Color.RESET}")


def print_section(title: str):
    print(f"\n{Color.BOLD}── {title} ──{Color.RESET}")


def reconcile():
    db = SessionLocal()
    try:
        run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print_header(f"IT 资产数据对账报告  |  {run_time}")

        # ================================================================
        # 1. 查询 assets 表中 status='闲置' 且未软删除的资产
        # ================================================================
        idle_assets = (
            db.query(Asset)
            .filter(Asset.status == "闲置", Asset.is_deleted == False)
            .all()
        )

        # 按品类分组
        idle_by_category = defaultdict(list)
        for asset in idle_assets:
            idle_by_category[asset.category].append(asset)

        print_section("1. assets 表中 status='闲置' 的资产统计")
        print(f"   {'品类':<16} {'数量':>6}")
        print(f"   {'─' * 24}")
        total_idle = 0
        for cat in sorted(idle_by_category.keys()):
            count = len(idle_by_category[cat])
            total_idle += count
            print(f"   {cat:<16} {count:>6}")
        print(f"   {'─' * 24}")
        print(f"   {'合计':<16} {total_idle:>6}")

        # ================================================================
        # 2. 查询 warehouse_assets 表中各品类的 available_quantity
        # ================================================================
        warehouse_items = db.query(WarehouseAsset).all()

        wh_by_category = defaultdict(lambda: {"available_qty": 0, "items": []})
        for item in warehouse_items:
            wh_by_category[item.category]["available_qty"] += item.available_quantity
            wh_by_category[item.category]["items"].append(item)

        print_section("2. warehouse_assets 表中各品类 available_quantity 汇总")
        print(f"   {'品类':<16} {'可用数量':>8}")
        print(f"   {'─' * 26}")
        total_wh_available = 0
        for cat in sorted(wh_by_category.keys()):
            qty = wh_by_category[cat]["available_qty"]
            total_wh_available += qty
            print(f"   {cat:<16} {qty:>8}")
        print(f"   {'─' * 26}")
        print(f"   {'合计':<16} {total_wh_available:>8}")

        # ================================================================
        # 3. 交叉对比：找出品类维度的差异
        # ================================================================
        all_categories = sorted(set(idle_by_category.keys()) | set(wh_by_category.keys()))

        print_section("3. 品类维度交叉对比")
        print(f"   {'品类':<16} {'闲置资产数':>10} {'库房可用量':>10} {'差额':>8} {'状态':>8}")
        print(f"   {'─' * 56}")

        discrepancies = []
        categories_only_in_assets = []
        categories_only_in_warehouse = []

        for cat in all_categories:
            idle_count = len(idle_by_category.get(cat, []))
            wh_available = wh_by_category.get(cat, {}).get("available_qty", 0)
            diff = idle_count - wh_available

            if cat in idle_by_category and cat not in wh_by_category:
                status = f"{Color.RED}仅assets{Color.RESET}"
                categories_only_in_assets.append(cat)
                discrepancies.append((cat, idle_count, wh_available, diff))
            elif cat not in idle_by_category and cat in wh_by_category:
                status = f"{Color.YELLOW}仅warehouse{Color.RESET}"
                categories_only_in_warehouse.append(cat)
            elif diff != 0:
                status = f"{Color.RED}不一致{Color.RESET}"
                discrepancies.append((cat, idle_count, wh_available, diff))
            else:
                status = f"{Color.GREEN}一致{Color.RESET}"

            print(f"   {cat:<16} {idle_count:>10} {wh_available:>10} {diff:>+8} {status}")

        # ================================================================
        # 4. 差异详情：输出不一致品类的资产标签清单
        # ================================================================
        if discrepancies:
            print_section("4. 差异详情 — 不一致品类的闲置资产标签清单")
            for cat, idle_count, wh_available, diff in discrepancies:
                print(f"\n   {Color.BOLD}[{cat}]{Color.RESET}  "
                      f"闲置资产: {idle_count}  |  库房可用量: {wh_available}  |  差额: {diff:+d}")
                assets_in_cat = idle_by_category.get(cat, [])
                if assets_in_cat:
                    print(f"   闲置资产标签列表:")
                    for a in sorted(assets_in_cat, key=lambda x: x.asset_tag):
                        emp_info = ""
                        if a.employee_name:
                            emp_info = f"  (使用人: {a.employee_name})"
                        location_info = ""
                        if a.location:
                            location_info = f"  [位置: {a.location}]"
                        print(f"     • {a.asset_tag}  {a.brand or ''} {a.model or ''}"
                              f"  状态={a.status}{emp_info}{location_info}")
                else:
                    print(f"   (assets 表中无该品类的闲置资产)")

                # 同时列出 warehouse_assets 中该品类的明细
                wh_items = wh_by_category.get(cat, {}).get("items", [])
                if wh_items:
                    print(f"   库房资产明细:")
                    for w in wh_items:
                        print(f"     • ID={w.id}  {w.name}  "
                              f"总量={w.total_quantity}  可用={w.available_quantity}  "
                              f"已分配={w.allocated_quantity}")
        else:
            print(f"\n   {Color.GREEN}✅ 所有品类的闲置资产数与库房可用量一致，无差异。{Color.RESET}")

        # ================================================================
        # 5. 数据完整性检查
        # ================================================================
        print_section("5. 数据完整性检查")

        # 5a. warehouse_assets 中 total != available + allocated 的记录
        integrity_issues = []
        for item in warehouse_items:
            if item.total_quantity != item.available_quantity + item.allocated_quantity:
                integrity_issues.append(item)

        if integrity_issues:
            print(f"   {Color.RED}⚠ 发现 {len(integrity_issues)} 条库房资产的"
                  f" total_quantity ≠ available_quantity + allocated_quantity:{Color.RESET}")
            for item in integrity_issues:
                expected = item.available_quantity + item.allocated_quantity
                print(f"     • ID={item.id}  {item.name}  "
                      f"total={item.total_quantity}  available={item.available_quantity}  "
                      f"allocated={item.allocated_quantity}  "
                      f"(期望 total={expected})")
        else:
            print(f"   {Color.GREEN}✅ 所有库房资产的 total = available + allocated，数量守恒正确。{Color.RESET}")

        # 5b. 闲置资产仍绑定员工信息的异常记录
        idle_with_employee = [
            a for a in idle_assets
            if a.employee_name and a.employee_name.strip()
        ]
        if idle_with_employee:
            print(f"\n   {Color.YELLOW}⚠ 发现 {len(idle_with_employee)} 条闲置资产仍绑定员工信息"
                  f"（可能未正确清除）:{Color.RESET}")
            for a in idle_with_employee[:20]:  # 最多显示20条
                print(f"     • {a.asset_tag}  使用人={a.employee_name}  "
                      f"工号={a.employee_id or '(空)'}  部门={a.department or '(空)'}")
            if len(idle_with_employee) > 20:
                print(f"     ... 还有 {len(idle_with_employee) - 20} 条，此处省略")
        else:
            print(f"   {Color.GREEN}✅ 所有闲置资产均已清除员工绑定信息。{Color.RESET}")

        # ================================================================
        # 6. 库存同步机制说明
        # ================================================================
        print_section("6. 库存同步机制说明")

        print(f"""
   当前系统的库存同步规则（已实现）：

   {Color.GREEN}【已实现】PUT /assets/{{asset_id}} — 资产状态变更{Color.RESET}
   文件: main.py → update_asset()
   规则: 状态从"闲置"变为其他 → _sync_warehouse_quantity(-1)
         状态变为"闲置"（非闲置→闲置）→ _sync_warehouse_quantity(+1)
   例外: from_warehouse=True 的资产（库房发放创建）跳过自动同步，
         其库存由库房模块独立管理。

   {Color.GREEN}【已实现】POST /assets/ — 新建资产{Color.RESET}
   文件: main.py → create_asset()
   规则: 新建状态为"闲置"的资产 → _sync_warehouse_quantity(+1)
         新建状态为"使用中"等其他状态 → 不触发同步

   {Color.GREEN}【已实现】DELETE /assets/{{asset_id}} — 删除资产{Color.RESET}
   文件: main.py → delete_asset()
   规则: 软删除状态为"闲置"的资产 → _sync_warehouse_quantity(-1)
         from_warehouse=True 的资产跳过同步

   {Color.CYAN}【注意】品类映射关系{Color.RESET}
   assets.category → warehouse_assets.category 的映射：
     台式机/笔记本电脑 → 计算机设备
     显示器           → 显示设备
     移动设备/手机     → 移动设备
     无线鼠标         → 输入设备
     打印机           → 其他配件
     网络设备         → 网络设备
   如果对账发现差异，请检查品类名称是否在上述映射中。

   {Color.YELLOW}【潜在风险】直接修改数据库{Color.RESET}
   绕过 API 直接修改 assets.status 不会触发库存同步，
   可能导致数据不一致。如需修复，运行：
     python migrate_fix_data_consistency.py

   {Color.RED}【高风险】DELETE /assets/{{asset_id}} — 删除资产接口{Color.RESET}
   文件: main.py → delete_asset()
   问题: 软删除一个状态为"闲置"的资产时，没有递减 warehouse_assets 的
         available_quantity。
   影响: 已删除的闲置资产仍被库房统计为可用。

   {Color.YELLOW}【中风险】PUT /warehouse/{{asset_id}} — 库房资产编辑接口{Color.RESET}
   文件: main.py → update_warehouse_asset()
   问题: 可以直接手动修改 available_quantity，没有校验是否与 assets 表中的
         实际闲置数量一致，也没有校验 total = available + allocated 的守恒关系。
   影响: 手动编辑可能引入不一致数据。

   {Color.YELLOW}【中风险】POST /warehouse/ — 新建库房资产接口{Color.RESET}
   文件: main.py → create_warehouse_asset()
   问题: 新建库房资产时的 available_quantity 由前端传入，没有与 assets 表交叉验证。

   {Color.CYAN}【根本原因】{Color.RESET}
   assets 表和 warehouse_assets 表之间{Color.BOLD}没有外键关联{Color.RESET}，品类字段仅靠名称
   字符串匹配。两张表的数据独立维护，缺少同步机制。当资产状态变更时，系统没有
   触发对库房可用量的联动更新，导致数据随时间推移逐渐偏离。

   {Color.CYAN}【建议修复方向】{Color.RESET}
   1. 在 update_asset() 中增加状态变更钩子：
      - 状态变为"闲置"时 → 对应品类的 available_quantity +1
      - 状态从"闲置"变为其他 → 对应品类的 available_quantity -1
   2. 在 delete_asset() 中检查被删资产是否为"闲置"，若是则递减 available_quantity
   3. 在 create_asset() 中检查新资产是否为"闲置"，若是则递增 available_quantity
   4. 在 update_warehouse_asset() 中增加 total = available + allocated 的守恒校验
   5. 长期方案：建立 assets 与 warehouse_assets 之间的外键关联，或改用事件驱动
      架构确保数据一致性
""")

        # ================================================================
        # 7. 汇总
        # ================================================================
        print_header("对账汇总")
        total_discrepancies = len(discrepancies)
        total_integrity = len(integrity_issues)
        total_employee_bind = len(idle_with_employee)

        if total_discrepancies == 0 and total_integrity == 0 and total_employee_bind == 0:
            print(f"   {Color.GREEN}✅ 未发现数据不一致问题。{Color.RESET}")
        else:
            print(f"   品类数量不一致:          {Color.RED}{total_discrepancies} 个品类{Color.RESET}")
            print(f"   库房数量守恒异常:        {Color.RED}{total_integrity} 条记录{Color.RESET}")
            print(f"   闲置资产仍绑定员工:      {Color.YELLOW}{total_employee_bind} 条记录{Color.RESET}")
            print(f"\n   请根据上述分析检查相关 API 接口逻辑。")

        print()

    finally:
        db.close()


if __name__ == "__main__":
    reconcile()
