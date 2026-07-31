"""仓储两级分类目录与历史单层分类的可重复迁移。

运行方式：
    cd backend && python migrate_asset_category_and_issuance.py

脚本不创建固定资产卡；它只建立目录结构、写入不覆盖管理员值的种子，
并将存在唯一有效精确映射的库房物料转为两级分类。
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Final
import unicodedata

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

import models
from category_policy import IssuePolicy, allowed_issue_policies, normalize_asset_category
from warehouse_category_seed import (
    WarehouseCategorySeedResult,
    seed_warehouse_categories,
)


class WarehouseCategoryMigrationError(RuntimeError):
    """目录或历史分类迁移无法安全完成时抛出。"""


@dataclass(frozen=True)
class LegacyMappingSeed:
    legacy_category: str
    primary_code: str
    secondary_code: str


@dataclass(frozen=True)
class WarehouseMigrationSnapshot:
    record_count: int
    total_quantity: int
    available_quantity: int
    allocated_quantity: int
    legacy_fields_digest: str


@dataclass(frozen=True)
class WarehouseCategoryMigrationResult:
    seed_result: WarehouseCategorySeedResult
    mappings_created: int
    migrated_assets: int
    pending_assets: int
    skipped_assets: int
    before: WarehouseMigrationSnapshot
    after: WarehouseMigrationSnapshot


# 仅为语义明确的一对一历史名称建立映射；“显示设备”“计算机设备”等
# 汇总名称不会被猜测分类，会进入待处理报告。
DEFAULT_LEGACY_MAPPING_SEEDS: Final[tuple[LegacyMappingSeed, ...]] = (
    LegacyMappingSeed("台式机", "TERMINAL_EQUIPMENT", "TERMINAL_DESKTOP"),
    LegacyMappingSeed("笔记本电脑", "TERMINAL_EQUIPMENT", "TERMINAL_LAPTOP"),
    LegacyMappingSeed("平板电脑", "TERMINAL_EQUIPMENT", "TERMINAL_TABLET"),
    LegacyMappingSeed("显示器", "DISPLAY_AUDIO_VIDEO", "DISPLAY_MONITOR"),
    LegacyMappingSeed("扬声器", "DISPLAY_AUDIO_VIDEO", "DISPLAY_SPEAKER"),
    LegacyMappingSeed("摄像头", "DISPLAY_AUDIO_VIDEO", "DISPLAY_CAMERA"),
    LegacyMappingSeed("扩展坞", "DISPLAY_AUDIO_VIDEO", "DISPLAY_DOCK"),
    LegacyMappingSeed("有线鼠标", "INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_WIRED_MOUSE"),
    LegacyMappingSeed("无线鼠标", "INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_WIRELESS_MOUSE"),
    LegacyMappingSeed("有线键盘", "INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_WIRED_KEYBOARD"),
    LegacyMappingSeed("无线键盘", "INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_WIRELESS_KEYBOARD"),
    LegacyMappingSeed("有线键鼠", "INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_WIRED_KEYBOARD_MOUSE"),
    LegacyMappingSeed("无线键鼠", "INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_WIRELESS_KEYBOARD_MOUSE"),
    LegacyMappingSeed("鼠标垫", "INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_MOUSE_PAD"),
    LegacyMappingSeed("打印机", "INPUT_OFFICE_PERIPHERALS", "PERIPHERAL_PRINTER"),
    LegacyMappingSeed("硬盘", "STORAGE_REPAIR_PARTS", "PART_HARD_DISK"),
    LegacyMappingSeed("内存", "STORAGE_REPAIR_PARTS", "PART_MEMORY"),
    LegacyMappingSeed("电源适配器", "STORAGE_REPAIR_PARTS", "PART_POWER_ADAPTER"),
    LegacyMappingSeed("电池", "STORAGE_REPAIR_PARTS", "PART_BATTERY"),
    LegacyMappingSeed("散热风扇", "STORAGE_REPAIR_PARTS", "PART_FAN"),
    LegacyMappingSeed("网线", "CABLES_CONNECTORS", "CABLE_NETWORK"),
    LegacyMappingSeed("数据线", "CABLES_CONNECTORS", "CABLE_DATA"),
    LegacyMappingSeed("HDMI线", "CABLES_CONNECTORS", "CABLE_HDMI"),
    LegacyMappingSeed("DP线", "CABLES_CONNECTORS", "CABLE_DISPLAYPORT"),
    LegacyMappingSeed("VGA线", "CABLES_CONNECTORS", "CABLE_VGA"),
    LegacyMappingSeed("USB线", "CABLES_CONNECTORS", "CABLE_USB"),
    LegacyMappingSeed("电源线", "CABLES_CONNECTORS", "CABLE_POWER"),
    LegacyMappingSeed("转接头", "CABLES_CONNECTORS", "CONNECTOR_ADAPTER"),
    LegacyMappingSeed("交换机", "NETWORK_SERVER_ROOM_CONSUMABLES", "NETWORK_SWITCH"),
    LegacyMappingSeed("路由器", "NETWORK_SERVER_ROOM_CONSUMABLES", "NETWORK_ROUTER"),
    LegacyMappingSeed("无线AP", "NETWORK_SERVER_ROOM_CONSUMABLES", "NETWORK_WIRELESS_AP"),
    LegacyMappingSeed("光模块", "NETWORK_SERVER_ROOM_CONSUMABLES", "NETWORK_OPTICAL_MODULE"),
    LegacyMappingSeed("光纤跳线", "NETWORK_SERVER_ROOM_CONSUMABLES", "NETWORK_FIBER_PATCH_CORD"),
    LegacyMappingSeed("机柜配件", "NETWORK_SERVER_ROOM_CONSUMABLES", "NETWORK_RACK_ACCESSORY"),
    LegacyMappingSeed("螺丝刀", "IT_TOOLS_LOAN_ITEMS", "TOOL_SCREWDRIVER"),
    LegacyMappingSeed("压线钳", "IT_TOOLS_LOAN_ITEMS", "TOOL_CRIMPING"),
    LegacyMappingSeed("测线仪", "IT_TOOLS_LOAN_ITEMS", "TOOL_CABLE_TESTER"),
    LegacyMappingSeed("万用表", "IT_TOOLS_LOAN_ITEMS", "TOOL_MULTIMETER"),
    LegacyMappingSeed("工具箱", "IT_TOOLS_LOAN_ITEMS", "TOOL_KIT"),
    LegacyMappingSeed("标签纸", "OFFICE_GENERAL_CONSUMABLES", "CONSUMABLE_LABEL"),
    LegacyMappingSeed("碳粉", "OFFICE_GENERAL_CONSUMABLES", "CONSUMABLE_TONER"),
    LegacyMappingSeed("墨盒", "OFFICE_GENERAL_CONSUMABLES", "CONSUMABLE_INK"),
    LegacyMappingSeed("色带", "OFFICE_GENERAL_CONSUMABLES", "CONSUMABLE_RIBBON"),
    LegacyMappingSeed("清洁用品", "OFFICE_GENERAL_CONSUMABLES", "CONSUMABLE_CLEANING"),
)


WAREHOUSE_ASSET_COLUMN_DEFINITIONS: Final[dict[str, str]] = {
    "primary_category_id": "INTEGER",
    "secondary_category_id": "INTEGER",
    "classification_status": (
        "VARCHAR(32) NOT NULL DEFAULT 'PENDING_MIGRATION'"
    ),
    "legacy_category": "VARCHAR(255)",
    "material_kind": "VARCHAR(32)",
    "issue_policy": "VARCHAR(16)",
    "low_stock_threshold": "INTEGER NOT NULL DEFAULT 0",
}

LEGACY_SNAPSHOT_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "name",
    "category",
    "subcategory",
    "brand",
    "model",
    "receiver_name",
    "total_quantity",
    "available_quantity",
    "allocated_quantity",
    "minimum_stock",
    "location",
    "notes",
    "created_at",
    "updated_at",
)


def normalize_legacy_category(value: str | None) -> str:
    """按显式规则标准化历史单层分类，不进行包含或相似度匹配。"""
    normalized = unicodedata.normalize("NFKC", value or "").strip()
    if not normalized:
        return ""
    return normalize_asset_category(normalized).casefold()


def _ensure_schema(connection: Connection) -> set[str]:
    """建立目录表并为既有 warehouse_assets 补充分类字段。"""
    inspector = inspect(connection)
    if not inspector.has_table("warehouse_assets"):
        models.Base.metadata.create_all(bind=connection)
        return set(WAREHOUSE_ASSET_COLUMN_DEFINITIONS)

    catalog_tables = [
        models.WarehousePrimaryCategory.__table__,
        models.WarehouseSecondaryCategory.__table__,
        models.WarehouseCategoryMapping.__table__,
    ]
    models.Base.metadata.create_all(bind=connection, tables=catalog_tables)

    column_names = {
        column["name"]
        for column in inspect(connection).get_columns("warehouse_assets")
    }
    added_columns: set[str] = set()
    for name, definition in WAREHOUSE_ASSET_COLUMN_DEFINITIONS.items():
        if name not in column_names:
            connection.execute(
                text(f"ALTER TABLE warehouse_assets ADD COLUMN {name} {definition}")
            )
            added_columns.add(name)

    models.Base.metadata.create_all(
        bind=connection,
        tables=[models.WarehouseCategoryMigrationIssue.__table__],
    )
    return added_columns


def _migrate_new_threshold_field(db: Session, added_columns: set[str]) -> None:
    """新列首次加入时沿用旧 minimum_stock，避免静默丢失预警阈值。"""
    if "low_stock_threshold" not in added_columns:
        return
    db.execute(
        text(
            "UPDATE warehouse_assets "
            "SET low_stock_threshold = COALESCE(minimum_stock, 0)"
        )
    )


def _snapshot(db: Session) -> WarehouseMigrationSnapshot:
    assets = (
        db.query(models.WarehouseAsset)
        .order_by(models.WarehouseAsset.id)
        .all()
    )
    digest = sha256()
    for asset in assets:
        record = {
            field: getattr(asset, field)
            for field in LEGACY_SNAPSHOT_FIELDS
        }
        digest.update(
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    return WarehouseMigrationSnapshot(
        record_count=len(assets),
        total_quantity=sum(asset.total_quantity for asset in assets),
        available_quantity=sum(asset.available_quantity for asset in assets),
        allocated_quantity=sum(asset.allocated_quantity for asset in assets),
        legacy_fields_digest=digest.hexdigest(),
    )


def _assert_snapshot_preserved(
    before: WarehouseMigrationSnapshot,
    after: WarehouseMigrationSnapshot,
) -> None:
    if before != after:
        raise WarehouseCategoryMigrationError(
            "仓储分类迁移核对失败：记录数、库存数量或非分类字段发生变化"
        )


def _preserve_legacy_updated_at(asset: models.WarehouseAsset) -> None:
    """将迁移产生的 UPDATE 与历史更新时间隔离，避免修改非分类元数据。"""
    # SQLAlchemy 对任意 UPDATE 自动填充 Column.onupdate。显式标脏并保留原值，
    # 使迁移只改变分类相关列，迁移后摘要才能覆盖全部历史非分类字段。
    flag_modified(asset, "updated_at")


def _seed_legacy_mappings(db: Session) -> int:
    """仅插入缺失的明确映射，绝不覆盖管理员维护的已有映射。"""
    primary_by_code = {
        item.code: item
        for item in db.query(models.WarehousePrimaryCategory).all()
    }
    secondary_by_key = {
        (item.primary_category.code, item.code): item
        for item in db.query(models.WarehouseSecondaryCategory).all()
    }
    planned: dict[str, LegacyMappingSeed] = {}
    for seed in DEFAULT_LEGACY_MAPPING_SEEDS:
        normalized = normalize_legacy_category(seed.legacy_category)
        previous = planned.setdefault(normalized, seed)
        if previous != seed:
            raise WarehouseCategoryMigrationError(
                f"历史分类“{seed.legacy_category}”存在相互冲突的默认映射"
            )

    created = 0
    for normalized, seed in planned.items():
        existing = (
            db.query(models.WarehouseCategoryMapping)
            .filter(
                models.WarehouseCategoryMapping.normalized_legacy_category
                == normalized
            )
            .all()
        )
        if existing:
            continue
        primary = primary_by_code.get(seed.primary_code)
        secondary = secondary_by_key.get((seed.primary_code, seed.secondary_code))
        if primary is None or secondary is None:
            raise WarehouseCategoryMigrationError(
                f"默认映射“{seed.legacy_category}”引用了不存在的分类种子"
            )
        db.add(
            models.WarehouseCategoryMapping(
                normalized_legacy_category=normalized,
                primary_category_id=primary.id,
                secondary_category_id=secondary.id,
                is_active=True,
            )
        )
        created += 1
    if created:
        db.flush()
    return created



def _legacy_category_for(asset: models.WarehouseAsset) -> str:
    return (asset.legacy_category or asset.category or "").strip()


def _existing_issue(
    db: Session,
    warehouse_asset_id: int,
) -> models.WarehouseCategoryMigrationIssue | None:
    return (
        db.query(models.WarehouseCategoryMigrationIssue)
        .filter(
            models.WarehouseCategoryMigrationIssue.warehouse_asset_id
            == warehouse_asset_id
        )
        .order_by(models.WarehouseCategoryMigrationIssue.id)
        .first()
    )


def _target_issue_reason(
    mapping: models.WarehouseCategoryMapping,
) -> tuple[str | None, str | None]:
    primary = mapping.primary_category
    secondary = mapping.secondary_category
    if primary is None or secondary is None:
        return "INVALID_PAIR", "映射目标分类不存在或一级/二级关系无效"
    if not mapping.is_active or not primary.is_active or not secondary.is_active:
        return "INACTIVE_TARGET", "映射目标或其分类目录已停用"
    if secondary.primary_category_id != primary.id:
        return "INVALID_PAIR", "映射目标二级分类不隶属于指定一级分类"
    return None, None


def _default_issue_policy(
    asset: models.WarehouseAsset,
    primary: models.WarehousePrimaryCategory,
) -> str:
    """为历史空策略补齐数据库活动记录所需的兼容值，保留已有有效值。"""
    valid_policies = {policy.value for policy in IssuePolicy}
    if asset.issue_policy in valid_policies:
        return asset.issue_policy

    allowed = allowed_issue_policies(primary.code, asset.name)
    if len(allowed) == 1:
        return next(iter(allowed)).value
    return IssuePolicy.CONSUMABLE.value


def _mark_pending(
    db: Session,
    asset: models.WarehouseAsset,
    *,
    original_category: str,
    normalized_category: str,
    reason_code: str,
    reason_detail: str,
) -> None:
    _preserve_legacy_updated_at(asset)
    asset.primary_category_id = None
    asset.secondary_category_id = None
    asset.classification_status = "PENDING_MIGRATION"
    # 分类字段为空白时用该占位值满足待处理记录的可追溯约束；原 category 不会改变。
    asset.legacy_category = original_category or "（空分类）"
    db.add(
        models.WarehouseCategoryMigrationIssue(
            warehouse_asset_id=asset.id,
            original_category=original_category,
            normalized_category=normalized_category or None,
            reason_code=reason_code,
            reason_detail=reason_detail,
            status="OPEN",
        )
    )


def _migrate_warehouse_assets(db: Session) -> tuple[int, int, int]:
    migrated = 0
    pending = 0
    skipped = 0
    assets = (
        db.query(models.WarehouseAsset)
        .order_by(models.WarehouseAsset.id)
        .all()
    )
    for asset in assets:
        if asset.classification_status == "ACTIVE":
            skipped += 1
            continue
        if _existing_issue(db, asset.id) is not None:
            # 已存在开放或已解决报告的记录只可由后续的受控解决流程处理。
            skipped += 1
            continue

        original_category = _legacy_category_for(asset)
        normalized_category = normalize_legacy_category(original_category)
        mappings = (
            db.query(models.WarehouseCategoryMapping)
            .filter(
                models.WarehouseCategoryMapping.normalized_legacy_category
                == normalized_category
            )
            .order_by(models.WarehouseCategoryMapping.id)
            .all()
        )
        if not mappings:
            _mark_pending(
                db,
                asset,
                original_category=original_category,
                normalized_category=normalized_category,
                reason_code="UNMAPPED",
                reason_detail="未找到该历史单层分类的唯一精确映射",
            )
            pending += 1
            continue
        if len(mappings) != 1:
            _mark_pending(
                db,
                asset,
                original_category=original_category,
                normalized_category=normalized_category,
                reason_code="AMBIGUOUS",
                reason_detail="该历史单层分类存在多个精确映射候选",
            )
            pending += 1
            continue

        mapping = mappings[0]
        reason_code, reason_detail = _target_issue_reason(mapping)
        if reason_code is not None:
            _mark_pending(
                db,
                asset,
                original_category=original_category,
                normalized_category=normalized_category,
                reason_code=reason_code,
                reason_detail=reason_detail or "映射目标无效",
            )
            pending += 1
            continue

        primary = mapping.primary_category
        _preserve_legacy_updated_at(asset)
        asset.primary_category_id = mapping.primary_category_id
        asset.secondary_category_id = mapping.secondary_category_id
        asset.legacy_category = original_category
        asset.issue_policy = _default_issue_policy(asset, primary)
        asset.classification_status = "ACTIVE"
        migrated += 1
    return migrated, pending, skipped


def migrate_warehouse_categories(db: Session) -> WarehouseCategoryMigrationResult:
    """在调用方事务中执行迁移；本函数不提交，便于隔离测试和部署编排。"""
    added_columns = _ensure_schema(db.connection())
    _migrate_new_threshold_field(db, added_columns)
    seed_result = seed_warehouse_categories(db)
    mappings_created = _seed_legacy_mappings(db)
    before = _snapshot(db)
    migrated, pending, skipped = _migrate_warehouse_assets(db)
    db.flush()
    after = _snapshot(db)
    _assert_snapshot_preserved(before, after)
    return WarehouseCategoryMigrationResult(
        seed_result=seed_result,
        mappings_created=mappings_created,
        migrated_assets=migrated,
        pending_assets=pending,
        skipped_assets=skipped,
        before=before,
        after=after,
    )


def run_migration() -> WarehouseCategoryMigrationResult:
    """以独立事务运行迁移；任一建表、种子、写入或核对失败都会回滚数据。"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        result = migrate_warehouse_categories(db)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    result = run_migration()
    print(
        "仓储分类迁移完成："
        f"新增一级 {result.seed_result.primary_created} 个，"
        f"新增二级 {result.seed_result.secondary_created} 个，"
        f"新增映射 {result.mappings_created} 条，"
        f"已迁移 {result.migrated_assets} 条，"
        f"待处理 {result.pending_assets} 条，"
        f"跳过 {result.skipped_assets} 条"
    )
