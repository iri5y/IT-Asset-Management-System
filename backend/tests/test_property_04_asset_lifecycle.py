"""合法固定资产生命周期原子转换的属性测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import models
from asset_lifecycle_service import (
    complete_repair,
    controlled_inbound,
    issue_fixed_asset,
    return_fixed_asset,
    send_for_repair,
    transfer_fixed_asset,
)
from category_policy import AssetCategoryCode, FixedAssetStatus


def _enable_sqlite_foreign_keys(
    dbapi_connection: Any, _connection_record: Any
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
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)(), engine


def _create_operator(db: Session, token: int) -> models.User:
    operator = models.User(
        username=f"property4-{token}",
        hashed_password="not-used-by-property-test",
        full_name="Property 4 经办人",
        is_active=True,
    )
    db.add(operator)
    db.commit()
    return operator


def _create_terminal_inventory(db: Session, token: int) -> models.WarehouseAsset:
    primary = models.WarehousePrimaryCategory(
        code="TERMINAL_EQUIPMENT",
        name=f"P4 终端设备库存 {token}",
        is_active=True,
    )
    db.add(primary)
    db.flush()
    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id,
        code=f"P4-TERMINAL-{token}",
        name=f"P4 终端二级 {token}",
        is_active=True,
    )
    db.add(secondary)
    db.flush()
    inventory = models.WarehouseAsset(
        name=f"P4 终端库存行 {token}",
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


def _inventory_quantities(db: Session, inventory_id: int) -> tuple[int, int, int]:
    inventory = db.get(models.WarehouseAsset, inventory_id)
    assert inventory is not None
    quantities = (
        inventory.total_quantity,
        inventory.available_quantity,
        inventory.allocated_quantity,
    )
    assert quantities[0] == quantities[1] + quantities[2]
    return quantities


def _binding(name: str, employee_id: str, department: str, issued_at: datetime) -> dict[str, Any]:
    return {
        "employee_name": name,
        "employee_id": employee_id,
        "department": department,
        "issue_date": issued_at,
    }


def _event_binding(binding: dict[str, Any] | None) -> dict[str, Any] | None:
    if binding is None:
        return None
    return {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in binding.items()
    }


def _assert_asset_state(
    db: Session,
    asset_id: int,
    *,
    status: FixedAssetStatus,
    binding: dict[str, Any] | None,
) -> None:
    asset = db.get(models.Asset, asset_id)
    assert asset is not None
    assert asset.status == status.value
    actual_binding = {
        "employee_name": asset.employee_name,
        "employee_id": asset.employee_id,
        "department": asset.department,
        "issue_date": asset.issue_date,
    }
    if binding is None:
        assert all(value is None for value in actual_binding.values())
    else:
        assert actual_binding == binding


def _assert_event(
    result: Any,
    *,
    event_type: str,
    asset_id: int,
    operator_id: int,
    inventory_id: int,
    previous_binding: dict[str, Any] | None,
    new_binding: dict[str, Any] | None,
) -> None:
    lifecycle_event = result.lifecycle_event
    assert lifecycle_event is not None
    assert lifecycle_event.event_type == event_type
    assert lifecycle_event.asset_id == asset_id
    assert lifecycle_event.operator_id == operator_id
    assert lifecycle_event.previous_binding == _event_binding(previous_binding)
    assert lifecycle_event.new_binding == _event_binding(new_binding)
    assert lifecycle_event.event_metadata == {"terminal_inventory_id": inventory_id}


# Feature: asset-category-and-issuance-management, Property 4: 合法固定资产生命周期原子转换
# **Validates: Requirements 2.6, 3.1, 4.1, 4.2, 4.3, 4.4**
@settings(max_examples=100, deadline=None)
@given(
    category=st.sampled_from(tuple(AssetCategoryCode)),
    source=st.sampled_from(("SCAN", "MANUAL")),
    token=st.integers(min_value=1, max_value=1_000_000),
    issue_day=st.integers(min_value=0, max_value=365),
    repair_completes_with_new_binding=st.booleans(),
)
def test_property_4_valid_fixed_asset_lifecycle_transitions_are_atomic(
    category: AssetCategoryCode,
    source: str,
    token: int,
    issue_day: int,
    repair_completes_with_new_binding: bool,
) -> None:
    """合法受控资产依次发放、转移、送修、完成维修和归还时保持状态、绑定和库存一致。"""
    db, engine = _new_session()
    try:
        operator = _create_operator(db, token)
        inventory = _create_terminal_inventory(db, token)
        issued_at = datetime(2025, 1, 1) + timedelta(days=issue_day)
        first_binding = _binding("领用人甲", f"P4-A-{token}", "信息部", issued_at)
        transferred_binding = _binding(
            "领用人乙", f"P4-B-{token}", "研发部", issued_at + timedelta(days=1)
        )
        repair_binding = _binding(
            "领用人丙", f"P4-C-{token}", "财务部", issued_at + timedelta(days=2)
        )

        inbound = controlled_inbound(
            db,
            operator_id=operator.id,
            terminal_inventory_id=inventory.id,
            source=source,
            asset_category_code=category,
            fixed_asset_number=f"P4-FA-{token}",
            serial_number=f"P4-SN-{token}",
        )
        asset_id = inbound.asset.id
        assert _inventory_quantities(db, inventory.id) == (1, 1, 0)
        _assert_asset_state(
            db, asset_id, status=FixedAssetStatus.IDLE, binding=None
        )

        first_issue = issue_fixed_asset(
            db,
            asset_id=asset_id,
            operator_id=operator.id,
            recipient_name=first_binding["employee_name"],
            recipient_employee_id=first_binding["employee_id"],
            recipient_department=first_binding["department"],
            issued_at=first_binding["issue_date"],
        )
        assert first_issue.issuance is not None
        assert first_issue.issuance.asset_id == asset_id
        assert first_issue.issuance.terminal_inventory_id == inventory.id
        assert _inventory_quantities(db, inventory.id) == (1, 0, 1)
        _assert_asset_state(
            db, asset_id, status=FixedAssetStatus.IN_USE, binding=first_binding
        )
        _assert_event(
            first_issue,
            event_type="ISSUE",
            asset_id=asset_id,
            operator_id=operator.id,
            inventory_id=inventory.id,
            previous_binding=None,
            new_binding=first_binding,
        )

        transfer = transfer_fixed_asset(
            db,
            asset_id=asset_id,
            operator_id=operator.id,
            recipient_name=transferred_binding["employee_name"],
            recipient_employee_id=transferred_binding["employee_id"],
            recipient_department=transferred_binding["department"],
            issued_at=transferred_binding["issue_date"],
        )
        assert _inventory_quantities(db, inventory.id) == (1, 0, 1)
        _assert_asset_state(
            db,
            asset_id,
            status=FixedAssetStatus.IN_USE,
            binding=transferred_binding,
        )
        _assert_event(
            transfer,
            event_type="TRANSFER",
            asset_id=asset_id,
            operator_id=operator.id,
            inventory_id=inventory.id,
            previous_binding=first_binding,
            new_binding=transferred_binding,
        )

        repair = send_for_repair(db, asset_id=asset_id, operator_id=operator.id)
        assert _inventory_quantities(db, inventory.id) == (1, 0, 1)
        _assert_asset_state(
            db, asset_id, status=FixedAssetStatus.IN_REPAIR, binding=None
        )
        _assert_event(
            repair,
            event_type="REPAIR_SENT",
            asset_id=asset_id,
            operator_id=operator.id,
            inventory_id=inventory.id,
            previous_binding=transferred_binding,
            new_binding=None,
        )

        if repair_completes_with_new_binding:
            completion = complete_repair(
                db,
                asset_id=asset_id,
                operator_id=operator.id,
                recipient_name=repair_binding["employee_name"],
                recipient_employee_id=repair_binding["employee_id"],
                recipient_department=repair_binding["department"],
                issued_at=repair_binding["issue_date"],
            )
            final_binding = repair_binding
            expected_after_completion = (1, 0, 1)
        else:
            completion = complete_repair(
                db, asset_id=asset_id, operator_id=operator.id
            )
            final_binding = None
            expected_after_completion = (1, 1, 0)

        assert _inventory_quantities(db, inventory.id) == expected_after_completion
        _assert_asset_state(
            db,
            asset_id,
            status=(
                FixedAssetStatus.IN_USE
                if final_binding is not None
                else FixedAssetStatus.IDLE
            ),
            binding=final_binding,
        )
        _assert_event(
            completion,
            event_type="REPAIR_COMPLETED",
            asset_id=asset_id,
            operator_id=operator.id,
            inventory_id=inventory.id,
            previous_binding=None,
            new_binding=final_binding,
        )

        if final_binding is None:
            final_issue = issue_fixed_asset(
                db,
                asset_id=asset_id,
                operator_id=operator.id,
                recipient_name=transferred_binding["employee_name"],
                recipient_employee_id=transferred_binding["employee_id"],
                recipient_department=transferred_binding["department"],
                issued_at=transferred_binding["issue_date"],
            )
            final_binding = transferred_binding
            assert _inventory_quantities(db, inventory.id) == (1, 0, 1)
            _assert_event(
                final_issue,
                event_type="ISSUE",
                asset_id=asset_id,
                operator_id=operator.id,
                inventory_id=inventory.id,
                previous_binding=None,
                new_binding=final_binding,
            )

        returned = return_fixed_asset(
            db,
            asset_id=asset_id,
            operator_id=operator.id,
            recipient_name=final_binding["employee_name"],
            recipient_employee_id=final_binding["employee_id"],
            recipient_department=final_binding["department"],
        )
        assert _inventory_quantities(db, inventory.id) == (1, 1, 0)
        _assert_asset_state(
            db, asset_id, status=FixedAssetStatus.IDLE, binding=None
        )
        _assert_event(
            returned,
            event_type="RETURN",
            asset_id=asset_id,
            operator_id=operator.id,
            inventory_id=inventory.id,
            previous_binding=final_binding,
            new_binding=None,
        )

        events = (
            db.query(models.AssetLifecycleEvent)
            .filter(models.AssetLifecycleEvent.asset_id == asset_id)
            .order_by(models.AssetLifecycleEvent.id)
            .all()
        )
        expected_event_types = ["ISSUE", "TRANSFER", "REPAIR_SENT", "REPAIR_COMPLETED"]
        if not repair_completes_with_new_binding:
            expected_event_types.append("ISSUE")
        expected_event_types.append("RETURN")
        assert [item.event_type for item in events] == expected_event_types
        assert db.query(models.FixedAssetIssuance).filter(
            models.FixedAssetIssuance.asset_id == asset_id
        ).count() == (1 if repair_completes_with_new_binding else 2)
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
