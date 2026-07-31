"""非法或非受控固定资产建卡无副作用的属性测试。"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import models
from asset_lifecycle_service import AssetLifecycleError, controlled_inbound, issue_fixed_asset
from category_policy import NON_FIXED_ASSET_CARD_ERROR
from schemas import FixedAssetStatusChangeRequest
from warehouse_material_service import WarehouseMaterialServiceError, create_material


CASES = st.sampled_from((
    "non_fixed_category", "uncontrolled_source", "blank_asset_number",
    "blank_serial_number", "duplicate_asset_number", "duplicate_serial_number",
    "missing_inventory", "wrong_inventory", "uncontrolled_issue",
    "invalid_status", "fixed_asset_via_warehouse", "non_fixed_purchase",
))


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


def _create_operator(db: Session, token: int) -> models.User:
    operator = models.User(
        username=f"property3-{token}", hashed_password="not-used-by-property-test",
        full_name="Property 3 经办人", is_active=True,
    )
    db.add(operator)
    db.commit()
    return operator


def _create_inventory(
    db: Session, token: int, *, primary_code: str = "TERMINAL_EQUIPMENT"
) -> models.WarehouseAsset:
    primary = models.WarehousePrimaryCategory(
        code=primary_code, name=f"P3 一级分类 {primary_code} {token}", is_active=True,
    )
    db.add(primary)
    db.flush()
    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id, code=f"P3-S-{primary_code}-{token}",
        name=f"P3 二级分类 {token}", is_active=True,
    )
    db.add(secondary)
    db.flush()
    inventory = models.WarehouseAsset(
        name=f"P3 库存行 {primary_code} {token}", category=primary.name,
        subcategory=secondary.name, total_quantity=0, available_quantity=0,
        allocated_quantity=0, minimum_stock=0, low_stock_threshold=0,
        primary_category_id=primary.id, secondary_category_id=secondary.id,
        classification_status="ACTIVE", issue_policy="CONSUMABLE",
    )
    db.add(inventory)
    db.commit()
    return inventory


def _fixed_asset_state(db: Session, inventory_id: int) -> tuple[Any, ...]:
    inventory = db.get(models.WarehouseAsset, inventory_id)
    assert inventory is not None
    assets = tuple(
        (asset.id, asset.asset_tag, asset.fixed_asset_number, asset.serial_number,
         asset.asset_category_code, asset.inbound_source, asset.status,
         asset.terminal_inventory_id)
        for asset in db.query(models.Asset).order_by(models.Asset.id)
    )
    inbounds = tuple(
        (row.id, row.asset_id, row.terminal_inventory_id, row.source, row.operator_id)
        for row in db.query(models.FixedAssetInbound).order_by(models.FixedAssetInbound.id)
    )
    return (
        assets, inbounds,
        (inventory.total_quantity, inventory.available_quantity, inventory.allocated_quantity),
        db.query(models.FixedAssetIssuance).count(),
        db.query(models.AssetLifecycleEvent).count(),
        db.query(models.AssetLog).count(), db.query(models.WarehouseAssetLog).count(),
        db.query(models.OperationLog).count(),
    )


# Feature: asset-category-and-issuance-management, Property 3: 非法或非受控固定资产建卡无副作用
# Validates: Requirements 1.4, 2.4, 2.5, 2.8, 3.2, 5.2, 5.4
@settings(max_examples=100, deadline=None)
@given(case=CASES, token=st.integers(min_value=1, max_value=1_000_000))
def test_property_3_invalid_or_uncontrolled_inbound_has_no_fixed_asset_side_effects(
    case: str, token: int,
) -> None:
    """非法建卡、库房绕过和无受控证明发放均不改变固定资产领域状态。"""
    db, engine = _new_session()
    try:
        operator = _create_operator(db, token)
        inventory = _create_inventory(db, token)
        target_inventory_id = inventory.id
        fixed_asset_number, serial_number = f"P3-FA-{token}", f"P3-SN-{token}"

        if case in {"duplicate_asset_number", "duplicate_serial_number"}:
            seed = controlled_inbound(
                db, operator_id=operator.id, terminal_inventory_id=inventory.id,
                source="SCAN", asset_category_code="PC",
                fixed_asset_number=f"P3-SEED-FA-{token}",
                serial_number=f"P3-SEED-SN-{token}",
            )
            if case == "duplicate_asset_number":
                fixed_asset_number = seed.asset.fixed_asset_number
            else:
                serial_number = seed.asset.serial_number
        elif case == "wrong_inventory":
            target_inventory_id = _create_inventory(
                db, token, primary_code="DISPLAY_AUDIO_VIDEO"
            ).id
        elif case == "uncontrolled_issue":
            db.add(models.Asset(
                asset_tag=f"P3-LEGACY-{token}", category="台式机", status="闲置",
            ))
            db.commit()

        before = _fixed_asset_state(db, target_inventory_id)
        if case == "non_fixed_purchase":
            before_assets, before_inbounds = before[0], before[1]
            material, _ = create_material(
                db, operator_id=operator.id,
                payload={
                    "name": "无线鼠标", "available_quantity": token % 20,
                    "allocated_quantity": 0, "low_stock_threshold": 0,
                    "primary_category_id": inventory.primary_category_id,
                    "secondary_category_id": inventory.secondary_category_id,
                    "issue_policy": "CONSUMABLE",
                },
            )
            assert material.name == "无线鼠标"
            assert db.query(models.Asset).count() == len(before_assets)
            assert tuple(
                (row.id, row.asset_id, row.terminal_inventory_id, row.source, row.operator_id)
                for row in db.query(models.FixedAssetInbound).order_by(models.FixedAssetInbound.id)
            ) == before_inbounds
            return

        if case == "invalid_status":
            with pytest.raises(ValidationError):
                FixedAssetStatusChangeRequest(status="库存中")
        elif case == "uncontrolled_issue":
            legacy_asset = db.query(models.Asset).one()
            with pytest.raises(AssetLifecycleError, match="请改入低值领用或仓储物料"):
                issue_fixed_asset(
                    db, asset_id=legacy_asset.id, operator_id=operator.id,
                    recipient_name="领用人", recipient_employee_id="P3-E",
                    recipient_department="信息部", issued_at=models.china_now(),
                )
        elif case == "fixed_asset_via_warehouse":
            with pytest.raises(WarehouseMaterialServiceError, match="受控固定资产入库"):
                create_material(
                    db, operator_id=operator.id,
                    payload={
                        "name": "台式机", "available_quantity": 1,
                        "allocated_quantity": 0, "low_stock_threshold": 0,
                        "primary_category_id": inventory.primary_category_id,
                        "secondary_category_id": inventory.secondary_category_id,
                        "issue_policy": "CONSUMABLE",
                    },
                )
        else:
            category, source = "PC", "SCAN"
            if case == "non_fixed_category":
                category = "鼠标"
            elif case == "uncontrolled_source":
                source = "WAREHOUSE"
            elif case == "blank_asset_number":
                fixed_asset_number = " \t"
            elif case == "blank_serial_number":
                serial_number = "\n"
            elif case == "missing_inventory":
                target_inventory_id = 999_999
            with pytest.raises(AssetLifecycleError) as error:
                controlled_inbound(
                    db, operator_id=operator.id, terminal_inventory_id=target_inventory_id,
                    source=source, asset_category_code=category,
                    fixed_asset_number=fixed_asset_number, serial_number=serial_number,
                )
            if case == "non_fixed_category":
                assert NON_FIXED_ASSET_CARD_ERROR in str(error.value)

        assert _fixed_asset_state(db, inventory.id if case == "missing_inventory" else target_inventory_id) == before
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
