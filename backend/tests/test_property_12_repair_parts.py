"""维修备件用途关联与库存原子性的属性测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import models
from material_issuance_service import MaterialIssuanceError, issue_repair_part
from transaction_audit import AuditLogPersistenceError


REPAIR_PART_CASES = st.sampled_from((
    "valid_asset",
    "valid_repair_order",
    "invalid_association",
    "missing_association",
    "non_positive_quantity",
    "insufficient_stock",
    "persistence_failure",
))


def _enable_sqlite_foreign_keys(
    dbapi_connection: Any,
    _connection_record: Any,
) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _new_session() -> tuple[Session, Any]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    return session, engine


def _create_context(
    db: Session,
    *,
    token: int,
    available_quantity: int,
) -> tuple[models.User, models.WarehouseAsset, models.Asset]:
    """创建有效维修备件、经办人和可维修的固定资产关联。"""
    operator = models.User(
        username=f"property12-operator-{token}",
        hashed_password="not-used-by-property-test",
        full_name="Property 12 经办人",
        is_active=True,
    )
    repair_primary = models.WarehousePrimaryCategory(
        code="STORAGE_REPAIR_PARTS",
        name=f"P12 存储与维修备件 {token}",
        is_active=True,
    )
    terminal_primary = models.WarehousePrimaryCategory(
        code="TERMINAL_EQUIPMENT",
        name=f"P12 终端设备库存 {token}",
        is_active=True,
    )
    db.add_all((operator, repair_primary, terminal_primary))
    db.flush()
    repair_secondary = models.WarehouseSecondaryCategory(
        primary_category_id=repair_primary.id,
        code=f"P12-REPAIR-{token}",
        name=f"P12 维修备件 {token}",
        is_active=True,
    )
    terminal_secondary = models.WarehouseSecondaryCategory(
        primary_category_id=terminal_primary.id,
        code=f"P12-TERMINAL-{token}",
        name=f"P12 终端库存 {token}",
        is_active=True,
    )
    db.add_all((repair_secondary, terminal_secondary))
    db.flush()
    material = models.WarehouseAsset(
        name=f"P12 硬盘 {token}",
        category=repair_primary.name,
        subcategory=repair_secondary.name,
        total_quantity=available_quantity,
        available_quantity=available_quantity,
        allocated_quantity=0,
        minimum_stock=0,
        low_stock_threshold=0,
        primary_category_id=repair_primary.id,
        secondary_category_id=repair_secondary.id,
        classification_status="ACTIVE",
        material_kind="NON_FIXED",
        issue_policy="CONSUMABLE",
    )
    terminal_inventory = models.WarehouseAsset(
        name=f"P12 目标资产终端库存 {token}",
        category=terminal_primary.name,
        subcategory=terminal_secondary.name,
        total_quantity=1,
        available_quantity=1,
        allocated_quantity=0,
        minimum_stock=0,
        low_stock_threshold=0,
        primary_category_id=terminal_primary.id,
        secondary_category_id=terminal_secondary.id,
        classification_status="ACTIVE",
        material_kind="NON_FIXED",
        issue_policy="CONSUMABLE",
    )
    db.add_all((material, terminal_inventory))
    db.flush()
    asset = models.Asset(
        asset_tag=f"P12-ASSET-{token}",
        category="台式机",
        status="维修中",
        fixed_asset_number=f"P12-FA-{token}",
        serial_number=f"P12-SERIAL-{token}",
        asset_category_code="PC",
        inbound_source="MANUAL",
        terminal_inventory_id=terminal_inventory.id,
        is_deleted=False,
    )
    db.add(asset)
    db.flush()
    db.add(models.FixedAssetInbound(
        asset_id=asset.id,
        terminal_inventory_id=terminal_inventory.id,
        source="MANUAL",
        operator_id=operator.id,
        inbound_at=datetime(2025, 1, 1, 8, 0),
    ))
    db.commit()
    return operator, material, asset


def _state(db: Session, material_id: int) -> tuple[Any, ...]:
    """获取失败命令必须完整保持不变的库存、记录与审计状态。"""
    db.expire_all()
    material = db.get(models.WarehouseAsset, material_id)
    assert material is not None
    material_issues = tuple(
        (item.id, item.quantity, item.unreturned_quantity, item.consumed_completed)
        for item in db.query(models.MaterialIssue)
        .filter(models.MaterialIssue.warehouse_asset_id == material_id)
        .order_by(models.MaterialIssue.id)
    )
    repair_issues = tuple(
        (item.id, item.material_issue_id, item.target_asset_id,
         item.repair_order_ref, item.disk_serial_number)
        for item in db.query(models.RepairPartIssue).order_by(models.RepairPartIssue.id)
    )
    audits = tuple(
        (item.id, item.action, item.resource_type, item.resource_id)
        for item in db.query(models.OperationLog).order_by(models.OperationLog.id)
    )
    return (
        (material.total_quantity, material.available_quantity, material.allocated_quantity),
        material_issues,
        repair_issues,
        audits,
    )


def _assert_audit_flush_failure(db: Session, command: Callable[[], Any]) -> None:
    """在审计落库时注入故障，验证同一事务内的业务记录和扣库均会回滚。"""
    original_flush = db.flush

    def fail_audit_flush(*args: Any, **kwargs: Any) -> Any:
        if any(isinstance(item, models.OperationLog) for item in db.new):
            raise RuntimeError("injected repair part audit persistence failure")
        return original_flush(*args, **kwargs)

    db.flush = fail_audit_flush  # type: ignore[method-assign]
    try:
        with pytest.raises(AuditLogPersistenceError, match="审计日志保存失败"):
            command()
    finally:
        db.flush = original_flush  # type: ignore[method-assign]


# Feature: asset-category-and-issuance-management, Property 12: 维修备件用途关联与扣库原子性
# **Validates: Requirements 8.1, 8.2, 8.3, 8.5**
@settings(max_examples=100, deadline=None)
@given(
    case=REPAIR_PART_CASES,
    token=st.integers(min_value=1, max_value=1_000_000),
    available_quantity=st.integers(min_value=1, max_value=100),
    requested_quantity=st.integers(min_value=1, max_value=100),
    non_positive_quantity=st.integers(min_value=-100, max_value=0),
    issued_offset_minutes=st.integers(min_value=0, max_value=525_600),
    include_disk_serial=st.booleans(),
)
def test_property_12_repair_part_association_and_inventory_atomicity(
    case: str,
    token: int,
    available_quantity: int,
    requested_quantity: int,
    non_positive_quantity: int,
    issued_offset_minutes: int,
    include_disk_serial: bool,
) -> None:
    """有效关联精确扣库；无效关联、数量、库存或持久化故障没有任何副作用。"""
    db, engine = _new_session()
    try:
        operator, material, target_asset = _create_context(
            db, token=token, available_quantity=available_quantity
        )
        quantity = min(requested_quantity, available_quantity)
        target_asset_id: int | None = target_asset.id
        repair_order_ref: str | None = None
        disk_serial_number = f"P12-DISK-{token}" if include_disk_serial else None
        issued_at = datetime(2025, 1, 2, 8, 0) + timedelta(
            minutes=issued_offset_minutes
        )

        if case == "valid_repair_order":
            target_asset_id = None
            repair_order_ref = f"P12-ORDER-{token}"
        elif case == "invalid_association":
            target_asset_id = target_asset.id + 100_000
        elif case == "missing_association":
            target_asset_id = None
        elif case == "non_positive_quantity":
            quantity = non_positive_quantity
        elif case == "insufficient_stock":
            quantity = available_quantity + 1

        if case in {"valid_asset", "valid_repair_order"}:
            result = issue_repair_part(
                db,
                warehouse_asset_id=material.id,
                quantity=quantity,
                issued_at=issued_at,
                operator_id=operator.id,
                target_asset_id=target_asset_id,
                repair_order_ref=repair_order_ref,
                disk_serial_number=disk_serial_number,
            )
            db.expire_all()
            persisted_material = db.get(models.WarehouseAsset, material.id)
            issue = db.get(models.MaterialIssue, result.issue.id)
            repair_issue = db.get(models.RepairPartIssue, result.specialized_issue.id)
            assert persisted_material is not None
            assert issue is not None
            assert repair_issue is not None
            assert issue.warehouse_asset_id == material.id
            assert issue.record_type == "CONSUMABLE"
            assert issue.issue_policy == "CONSUMABLE"
            assert issue.quantity == quantity
            assert issue.unreturned_quantity == 0
            assert issue.consumed_completed is True
            assert issue.issued_at == issued_at
            assert issue.operator_id == operator.id
            assert repair_issue.material_issue_id == issue.id
            assert repair_issue.target_asset_id == target_asset_id
            assert repair_issue.repair_order_ref == repair_order_ref
            assert repair_issue.disk_serial_number == disk_serial_number
            assert persisted_material.total_quantity == available_quantity
            assert persisted_material.available_quantity == available_quantity - quantity
            assert persisted_material.allocated_quantity == quantity
            assert result.audit_log.action == "issue_repair_part"
            assert result.audit_log.resource_id == repair_issue.id
            return

        before = _state(db, material.id)
        command = lambda: issue_repair_part(
            db,
            warehouse_asset_id=material.id,
            quantity=quantity,
            issued_at=issued_at,
            operator_id=operator.id,
            target_asset_id=target_asset_id,
            repair_order_ref=repair_order_ref,
            disk_serial_number=disk_serial_number,
        )
        if case == "persistence_failure":
            _assert_audit_flush_failure(db, command)
        else:
            with pytest.raises(MaterialIssuanceError):
                command()
        assert _state(db, material.id) == before
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
