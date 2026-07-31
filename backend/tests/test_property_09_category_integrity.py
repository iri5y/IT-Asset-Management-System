"""仓储两级分类从属与物料组合完整性的属性测试。"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

import models
from warehouse_category_service import (
    WarehouseCategoryServiceError,
    validate_active_category_pair,
)
from warehouse_material_service import (
    WarehouseMaterialServiceError,
    create_material,
    update_material,
)


INVALID_PAIR_CASES = st.sampled_from(
    (
        "cross_parent",
        "missing_primary",
        "missing_secondary",
        "inactive_primary",
        "inactive_secondary",
        "nonexistent_primary",
        "nonexistent_secondary",
    )
)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _catalog_state(db: Session) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (category.id, category.primary_category_id, category.is_active)
        for category in db.query(models.WarehouseSecondaryCategory)
        .order_by(models.WarehouseSecondaryCategory.id)
        .all()
    )


def _material_state(db: Session, material_id: int) -> tuple[object, ...]:
    material = db.get(models.WarehouseAsset, material_id)
    assert material is not None
    return (
        material.primary_category_id,
        material.secondary_category_id,
        material.classification_status,
        material.available_quantity,
        material.allocated_quantity,
        material.total_quantity,
    )


def _assert_database_rejects_invalid_category_rows(
    db: Session,
    primary_a_id: int,
    secondary_b_id: int,
) -> None:
    """二级分类不得缺少父项，物料不得绕过复合外键交叉引用。"""
    db.add(
        models.WarehouseSecondaryCategory(
            primary_category_id=None,
            code="P9-MISSING-PARENT",
            name="P9 缺失父级",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    db.add(
        models.WarehouseAsset(
            name="P9 数据库交叉父级物料",
            category="一级 A",
            subcategory="二级 B",
            total_quantity=1,
            available_quantity=1,
            allocated_quantity=0,
            minimum_stock=0,
            low_stock_threshold=0,
            primary_category_id=primary_a_id,
            secondary_category_id=secondary_b_id,
            classification_status="ACTIVE",
            issue_policy="CONSUMABLE",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    assert db.query(models.WarehouseAsset).count() == 0


def _invalid_pair(
    case: str,
    primary_a_id: int,
    primary_b_id: int,
    secondary_a_id: int,
    secondary_b_id: int,
) -> tuple[int | None, int | None]:
    if case == "cross_parent":
        return primary_a_id, secondary_b_id
    if case == "missing_primary":
        return None, secondary_a_id
    if case == "missing_secondary":
        return primary_a_id, None
    if case == "inactive_primary":
        return primary_b_id, secondary_b_id
    if case == "inactive_secondary":
        return primary_b_id, secondary_b_id
    if case == "nonexistent_primary":
        return 99_999, secondary_a_id
    return primary_a_id, 99_999


def _invalid_payload(
    primary_id: int | None,
    secondary_id: int | None,
    quantity: int,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "P9 待拒绝物料",
        "available_quantity": quantity,
        "allocated_quantity": 0,
        "low_stock_threshold": 0,
        "issue_policy": "CONSUMABLE",
    }
    if primary_id is not None:
        payload["primary_category_id"] = primary_id
    if secondary_id is not None:
        payload["secondary_category_id"] = secondary_id
    return payload


# Feature: asset-category-and-issuance-management, Property 9: 两级分类从属与物料组合完整性
# Validates: Requirements 7.2, 7.3, 7.4, 7.5
@settings(max_examples=100, deadline=None)
@given(case=INVALID_PAIR_CASES, quantity=st.integers(min_value=0, max_value=100))
def test_property_9_category_parentage_and_material_pair_integrity(
    case: str,
    quantity: int,
) -> None:
    """无效一级/二级组合必须由服务与数据库共同拒绝，且不改变既有目录或物料。"""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        operator = models.User(
            username="property9-operator",
            hashed_password="not-used-by-property-test",
            full_name="Property 9 经办人",
            is_active=True,
        )
        primary_a = models.WarehousePrimaryCategory(
            code="INPUT_OFFICE_PERIPHERALS", name="一级 A", is_active=True
        )
        primary_b = models.WarehousePrimaryCategory(
            code="STORAGE_REPAIR_PARTS", name="一级 B", is_active=True
        )
        db.add_all((operator, primary_a, primary_b))
        db.flush()
        secondary_a = models.WarehouseSecondaryCategory(
            primary_category_id=primary_a.id,
            code="P9-A",
            name="二级 A",
            is_active=True,
        )
        secondary_b = models.WarehouseSecondaryCategory(
            primary_category_id=primary_b.id,
            code="P9-B",
            name="二级 B",
            is_active=True,
        )
        db.add_all((secondary_a, secondary_b))
        db.commit()
        primary_a_id, primary_b_id = primary_a.id, primary_b.id
        secondary_a_id, secondary_b_id = secondary_a.id, secondary_b.id

        assert secondary_a.primary_category_id == primary_a_id
        assert secondary_b.primary_category_id == primary_b_id
        assert all(parent_id is not None for _, parent_id, _ in _catalog_state(db))
        _assert_database_rejects_invalid_category_rows(
            db, primary_a_id, secondary_b_id
        )

        material, _ = create_material(
            db,
            payload={
                "name": "P9 有效物料",
                "available_quantity": quantity,
                "allocated_quantity": 0,
                "low_stock_threshold": 0,
                "primary_category_id": primary_a_id,
                "secondary_category_id": secondary_a_id,
                "issue_policy": "CONSUMABLE",
            },
            operator_id=operator.id,
        )
        material_id = material.id

        if case == "inactive_primary":
            db.get(models.WarehousePrimaryCategory, primary_b_id).is_active = False
            db.commit()
        elif case == "inactive_secondary":
            db.get(models.WarehouseSecondaryCategory, secondary_b_id).is_active = False
            db.commit()

        invalid_primary_id, invalid_secondary_id = _invalid_pair(
            case,
            primary_a_id,
            primary_b_id,
            secondary_a_id,
            secondary_b_id,
        )
        catalog_before = _catalog_state(db)
        material_before = _material_state(db, material_id)

        with pytest.raises(WarehouseCategoryServiceError):
            validate_active_category_pair(db, invalid_primary_id, invalid_secondary_id)

        payload = _invalid_payload(
            invalid_primary_id, invalid_secondary_id, quantity
        )
        with pytest.raises((WarehouseCategoryServiceError, WarehouseMaterialServiceError)):
            create_material(db, payload=payload, operator_id=operator.id)
        assert _catalog_state(db) == catalog_before
        assert _material_state(db, material_id) == material_before
        assert db.query(models.WarehouseAsset).count() == 1

        with pytest.raises((WarehouseCategoryServiceError, WarehouseMaterialServiceError)):
            update_material(
                db,
                material_id,
                changes={
                    key: value
                    for key, value in payload.items()
                    if key in {"primary_category_id", "secondary_category_id"}
                },
                operator_id=operator.id,
            )
        assert _catalog_state(db) == catalog_before
        assert _material_state(db, material_id) == material_before
        assert db.query(models.WarehouseAsset).count() == 1
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
