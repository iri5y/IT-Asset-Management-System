"""仓储两级分类目录种子的示例与幂等测试。"""

from __future__ import annotations

import models
from warehouse_category_seed import (
    PRIMARY_CATEGORY_SEED_DATA,
    SECONDARY_CATEGORY_SEED_DATA,
    seed_warehouse_categories,
)


EXPECTED_PRIMARY_CATEGORIES = (
    ("TERMINAL_EQUIPMENT", "终端设备库存"),
    ("DISPLAY_AUDIO_VIDEO", "显示与音视频设备"),
    ("INPUT_OFFICE_PERIPHERALS", "输入与办公外设"),
    ("STORAGE_REPAIR_PARTS", "存储与维修备件"),
    ("CABLES_CONNECTORS", "线缆与连接配件"),
    ("NETWORK_SERVER_ROOM_CONSUMABLES", "网络与机房耗材"),
    ("IT_TOOLS_LOAN_ITEMS", "IT工具与借用物品"),
    ("OFFICE_GENERAL_CONSUMABLES", "办公与通用耗材"),
)


def test_seed_creates_all_required_primary_categories(db_session) -> None:
    """内置种子应完整创建需求规定的八个一级分类。"""
    result = seed_warehouse_categories(db_session)
    db_session.commit()

    categories = (
        db_session.query(models.WarehousePrimaryCategory)
        .order_by(models.WarehousePrimaryCategory.sort_order)
        .all()
    )

    assert result.primary_created == len(EXPECTED_PRIMARY_CATEGORIES)
    assert [(category.code, category.name) for category in categories] == list(
        EXPECTED_PRIMARY_CATEGORIES
    )
    assert all(category.is_active for category in categories)


def test_seed_secondary_categories_each_have_exactly_one_seeded_parent(
    db_session,
) -> None:
    """每个二级分类必须且只能关联至其种子声明的一个一级分类。"""
    seed_warehouse_categories(db_session)
    db_session.commit()

    secondary_categories = db_session.query(models.WarehouseSecondaryCategory).all()
    expected_parent_codes = {
        seed.code: seed.primary_code for seed in SECONDARY_CATEGORY_SEED_DATA
    }
    primary_ids = {
        category.id
        for category in db_session.query(models.WarehousePrimaryCategory).all()
    }

    assert len(secondary_categories) == len(SECONDARY_CATEGORY_SEED_DATA)
    assert all(category.primary_category_id in primary_ids for category in secondary_categories)
    assert all(category.primary_category is not None for category in secondary_categories)
    assert {
        category.code: category.primary_category.code
        for category in secondary_categories
    } == expected_parent_codes


def test_repeated_seed_does_not_duplicate_or_overwrite_maintained_values(
    db_session,
) -> None:
    """重复运行仅补齐缺项，不重置管理员维护的目录字段或二级从属。"""
    first_result = seed_warehouse_categories(db_session)
    db_session.commit()

    maintained_primary = (
        db_session.query(models.WarehousePrimaryCategory)
        .filter_by(code="TERMINAL_EQUIPMENT")
        .one()
    )
    maintained_secondary = (
        db_session.query(models.WarehouseSecondaryCategory)
        .filter_by(code="TERMINAL_DESKTOP")
        .one()
    )
    maintained_primary.name = "管理员维护的终端分类"
    maintained_primary.sort_order = 999
    maintained_primary.is_active = False
    maintained_secondary.name = "管理员维护的台式机"
    maintained_secondary.sort_order = 888
    maintained_secondary.is_active = False
    maintained_primary_id = maintained_primary.id
    maintained_secondary_parent_id = maintained_secondary.primary_category_id
    db_session.commit()

    second_result = seed_warehouse_categories(db_session)
    db_session.commit()

    db_session.refresh(maintained_primary)
    db_session.refresh(maintained_secondary)
    assert first_result.primary_created == len(PRIMARY_CATEGORY_SEED_DATA)
    assert first_result.secondary_created == len(SECONDARY_CATEGORY_SEED_DATA)
    assert second_result.primary_created == 0
    assert second_result.secondary_created == 0
    assert db_session.query(models.WarehousePrimaryCategory).count() == len(
        PRIMARY_CATEGORY_SEED_DATA
    )
    assert db_session.query(models.WarehouseSecondaryCategory).count() == len(
        SECONDARY_CATEGORY_SEED_DATA
    )
    assert (
        maintained_primary.id,
        maintained_primary.name,
        maintained_primary.sort_order,
        maintained_primary.is_active,
    ) == (maintained_primary_id, "管理员维护的终端分类", 999, False)
    assert (
        maintained_secondary.name,
        maintained_secondary.sort_order,
        maintained_secondary.is_active,
        maintained_secondary.primary_category_id,
    ) == ("管理员维护的台式机", 888, False, maintained_secondary_parent_id)
