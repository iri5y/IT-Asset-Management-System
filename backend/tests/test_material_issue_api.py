"""低值物料发放与归还 API 集成测试。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import main
import material_issuance_service
import models
from auth import get_current_active_user
from database import get_db
from transaction_audit import AuditLogPersistenceError

READONLY_WRITE_ERROR = "只读账号无权限执行修改或新增操作"


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


@pytest.fixture
def material_issue_api_env() -> Iterator[tuple[TestClient, Session, dict[str, Any]]]:
    """提供真实路由、认证依赖和两种领用策略物料的隔离环境。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    writer = models.User(
        username="material-issue-api-writer",
        hashed_password="not-used-by-api-test",
        full_name="低值领用测试经办人",
        role="MIS",
        is_active=True,
    )
    readonly = models.User(
        username="material-issue-api-readonly",
        hashed_password="not-used-by-api-test",
        full_name="低值领用只读用户",
        role="readonly",
        is_active=True,
    )
    primary = models.WarehousePrimaryCategory(
        code="DISPLAY_AUDIO_VIDEO", name="显示与音视频设备", is_active=True
    )
    db.add_all((writer, readonly, primary))
    db.flush()
    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id,
        code="API_LOW_VALUE",
        name="API 低值物料",
        is_active=True,
    )
    db.add(secondary)
    office_primary = models.WarehousePrimaryCategory(
        code="OFFICE_GENERAL_CONSUMABLES", name="办公与通用耗材", is_active=True
    )
    db.add(office_primary)
    db.flush()
    office_secondary = models.WarehouseSecondaryCategory(
        primary_category_id=office_primary.id,
        code="API_OFFICE",
        name="API 办公耗材",
        is_active=True,
    )
    db.add(office_secondary)
    db.flush()

    def add_material(name: str, policy: str, quantity: int) -> models.WarehouseAsset:
        material = models.WarehouseAsset(
            name=name,
            category=primary.name,
            subcategory=secondary.name,
            total_quantity=quantity,
            available_quantity=quantity,
            allocated_quantity=0,
            minimum_stock=0,
            low_stock_threshold=0,
            primary_category_id=primary.id,
            secondary_category_id=secondary.id,
            classification_status="ACTIVE",
            material_kind="NON_FIXED",
            issue_policy=policy,
        )
        db.add(material)
        return material

    returnable = add_material("显示器", "RETURNABLE", 10)
    consumable = add_material("鼠标", "CONSUMABLE", 10)
    invalid_policy = models.WarehouseAsset(
        name="API 非法策略办公物料",
        category=office_primary.name,
        subcategory=office_secondary.name,
        total_quantity=5,
        available_quantity=5,
        allocated_quantity=0,
        minimum_stock=0,
        low_stock_threshold=0,
        primary_category_id=office_primary.id,
        secondary_category_id=office_secondary.id,
        classification_status="ACTIVE",
        material_kind="NON_FIXED",
        issue_policy="RETURNABLE",
    )
    db.add(invalid_policy)
    db.commit()

    context: dict[str, Any] = {
        "writer": writer,
        "readonly": readonly,
        "current_user": writer,
        "returnable_id": returnable.id,
        "consumable_id": consumable.id,
        "invalid_policy_id": invalid_policy.id,
    }
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[get_current_active_user] = lambda: context["current_user"]
    with TestClient(main.app) as client:
        yield client, db, context
    main.app.dependency_overrides.clear()
    db.close()
    models.Base.metadata.drop_all(engine)
    engine.dispose()


def _issue_payload(material_id: int, quantity: int) -> dict[str, object]:
    return {
        "warehouse_asset_id": material_id,
        "quantity": quantity,
        "issued_at": "2025-01-02T09:30:00",
    }


def _material_state(db: Session, material_ids: tuple[int, ...]) -> tuple[object, ...]:
    """记录失败和权限拒绝前后必须一致的库存、领域记录与审计状态。"""
    db.expire_all()
    inventories = tuple(
        (material.id, material.total_quantity, material.available_quantity, material.allocated_quantity)
        for material in db.query(models.WarehouseAsset)
        .filter(models.WarehouseAsset.id.in_(material_ids))
        .order_by(models.WarehouseAsset.id)
    )
    issues = tuple(
        (
            issue.id,
            issue.warehouse_asset_id,
            issue.record_type,
            issue.issue_policy,
            issue.quantity,
            issue.unreturned_quantity,
            issue.consumed_completed,
        )
        for issue in db.query(models.MaterialIssue).order_by(models.MaterialIssue.id)
    )
    returns = tuple(
        (record.id, record.material_issue_id, record.quantity, record.operator_id)
        for record in db.query(models.MaterialReturn).order_by(models.MaterialReturn.id)
    )
    audits = tuple(
        (audit.id, audit.action, audit.resource_type, audit.resource_id)
        for audit in db.query(models.OperationLog).order_by(models.OperationLog.id)
    )
    return inventories, issues, returns, audits


def test_issue_accepts_all_optional_recipient_fields_as_empty(
    material_issue_api_env,
) -> None:
    """补充信息全部为空时，仍可创建待归还记录并扣减库存。"""
    client, db, context = material_issue_api_env
    response = client.post(
        "/material-issues",
        json=_issue_payload(context["returnable_id"], 3),
    )

    assert response.status_code == 200
    payload = response.json()
    issue = payload["material_issue"]
    assert issue["record_type"] == "RETURNABLE"
    assert issue["issue_policy"] == "RETURNABLE"
    assert issue["quantity"] == issue["unreturned_quantity"] == 3
    assert issue["consumed_completed"] is False
    assert {field: issue[field] for field in (
        "recipient_name",
        "recipient_employee_id",
        "recipient_department",
        "purpose",
    )} == {
        "recipient_name": None,
        "recipient_employee_id": None,
        "recipient_department": None,
        "purpose": None,
    }
    assert payload["inventory"] == {
        "id": context["returnable_id"],
        "name": "显示器",
        "total_quantity": 10,
        "available_quantity": 7,
        "allocated_quantity": 3,
        "low_stock": False,
        "low_stock_message": None,
    }
    assert payload["audit_log_id"] > 0
    assert db.get(models.MaterialIssue, issue["id"]).recipient_name is None


def test_issue_rejects_invalid_policy_and_insufficient_stock_without_side_effects(
    material_issue_api_env,
) -> None:
    """非法策略和库存不足分别返回中文业务错误，且不写入任何部分结果。"""
    client, db, context = material_issue_api_env
    material_ids = (
        context["returnable_id"],
        context["invalid_policy_id"],
    )
    before = _material_state(db, material_ids)

    invalid_policy = client.post(
        "/material-issues",
        json=_issue_payload(context["invalid_policy_id"], 1),
    )
    assert invalid_policy.status_code == 400
    assert "办公与通用耗材仅支持“一次性消耗品”领用策略" in invalid_policy.json()["detail"]
    assert _material_state(db, material_ids) == before

    insufficient = client.post(
        "/material-issues",
        json=_issue_payload(context["returnable_id"], 11),
    )
    assert insufficient.status_code == 409
    assert insufficient.json()["detail"] == "物料可用库存不足"
    assert _material_state(db, material_ids) == before


def test_return_endpoint_supports_partial_then_full_return_with_exact_inventory(
    material_issue_api_env,
) -> None:
    """部分和全量归还均应精确更新待归还余额、库存和归还记录。"""
    client, db, context = material_issue_api_env
    issued = client.post(
        "/material-issues",
        json={
            **_issue_payload(context["returnable_id"], 5),
            "recipient_name": "领用人甲",
            "recipient_employee_id": "EMP-001",
            "recipient_department": "信息部",
            "purpose": "会议室展示",
        },
    )
    assert issued.status_code == 200
    issue_id = issued.json()["material_issue"]["id"]

    partial = client.post(
        f"/material-issues/{issue_id}/returns",
        json={"quantity": 2, "returned_at": "2025-01-03T10:00:00"},
    )
    assert partial.status_code == 200
    assert partial.json()["material_return"]["quantity"] == 2
    assert partial.json()["material_issue"]["unreturned_quantity"] == 3
    assert partial.json()["inventory"]["available_quantity"] == 7
    assert partial.json()["inventory"]["allocated_quantity"] == 3

    full = client.post(
        f"/material-issues/{issue_id}/returns",
        json={"quantity": 3, "returned_at": "2025-01-04T10:00:00"},
    )
    assert full.status_code == 200
    assert full.json()["material_issue"]["unreturned_quantity"] == 0
    assert full.json()["inventory"]["available_quantity"] == 10
    assert full.json()["inventory"]["allocated_quantity"] == 0
    assert db.query(models.MaterialReturn).filter(
        models.MaterialReturn.material_issue_id == issue_id
    ).count() == 2


def test_return_endpoint_rejects_consumable_record_without_side_effects(
    material_issue_api_env,
) -> None:
    """一次性消耗完成记录不得归还或回补库存。"""
    client, db, context = material_issue_api_env
    issued = client.post(
        "/material-issues",
        json=_issue_payload(context["consumable_id"], 4),
    )
    assert issued.status_code == 200
    issue_id = issued.json()["material_issue"]["id"]
    assert issued.json()["material_issue"]["consumed_completed"] is True
    before = _material_state(db, (context["consumable_id"],))

    rejected = client.post(
        f"/material-issues/{issue_id}/returns",
        json={"quantity": 1, "returned_at": "2025-01-03T09:30:00"},
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "一次性消耗品不允许归还"
    assert _material_state(db, (context["consumable_id"],)) == before


def test_audit_failure_rolls_back_material_issue_api_transaction(
    material_issue_api_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """审计日志持久化失败时，发放记录、库存和审计均须整体回滚。"""
    client, db, context = material_issue_api_env
    material_id = context["returnable_id"]
    before = _material_state(db, (material_id,))

    def fail_audit(*_args: Any, **_kwargs: Any) -> None:
        raise AuditLogPersistenceError()

    monkeypatch.setattr(
        material_issuance_service.DomainTransaction,
        "record_audit",
        fail_audit,
    )
    response = client.post("/material-issues", json=_issue_payload(material_id, 2))

    assert response.status_code == 500
    assert "审计日志保存失败" in response.json()["detail"]
    assert _material_state(db, (material_id,)) == before


def test_readonly_user_cannot_issue_or_return_materials(
    material_issue_api_env,
) -> None:
    """只读用户对发放和归还两个写端点均被拒绝，且数据保持不变。"""
    client, db, context = material_issue_api_env
    issued = client.post(
        "/material-issues",
        json=_issue_payload(context["returnable_id"], 2),
    )
    assert issued.status_code == 200
    issue_id = issued.json()["material_issue"]["id"]
    context["current_user"] = context["readonly"]
    before = _material_state(db, (context["returnable_id"],))

    issue_denied = client.post(
        "/material-issues",
        json=_issue_payload(context["returnable_id"], 1),
    )
    assert issue_denied.status_code == 403
    assert issue_denied.json()["detail"] == READONLY_WRITE_ERROR
    assert _material_state(db, (context["returnable_id"],)) == before

    return_denied = client.post(
        f"/material-issues/{issue_id}/returns",
        json={"quantity": 1, "returned_at": "2025-01-03T09:30:00"},
    )
    assert return_denied.status_code == 403
    assert return_denied.json()["detail"] == READONLY_WRITE_ERROR
    assert _material_state(db, (context["returnable_id"],)) == before
