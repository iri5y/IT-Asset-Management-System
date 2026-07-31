"""历史单层分类迁移保真与待处理可追溯的属性测试。"""

from __future__ import annotations

import string

from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

import models
from migrate_asset_category_and_issuance import (
    migrate_warehouse_categories,
    normalize_legacy_category,
)
from warehouse_category_seed import seed_warehouse_categories


MIGRATION_OUTCOMES = st.sampled_from(
    ("unique", "unmapped", "ambiguous", "inactive", "invalid_pair")
)
TEXT_ALPHABET = string.ascii_letters + string.digits + "-_"
METADATA_TEXT = st.text(alphabet=TEXT_ALPHABET, min_size=1, max_size=24)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _category_ids(db: Session) -> tuple[int, int, int, int]:
    display_primary = (
        db.query(models.WarehousePrimaryCategory)
        .filter_by(code="DISPLAY_AUDIO_VIDEO")
        .one()
    )
    display_secondary = (
        db.query(models.WarehouseSecondaryCategory)
        .filter_by(code="DISPLAY_MONITOR")
        .one()
    )
    terminal_secondary = (
        db.query(models.WarehouseSecondaryCategory)
        .filter_by(code="TERMINAL_DESKTOP")
        .one()
    )
    return (
        display_primary.id,
        display_secondary.id,
        terminal_secondary.primary_category_id,
        terminal_secondary.id,
    )


def _replace_mapping_table_without_constraints(db: Session) -> None:
    """构造历史异常映射数据；当前受控模型已禁止此类数据直接写入。"""
    db.execute(text("DROP TABLE warehouse_category_mappings"))
    db.execute(
        text(
            """
            CREATE TABLE warehouse_category_mappings (
                id INTEGER PRIMARY KEY,
                normalized_legacy_category VARCHAR(255) NOT NULL,
                primary_category_id INTEGER NOT NULL,
                secondary_category_id INTEGER NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_by INTEGER,
                created_at DATETIME
            )
            """
        )
    )


def _insert_legacy_mapping(
    db: Session,
    *,
    normalized_category: str,
    primary_id: int,
    secondary_id: int,
    is_active: bool = True,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO warehouse_category_mappings
                (normalized_legacy_category, primary_category_id,
                 secondary_category_id, is_active)
            VALUES
                (:normalized_category, :primary_id, :secondary_id, :is_active)
            """
        ),
        {
            "normalized_category": normalized_category,
            "primary_id": primary_id,
            "secondary_id": secondary_id,
            "is_active": is_active,
        },
    )


def _configure_mapping(
    db: Session,
    *,
    outcome: str,
    normalized_category: str,
) -> tuple[int, int]:
    display_primary_id, display_secondary_id, terminal_primary_id, terminal_secondary_id = (
        _category_ids(db)
    )
    if outcome == "unique":
        db.add(
            models.WarehouseCategoryMapping(
                normalized_legacy_category=normalized_category,
                primary_category_id=display_primary_id,
                secondary_category_id=display_secondary_id,
                is_active=True,
            )
        )
    elif outcome == "inactive":
        db.add(
            models.WarehouseCategoryMapping(
                normalized_legacy_category=normalized_category,
                primary_category_id=display_primary_id,
                secondary_category_id=display_secondary_id,
                is_active=False,
            )
        )
    elif outcome in {"ambiguous", "invalid_pair"}:
        _replace_mapping_table_without_constraints(db)
        _insert_legacy_mapping(
            db,
            normalized_category=normalized_category,
            primary_id=display_primary_id,
            secondary_id=display_secondary_id,
        )
        if outcome == "ambiguous":
            _insert_legacy_mapping(
                db,
                normalized_category=normalized_category,
                primary_id=terminal_primary_id,
                secondary_id=terminal_secondary_id,
            )
        else:
            _insert_legacy_mapping(
                db,
                normalized_category=normalized_category,
                primary_id=display_primary_id,
                secondary_id=terminal_secondary_id,
            )
    db.flush()
    return display_primary_id, display_secondary_id


def _non_classification_state(asset: models.WarehouseAsset) -> tuple[object, ...]:
    return (
        asset.id,
        asset.name,
        asset.category,
        asset.subcategory,
        asset.brand,
        asset.model,
        asset.receiver_name,
        asset.total_quantity,
        asset.available_quantity,
        asset.allocated_quantity,
        asset.minimum_stock,
        asset.low_stock_threshold,
        asset.location,
        asset.notes,
        asset.material_kind,
        asset.created_at,
        asset.updated_at,
    )


def _full_migration_state(asset: models.WarehouseAsset) -> tuple[object, ...]:
    return _non_classification_state(asset) + (
        asset.primary_category_id,
        asset.secondary_category_id,
        asset.classification_status,
        asset.legacy_category,
        asset.issue_policy,
    )


# Feature: asset-category-and-issuance-management, Property 11: 历史单层分类迁移保真与待处理可追溯
# Validates: Requirements 7.8, 7.9
@settings(max_examples=100, deadline=None)
@given(
    outcome=MIGRATION_OUTCOMES,
    suffix=METADATA_TEXT,
    padding=st.sampled_from(("", " ", "\t", "  ")),
    available_quantity=st.integers(min_value=0, max_value=100),
    allocated_quantity=st.integers(min_value=0, max_value=100),
    minimum_stock=st.integers(min_value=0, max_value=100),
    low_stock_threshold=st.integers(min_value=0, max_value=100),
    metadata=METADATA_TEXT,
)
def test_property_11_legacy_category_migration_preserves_data_and_reports_unresolved(
    outcome: str,
    suffix: str,
    padding: str,
    available_quantity: int,
    allocated_quantity: int,
    minimum_stock: int,
    low_stock_threshold: int,
    metadata: str,
) -> None:
    """所有历史映射结果均保留数据、可追溯且重复执行不产生新结果。"""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = session_factory()
    try:
        seed_warehouse_categories(db)
        legacy_category = f"{padding}Property11-{suffix}{padding}"
        original_category = legacy_category.strip()
        normalized_category = normalize_legacy_category(legacy_category)
        expected_primary_id, expected_secondary_id = _configure_mapping(
            db,
            outcome=outcome,
            normalized_category=normalized_category,
        )
        asset = models.WarehouseAsset(
            name=f"历史物料-{metadata}",
            category=legacy_category,
            subcategory=f"子类-{metadata}",
            brand=f"品牌-{metadata}",
            model=f"型号-{metadata}",
            receiver_name=f"领用人-{metadata}",
            total_quantity=available_quantity + allocated_quantity,
            available_quantity=available_quantity,
            allocated_quantity=allocated_quantity,
            minimum_stock=minimum_stock,
            low_stock_threshold=low_stock_threshold,
            location=f"库位-{metadata}",
            notes=f"备注-{metadata}",
            material_kind=f"LEGACY-{metadata}",
        )
        db.add(asset)
        db.flush()
        asset_id = asset.id
        before_non_classification = _non_classification_state(asset)

        first_result = migrate_warehouse_categories(db)
        db.commit()
        db.expire_all()
        migrated_asset = db.get(models.WarehouseAsset, asset_id)
        assert migrated_asset is not None
        assert first_result.before == first_result.after
        assert _non_classification_state(migrated_asset) == before_non_classification

        expected_reason = {
            "unmapped": "UNMAPPED",
            "ambiguous": "AMBIGUOUS",
            "inactive": "INACTIVE_TARGET",
            "invalid_pair": "INVALID_PAIR",
        }.get(outcome)
        if outcome == "unique":
            assert first_result.migrated_assets == 1
            assert first_result.pending_assets == 0
            assert migrated_asset.classification_status == "ACTIVE"
            assert (
                migrated_asset.primary_category_id,
                migrated_asset.secondary_category_id,
            ) == (expected_primary_id, expected_secondary_id)
            assert migrated_asset.legacy_category == original_category
            assert (
                db.query(models.WarehouseCategoryMigrationIssue)
                .filter_by(warehouse_asset_id=asset_id)
                .count()
                == 0
            )
        else:
            assert first_result.migrated_assets == 0
            assert first_result.pending_assets == 1
            assert migrated_asset.classification_status == "PENDING_MIGRATION"
            assert migrated_asset.primary_category_id is None
            assert migrated_asset.secondary_category_id is None
            assert migrated_asset.category == legacy_category
            assert migrated_asset.legacy_category == original_category
            issues = (
                db.query(models.WarehouseCategoryMigrationIssue)
                .filter_by(warehouse_asset_id=asset_id, status="OPEN")
                .all()
            )
            assert len(issues) == 1
            issue = issues[0]
            assert issue.original_category == original_category
            assert issue.normalized_category == normalized_category
            assert issue.reason_code == expected_reason
            assert issue.reason_detail

        first_state = _full_migration_state(migrated_asset)
        first_issue_ids = tuple(
            issue.id
            for issue in db.query(models.WarehouseCategoryMigrationIssue)
            .filter_by(warehouse_asset_id=asset_id)
            .order_by(models.WarehouseCategoryMigrationIssue.id)
        )
        second_result = migrate_warehouse_categories(db)
        db.commit()
        db.expire_all()
        rerun_asset = db.get(models.WarehouseAsset, asset_id)
        assert rerun_asset is not None
        assert second_result.migrated_assets == 0
        assert second_result.pending_assets == 0
        assert second_result.skipped_assets == 1
        assert _full_migration_state(rerun_asset) == first_state
        assert tuple(
            issue.id
            for issue in db.query(models.WarehouseCategoryMigrationIssue)
            .filter_by(warehouse_asset_id=asset_id)
            .order_by(models.WarehouseCategoryMigrationIssue.id)
        ) == first_issue_ids
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
