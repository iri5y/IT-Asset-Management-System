"""仓储单层分类迁移的隔离数据库集成测试。"""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import database
import models
from migrate_asset_category_and_issuance import (
    migrate_warehouse_categories,
    run_migration,
)
from warehouse_category_seed import seed_warehouse_categories


def _category_ids(db_session, primary_code: str, secondary_code: str) -> tuple[int, int]:
    primary = (
        db_session.query(models.WarehousePrimaryCategory)
        .filter_by(code=primary_code)
        .one()
    )
    secondary = (
        db_session.query(models.WarehouseSecondaryCategory)
        .filter_by(code=secondary_code)
        .one()
    )
    return primary.id, secondary.id


def _add_legacy_assets(db_session) -> dict[str, models.WarehouseAsset]:
    records = {
        "unique": models.WarehouseAsset(
            name="唯一映射物料",
            category="　唯一分类　",
            subcategory="历史子类",
            brand="品牌 A",
            model="型号 A",
            receiver_name="领用人 A",
            total_quantity=9,
            available_quantity=7,
            allocated_quantity=2,
            minimum_stock=3,
            location="A-01",
            notes="保留全部非分类字段",
        ),
        "unmapped": models.WarehouseAsset(
            name="零映射物料",
            category="未配置历史分类",
            total_quantity=8,
            available_quantity=8,
            allocated_quantity=0,
            location="A-02",
        ),
        "ambiguous": models.WarehouseAsset(
            name="歧义映射物料",
            category="歧义历史分类",
            total_quantity=7,
            available_quantity=5,
            allocated_quantity=2,
            location="A-03",
        ),
        "inactive": models.WarehouseAsset(
            name="停用目标物料",
            category="停用目标历史分类",
            total_quantity=6,
            available_quantity=6,
            allocated_quantity=0,
            location="A-04",
        ),
        "invalid_pair": models.WarehouseAsset(
            name="错误从属物料",
            category="错误从属历史分类",
            total_quantity=5,
            available_quantity=4,
            allocated_quantity=1,
            location="A-05",
        ),
    }
    db_session.add_all(records.values())
    db_session.flush()
    return records


def _non_classification_summary(
    assets: Iterable[models.WarehouseAsset],
) -> dict[int, tuple[object, ...]]:
    return {
        asset.id: (
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
            asset.location,
            asset.notes,
            asset.created_at,
            asset.updated_at,
        )
        for asset in assets
    }


def _replace_mapping_table_without_unique_constraint(db_session) -> None:
    """模拟历史映射表，以真实数据库行构造已无法再创建的歧义数据。"""
    db_session.execute(text("DROP TABLE warehouse_category_mappings"))
    db_session.execute(
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


def _insert_mapping(
    db_session,
    *,
    normalized_category: str,
    primary_id: int,
    secondary_id: int,
) -> None:
    db_session.execute(
        text(
            """
            INSERT INTO warehouse_category_mappings
                (normalized_legacy_category, primary_category_id, secondary_category_id, is_active)
            VALUES
                (:normalized_category, :primary_id, :secondary_id, 1)
            """
        ),
        {
            "normalized_category": normalized_category,
            "primary_id": primary_id,
            "secondary_id": secondary_id,
        },
    )


def test_migration_preserves_legacy_data_reports_unresolved_cases_and_is_idempotent(
    db_session,
) -> None:
    """两次真实迁移应保真转换唯一映射，并幂等报告所有不可确定分类。"""
    seed_warehouse_categories(db_session)
    db_session.flush()
    _replace_mapping_table_without_unique_constraint(db_session)

    display_primary_id, monitor_secondary_id = _category_ids(
        db_session, "DISPLAY_AUDIO_VIDEO", "DISPLAY_MONITOR"
    )
    _, speaker_secondary_id = _category_ids(
        db_session, "DISPLAY_AUDIO_VIDEO", "DISPLAY_SPEAKER"
    )
    terminal_primary_id, desktop_secondary_id = _category_ids(
        db_session, "TERMINAL_EQUIPMENT", "TERMINAL_DESKTOP"
    )
    inactive_secondary = (
        db_session.query(models.WarehouseSecondaryCategory)
        .filter_by(id=speaker_secondary_id)
        .one()
    )
    inactive_secondary.is_active = False

    _insert_mapping(
        db_session,
        normalized_category="唯一分类",
        primary_id=display_primary_id,
        secondary_id=monitor_secondary_id,
    )
    _insert_mapping(
        db_session,
        normalized_category="歧义历史分类",
        primary_id=display_primary_id,
        secondary_id=monitor_secondary_id,
    )
    _insert_mapping(
        db_session,
        normalized_category="歧义历史分类",
        primary_id=display_primary_id,
        secondary_id=speaker_secondary_id,
    )
    _insert_mapping(
        db_session,
        normalized_category="停用目标历史分类",
        primary_id=display_primary_id,
        secondary_id=speaker_secondary_id,
    )
    _insert_mapping(
        db_session,
        normalized_category="错误从属历史分类",
        primary_id=display_primary_id,
        secondary_id=desktop_secondary_id,
    )
    assets = _add_legacy_assets(db_session)
    db_session.commit()

    before_summary = _non_classification_summary(assets.values())
    first_result = migrate_warehouse_categories(db_session)
    db_session.commit()

    persisted_assets = {
        asset.name: asset
        for asset in db_session.query(models.WarehouseAsset)
        .order_by(models.WarehouseAsset.id)
        .all()
    }
    unique = persisted_assets["唯一映射物料"]
    assert first_result.migrated_assets == 1
    assert first_result.pending_assets == 4
    assert first_result.before == first_result.after
    assert unique.id == assets["unique"].id
    assert unique.classification_status == "ACTIVE"
    assert (unique.primary_category_id, unique.secondary_category_id) == (
        display_primary_id,
        monitor_secondary_id,
    )
    assert unique.legacy_category == "唯一分类"
    assert _non_classification_summary(persisted_assets.values()) == before_summary
    assert db_session.query(models.Asset).count() == 0

    issues = {
        issue.warehouse_asset.name: issue
        for issue in db_session.query(models.WarehouseCategoryMigrationIssue).all()
    }
    expected_reasons = {
        "零映射物料": "UNMAPPED",
        "歧义映射物料": "AMBIGUOUS",
        "停用目标物料": "INACTIVE_TARGET",
        "错误从属物料": "INVALID_PAIR",
    }
    assert set(issues) == set(expected_reasons)
    for name, reason_code in expected_reasons.items():
        asset = persisted_assets[name]
        issue = issues[name]
        assert asset.classification_status == "PENDING_MIGRATION"
        assert asset.primary_category_id is None
        assert asset.secondary_category_id is None
        assert asset.legacy_category == asset.category
        assert issue.status == "OPEN"
        assert issue.reason_code == reason_code
        assert issue.original_category == asset.category
        assert issue.reason_detail

    second_result = migrate_warehouse_categories(db_session)
    db_session.commit()
    assert second_result.migrated_assets == 0
    assert second_result.pending_assets == 0
    assert second_result.skipped_assets == len(assets)
    assert db_session.query(models.WarehouseCategoryMigrationIssue).count() == 4
    assert _non_classification_summary(
        db_session.query(models.WarehouseAsset).all()
    ) == before_summary


def test_run_migration_rolls_back_all_writes_when_database_update_fails(
    db_session,
    sqlite_session_factory,
    monkeypatch,
) -> None:
    """脚本运行中数据库更新失败时，目录、映射和物料分类状态必须全部回滚。"""
    asset = models.WarehouseAsset(
        name="触发回滚的显示器",
        category="显示器",
        total_quantity=1,
        available_quantity=1,
        allocated_quantity=0,
    )
    db_session.add(asset)
    db_session.commit()
    db_session.execute(
        text(
            """
            CREATE TRIGGER fail_category_migration_update
            BEFORE UPDATE OF classification_status ON warehouse_assets
            WHEN NEW.classification_status = 'ACTIVE'
            BEGIN
                SELECT RAISE(ABORT, 'forced migration failure');
            END
            """
        )
    )
    db_session.commit()
    monkeypatch.setattr(database, "SessionLocal", sqlite_session_factory)

    with pytest.raises(IntegrityError, match="forced migration failure"):
        run_migration()

    db_session.expire_all()
    persisted = db_session.query(models.WarehouseAsset).filter_by(id=asset.id).one()
    assert persisted.classification_status == "PENDING_MIGRATION"
    assert persisted.legacy_category is None
    assert persisted.primary_category_id is None
    assert persisted.secondary_category_id is None
    assert db_session.query(models.WarehousePrimaryCategory).count() == 0
    assert db_session.query(models.WarehouseSecondaryCategory).count() == 0
    assert db_session.query(models.WarehouseCategoryMapping).count() == 0
    assert db_session.query(models.WarehouseCategoryMigrationIssue).count() == 0
