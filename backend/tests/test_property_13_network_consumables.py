"""网络与机房耗材用途关联及库存原子性的属性测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import models
from material_issuance_service import MaterialIssuanceError, issue_network_consumable
from transaction_audit import AuditLogPersistenceError


NETWORK_CASES = st.sampled_from((
    "valid_empty", "valid_department", "valid_project", "valid_server_room",
    "valid_work_order", "valid_mixed", "invalid_department", "blank_project",
    "non_positive_quantity", "insufficient_stock", "persistence_failure",
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


def _create_context(
    db: Session, *, token: int, available_quantity: int
) -> tuple[models.User, models.WarehouseAsset, models.Department]:
    """创建活动网络耗材、经办人与真实有效部门关联。"""
    operator = models.User(
        username=f"property13-operator-{token}",
        hashed_password="not-used-by-property-test",
        full_name="Property 13 经办人",
        is_active=True,
    )
    department = models.Department(name=f"P13 网络运维部 {token}")
    primary = models.WarehousePrimaryCategory(
        code="NETWORK_SERVER_ROOM_CONSUMABLES",
        name=f"P13 网络与机房耗材 {token}",
        is_active=True,
    )
    db.add_all((operator, department, primary))
    db.flush()
    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id,
        code=f"P13-NETWORK-{token}",
        name=f"P13 网络耗材 {token}",
        is_active=True,
    )
    db.add(secondary)
    db.flush()
    material = models.WarehouseAsset(
        name=f"P13 网线 {token}",
        category=primary.name,
        subcategory=secondary.name,
        total_quantity=available_quantity,
        available_quantity=available_quantity,
        allocated_quantity=0,
        minimum_stock=0,
        low_stock_threshold=0,
        primary_category_id=primary.id,
        secondary_category_id=secondary.id,
        classification_status="ACTIVE",
        material_kind="NON_FIXED",
        issue_policy="CONSUMABLE",
    )
    db.add(material)
    db.commit()
    return operator, material, department


def _state(db: Session, material_id: int) -> tuple[Any, ...]:
    """获取失败操作必须保持不变的库存、领域记录与审计状态。"""
    db.expire_all()
    material = db.get(models.WarehouseAsset, material_id)
    assert material is not None
    material_issues = tuple(
        (issue.id, issue.warehouse_asset_id, issue.quantity, issue.unreturned_quantity,
         issue.consumed_completed)
        for issue in db.query(models.MaterialIssue)
        .filter(models.MaterialIssue.warehouse_asset_id == material_id)
        .order_by(models.MaterialIssue.id)
    )
    network_issues = tuple(
        (issue.id, issue.material_issue_id, issue.department_id, issue.project_ref,
         issue.server_room_ref, issue.work_order_ref)
        for issue in db.query(models.NetworkConsumableIssue)
        .order_by(models.NetworkConsumableIssue.id)
    )
    audits = tuple(
        (audit.id, audit.action, audit.resource_type, audit.resource_id)
        for audit in db.query(models.OperationLog).order_by(models.OperationLog.id)
    )
    return (
        (material.total_quantity, material.available_quantity, material.allocated_quantity),
        material_issues,
        network_issues,
        audits,
    )


def _assert_audit_flush_failure(db: Session, command: Callable[[], Any]) -> None:
    """在审计日志写入时失败，验证此前的领域写入和扣库同步回滚。"""
    original_flush = db.flush

    def fail_audit_flush(*args: Any, **kwargs: Any) -> Any:
        if any(isinstance(item, models.OperationLog) for item in db.new):
            raise RuntimeError("injected network consumable audit persistence failure")
        return original_flush(*args, **kwargs)

    db.flush = fail_audit_flush  # type: ignore[method-assign]
    try:
        with pytest.raises(AuditLogPersistenceError, match="审计日志保存失败"):
            command()
    finally:
        db.flush = original_flush  # type: ignore[method-assign]


# Feature: asset-category-and-issuance-management, Property 13: 网络机房耗材用途关联与扣库原子性
# **Validates: Requirements 9.1, 9.2, 9.3, 9.4**
@settings(max_examples=100, deadline=None)
@given(
    case=NETWORK_CASES,
    token=st.integers(min_value=1, max_value=1_000_000),
    available_quantity=st.integers(min_value=1, max_value=100),
    requested_quantity=st.integers(min_value=1, max_value=100),
    non_positive_quantity=st.integers(min_value=-100, max_value=0),
    issued_offset_minutes=st.integers(min_value=0, max_value=525_600),
)
def test_property_13_network_consumable_purpose_and_inventory_atomicity(
    case: str,
    token: int,
    available_quantity: int,
    requested_quantity: int,
    non_positive_quantity: int,
    issued_offset_minutes: int,
) -> None:
    """空用途可发放；有效用途持久化，非法输入及审计失败均完整回滚。"""
    db, engine = _new_session()
    try:
        operator, material, department = _create_context(
            db, token=token, available_quantity=available_quantity
        )
        quantity = min(requested_quantity, available_quantity)
        department_id: int | None = None
        project_ref: str | None = None
        server_room_ref: str | None = None
        work_order_ref: str | None = None
        issued_at = datetime(2025, 1, 2, 8, 0) + timedelta(
            minutes=issued_offset_minutes
        )

        if case == "valid_department":
            department_id = department.id
        elif case == "valid_project":
            project_ref = f"P13-PROJECT-{token}"
        elif case == "valid_server_room":
            server_room_ref = f"P13-ROOM-{token}"
        elif case == "valid_work_order":
            work_order_ref = f"P13-WORK-{token}"
        elif case in {"valid_mixed", "persistence_failure"}:
            department_id = department.id
            project_ref = f"P13-PROJECT-{token}"
            server_room_ref = f"P13-ROOM-{token}"
            work_order_ref = f"P13-WORK-{token}"
        elif case == "invalid_department":
            department_id = department.id + 100_000
        elif case == "blank_project":
            project_ref = " "
        elif case == "non_positive_quantity":
            quantity = non_positive_quantity
        elif case == "insufficient_stock":
            quantity = available_quantity + 1

        command = lambda: issue_network_consumable(
            db,
            warehouse_asset_id=material.id,
            quantity=quantity,
            issued_at=issued_at,
            operator_id=operator.id,
            department_id=department_id,
            project_ref=project_ref,
            server_room_ref=server_room_ref,
            work_order_ref=work_order_ref,
        )
        if case.startswith("valid_"):
            result = command()
            db.expire_all()
            persisted_material = db.get(models.WarehouseAsset, material.id)
            issue = db.get(models.MaterialIssue, result.issue.id)
            network_issue = db.get(
                models.NetworkConsumableIssue, result.specialized_issue.id
            )
            assert persisted_material is not None
            assert issue is not None and network_issue is not None
            assert issue.warehouse_asset_id == material.id
            assert issue.record_type == issue.issue_policy == "CONSUMABLE"
            assert issue.quantity == quantity
            assert issue.unreturned_quantity == 0 and issue.consumed_completed is True
            assert issue.issued_at == issued_at and issue.operator_id == operator.id
            assert network_issue.material_issue_id == issue.id
            assert network_issue.department_id == department_id
            assert network_issue.project_ref == project_ref
            assert network_issue.server_room_ref == server_room_ref
            assert network_issue.work_order_ref == work_order_ref
            assert persisted_material.total_quantity == available_quantity
            assert persisted_material.available_quantity == available_quantity - quantity
            assert persisted_material.allocated_quantity == quantity
            assert result.audit_log.action == "issue_network_consumable"
            assert result.audit_log.resource_id == network_issue.id
            return

        before = _state(db, material.id)
        if case == "persistence_failure":
            _assert_audit_flush_failure(db, command)
        else:
            with pytest.raises(MaterialIssuanceError):
                command()
        assert _state(db, material.id) == before
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
