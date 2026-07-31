"""仓储分类与物料 API 的只读权限集成测试。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from auth import get_current_active_user
from database import get_db

READONLY_WRITE_ERROR = "只读账号无权限执行修改或新增操作"


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


@pytest.fixture
def readonly_warehouse_api_env() -> Iterator[tuple[TestClient, Session, dict[str, int]]]:
    """提供含活动物料和待处理迁移项的只读 API 场景。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    readonly_user = models.User(
        username="warehouse-readonly-user",
        hashed_password="not-used-by-api-test",
        full_name="仓储只读测试用户",
        role="readonly",
        is_active=True,
    )
    primary = models.WarehousePrimaryCategory(
        code="PERMISSION_PRIMARY", name="权限测试一级分类", sort_order=1
    )
    db.add_all((readonly_user, primary))
    db.flush()

    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id,
        code="PERMISSION_SECONDARY",
        name="权限测试二级分类",
        sort_order=1,
    )
    db.add(secondary)
    db.flush()
    material = models.WarehouseAsset(
        name="权限测试活动物料",
        category=primary.name,
        subcategory=secondary.name,
        total_quantity=4,
        available_quantity=4,
        allocated_quantity=0,
        minimum_stock=0,
        low_stock_threshold=1,
        location="P-01",
        primary_category_id=primary.id,
        secondary_category_id=secondary.id,
        classification_status="ACTIVE",
        issue_policy="CONSUMABLE",
    )
    pending_material = models.WarehouseAsset(
        name="权限测试待处理物料",
        category="历史未映射分类",
        total_quantity=2,
        available_quantity=2,
        allocated_quantity=0,
        minimum_stock=0,
        low_stock_threshold=0,
        classification_status="PENDING_MIGRATION",
        legacy_category="历史未映射分类",
        issue_policy="CONSUMABLE",
    )
    db.add_all((material, pending_material))
    db.flush()
    migration_issue = models.WarehouseCategoryMigrationIssue(
        warehouse_asset_id=pending_material.id,
        original_category="历史未映射分类",
        normalized_category="历史未映射分类",
        reason_code="UNMAPPED",
        reason_detail="未配置唯一有效映射",
    )
    db.add(migration_issue)
    db.commit()

    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[get_current_active_user] = lambda: readonly_user
    ids = {
        "primary": primary.id,
        "secondary": secondary.id,
        "material": material.id,
        "migration_issue": migration_issue.id,
    }
    with TestClient(main.app) as client:
        yield client, db, ids
    main.app.dependency_overrides.clear()
    db.close()
    models.Base.metadata.drop_all(engine)
    engine.dispose()


def _warehouse_state(db: Session) -> tuple[object, ...]:
    """返回所有会被本任务写端点修改的持久化数据快照。"""
    db.expire_all()
    return (
        tuple(
            (item.id, item.code, item.name, item.is_active, item.sort_order)
            for item in db.query(models.WarehousePrimaryCategory)
            .order_by(models.WarehousePrimaryCategory.id)
        ),
        tuple(
            (
                item.id,
                item.primary_category_id,
                item.code,
                item.name,
                item.is_active,
                item.sort_order,
            )
            for item in db.query(models.WarehouseSecondaryCategory)
            .order_by(models.WarehouseSecondaryCategory.id)
        ),
        tuple(
            (
                item.id,
                item.name,
                item.primary_category_id,
                item.secondary_category_id,
                item.classification_status,
                item.available_quantity,
                item.allocated_quantity,
                item.total_quantity,
                item.location,
                item.issue_policy,
            )
            for item in db.query(models.WarehouseAsset).order_by(models.WarehouseAsset.id)
        ),
        tuple(
            (item.id, item.status, item.resolved_by, item.resolved_at)
            for item in db.query(models.WarehouseCategoryMigrationIssue)
            .order_by(models.WarehouseCategoryMigrationIssue.id)
        ),
        db.query(models.WarehouseAssetLog).count(),
        db.query(models.OperationLog).count(),
    )


def test_readonly_user_can_read_categories_materials_and_pending_migration_details(
    readonly_warehouse_api_env,
) -> None:
    """只读角色仍可查询目录、物料列表/详情和待处理迁移报告。"""
    client, _, ids = readonly_warehouse_api_env

    tree = client.get("/warehouse/categories")
    assert tree.status_code == 200
    assert any(item["id"] == ids["primary"] for item in tree.json()["categories"])

    primary = client.get("/warehouse/categories/primary")
    assert primary.status_code == 200
    assert any(item["id"] == ids["primary"] for item in primary.json())

    secondary = client.get(f"/warehouse/categories/primary/{ids['primary']}/secondary")
    assert secondary.status_code == 200
    assert any(
        item["id"] == ids["secondary"]
        and item["primary_category_id"] == ids["primary"]
        for item in secondary.json()
    )

    materials = client.get("/warehouse/materials")
    assert materials.status_code == 200
    assert any(item["id"] == ids["material"] for item in materials.json())

    material = client.get(f"/warehouse/materials/{ids['material']}")
    assert material.status_code == 200
    assert material.json()["name"] == "权限测试活动物料"

    issues = client.get("/warehouse/category-migration-issues")
    assert issues.status_code == 200
    issue = next(item for item in issues.json() if item["id"] == ids["migration_issue"])
    assert issue["warehouse_asset_id"] > 0
    assert issue["original_category"] == "历史未映射分类"
    assert issue["reason_detail"] == "未配置唯一有效映射"


def test_readonly_user_cannot_mutate_categories_materials_or_migration_issues(
    readonly_warehouse_api_env,
) -> None:
    """所有分类、物料和迁移解决写端点均以中文 403 拒绝且无副作用。"""
    client, db, ids = readonly_warehouse_api_env
    before = _warehouse_state(db)
    requests = (
        ("post", "/warehouse/categories/primary", {
            "code": "FORBIDDEN_PRIMARY", "name": "禁止新增一级", "sort_order": 2,
        }),
        ("patch", f"/warehouse/categories/primary/{ids['primary']}", {
            "name": "禁止修改一级", "sort_order": 2, "is_active": False,
        }),
        ("post", "/warehouse/categories/secondary", {
            "primary_category_id": ids["primary"], "code": "FORBIDDEN_SECONDARY",
            "name": "禁止新增二级", "sort_order": 2,
        }),
        ("patch", f"/warehouse/categories/secondary/{ids['secondary']}", {
            "name": "禁止修改二级", "sort_order": 2, "is_active": False,
        }),
        ("post", "/warehouse/materials", {
            "name": "禁止新增物料", "primary_category_id": ids["primary"],
            "secondary_category_id": ids["secondary"], "available_quantity": 1,
            "allocated_quantity": 0, "location": "P-02",
            "low_stock_threshold": 0, "issue_policy": "CONSUMABLE",
        }),
        ("put", f"/warehouse/materials/{ids['material']}", {"location": "禁止修改位置"}),
        ("post", f"/warehouse/category-migration-issues/{ids['migration_issue']}/resolve", {
            "primary_category_id": ids["primary"],
            "secondary_category_id": ids["secondary"],
            "resolution_note": "禁止解决迁移问题",
        }),
    )

    for method, path, payload in requests:
        response = getattr(client, method)(path, json=payload)
        assert response.status_code == 403
        assert response.json()["detail"] == READONLY_WRITE_ERROR
        assert _warehouse_state(db) == before
