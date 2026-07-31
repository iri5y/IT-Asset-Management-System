"""业务及分类目录写操作审计同成同败的属性测试。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import models
from asset_lifecycle_service import controlled_inbound
from transaction_audit import AuditLogPersistenceError
from warehouse_category_service import (
    create_primary_category,
    create_secondary_category,
    migrate_secondary_references,
    update_primary_category,
    update_secondary_category,
)
from warehouse_material_service import create_material, update_material


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _new_session() -> tuple[Session, Any]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)(), engine


def _create_operator(db: Session, token: int) -> models.User:
    operator = models.User(
        username=f"property16-{token}",
        hashed_password="not-used-by-property-test",
        full_name="Property 16 经办人",
        is_active=True,
    )
    db.add(operator)
    db.commit()
    return operator


def _audit_payload(log: models.OperationLog, field: str) -> dict[str, Any]:
    raw_value = getattr(log, field)
    assert raw_value is not None
    payload = json.loads(raw_value)
    assert payload["snapshot_at"] == log.created_at.isoformat()
    assert "values" in payload
    return payload


def _assert_audit(
    audit: models.OperationLog,
    *,
    operator_id: int,
    level: str | None = None,
    parent_id: int | None = None,
) -> None:
    """所有成功写入都须保留经办人、UTC+8 时间和前后快照。"""
    assert audit.user_id == operator_id
    assert audit.created_at.tzinfo is None
    assert abs((models.china_now() - audit.created_at).total_seconds()) < 5
    before = _audit_payload(audit, "old_value")
    after = _audit_payload(audit, "new_value")
    assert before["snapshot_at"] == after["snapshot_at"]
    if level is not None:
        related = after["related_records"]
        assert related["category_level"] == level
        assert related["category_id"] == audit.resource_id
        assert related["primary_category_id"] == parent_id


def _category_state(db: Session) -> tuple[tuple[Any, ...], ...]:
    primary = tuple(
        (item.id, item.code, item.name, item.sort_order, item.is_active)
        for item in db.query(models.WarehousePrimaryCategory)
        .order_by(models.WarehousePrimaryCategory.id)
        .all()
    )
    secondary = tuple(
        (
            item.id,
            item.primary_category_id,
            item.code,
            item.name,
            item.sort_order,
            item.is_active,
        )
        for item in db.query(models.WarehouseSecondaryCategory)
        .order_by(models.WarehouseSecondaryCategory.id)
        .all()
    )
    return primary, secondary


def _material_state(db: Session) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            item.id,
            item.name,
            item.primary_category_id,
            item.secondary_category_id,
            item.category,
            item.subcategory,
            item.available_quantity,
            item.allocated_quantity,
            item.total_quantity,
            item.location,
        )
        for item in db.query(models.WarehouseAsset)
        .order_by(models.WarehouseAsset.id)
        .all()
    )


def _audit_failure_rolls_back(
    db: Session,
    command: Callable[[], Any],
    state: Callable[[], Any],
) -> None:
    """仅让包含 OperationLog 的 flush 失败，验证真实事务会撤销所有前置写入。"""
    before = state()
    original_flush = db.flush

    def fail_audit_flush(*args: Any, **kwargs: Any) -> Any:
        if any(isinstance(item, models.OperationLog) for item in db.new):
            raise RuntimeError("injected audit persistence failure")
        return original_flush(*args, **kwargs)

    db.flush = fail_audit_flush  # type: ignore[method-assign]
    try:
        with pytest.raises(AuditLogPersistenceError, match="审计日志保存失败"):
            command()
    finally:
        db.flush = original_flush  # type: ignore[method-assign]
    assert state() == before


def _create_catalog(
    db: Session,
    operator_id: int,
    token: int,
    sort_order: int,
) -> dict[str, Any]:
    """创建可用于目录维护、引用迁移、物料和受控入库的最小受控目录。"""
    source_primary, _ = create_primary_category(
        db,
        code="INPUT_OFFICE_PERIPHERALS",
        name=f"P16 输入外设 {token}",
        sort_order=sort_order,
        operator_id=operator_id,
    )
    target_primary, _ = create_primary_category(
        db,
        code="OFFICE_GENERAL_CONSUMABLES",
        name=f"P16 办公耗材 {token}",
        sort_order=sort_order + 1,
        operator_id=operator_id,
    )
    terminal_primary, _ = create_primary_category(
        db,
        code="TERMINAL_EQUIPMENT",
        name=f"P16 终端库存 {token}",
        sort_order=sort_order + 2,
        operator_id=operator_id,
    )
    idle_primary, _ = create_primary_category(
        db,
        code="DISPLAY_AUDIO_VIDEO",
        name=f"P16 独立分类 {token}",
        sort_order=sort_order + 3,
        operator_id=operator_id,
    )
    source_secondary, _ = create_secondary_category(
        db,
        primary_category_id=source_primary.id,
        code=f"P16-SOURCE-{token}",
        name=f"P16 源二级 {token}",
        sort_order=sort_order,
        operator_id=operator_id,
    )
    target_secondary, _ = create_secondary_category(
        db,
        primary_category_id=target_primary.id,
        code=f"P16-TARGET-{token}",
        name=f"P16 目标二级 {token}",
        sort_order=sort_order,
        operator_id=operator_id,
    )
    terminal_secondary, _ = create_secondary_category(
        db,
        primary_category_id=terminal_primary.id,
        code=f"P16-TERMINAL-{token}",
        name=f"P16 终端二级 {token}",
        sort_order=sort_order,
        operator_id=operator_id,
    )
    return {
        "source_primary": source_primary,
        "target_primary": target_primary,
        "terminal_primary": terminal_primary,
        "idle_primary": idle_primary,
        "source_secondary": source_secondary,
        "target_secondary": target_secondary,
        "terminal_secondary": terminal_secondary,
    }


def _create_terminal_inventory(
    db: Session,
    catalog: dict[str, Any],
    token: int,
) -> models.WarehouseAsset:
    primary = catalog["terminal_primary"]
    secondary = catalog["terminal_secondary"]
    inventory = models.WarehouseAsset(
        name=f"P16 终端库存行 {token}",
        category=primary.name,
        subcategory=secondary.name,
        total_quantity=0,
        available_quantity=0,
        allocated_quantity=0,
        minimum_stock=0,
        low_stock_threshold=0,
        primary_category_id=primary.id,
        secondary_category_id=secondary.id,
        classification_status="ACTIVE",
        issue_policy="CONSUMABLE",
    )
    db.add(inventory)
    db.commit()
    return inventory


# Feature: asset-category-and-issuance-management, Property 16: 所有业务及分类目录写操作与审计同成同败
# Validates: Requirements 12.2, 12.3
@settings(max_examples=100, deadline=None)
@given(
    token=st.integers(min_value=1, max_value=1_000_000),
    sort_order=st.integers(min_value=0, max_value=100),
    quantity=st.integers(min_value=0, max_value=100),
)
def test_property_16_successful_category_and_business_writes_have_complete_audit(
    token: int,
    sort_order: int,
    quantity: int,
) -> None:
    """目录各维护命令和代表性物料/入库命令均与完整审计一起提交。"""
    db, engine = _new_session()
    try:
        operator = _create_operator(db, token)
        catalog = _create_catalog(db, operator.id, token, sort_order)
        for key in ("source_primary", "target_primary", "terminal_primary", "idle_primary"):
            category = catalog[key]
            audit = (
                db.query(models.OperationLog)
                .filter(
                    models.OperationLog.action == "create_warehouse_primary_category",
                    models.OperationLog.resource_id == category.id,
                )
                .one()
            )
            _assert_audit(audit, operator_id=operator.id, level="PRIMARY", parent_id=None)
        for key in ("source_secondary", "target_secondary", "terminal_secondary"):
            category = catalog[key]
            audit = (
                db.query(models.OperationLog)
                .filter(
                    models.OperationLog.action == "create_warehouse_secondary_category",
                    models.OperationLog.resource_id == category.id,
                )
                .one()
            )
            _assert_audit(
                audit,
                operator_id=operator.id,
                level="SECONDARY",
                parent_id=category.primary_category_id,
            )

        source_primary = catalog["source_primary"]
        source_primary, audit = update_primary_category(
            db,
            source_primary.id,
            changes={"name": f"P16 已改名一级 {token}"},
            operator_id=operator.id,
        )
        _assert_audit(audit, operator_id=operator.id, level="PRIMARY", parent_id=None)
        source_primary, audit = update_primary_category(
            db,
            source_primary.id,
            changes={"sort_order": sort_order + 10},
            operator_id=operator.id,
        )
        _assert_audit(audit, operator_id=operator.id, level="PRIMARY", parent_id=None)

        source_secondary = catalog["source_secondary"]
        source_secondary, audit = update_secondary_category(
            db,
            source_secondary.id,
            changes={"name": f"P16 已改名二级 {token}"},
            operator_id=operator.id,
        )
        _assert_audit(
            audit,
            operator_id=operator.id,
            level="SECONDARY",
            parent_id=source_primary.id,
        )
        source_secondary, audit = update_secondary_category(
            db,
            source_secondary.id,
            changes={"sort_order": sort_order + 11},
            operator_id=operator.id,
        )
        _assert_audit(
            audit,
            operator_id=operator.id,
            level="SECONDARY",
            parent_id=source_primary.id,
        )
        source_secondary, audit = update_secondary_category(
            db,
            source_secondary.id,
            changes={"is_active": False},
            operator_id=operator.id,
        )
        _assert_audit(
            audit,
            operator_id=operator.id,
            level="SECONDARY",
            parent_id=source_primary.id,
        )
        source_secondary, audit = update_secondary_category(
            db,
            source_secondary.id,
            changes={"is_active": True},
            operator_id=operator.id,
        )
        _assert_audit(
            audit,
            operator_id=operator.id,
            level="SECONDARY",
            parent_id=source_primary.id,
        )

        idle_primary = catalog["idle_primary"]
        idle_primary, audit = update_primary_category(
            db,
            idle_primary.id,
            changes={"is_active": False},
            operator_id=operator.id,
        )
        _assert_audit(audit, operator_id=operator.id, level="PRIMARY", parent_id=None)
        idle_primary, audit = update_primary_category(
            db,
            idle_primary.id,
            changes={"is_active": True},
            operator_id=operator.id,
        )
        _assert_audit(audit, operator_id=operator.id, level="PRIMARY", parent_id=None)

        material, audit = create_material(
            db,
            payload={
                "name": "鼠标",
                "available_quantity": quantity,
                "allocated_quantity": 0,
                "low_stock_threshold": sort_order,
                "location": "P16-A-01",
                "primary_category_id": source_primary.id,
                "secondary_category_id": source_secondary.id,
                "issue_policy": "CONSUMABLE",
            },
            operator_id=operator.id,
        )
        _assert_audit(audit, operator_id=operator.id)
        assert _audit_payload(audit, "new_value")["related_records"] == {
            "primary_category_id": source_primary.id,
            "secondary_category_id": source_secondary.id,
            "inbound_type": "NON_FIXED_PURCHASE",
        }
        material, audit = update_material(
            db,
            material.id,
            changes={"location": "P16-B-02"},
            operator_id=operator.id,
        )
        _assert_audit(audit, operator_id=operator.id)

        migrated_count, audit = migrate_secondary_references(
            db,
            source_secondary.id,
            target_primary_category_id=catalog["target_primary"].id,
            target_secondary_category_id=catalog["target_secondary"].id,
            operator_id=operator.id,
        )
        assert migrated_count == 1
        _assert_audit(
            audit,
            operator_id=operator.id,
            level="SECONDARY",
            parent_id=source_primary.id,
        )
        db.refresh(material)
        assert (
            material.primary_category_id,
            material.secondary_category_id,
        ) == (catalog["target_primary"].id, catalog["target_secondary"].id)

        inventory = _create_terminal_inventory(db, catalog, token)
        result = controlled_inbound(
            db,
            operator_id=operator.id,
            terminal_inventory_id=inventory.id,
            source="MANUAL",
            asset_category_code="PC",
            fixed_asset_number=f"P16-FA-{token}",
            serial_number=f"P16-SN-{token}",
        )
        _assert_audit(result.audit_log, operator_id=operator.id)
        inbound_related = _audit_payload(result.audit_log, "new_value")["related_records"]
        assert inbound_related["asset_id"] == result.asset.id
        assert inbound_related["terminal_inventory_id"] == inventory.id
        assert inbound_related["fixed_asset_inbound_id"] == result.inbound.id
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()


def test_property_16_audit_persistence_failure_rolls_back_each_write_command() -> None:
    """注入审计失败后，目录、物料、引用迁移及固定资产入库均不留下部分结果。"""
    db, engine = _new_session()
    try:
        operator = _create_operator(db, 9_160)
        catalog = _create_catalog(db, operator.id, 9_160, 1)
        source_primary = catalog["source_primary"]
        source_secondary = catalog["source_secondary"]
        target_primary = catalog["target_primary"]
        target_secondary = catalog["target_secondary"]
        idle_primary = catalog["idle_primary"]

        catalog_and_log_state = lambda: (
            _category_state(db),
            db.query(models.OperationLog).count(),
        )
        _audit_failure_rolls_back(
            db,
            lambda: create_primary_category(
                db,
                code="NETWORK_SERVER_ROOM_CONSUMABLES",
                name="P16 审计失败一级",
                sort_order=99,
                operator_id=operator.id,
            ),
            catalog_and_log_state,
        )
        _audit_failure_rolls_back(
            db,
            lambda: update_primary_category(
                db,
                source_primary.id,
                changes={"name": "P16 不应保存的一级改名"},
                operator_id=operator.id,
            ),
            catalog_and_log_state,
        )
        _audit_failure_rolls_back(
            db,
            lambda: update_primary_category(
                db,
                source_primary.id,
                changes={"sort_order": 99},
                operator_id=operator.id,
            ),
            catalog_and_log_state,
        )
        _audit_failure_rolls_back(
            db,
            lambda: update_primary_category(
                db,
                idle_primary.id,
                changes={"is_active": False},
                operator_id=operator.id,
            ),
            catalog_and_log_state,
        )
        _audit_failure_rolls_back(
            db,
            lambda: create_secondary_category(
                db,
                primary_category_id=source_primary.id,
                code="P16-AUDIT-FAIL-CHILD",
                name="P16 审计失败二级",
                sort_order=99,
                operator_id=operator.id,
            ),
            catalog_and_log_state,
        )
        _audit_failure_rolls_back(
            db,
            lambda: update_secondary_category(
                db,
                source_secondary.id,
                changes={"name": "P16 不应保存的二级改名"},
                operator_id=operator.id,
            ),
            catalog_and_log_state,
        )
        _audit_failure_rolls_back(
            db,
            lambda: update_secondary_category(
                db,
                source_secondary.id,
                changes={"sort_order": 99},
                operator_id=operator.id,
            ),
            catalog_and_log_state,
        )
        _audit_failure_rolls_back(
            db,
            lambda: update_secondary_category(
                db,
                source_secondary.id,
                changes={"is_active": False},
                operator_id=operator.id,
            ),
            catalog_and_log_state,
        )

        material_and_log_state = lambda: (
            _material_state(db),
            db.query(models.WarehouseAssetLog).count(),
            db.query(models.OperationLog).count(),
        )
        material_payload = {
            "name": "鼠标",
            "available_quantity": 5,
            "allocated_quantity": 0,
            "low_stock_threshold": 1,
            "location": "P16-A-01",
            "primary_category_id": source_primary.id,
            "secondary_category_id": source_secondary.id,
            "issue_policy": "CONSUMABLE",
        }
        _audit_failure_rolls_back(
            db,
            lambda: create_material(
                db,
                payload=material_payload,
                operator_id=operator.id,
            ),
            material_and_log_state,
        )
        material, _ = create_material(
            db,
            payload=material_payload,
            operator_id=operator.id,
        )
        _audit_failure_rolls_back(
            db,
            lambda: update_material(
                db,
                material.id,
                changes={"location": "P16 不应保存的位置"},
                operator_id=operator.id,
            ),
            material_and_log_state,
        )
        _audit_failure_rolls_back(
            db,
            lambda: migrate_secondary_references(
                db,
                source_secondary.id,
                target_primary_category_id=target_primary.id,
                target_secondary_category_id=target_secondary.id,
                operator_id=operator.id,
            ),
            material_and_log_state,
        )

        inventory = _create_terminal_inventory(db, catalog, 9_160)

        def inbound_state() -> tuple[Any, ...]:
            persisted_inventory = db.get(models.WarehouseAsset, inventory.id)
            assert persisted_inventory is not None
            return (
                (
                    persisted_inventory.total_quantity,
                    persisted_inventory.available_quantity,
                    persisted_inventory.allocated_quantity,
                ),
                db.query(models.Asset).count(),
                db.query(models.FixedAssetInbound).count(),
                db.query(models.AssetLog).count(),
                db.query(models.WarehouseAssetLog).count(),
                db.query(models.OperationLog).count(),
            )

        _audit_failure_rolls_back(
            db,
            lambda: controlled_inbound(
                db,
                operator_id=operator.id,
                terminal_inventory_id=inventory.id,
                source="SCAN",
                asset_category_code="NB",
                fixed_asset_number="P16-AUDIT-FAIL-ASSET",
                serial_number="P16-AUDIT-FAIL-SERIAL",
            ),
            inbound_state,
        )
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
