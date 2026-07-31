"""仓储物料组合筛选与严格低库存判定的属性测试。"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import models
from warehouse_category_service import validate_active_category_pair
from warehouse_material_service import list_materials


FILTER_FIELDS = (
    "name",
    "primary_category_id",
    "secondary_category_id",
    "available_quantity",
    "allocated_quantity",
    "location",
    "low_stock_threshold",
    "low_stock",
)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _matches_all_filters(
    material: models.WarehouseAsset,
    filters: dict[str, Any],
) -> bool:
    if "name" in filters and filters["name"].strip().casefold() not in material.name.casefold():
        return False
    for field in (
        "primary_category_id",
        "secondary_category_id",
        "available_quantity",
        "allocated_quantity",
        "low_stock_threshold",
        "location",
    ):
        if field in filters and getattr(material, field) != filters[field]:
            return False
    return (
        "low_stock" not in filters
        or (material.available_quantity < material.low_stock_threshold)
        is filters["low_stock"]
    )


def _create_active_materials(
    db: Session,
    *,
    equality_quantity: int,
    available_quantities: list[int],
    allocated_quantities: list[int],
    thresholds: list[int],
    locations: list[str],
) -> list[models.WarehouseAsset]:
    primary_a = models.WarehousePrimaryCategory(
        code="INPUT_OFFICE_PERIPHERALS",
        name="P10 一级分类 A",
        is_active=True,
    )
    primary_b = models.WarehousePrimaryCategory(
        code="NETWORK_SERVER_CONSUMABLES",
        name="P10 一级分类 B",
        is_active=True,
    )
    db.add_all((primary_a, primary_b))
    db.flush()
    secondary_a1 = models.WarehouseSecondaryCategory(
        primary_category_id=primary_a.id,
        code="P10-A1",
        name="P10 二级分类 A1",
        is_active=True,
    )
    secondary_a2 = models.WarehouseSecondaryCategory(
        primary_category_id=primary_a.id,
        code="P10-A2",
        name="P10 二级分类 A2",
        is_active=True,
    )
    secondary_b1 = models.WarehouseSecondaryCategory(
        primary_category_id=primary_b.id,
        code="P10-B1",
        name="P10 二级分类 B1",
        is_active=True,
    )
    db.add_all((secondary_a1, secondary_a2, secondary_b1))
    db.flush()

    category_pairs = (
        (primary_a, secondary_a1),
        (primary_a, secondary_a2),
        (primary_b, secondary_b1),
        (primary_b, secondary_b1),
    )
    quantities = (equality_quantity, *available_quantities)
    minimums = (equality_quantity, *thresholds)
    materials: list[models.WarehouseAsset] = []
    for index, ((primary, secondary), available, allocated, threshold, location) in enumerate(
        zip(category_pairs, quantities, allocated_quantities, minimums, locations)
    ):
        material = models.WarehouseAsset(
            name=f"P10-Material-{index}",
            category=primary.name,
            subcategory=secondary.name,
            total_quantity=available + allocated,
            available_quantity=available,
            allocated_quantity=allocated,
            minimum_stock=threshold,
            low_stock_threshold=threshold,
            location=location,
            primary_category_id=primary.id,
            secondary_category_id=secondary.id,
            classification_status="ACTIVE",
            issue_policy="CONSUMABLE",
        )
        db.add(material)
        materials.append(material)
    db.commit()
    return materials


def _filter_values(material: models.WarehouseAsset) -> dict[str, Any]:
    return {
        "name": material.name.lower(),
        "primary_category_id": material.primary_category_id,
        "secondary_category_id": material.secondary_category_id,
        "available_quantity": material.available_quantity,
        "allocated_quantity": material.allocated_quantity,
        "location": material.location,
        "low_stock_threshold": material.low_stock_threshold,
        "low_stock": material.available_quantity < material.low_stock_threshold,
    }


# Feature: asset-category-and-issuance-management, Property 10: 两级组合筛选与严格低库存判定
# Validates: Requirements 7.7, 7.10, 7.11, 11.5
@settings(max_examples=100, deadline=None)
@given(
    selected_index=st.integers(min_value=0, max_value=3),
    filter_fields=st.sets(st.sampled_from(FILTER_FIELDS)),
    equality_quantity=st.integers(min_value=0, max_value=30),
    available_quantities=st.lists(
        st.integers(min_value=0, max_value=30), min_size=3, max_size=3
    ),
    allocated_quantities=st.lists(
        st.integers(min_value=0, max_value=30), min_size=4, max_size=4
    ),
    thresholds=st.lists(
        st.integers(min_value=0, max_value=30), min_size=3, max_size=3
    ),
    locations=st.lists(
        st.sampled_from(("P10 库位 A", "P10 库位 B", "P10 库位 C")),
        min_size=4,
        max_size=4,
    ),
)
def test_property_10_material_filters_intersect_and_low_stock_is_strict(
    selected_index: int,
    filter_fields: set[str],
    equality_quantity: int,
    available_quantities: list[int],
    allocated_quantities: list[int],
    thresholds: list[int],
    locations: list[str],
) -> None:
    """任意筛选条件子集取交集，一级/二级组合有效且低库存严格小于阈值。"""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        materials = _create_active_materials(
            db,
            equality_quantity=equality_quantity,
            available_quantities=available_quantities,
            allocated_quantities=allocated_quantities,
            thresholds=thresholds,
            locations=locations,
        )
        selected = materials[selected_index]
        values = _filter_values(selected)
        filters = {field: values[field] for field in filter_fields}

        result = list_materials(db, filters=filters)
        expected = [
            material
            for material in materials
            if _matches_all_filters(material, filters)
        ]
        assert [row["id"] for row in result] == sorted(
            (material.id for material in expected), reverse=True
        )

        validate_active_category_pair(
            db, selected.primary_category_id, selected.secondary_category_id
        )
        pair_filters = {
            "primary_category_id": selected.primary_category_id,
            "secondary_category_id": selected.secondary_category_id,
        }
        pair_result = list_materials(db, filters=pair_filters)
        assert [row["id"] for row in pair_result] == sorted(
            (
                material.id
                for material in materials
                if _matches_all_filters(material, pair_filters)
            ),
            reverse=True,
        )

        all_rows = {row["id"]: row for row in list_materials(db, filters={})}
        assert set(all_rows) == {material.id for material in materials}
        for material in materials:
            expected_low_stock = material.available_quantity < material.low_stock_threshold
            row = all_rows[material.id]
            assert row["low_stock"] is expected_low_stock
            assert row["low_stock_message"] == (
                "低库存预警" if expected_low_stock else None
            )

        equality_row = all_rows[materials[0].id]
        assert equality_row["available_quantity"] == equality_row["low_stock_threshold"]
        assert equality_row["low_stock"] is False
        assert equality_row["low_stock_message"] is None
        for low_stock in (True, False):
            low_stock_result = list_materials(db, filters={"low_stock": low_stock})
            assert [row["id"] for row in low_stock_result] == sorted(
                (
                    material.id
                    for material in materials
                    if (material.available_quantity < material.low_stock_threshold)
                    is low_stock
                ),
                reverse=True,
            )
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
