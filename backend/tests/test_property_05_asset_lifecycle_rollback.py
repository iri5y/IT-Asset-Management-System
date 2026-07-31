"""非法固定资产生命周期操作完整回滚的属性测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import models
from asset_lifecycle_service import (
    AssetLifecycleError,
    complete_repair,
    controlled_inbound,
    issue_fixed_asset,
    return_fixed_asset,
    send_for_repair,
    transfer_fixed_asset,
)
from transaction_audit import AuditLogPersistenceError


INVALID_LIFECYCLE_CASES = st.sampled_from(
    (
        "invalid_asset",
        "illegal_source_state",
        "mismatched_return_binding",
        "same_transfer_recipient",
        "invalid_repair_completion_binding",
        "insufficient_inventory",
        "invalid_issuance_binding",
        "persistence_failure",
    )
)


def _enable_sqlite_foreign_keys(connection: Any, _record: Any) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _new_session() -> tuple[Session, Any]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)(), engine


def _create_context(
    db: Session, token: int, category: str
) -> tuple[models.User, models.WarehouseAsset, models.Asset]:
    operator = models.User(
        username=f"property5-{token}",
        hashed_password="not-used-by-property-test",
        full_name="Property 5 经办人",
        is_active=True,
    )
    primary = models.WarehousePrimaryCategory(
        code="TERMINAL_EQUIPMENT",
        name=f"P5 终端设备库存 {token}",
        is_active=True,
    )
    db.add_all((operator, primary))
    db.flush()
    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id,
        code=f"P5-TERMINAL-{token}",
        name=f"P5 终端二级 {token}",
        is_active=True,
    )
    db.add(secondary)
    db.flush()
    inventory = models.WarehouseAsset(
        name=f"P5 终端库存行 {token}",
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
    inbound = controlled_inbound(
        db,
        operator_id=operator.id,
        terminal_inventory_id=inventory.id,
        source="SCAN",
        asset_category_code=category,
        fixed_asset_number=f"P5-FA-{token}",
        serial_number=f"P5-SN-{token}",
    )
    return operator, inventory, inbound.asset


def _binding(token: int, day: int) -> dict[str, Any]:
    return {
        "recipient_name": "当前领用人",
        "recipient_employee_id": f"P5-E-{token}",
        "recipient_department": "信息部",
        "issued_at": datetime(2025, 1, 1) + timedelta(days=day),
    }


def _issue_for_context(
    db: Session,
    asset_id: int,
    operator_id: int,
    binding: dict[str, Any],
) -> None:
    issue_fixed_asset(db, asset_id=asset_id, operator_id=operator_id, **binding)


def _snapshot(
    db: Session, asset_id: int, inventory_id: int
) -> tuple[Any, ...]:
    """覆盖指定的资产状态、绑定、库存及所有相关发放和生命周期记录。"""
    asset = db.get(models.Asset, asset_id)
    inventory = db.get(models.WarehouseAsset, inventory_id)
    assert asset is not None
    assert inventory is not None
    events = tuple(
        (
            item.id,
            item.event_type,
            item.previous_binding,
            item.new_binding,
            item.operator_id,
            item.event_metadata,
        )
        for item in db.query(models.AssetLifecycleEvent)
        .filter(models.AssetLifecycleEvent.asset_id == asset_id)
        .order_by(models.AssetLifecycleEvent.id)
    )
    issuances = tuple(
        (
            item.id,
            item.terminal_inventory_id,
            item.recipient_name,
            item.recipient_employee_id,
            item.recipient_department,
            item.issued_at,
            item.operator_id,
        )
        for item in db.query(models.FixedAssetIssuance)
        .filter(models.FixedAssetIssuance.asset_id == asset_id)
        .order_by(models.FixedAssetIssuance.id)
    )
    return (
        (
            asset.status,
            asset.employee_name,
            asset.employee_id,
            asset.department,
            asset.issue_date,
            asset.terminal_inventory_id,
        ),
        (
            inventory.total_quantity,
            inventory.available_quantity,
            inventory.allocated_quantity,
        ),
        events,
        issuances,
        db.query(models.AssetLog).filter(models.AssetLog.asset_id == asset_id).count(),
        db.query(models.WarehouseAssetLog)
        .filter(models.WarehouseAssetLog.asset_id == inventory_id)
        .count(),
        db.query(models.OperationLog).count(),
    )


def _run_with_persistence_failure(
    db: Session,
    command: Callable[[], Any],
) -> None:
    """只让审计日志的 flush 失败，保留真实命令前的全部领域写入路径。"""
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


# Feature: asset-category-and-issuance-management, Property 5: 非法固定资产生命周期操作完全回滚
# **Validates: Requirements 3.3, 4.5**
@settings(max_examples=100, deadline=None)
@given(
    case=INVALID_LIFECYCLE_CASES,
    category=st.sampled_from(("PC", "NB", "PD")),
    token=st.integers(min_value=1, max_value=1_000_000),
    day=st.integers(min_value=0, max_value=365),
)
def test_property_5_invalid_lifecycle_operations_fully_roll_back(
    case: str,
    category: str,
    token: int,
    day: int,
) -> None:
    """任意非法生命周期命令或持久化故障都不得改变可观察的领域状态。"""
    db, engine = _new_session()
    try:
        operator, inventory, asset = _create_context(db, token, category)
        binding = _binding(token, day)
        asset_id, inventory_id = asset.id, inventory.id

        if case == "invalid_asset":
            before = _snapshot(db, asset_id, inventory_id)
            with pytest.raises(AssetLifecycleError):
                send_for_repair(
                    db, asset_id=asset_id + 100_000, operator_id=operator.id
                )
        elif case == "illegal_source_state":
            before = _snapshot(db, asset_id, inventory_id)
            with pytest.raises(AssetLifecycleError):
                return_fixed_asset(
                    db,
                    asset_id=asset_id,
                    operator_id=operator.id,
                    recipient_name=binding["recipient_name"],
                    recipient_employee_id=binding["recipient_employee_id"],
                    recipient_department=binding["recipient_department"],
                )
        elif case == "mismatched_return_binding":
            _issue_for_context(db, asset_id, operator.id, binding)
            before = _snapshot(db, asset_id, inventory_id)
            with pytest.raises(AssetLifecycleError):
                return_fixed_asset(
                    db,
                    asset_id=asset_id,
                    operator_id=operator.id,
                    recipient_name="不匹配的领用人",
                    recipient_employee_id=binding["recipient_employee_id"],
                    recipient_department=binding["recipient_department"],
                )
        elif case == "same_transfer_recipient":
            _issue_for_context(db, asset_id, operator.id, binding)
            before = _snapshot(db, asset_id, inventory_id)
            with pytest.raises(AssetLifecycleError):
                transfer_fixed_asset(
                    db,
                    asset_id=asset_id,
                    operator_id=operator.id,
                    recipient_name="同一工号的其他姓名",
                    recipient_employee_id=binding["recipient_employee_id"],
                    recipient_department="研发部",
                    issued_at=binding["issued_at"] + timedelta(days=1),
                )
        elif case == "invalid_repair_completion_binding":
            send_for_repair(db, asset_id=asset_id, operator_id=operator.id)
            before = _snapshot(db, asset_id, inventory_id)
            with pytest.raises(AssetLifecycleError):
                complete_repair(
                    db,
                    asset_id=asset_id,
                    operator_id=operator.id,
                    recipient_name="只有部分新绑定",
                )
        elif case == "insufficient_inventory":
            inventory.total_quantity = 0
            inventory.available_quantity = 0
            inventory.allocated_quantity = 0
            db.commit()
            before = _snapshot(db, asset_id, inventory_id)
            with pytest.raises(AssetLifecycleError):
                _issue_for_context(db, asset_id, operator.id, binding)
        elif case == "invalid_issuance_binding":
            before = _snapshot(db, asset_id, inventory_id)
            with pytest.raises(AssetLifecycleError):
                issue_fixed_asset(
                    db,
                    asset_id=asset_id,
                    operator_id=operator.id,
                    recipient_name=" ",
                    recipient_employee_id=binding["recipient_employee_id"],
                    recipient_department=binding["recipient_department"],
                    issued_at=binding["issued_at"],
                )
        else:
            before = _snapshot(db, asset_id, inventory_id)
            _run_with_persistence_failure(
                db,
                lambda: _issue_for_context(db, asset_id, operator.id, binding),
            )

        assert _snapshot(db, asset_id, inventory_id) == before
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
