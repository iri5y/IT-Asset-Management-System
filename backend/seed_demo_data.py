"""创建本地演示数据。

运行方式：python seed_demo_data.py
特点：仅新增带有“演示数据”标识的记录；重复运行不会覆盖或重复插入。
"""
from __future__ import annotations

from datetime import timedelta

from category_policy import require_consumable_category
from database import SessionLocal, engine
import models

DEMO_NOTE = "[演示数据]"


def get_or_create_named(db, model, name, **kwargs):
    existing = db.query(model).filter(model.name == name).one_or_none()
    if existing:
        return existing, False
    record = model(name=name, **kwargs)
    db.add(record)
    db.flush()
    return record, True


def get_or_create_department(db, name, parent=None):
    existing = db.query(models.Department).filter(
        models.Department.name == name
    ).one_or_none()
    if existing:
        return existing, False
    department = models.Department(
        name=name,
        parent_id=parent.id if parent else None,
    )
    db.add(department)
    db.flush()
    return department, True


def get_or_create_warehouse(db, data):
    existing = db.query(models.WarehouseAsset).filter(
        models.WarehouseAsset.name == data["name"]
    ).one_or_none()
    if existing:
        return existing, False
    warehouse = models.WarehouseAsset(
        **{**data, "category": require_consumable_category(data["category"])}
    )
    db.add(warehouse)
    db.flush()
    db.add(models.WarehouseAssetLog(
        asset_id=warehouse.id,
        action="演示数据入库",
        description=f"{DEMO_NOTE} 创建测试库存记录",
        operator="演示数据脚本",
    ))
    return warehouse, True


def get_or_create_asset(db, data):
    existing = db.query(models.Asset).filter(
        models.Asset.asset_tag == data["asset_tag"]
    ).one_or_none()
    if existing:
        return existing, False
    asset = models.Asset(**data)
    db.add(asset)
    db.flush()
    db.add(models.AssetLog(
        asset_id=asset.id,
        action="演示数据创建",
        description=f"{DEMO_NOTE} 创建测试资产 {asset.asset_tag}",
        operator="演示数据脚本",
    ))
    return asset, True


def get_or_create_return(db, data):
    existing = db.query(models.ReturnRecord).filter(
        models.ReturnRecord.employee_id == data["employee_id"],
        models.ReturnRecord.asset_name == data["asset_name"],
        models.ReturnRecord.return_reason == data["return_reason"],
        models.ReturnRecord.notes == data["notes"],
    ).one_or_none()
    if existing:
        return existing, False
    record = models.ReturnRecord(**data)
    db.add(record)
    db.flush()
    return record, True


def seed_demo_data():
    """在当前模型中创建覆盖主要展示场景的演示数据。"""
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    counts = {
        "brands": 0,
        "departments": 0,
        "locations": 0,
        "assets": 0,
        "warehouse": 0,
        "returns": 0,
        "part_logs": 0,
        "hostname_history": 0,
    }
    try:
        brand_names = (
            "Dell", "Lenovo", "Samsung", "HP", "ASUS", "Apple", "Acer",
            "Microsoft", "Huawei", "Logitech", "Kingston", "SanDisk",
            "TP-Link", "Cisco", "通用", "得力",
        )
        for brand_name in brand_names:
            _, created = get_or_create_named(db, models.Brand, brand_name)
            counts["brands"] += int(created)

        warehouse_locations = (
            ("IT库房", "IT 设备与耗材主库"),
            ("A区货架", "显示和输入设备存放区"),
            ("B区货架", "线缆与连接配件存放区"),
            ("C区货架", "存储设备与备件存放区"),
            ("D区货架", "办公耗材存放区"),
            ("维修备件区", "维修替换件和工具存放区"),
            ("待检区", "新到货物料验收暂存区"),
            ("临时存放区", "待检修或待入库设备暂存"),
        )
        office_locations = (
            ("办公区域", "办公工位使用中的设备"),
            ("IT支持中心", "IT 支持团队办公区域"),
            ("研发中心一楼", "研发团队固定资产使用区"),
            ("研发中心二楼", "实验室与工程团队使用区"),
            ("财务共享中心", "财务团队办公区域"),
            ("生产办公区", "生产运营团队办公区域"),
            ("行政办公区", "行政和人力资源团队办公区域"),
            ("会议培训区", "共享会议与培训设备区域"),
        )
        for name, description in warehouse_locations:
            _, created = get_or_create_named(
                db, models.WarehouseLocation, name, description=description
            )
            counts["locations"] += int(created)
        for name, description in office_locations:
            _, created = get_or_create_named(
                db, models.OfficeLocation, name, description=description
            )
            counts["locations"] += int(created)

        department_tree = {
            "信息技术部": ("IT支持组", "基础架构组", "信息安全组", "应用开发组"),
            "财务部": ("会计组", "成本控制组", "资金管理组", "审计组"),
            "工程部": ("硬件工程组", "软件工程组", "测试工程组", "项目管理组"),
            "人力资源部": ("招聘组", "员工关系组", "薪酬福利组", "培训发展组"),
            "生产运营部": ("生产一组", "生产二组", "设备维护组", "计划调度组"),
            "质量管理部": ("质量保证组", "质量控制组", "客户质量组"),
            "采购与供应链部": ("采购组", "供应商管理组", "物流仓储组"),
            "销售与市场部": ("国内销售组", "海外销售组", "市场推广组"),
            "行政管理部": ("行政事务组", "设施管理组", "前台服务组"),
        }
        selectable_departments = []
        for parent_name, child_names in department_tree.items():
            parent, created = get_or_create_department(db, parent_name)
            counts["departments"] += int(created)
            for child_name in child_names:
                _, created = get_or_create_department(db, child_name, parent=parent)
                counts["departments"] += int(created)
                selectable_departments.append(child_name)

        warehouse_specs = (
            ("演示库存-显示器", "显示设备", "显示器", "Dell", "P2422H", 10, 3, 5, "A区货架"),
            ("演示库存-便携显示器", "显示设备", "便携显示器", "ASUS", "MB16AC", 8, 6, 3, "A区货架"),
            ("演示库存-HDMI投屏器", "显示设备", "投屏器", "Microsoft", "Wireless Display", 6, 2, 3, "A区货架"),
            ("演示库存-USB耳机", "音频设备", "耳机", "Logitech", "H390", 20, 14, 5, "A区货架"),
            ("演示库存-会议麦克风", "音频设备", "麦克风", "Logitech", "MeetUp Mic", 5, 1, 2, "A区货架"),
            ("演示库存-桌面音箱", "音频设备", "音箱", "通用", "USB Speaker", 8, 5, 2, "A区货架"),
            ("演示库存-备用手机", "手机", "安卓手机", "Samsung", "Galaxy A54", 10, 4, 3, "IT库房"),
            ("演示库存-手机充电器", "手机", "充电器", "Huawei", "66W USB-C", 30, 18, 8, "B区货架"),
            ("演示库存-手机保护壳", "手机", "保护壳", "通用", "6.5英寸", 40, 28, 10, "D区货架"),
            ("演示库存-有线鼠标", "输入设备", "有线鼠标", "通用", "USB", 12, 8, 3, "IT库房"),
            ("演示库存-无线鼠标", "输入设备", "无线鼠标", "Logitech", "M331", 25, 16, 6, "A区货架"),
            ("演示库存-办公键盘", "输入设备", "键盘", "Logitech", "K120", 18, 7, 5, "A区货架"),
            ("演示库存-固态硬盘", "存储设备", "SSD", "Kingston", "NV2 1TB", 15, 4, 5, "C区货架"),
            ("演示库存-内存条", "存储设备", "内存", "Kingston", "DDR4 16GB", 24, 11, 6, "C区货架"),
            ("演示库存-U盘", "存储设备", "U盘", "SanDisk", "64GB", 35, 22, 8, "C区货架"),
            ("演示库存-网线", "线缆与连接配件", "网线", "通用", "CAT6", 100, 76, 20, "B区货架"),
            ("演示库存-HDMI线", "线缆与连接配件", "视频线", "通用", "HDMI 2米", 30, 9, 10, "B区货架"),
            ("演示库存-Type-C扩展坞", "线缆与连接配件", "扩展坞", "Dell", "WD19S", 12, 2, 4, "B区货架"),
            ("演示库存-工具箱", "工具", "工具箱", "得力", "工具套装", 6, 2, 2, "临时存放区"),
            ("演示库存-网络测线仪", "工具", "网络工具", "通用", "RJ45 Tester", 5, 3, 2, "维修备件区"),
            ("演示库存-螺丝刀套装", "工具", "维修工具", "得力", "精密套装", 8, 5, 2, "维修备件区"),
            ("演示库存-A4打印纸", "办公与通用耗材", "打印纸", "通用", "A4 80g", 60, 42, 15, "D区货架"),
            ("演示库存-标签纸", "办公与通用耗材", "标签耗材", "通用", "50x30mm", 50, 12, 15, "D区货架"),
            ("演示库存-硒鼓", "办公与通用耗材", "打印耗材", "HP", "W1370A", 12, 3, 4, "D区货架"),
        )
        warehouse_items = {}
        for spec in warehouse_specs:
            name, category, subcategory, brand, model, total, available, minimum, location = spec
            item, created = get_or_create_warehouse(db, {
                "name": name,
                "category": category,
                "subcategory": subcategory,
                "brand": brand,
                "model": model,
                "total_quantity": total,
                "available_quantity": available,
                "allocated_quantity": total - available,
                "minimum_stock": minimum,
                "location": location,
                "notes": DEMO_NOTE,
            })
            warehouse_items[name] = item
            counts["warehouse"] += int(created)

        category_specs = (
            ("PC", "台式机", "Dell", "OptiPlex 7010"),
            ("NB", "笔记本电脑", "Lenovo", "ThinkPad E14"),
            ("PD", "平板电脑", "Apple", "iPad Air"),
        )
        statuses = ("使用中", "使用中", "闲置", "维修中", "报废")
        office_names = tuple(name for name, _ in office_locations)
        warehouse_names = tuple(name for name, _ in warehouse_locations)
        assets_by_index = {}
        for index in range(1, 61):
            code, category, brand, model = category_specs[(index - 1) % len(category_specs)]
            status = statuses[(index - 1) % len(statuses)]
            in_use = status == "使用中"
            department = selectable_departments[(index - 1) % len(selectable_departments)]
            employee_id = f"DEMO-E{index:03d}" if in_use else None
            employee_name = f"演示员工-{index:03d}" if in_use else None
            tag_number = 900000 + index
            asset, created = get_or_create_asset(db, {
                "asset_tag": f"ZS-{code}26-{tag_number:06d}",
                "category": category,
                "brand": brand,
                "model": model,
                "serial_number": f"DEMO-SN-{code}-{tag_number:06d}",
                "fixed_asset_number": f"FA-DEMO-2026-{index:04d}",
                "status": status,
                "employee_id": employee_id,
                "employee_name": employee_name,
                "department": department if in_use else None,
                "hostname": f"DEMO-{code}-{index:03d}" if category != "平板电脑" else None,
                "mac_address": f"02:00:00:00:{index // 256:02X}:{index % 256:02X}",
                "ip_address": f"192.0.2.{100 + index}" if in_use else None,
                "purchase_date": models.china_now() - timedelta(days=30 + index * 9),
                "issue_date": models.china_now() - timedelta(days=index * 3) if in_use else None,
                "location": office_names[(index - 1) % len(office_names)] if in_use else warehouse_names[(index - 1) % len(warehouse_names)],
                "po_number": f"PO-DEMO-2026-{(index - 1) // 10 + 1:03d}",
                "system_version": "Windows 11 企业版" if category != "平板电脑" else "iPadOS 18",
                "antivirus_software": "Microsoft Defender" if category != "平板电脑" else None,
                "lock_number": f"LOCK-{index:04d}" if category == "台式机" else None,
                "bios_password": category == "笔记本电脑" and index % 2 == 0,
                "tpm_status": category != "平板电脑",
                "has_desktop": category == "笔记本电脑" and index % 4 == 0,
                "condition": "损坏" if status == "维修中" else ("待报废" if status == "报废" else "可用"),
                "notes": f"{DEMO_NOTE} 批量展示资产 {index:03d}",
                "quantity": 1,
                "additional_info": {"demo_batch": "2026-A", "warranty_years": 3},
            })
            assets_by_index[index] = asset
            counts["assets"] += int(created)

        part_names = tuple(warehouse_items)
        for index in range(1, 19):
            asset = assets_by_index[index]
            item = warehouse_items[part_names[(index - 1) % len(part_names)]]
            notes = f"{DEMO_NOTE} 配件维护记录 {index:02d}"
            exists = db.query(models.AssetPartLog).filter(
                models.AssetPartLog.asset_id == asset.id,
                models.AssetPartLog.notes == notes,
            ).first()
            if not exists:
                db.add(models.AssetPartLog(
                    asset_id=asset.id,
                    warehouse_item_id=item.id,
                    warehouse_item_name=item.name,
                    action="更换" if index % 2 else "新增",
                    quantity=1,
                    notes=notes,
                    operator="演示数据脚本",
                ))
                counts["part_logs"] += 1

        for index in range(1, 16):
            asset = assets_by_index[index]
            if not asset.hostname:
                continue
            new_hostname = f"{asset.hostname}-NEW"
            exists = db.query(models.HostnameHistory).filter(
                models.HostnameHistory.asset_id == asset.id,
                models.HostnameHistory.new_hostname == new_hostname,
            ).first()
            if not exists:
                db.add(models.HostnameHistory(
                    asset_id=asset.id,
                    old_hostname=f"DEMO-OLD-{index:03d}",
                    new_hostname=new_hostname,
                    change_reason=f"{DEMO_NOTE} 设备调整演示",
                ))
                counts["hostname_history"] += 1

        for index in range(3, 16):
            asset = assets_by_index[index]
            returned = index % 3 != 0
            data = {
                "asset_name": f"{asset.asset_tag} {asset.category}",
                "employee_id": f"DEMO-E{index:03d}",
                "employee_name": f"演示员工-{index:03d}",
                "department": selectable_departments[(index - 1) % len(selectable_departments)],
                "return_reason": ("设备更换", "离职归还", "借用到期")[index % 3],
                "is_returned": returned,
                "return_date": models.china_now() - timedelta(days=index) if returned else None,
                "notes": f"{DEMO_NOTE} 归还流程记录 {index:03d}",
            }
            _, created = get_or_create_return(db, data)
            counts["returns"] += int(created)

        if sum(counts.values()):
            admin = db.query(models.User).filter(
                models.User.username == "admin"
            ).one_or_none()
            if admin:
                db.add(models.OperationLog(
                    user_id=admin.id,
                    action="seed_demo_data",
                    resource_type="demo_data",
                    description=f"{DEMO_NOTE} 初始化演示数据：{counts}",
                ))
        db.commit()
        print("演示数据创建完成（以下为本次新增）：")
        print(f"  品牌: {counts['brands']} 条")
        print(f"  部门: {counts['departments']} 条")
        print(f"  位置: {counts['locations']} 条")
        print(f"  固定资产: {counts['assets']} 条")
        print(f"  仓储物料: {counts['warehouse']} 条")
        print(f"  归还记录: {counts['returns']} 条")
        print(f"  配件维护记录: {counts['part_logs']} 条")
        print(f"  主机名历史: {counts['hostname_history']} 条")
        print("重复运行将跳过已存在的演示数据，不会覆盖业务数据。")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()
