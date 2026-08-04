"""创建本地演示数据。

运行方式：python seed_demo_data.py
特点：仅新增带有“演示数据”标识的记录；重复运行不会覆盖或重复插入。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from database import SessionLocal, engine
import models
from warehouse_category_seed import seed_warehouse_categories

DEMO_NOTE = "[演示数据]"


def get_or_create_employee(db, employee_no, name, department, email, inactive=False):
    employee = (
        db.query(models.Employee)
        .filter(models.Employee.employee_no == employee_no)
        .one_or_none()
    )
    if employee:
        return employee, False
    employee = models.Employee(
        employee_no=employee_no,
        name=name,
        department=department,
        email=email,
        status="INACTIVE" if inactive else "ACTIVE",
        departure_date=(models.china_now() - timedelta(days=30)) if inactive else None,
    )
    db.add(employee)
    db.flush()
    return employee, True


def get_or_create_warehouse(db, data, primary_code, secondary_code):
    existing = (
        db.query(models.WarehouseAsset)
        .filter(models.WarehouseAsset.name == data["name"])
        .one_or_none()
    )
    if existing:
        return existing, False
    primary = (
        db.query(models.WarehousePrimaryCategory)
        .filter(models.WarehousePrimaryCategory.code == primary_code)
        .one()
    )
    secondary = (
        db.query(models.WarehouseSecondaryCategory)
        .filter(
            models.WarehouseSecondaryCategory.code == secondary_code,
            models.WarehouseSecondaryCategory.primary_category_id == primary.id,
        )
        .one()
    )
    warehouse = models.WarehouseAsset(
        **data,
        category=primary.name,
        subcategory=secondary.name,
        primary_category_id=primary.id,
        secondary_category_id=secondary.id,
        classification_status="ACTIVE",
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
    existing = (
        db.query(models.Asset)
        .filter(models.Asset.asset_tag == data["asset_tag"])
        .one_or_none()
    )
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
    existing = (
        db.query(models.ReturnRecord)
        .filter(
            models.ReturnRecord.employee_id == data["employee_id"],
            models.ReturnRecord.asset_name == data["asset_name"],
            models.ReturnRecord.return_reason == data["return_reason"],
            models.ReturnRecord.notes == data["notes"],
        )
        .one_or_none()
    )
    if existing:
        return existing, False
    record = models.ReturnRecord(**data)
    db.add(record)
    db.flush()
    return record, True


def seed_demo_data():
    # 兼容首次运行：按当前 ORM 创建缺失表；不会删除已有数据。
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    counts = {"employees": 0, "assets": 0, "warehouse": 0, "returns": 0}
    try:
        # 先确保两级仓储分类存在，后续库存记录依赖其外键。
        seed_warehouse_categories(db)
        db.flush()

        employees = {}
        employee_data = [
            ("DEMO-E001", "演示员工-张伟", "信息技术部", "demo-zhang@example.invalid", False),
            ("DEMO-E002", "演示员工-李娜", "财务部", "demo-li@example.invalid", False),
            ("DEMO-E003", "演示员工-王强", "工程部", "demo-wang@example.invalid", True),
        ]
        for row in employee_data:
            employee, created = get_or_create_employee(db, *row)
            employees[row[0]] = employee
            counts["employees"] += int(created)

        warehouse_data = [
            ({
                "name": "演示库存-笔记本电脑",
                "brand": "Lenovo",
                "model": "ThinkPad E14",
                "total_quantity": 12,
                "available_quantity": 8,
                "allocated_quantity": 4,
                "minimum_stock": 3,
                "low_stock_threshold": 2,
                "location": "IT库房",
                "notes": DEMO_NOTE,
                "issue_policy": "RETURNABLE",
                "material_kind": "FIXED_ASSET_TERMINAL",
            }, "TERMINAL_EQUIPMENT", "TERMINAL_LAPTOP"),
            ({
                "name": "演示库存-显示器",
                "brand": "Dell",
                "model": "P2422H",
                "total_quantity": 10,
                "available_quantity": 3,
                "allocated_quantity": 7,
                "minimum_stock": 5,
                "low_stock_threshold": 2,
                "location": "A区货架",
                "notes": DEMO_NOTE,
                "issue_policy": "RETURNABLE",
                "material_kind": "LOW_VALUE_RETURNABLE",
            }, "DISPLAY_AUDIO_VIDEO", "DISPLAY_MONITOR"),
            ({
                "name": "演示库存-网线",
                "brand": "通用",
                "model": "CAT6",
                "total_quantity": 100,
                "available_quantity": 76,
                "allocated_quantity": 24,
                "minimum_stock": 20,
                "low_stock_threshold": 10,
                "location": "B区货架",
                "notes": DEMO_NOTE,
                "issue_policy": "CONSUMABLE",
                "material_kind": "CONSUMABLE",
            }, "CABLES_CONNECTORS", "CABLE_NETWORK"),
            ({
                "name": "演示库存-工具箱",
                "brand": "得力",
                "model": "工具套装",
                "total_quantity": 6,
                "available_quantity": 2,
                "allocated_quantity": 4,
                "minimum_stock": 2,
                "low_stock_threshold": 1,
                "location": "临时存放区",
                "notes": DEMO_NOTE,
                "issue_policy": "RETURNABLE",
                "material_kind": "LOANABLE_TOOL",
            }, "IT_TOOLS_LOAN_ITEMS", "TOOL_KIT"),
        ]
        warehouses = {}
        for data, primary_code, secondary_code in warehouse_data:
            warehouse, created = get_or_create_warehouse(
                db, data, primary_code, secondary_code
            )
            warehouses[data["name"]] = warehouse
            counts["warehouse"] += int(created)

        asset_data = [
            {
                "asset_tag": "ZS-PC26-900001",
                "category": "台式机",
                "brand": "Dell",
                "model": "OptiPlex 7010",
                "serial_number": "DEMO-SN-PC-900001",
                "status": "使用中",
                "employee_ref_id": employees["DEMO-E001"].id,
                "employee_id": "DEMO-E001",
                "employee_name": employees["DEMO-E001"].name,
                "department": employees["DEMO-E001"].department,
                "hostname": "DEMO-PC-001",
                "ip_address": "192.0.2.101",
                "location": "办公区域",
                "notes": DEMO_NOTE,
                "quantity": 1,
            },
            {
                "asset_tag": "ZS-NB26-900002",
                "category": "笔记本电脑",
                "brand": "Lenovo",
                "model": "ThinkPad E14",
                "serial_number": "DEMO-SN-NB-900002",
                "status": "使用中",
                "employee_ref_id": employees["DEMO-E002"].id,
                "employee_id": "DEMO-E002",
                "employee_name": employees["DEMO-E002"].name,
                "department": employees["DEMO-E002"].department,
                "hostname": "DEMO-NB-002",
                "location": "办公区域",
                "notes": DEMO_NOTE,
                "quantity": 1,
            },
            {
                "asset_tag": "ZS-MR26-900003",
                "category": "显示器",
                "brand": "Dell",
                "model": "P2422H",
                "serial_number": "DEMO-SN-MR-900003",
                "status": "闲置",
                "location": "IT库房",
                "notes": DEMO_NOTE,
                "quantity": 1,
            },
            {
                "asset_tag": "ZS-PC26-900004",
                "category": "台式机",
                "brand": "HP",
                "model": "ProDesk 400",
                "serial_number": "DEMO-SN-PC-900004",
                "status": "维修中",
                "location": "临时存放区",
                "notes": DEMO_NOTE,
                "quantity": 1,
            },
            {
                "asset_tag": "ZS-NB26-900005",
                "category": "笔记本电脑",
                "brand": "ASUS",
                "model": "ExpertBook B1",
                "serial_number": "DEMO-SN-NB-900005",
                "status": "报废",
                "employee_ref_id": employees["DEMO-E003"].id,
                "employee_id": "DEMO-E003",
                "employee_name": employees["DEMO-E003"].name,
                "department": employees["DEMO-E003"].department,
                "location": "IT库房",
                "notes": DEMO_NOTE,
                "quantity": 1,
            },
            {
                "asset_tag": "ZS-PD26-900006",
                "category": "平板电脑",
                "brand": "Apple",
                "model": "iPad Air",
                "serial_number": "DEMO-SN-PD-900006",
                "status": "闲置",
                "location": "IT库房",
                "notes": DEMO_NOTE,
                "quantity": 1,
            },
        ]
        for data in asset_data:
            _, created = get_or_create_asset(db, data)
            counts["assets"] += int(created)

        return_data = [
            {
                "asset_name": "演示资产-离职员工笔记本",
                "employee_id": "DEMO-E003",
                "employee_name": employees["DEMO-E003"].name,
                "department": employees["DEMO-E003"].department,
                "return_reason": "离职归还",
                "is_returned": False,
                "notes": f"{DEMO_NOTE} 待确认归还",
            },
            {
                "asset_name": "演示资产-已归还显示器",
                "employee_id": "DEMO-E002",
                "employee_name": employees["DEMO-E002"].name,
                "department": employees["DEMO-E002"].department,
                "return_reason": "设备更换",
                "is_returned": True,
                "return_date": models.china_now() - timedelta(days=7),
                "notes": f"{DEMO_NOTE} 已完成归还",
            },
        ]
        for data in return_data:
            _, created = get_or_create_return(db, data)
            counts["returns"] += int(created)

        admin = db.query(models.User).filter(models.User.username == "admin").one_or_none()
        if admin:
            db.add(models.OperationLog(
                user_id=admin.id,
                action="seed_demo_data",
                resource_type="demo_data",
                description=f"{DEMO_NOTE} 初始化演示数据：{counts}",
            ))
        db.commit()
        print("演示数据创建完成：")
        print(f"  员工: {counts['employees']} 条")
        print(f"  固定资产: {counts['assets']} 条")
        print(f"  仓储物料: {counts['warehouse']} 条")
        print(f"  归还记录: {counts['returns']} 条")
        print("重复运行将跳过已存在的演示数据，不会覆盖业务数据。")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()
