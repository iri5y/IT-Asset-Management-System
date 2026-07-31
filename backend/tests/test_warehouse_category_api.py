"""仓储两级分类目录 API 集成测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from auth import get_current_active_user
from database import get_db
from warehouse_category_seed import seed_warehouse_categories


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


@pytest.fixture
def category_api_env():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    user = models.User(
        username="warehouse-category-api-user",
        hashed_password="not-used-by-api-test",
        full_name="分类目录测试经办人",
        role="MIS",
        is_active=True,
    )
    db.add(user)
    db.commit()

    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[get_current_active_user] = lambda: user
    with TestClient(main.app) as client:
        yield client, db, user
    main.app.dependency_overrides.clear()
    db.close()
    models.Base.metadata.drop_all(engine)
    engine.dispose()


def _create_category_pair(db):
    primary_a = models.WarehousePrimaryCategory(
        code="INPUT_OFFICE_PERIPHERALS", name="输入与办公外设"
    )
    primary_b = models.WarehousePrimaryCategory(
        code="STORAGE_REPAIR_PARTS", name="存储与维修备件"
    )
    db.add_all((primary_a, primary_b))
    db.flush()
    secondary_a = models.WarehouseSecondaryCategory(
        primary_category_id=primary_a.id, code="API_INPUT", name="API 输入设备"
    )
    secondary_b = models.WarehouseSecondaryCategory(
        primary_category_id=primary_b.id, code="API_STORAGE", name="API 存储备件"
    )
    db.add_all((secondary_a, secondary_b))
    db.commit()
    return primary_a, primary_b, secondary_a, secondary_b


def test_category_read_apis_return_tree_flat_and_parent_scoped_children(
    category_api_env,
) -> None:
    """目录读取 API 应返回八个一级分类、平铺一级项和按父级过滤的二级项。"""
    client, db, _ = category_api_env
    seed_warehouse_categories(db)
    db.commit()

    tree_response = client.get("/warehouse/categories")
    assert tree_response.status_code == 200
    tree_categories = tree_response.json()["categories"]
    assert len(tree_categories) == 8
    terminal = next(item for item in tree_categories if item["code"] == "TERMINAL_EQUIPMENT")
    assert terminal["name"] == "终端设备库存"
    assert terminal["secondary_categories"]

    primary_response = client.get("/warehouse/categories/primary")
    assert primary_response.status_code == 200
    assert {item["id"] for item in primary_response.json()} == {
        item["id"] for item in tree_categories
    }

    secondary_response = client.get(
        f"/warehouse/categories/primary/{terminal['id']}/secondary"
    )
    assert secondary_response.status_code == 200
    assert secondary_response.json()
    assert all(
        item["primary_category_id"] == terminal["id"]
        for item in secondary_response.json()
    )


def test_category_maintenance_rejects_duplicate_primary_and_sibling_secondary(
    category_api_env,
) -> None:
    """维护端点必须分别拒绝重复一级标识和同一父级下的重复二级标识。"""
    client, _, _ = category_api_env
    primary_payload = {"code": "API_UNIQUE", "name": "API 唯一一级", "sort_order": 1}
    created_primary = client.post("/warehouse/categories/primary", json=primary_payload)
    assert created_primary.status_code == 200
    primary_id = created_primary.json()["id"]

    duplicate_primary = client.post(
        "/warehouse/categories/primary",
        json={"code": "API_UNIQUE", "name": "不同的一级名称", "sort_order": 2},
    )
    assert duplicate_primary.status_code == 409

    secondary_payload = {
        "primary_category_id": primary_id,
        "code": "API_UNIQUE_CHILD",
        "name": "API 唯一二级",
        "sort_order": 1,
    }
    assert client.post("/warehouse/categories/secondary", json=secondary_payload).status_code == 200
    duplicate_secondary = client.post("/warehouse/categories/secondary", json=secondary_payload)
    assert duplicate_secondary.status_code == 409


def test_category_deactivation_rejects_active_children_and_material_references(
    category_api_env,
) -> None:
    """被启用二级项或活动物料引用的分类不能直接停用。"""
    client, db, _ = category_api_env
    primary_a, primary_b, secondary_a, _ = _create_category_pair(db)

    primary_conflict = client.patch(
        f"/warehouse/categories/primary/{primary_a.id}", json={"is_active": False}
    )
    assert primary_conflict.status_code == 409

    material_response = client.post(
        "/warehouse/materials",
        json={
            "name": "API 测试鼠标",
            "primary_category_id": primary_a.id,
            "secondary_category_id": secondary_a.id,
            "available_quantity": 3,
            "allocated_quantity": 0,
            "location": "A-01",
            "low_stock_threshold": 1,
            "issue_policy": "CONSUMABLE",
        },
    )
    assert material_response.status_code == 200

    secondary_conflict = client.patch(
        f"/warehouse/categories/secondary/{secondary_a.id}", json={"is_active": False}
    )
    assert secondary_conflict.status_code == 409
    db.refresh(secondary_a)
    assert secondary_a.is_active is True

    db.refresh(primary_b)
    assert primary_b.is_active is True


def test_migration_issue_api_lists_open_issue_and_resolves_to_valid_pair(
    category_api_env,
) -> None:
    """待处理报告应展示历史分类，并在解决后激活原物料及关闭问题。"""
    client, db, _ = category_api_env
    primary_a, _, secondary_a, _ = _create_category_pair(db)
    pending_material = models.WarehouseAsset(
        name="待迁移 API 物料",
        category="旧显示设备分类",
        total_quantity=4,
        available_quantity=4,
        allocated_quantity=0,
        minimum_stock=0,
        low_stock_threshold=0,
        classification_status="PENDING_MIGRATION",
        legacy_category="旧显示设备分类",
        issue_policy="CONSUMABLE",
    )
    db.add(pending_material)
    db.flush()
    issue = models.WarehouseCategoryMigrationIssue(
        warehouse_asset_id=pending_material.id,
        original_category="旧显示设备分类",
        normalized_category="旧显示设备分类",
        reason_code="UNMAPPED",
        reason_detail="未配置唯一有效映射",
    )
    db.add(issue)
    db.commit()

    open_response = client.get("/warehouse/category-migration-issues")
    assert open_response.status_code == 200
    issue_payload = next(item for item in open_response.json() if item["id"] == issue.id)
    assert issue_payload["warehouse_asset_id"] == pending_material.id
    assert issue_payload["material_name"] == "待迁移 API 物料"
    assert issue_payload["original_category"] == "旧显示设备分类"
    assert issue_payload["reason_code"] == "UNMAPPED"
    assert issue_payload["status"] == "OPEN"

    resolved_response = client.post(
        f"/warehouse/category-migration-issues/{issue.id}/resolve",
        json={
            "primary_category_id": primary_a.id,
            "secondary_category_id": secondary_a.id,
            "resolution_note": "按管理员确认的目录映射",
        },
    )
    assert resolved_response.status_code == 200
    assert resolved_response.json()["warehouse_asset_id"] == pending_material.id
    assert resolved_response.json()["audit_log_id"] > 0

    resolved_issues = client.get("/warehouse/category-migration-issues", params={"status": "RESOLVED"})
    assert resolved_issues.status_code == 200
    assert any(item["id"] == issue.id and item["resolved_at"] for item in resolved_issues.json())
    db.refresh(pending_material)
    assert (pending_material.classification_status, pending_material.primary_category_id, pending_material.secondary_category_id) == (
        "ACTIVE", primary_a.id, secondary_a.id
    )


def test_material_apis_return_both_category_dimensions(category_api_env) -> None:
    """物料创建、列表和详情响应均应包含稳定 ID 与一级/二级名称。"""
    client, db, _ = category_api_env
    primary_a, _, secondary_a, _ = _create_category_pair(db)
    created = client.post(
        "/warehouse/materials",
        json={
            "name": "API 双分类物料",
            "primary_category_id": primary_a.id,
            "secondary_category_id": secondary_a.id,
            "available_quantity": 2,
            "allocated_quantity": 0,
            "location": "B-02",
            "low_stock_threshold": 3,
            "issue_policy": "CONSUMABLE",
        },
    )
    assert created.status_code == 200
    created_payload = created.json()
    expected = {
        "primary_category_id": primary_a.id,
        "primary_category_code": primary_a.code,
        "primary_category_name": primary_a.name,
        "secondary_category_id": secondary_a.id,
        "secondary_category_code": secondary_a.code,
        "secondary_category_name": secondary_a.name,
    }
    assert {key: created_payload[key] for key in expected} == expected

    listed = client.get("/warehouse/materials", params={"primary_category_id": primary_a.id})
    assert listed.status_code == 200
    assert any(item["id"] == created_payload["id"] and all(item[key] == value for key, value in expected.items()) for item in listed.json())
    detail = client.get(f"/warehouse/materials/{created_payload['id']}")
    assert detail.status_code == 200
    assert {key: detail.json()[key] for key in expected} == expected


@pytest.mark.parametrize("session_factory_fixture", ("sqlite_session_factory", "postgresql_session_factory"))
def test_database_rejects_cross_parent_category_pair(
    request,
    session_factory_fixture: str,
) -> None:
    """SQLite 与可选 PostgreSQL 均必须以复合外键拒绝跨一级分类的物料组合。"""
    session_factory = request.getfixturevalue(session_factory_fixture)
    db = session_factory()
    try:
        primary_a = models.WarehousePrimaryCategory(code="API_DB_A", name="数据库一级 A")
        primary_b = models.WarehousePrimaryCategory(code="API_DB_B", name="数据库一级 B")
        db.add_all((primary_a, primary_b))
        db.flush()
        secondary_a = models.WarehouseSecondaryCategory(
            primary_category_id=primary_a.id, code="API_DB_A_CHILD", name="数据库二级 A"
        )
        secondary_b = models.WarehouseSecondaryCategory(
            primary_category_id=primary_b.id, code="API_DB_B_CHILD", name="数据库二级 B"
        )
        db.add_all((secondary_a, secondary_b))
        db.commit()

        db.add(
            models.WarehouseAsset(
                name="跨父级组合物料",
                category="数据库一级 A",
                subcategory="数据库二级 B",
                total_quantity=1,
                available_quantity=1,
                allocated_quantity=0,
                minimum_stock=0,
                low_stock_threshold=0,
                primary_category_id=primary_a.id,
                secondary_category_id=secondary_b.id,
                classification_status="ACTIVE",
                issue_policy="CONSUMABLE",
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
    finally:
        db.close()
