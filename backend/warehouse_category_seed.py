"""仓储两级分类目录的内置种子。

种子仅以稳定代码识别记录：已存在的记录绝不覆盖名称、排序或启停等管理员维护值。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlalchemy.orm import Session

import models
from category_policy import PRIMARY_CATEGORY_SEEDS


class WarehouseCategorySeedError(ValueError):
    """目录中已有与内置稳定代码冲突的记录时抛出。"""


@dataclass(frozen=True)
class PrimaryCategorySeed:
    code: str
    name: str
    sort_order: int


@dataclass(frozen=True)
class SecondaryCategorySeed:
    primary_code: str
    code: str
    name: str
    sort_order: int


@dataclass(frozen=True)
class WarehouseCategorySeedResult:
    primary_created: int
    secondary_created: int


PRIMARY_CATEGORY_SEED_DATA: Final[tuple[PrimaryCategorySeed, ...]] = tuple(
    PrimaryCategorySeed(code=code, name=name, sort_order=index * 10)
    for index, (code, name) in enumerate(PRIMARY_CATEGORY_SEEDS, start=1)
)


SECONDARY_CATEGORY_SEED_DATA: Final[tuple[SecondaryCategorySeed, ...]] = (
    # 终端设备库存
    SecondaryCategorySeed("TERMINAL_EQUIPMENT", "TERMINAL_DESKTOP", "台式机", 10),
    SecondaryCategorySeed("TERMINAL_EQUIPMENT", "TERMINAL_LAPTOP", "笔记本电脑", 20),
    SecondaryCategorySeed("TERMINAL_EQUIPMENT", "TERMINAL_TABLET", "平板电脑", 30),
    # 显示与音视频设备
    SecondaryCategorySeed("DISPLAY_AUDIO_VIDEO", "DISPLAY_MONITOR", "显示器", 10),
    SecondaryCategorySeed("DISPLAY_AUDIO_VIDEO", "DISPLAY_SPEAKER", "扬声器", 20),
    SecondaryCategorySeed("DISPLAY_AUDIO_VIDEO", "DISPLAY_CAMERA", "摄像头", 30),
    SecondaryCategorySeed("DISPLAY_AUDIO_VIDEO", "DISPLAY_DOCK", "扩展坞", 40),
    # 输入与办公外设
    SecondaryCategorySeed("INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_WIRED_MOUSE", "有线鼠标", 10),
    SecondaryCategorySeed("INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_WIRELESS_MOUSE", "无线鼠标", 20),
    SecondaryCategorySeed("INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_WIRED_KEYBOARD", "有线键盘", 30),
    SecondaryCategorySeed("INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_WIRELESS_KEYBOARD", "无线键盘", 40),
    SecondaryCategorySeed("INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_WIRED_KEYBOARD_MOUSE", "有线键鼠", 50),
    SecondaryCategorySeed("INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_WIRELESS_KEYBOARD_MOUSE", "无线键鼠", 60),
    SecondaryCategorySeed("INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_MOUSE_PAD", "鼠标垫", 70),
    SecondaryCategorySeed("INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_PRINTER", "打印机", 80),
    # 存储与维修备件
    SecondaryCategorySeed("STORAGE_REPAIR_PARTS", "PART_HARD_DISK", "硬盘", 10),
    SecondaryCategorySeed("STORAGE_REPAIR_PARTS", "PART_MEMORY", "内存", 20),
    SecondaryCategorySeed("STORAGE_REPAIR_PARTS", "PART_POWER_ADAPTER", "电源适配器", 30),
    SecondaryCategorySeed("STORAGE_REPAIR_PARTS", "PART_BATTERY", "电池", 40),
    SecondaryCategorySeed("STORAGE_REPAIR_PARTS", "PART_FAN", "散热风扇", 50),
    # 线缆与连接配件
    SecondaryCategorySeed("CABLES_CONNECTORS", "CABLE_NETWORK", "网线", 10),
    SecondaryCategorySeed("CABLES_CONNECTORS", "CABLE_DATA", "数据线", 20),
    SecondaryCategorySeed("CABLES_CONNECTORS", "CABLE_HDMI", "HDMI线", 30),
    SecondaryCategorySeed("CABLES_CONNECTORS", "CABLE_DISPLAYPORT", "DP线", 40),
    SecondaryCategorySeed("CABLES_CONNECTORS", "CABLE_VGA", "VGA线", 50),
    SecondaryCategorySeed("CABLES_CONNECTORS", "CABLE_USB", "USB线", 60),
    SecondaryCategorySeed("CABLES_CONNECTORS", "CABLE_POWER", "电源线", 70),
    SecondaryCategorySeed("CABLES_CONNECTORS", "CONNECTOR_ADAPTER", "转接头", 80),
    # 网络与机房耗材
    SecondaryCategorySeed("NETWORK_SERVER_ROOM_CONSUMABLES", "NETWORK_SWITCH", "交换机", 10),
    SecondaryCategorySeed("NETWORK_SERVER_ROOM_CONSUMABLES", "NETWORK_ROUTER", "路由器", 20),
    SecondaryCategorySeed("NETWORK_SERVER_ROOM_CONSUMABLES", "NETWORK_WIRELESS_AP", "无线AP", 30),
    SecondaryCategorySeed("NETWORK_SERVER_ROOM_CONSUMABLES", "NETWORK_OPTICAL_MODULE", "光模块", 40),
    SecondaryCategorySeed("NETWORK_SERVER_ROOM_CONSUMABLES", "NETWORK_FIBER_PATCH_CORD", "光纤跳线", 50),
    SecondaryCategorySeed("NETWORK_SERVER_ROOM_CONSUMABLES", "NETWORK_RACK_ACCESSORY", "机柜配件", 60),
    # IT 工具与借用物品
    SecondaryCategorySeed("IT_TOOLS_LOAN_ITEMS", "TOOL_SCREWDRIVER", "螺丝刀", 10),
    SecondaryCategorySeed("IT_TOOLS_LOAN_ITEMS", "TOOL_CRIMPING", "压线钳", 20),
    SecondaryCategorySeed("IT_TOOLS_LOAN_ITEMS", "TOOL_CABLE_TESTER", "测线仪", 30),
    SecondaryCategorySeed("IT_TOOLS_LOAN_ITEMS", "TOOL_MULTIMETER", "万用表", 40),
    SecondaryCategorySeed("IT_TOOLS_LOAN_ITEMS", "TOOL_KIT", "工具箱", 50),
    # 办公与通用耗材
    SecondaryCategorySeed("OFFICE_GENERAL_CONSUMABLES", "CONSUMABLE_LABEL", "标签纸", 10),
    SecondaryCategorySeed("OFFICE_GENERAL_CONSUMABLES", "CONSUMABLE_TONER", "碳粉", 20),
    SecondaryCategorySeed("OFFICE_GENERAL_CONSUMABLES", "CONSUMABLE_INK", "墨盒", 30),
    SecondaryCategorySeed("OFFICE_GENERAL_CONSUMABLES", "CONSUMABLE_RIBBON", "色带", 40),
    SecondaryCategorySeed("OFFICE_GENERAL_CONSUMABLES", "CONSUMABLE_CLEANING", "清洁用品", 50),
)


def _validate_seed_definitions() -> None:
    primary_codes = {seed.code for seed in PRIMARY_CATEGORY_SEED_DATA}
    if len(primary_codes) != len(PRIMARY_CATEGORY_SEED_DATA):
        raise WarehouseCategorySeedError("一级分类种子代码重复")

    secondary_codes = {seed.code for seed in SECONDARY_CATEGORY_SEED_DATA}
    if len(secondary_codes) != len(SECONDARY_CATEGORY_SEED_DATA):
        raise WarehouseCategorySeedError("二级分类种子代码重复")

    unknown_parents = {
        seed.primary_code
        for seed in SECONDARY_CATEGORY_SEED_DATA
        if seed.primary_code not in primary_codes
    }
    if unknown_parents:
        raise WarehouseCategorySeedError(
            f"二级分类种子引用了不存在的一级分类代码：{', '.join(sorted(unknown_parents))}"
        )


def _check_existing_conflicts(db: Session) -> None:
    """先识别冲突，避免调用方在未开启事务时得到半套目录。"""
    for seed in PRIMARY_CATEGORY_SEED_DATA:
        existing = (
            db.query(models.WarehousePrimaryCategory)
            .filter(models.WarehousePrimaryCategory.code == seed.code)
            .one_or_none()
        )
        if existing is None:
            name_owner = (
                db.query(models.WarehousePrimaryCategory)
                .filter(models.WarehousePrimaryCategory.name == seed.name)
                .one_or_none()
            )
            if name_owner is not None:
                raise WarehouseCategorySeedError(
                    f"一级分类名称“{seed.name}”已由代码“{name_owner.code}”使用"
                )

    for seed in SECONDARY_CATEGORY_SEED_DATA:
        existing_matches = (
            db.query(models.WarehouseSecondaryCategory)
            .filter(models.WarehouseSecondaryCategory.code == seed.code)
            .all()
        )
        if len(existing_matches) > 1:
            raise WarehouseCategorySeedError(
                f"二级分类稳定代码“{seed.code}”存在多个记录，无法安全写入种子"
            )
        if existing_matches:
            existing = existing_matches[0]
            if existing.primary_category.code != seed.primary_code:
                raise WarehouseCategorySeedError(
                    f"二级分类代码“{seed.code}”已属于一级分类“{existing.primary_category.code}”，不会改变其从属关系"
                )
            continue

        parent = (
            db.query(models.WarehousePrimaryCategory)
            .filter(models.WarehousePrimaryCategory.code == seed.primary_code)
            .one_or_none()
        )
        if parent is not None:
            name_owner = (
                db.query(models.WarehouseSecondaryCategory)
                .filter(
                    models.WarehouseSecondaryCategory.primary_category_id == parent.id,
                    models.WarehouseSecondaryCategory.name == seed.name,
                )
                .one_or_none()
            )
            if name_owner is not None:
                raise WarehouseCategorySeedError(
                    f"二级分类名称“{seed.name}”已由代码“{name_owner.code}”使用"
                )


def seed_warehouse_categories(db: Session) -> WarehouseCategorySeedResult:
    """写入缺失的内置目录项，但不提交、不覆盖已有记录。"""
    _validate_seed_definitions()
    _check_existing_conflicts(db)

    primary_by_code = {
        category.code: category
        for category in db.query(models.WarehousePrimaryCategory).all()
    }
    primary_created = 0
    for seed in PRIMARY_CATEGORY_SEED_DATA:
        if seed.code not in primary_by_code:
            category = models.WarehousePrimaryCategory(
                code=seed.code,
                name=seed.name,
                sort_order=seed.sort_order,
                is_active=True,
            )
            db.add(category)
            primary_by_code[seed.code] = category
            primary_created += 1

    if primary_created:
        db.flush()

    secondary_created = 0
    for seed in SECONDARY_CATEGORY_SEED_DATA:
        existing = (
            db.query(models.WarehouseSecondaryCategory)
            .filter(models.WarehouseSecondaryCategory.code == seed.code)
            .one_or_none()
        )
        if existing is not None:
            continue

        db.add(
            models.WarehouseSecondaryCategory(
                primary_category_id=primary_by_code[seed.primary_code].id,
                code=seed.code,
                name=seed.name,
                sort_order=seed.sort_order,
                is_active=True,
            )
        )
        secondary_created += 1

    if secondary_created:
        db.flush()

    return WarehouseCategorySeedResult(
        primary_created=primary_created,
        secondary_created=secondary_created,
    )


def initialize_warehouse_categories() -> WarehouseCategorySeedResult:
    """以独立事务执行种子，供命令行或部署流程调用。"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        result = seed_warehouse_categories(db)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    result = initialize_warehouse_categories()
    print(
        "仓储分类种子完成："
        f"新增一级分类 {result.primary_created} 个，"
        f"新增二级分类 {result.secondary_created} 个"
    )
