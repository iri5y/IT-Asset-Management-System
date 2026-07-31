"""受控固定资产入库创建唯一可追溯卡的属性测试。"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import models
from asset_lifecycle_service import controlled_inbound
from category_policy import ASSET_CATEGORY_NAMES, AssetCategoryCode, FixedAssetStatus


IDENTIFIER_TOKENS = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    min_size=1,
    max_size=24,
)


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _create_terminal_inventory(db: Session, token: str) -> models.WarehouseAsset:
    primary = models.WarehousePrimaryCategory(
        code="TERMINAL_EQUIPMENT",
        name=f"P2 终端设备库存 {token}",
        is_active=True,
    )
    db.add(primary)
    db.flush()
    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id,
        code=f"P2-TERMINAL-{token}",
        name=f"P2 终端二级 {token}",
        is_active=True,
    )
    db.add(secondary)
    db.flush()
    inventory = models.WarehouseAsset(
        name=f"P2 终端库存行 {token}",
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


# Feature: asset-category-and-issuance-management, Property 2: 受控固定资产入库创建唯一可追溯卡
# Validates: Requirements 2.1, 2.2, 2.3, 2.7
@settings(max_examples=100, deadline=None)
@given(
    category=st.sampled_from(tuple(AssetCategoryCode)),
    source=st.sampled_from(("SCAN", "MANUAL")),
    token=IDENTIFIER_TOKENS,
)
def test_property_2_controlled_inbound_creates_unique_traceable_asset_card(
    category: AssetCategoryCode,
    source: str,
    token: str,
) -> None:
    """任意有效受控入库均创建一张闲置卡、入库记录及一单位可用终端库存。"""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        operator = models.User(
            username=f"property2-{token}",
            hashed_password="not-used-by-property-test",
            full_name="Property 2 经办人",
            is_active=True,
        )
        db.add(operator)
        db.commit()
        inventory = _create_terminal_inventory(db, token)
        fixed_asset_number = f"P2-FA-{token}"
        serial_number = f"P2-SN-{token}"

        result = controlled_inbound(
            db,
            operator_id=operator.id,
            terminal_inventory_id=inventory.id,
            source=source,
            asset_category_code=category,
            fixed_asset_number=fixed_asset_number,
            serial_number=serial_number,
        )

        cards = (
            db.query(models.Asset)
            .filter(models.Asset.serial_number == serial_number)
            .all()
        )
        assert len(cards) == 1
        asset = cards[0]
        assert asset.id == result.asset.id
        assert asset.fixed_asset_number == fixed_asset_number
        assert asset.asset_tag == fixed_asset_number
        assert asset.asset_category_code == category.value
        assert asset.category == ASSET_CATEGORY_NAMES[category]
        assert asset.inbound_source == source
        assert asset.terminal_inventory_id == inventory.id
        assert asset.status == FixedAssetStatus.IDLE.value
        assert asset.status in {status.value for status in FixedAssetStatus}

        inbounds = (
            db.query(models.FixedAssetInbound)
            .filter(models.FixedAssetInbound.asset_id == asset.id)
            .all()
        )
        assert len(inbounds) == 1
        inbound = inbounds[0]
        assert inbound.id == result.inbound.id
        assert inbound.source == source
        assert inbound.terminal_inventory_id == inventory.id
        assert inbound.operator_id == operator.id
        assert inbound.asset_id == asset.id

        persisted_inventory = db.get(models.WarehouseAsset, inventory.id)
        assert persisted_inventory is not None
        assert persisted_inventory.total_quantity == 1
        assert persisted_inventory.available_quantity == 1
        assert persisted_inventory.allocated_quantity == 0
        assert db.query(models.Asset).count() == 1
        assert db.query(models.FixedAssetInbound).count() == 1
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
