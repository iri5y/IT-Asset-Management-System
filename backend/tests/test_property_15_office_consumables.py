"""办公与通用耗材一次性消耗发放的属性测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import models
from material_issuance_service import MaterialIssuanceError, issue_office_consumable
from transaction_audit import AuditLogPersistenceError


OFFICE_CONSUMABLE_CASES = st.sampled_from((
    "valid",
    "zero_quantity",
    "negative_quantity",
    "missing_material",
    "missing_quantity",
    "missing_issued_at",
    "missing_operator",
    "insufficient_stock",
    "persistence_failure",
))


def _enable_sqlite_foreign_keys(
    dbapi_connection: Any,
    _connection_record: Any,
) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _new_session() -> tuple[Session, Any]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    return session, engine


def _create_context(
    db: Session,
    *,
    token: int,
    available_quantity: int,
) -> tuple[models.User, models.WarehouseAsset]:
    """创建有效办公耗材、受控分类组合及已登录经办人。"""
    operator = models.User(
        username=f"property15-operator-{token}",
        hashed_password="not-used-by-property-test",
        full_name="Property 15 经办人",
        is_active=True,
    )
    primary = models.WarehousePrimaryCategory(
        code="OFFICE_GENERAL_CONSUMABLES",
        name=f"P15 办公与通用耗材 {token}",
        is_active=True,
    )
    db.add_all((operator, primary))
    db.flush()
    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id,
        code=f"P15-OFFICE-{token}",
        name=f"P15 办公耗材 {token}",
        is_active=True,
    )
    db.add(secondary)
    db.flush()
    material = models.WarehouseAsset(
        name=f"P15 打印纸 {token}",
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
    return operator, material


def _state(db: Session, material_id: int) -> tuple[Any, ...]:
    """返回拒绝发放后必须保持不变的库存、消耗记录和审计状态。"""
    db.expire_all()
    material = db.get(models.WarehouseAsset, material_id)
    assert material is not None
    issues = tuple(
        (
            issue.id,
            issue.warehouse_asset_id,
            issue.record_type,
            issue.issue_policy,
            issue.quantity,
            issue.unreturned_quantity,
            issue.consumed_completed,
            issue.operator_id,
            issue.issued_at,
        )
        for issue in db.query(models.MaterialIssue)
        .filter(models.MaterialIssue.warehouse_asset_id == material_id)
        .order_by(models.MaterialIssue.id)
    )
    audits = tuple(
        (audit.id, audit.action, audit.resource_type, audit.resource_id)
        for audit in db.query(models.OperationLog).order_by(models.OperationLog.id)
    )
    return (
        (
            material.total_quantity,
            material.available_quantity,
            material.allocated_quantity,
        ),
        issues,
        audits,
    )


def _assert_audit_flush_failure(db: Session, command: Callable[[], Any]) -> None:
    """注入审计落库故障，验证消耗记录和库存同一事务整体回滚。"""
    original_flush = db.flush

    def fail_audit_flush(*args: Any, **kwargs: Any) -> Any:
        if any(isinstance(item, models.OperationLog) for item in db.new):
            raise RuntimeError("injected office consumable audit persistence failure")
        return original_flush(*args, **kwargs)

    db.flush = fail_audit_flush  # type: ignore[method-assign]
    try:
        with pytest.raises(AuditLogPersistenceError, match="审计日志保存失败"):
            command()
    finally:
        db.flush = original_flush  # type: ignore[method-assign]


# Feature: asset-category-and-issuance-management, Property 15: 办公耗材作为一次性消耗品原子发放
# **Validates: Requirements 11.2, 11.3, 11.4**
@settings(max_examples=100, deadline=None)
@given(
    case=OFFICE_CONSUMABLE_CASES,
    token=st.integers(min_value=1, max_value=1_000_000),
    available_quantity=st.integers(min_value=1, max_value=100),
    requested_quantity=st.integers(min_value=1, max_value=100),
    negative_quantity=st.integers(min_value=-100, max_value=-1),
    issued_offset_minutes=st.integers(min_value=0, max_value=525_600),
)
def test_property_15_office_consumable_issue_is_atomic(
    case: str,
    token: int,
    available_quantity: int,
    requested_quantity: int,
    negative_quantity: int,
    issued_offset_minutes: int,
) -> None:
    """有效办公耗材发放创建完成消耗记录；任一拒绝路径均无库存或记录副作用。"""
    db, engine = _new_session()
    try:
        operator, material = _create_context(
            db,
            token=token,
            available_quantity=available_quantity,
        )
        quantity: Any = min(requested_quantity, available_quantity)
        material_id: Any = material.id
        issued_at: Any = datetime(2025, 1, 2, 8, 0) + timedelta(
            minutes=issued_offset_minutes
        )
        operator_id: Any = operator.id

        if case == "zero_quantity":
            quantity = 0
        elif case == "negative_quantity":
            quantity = negative_quantity
        elif case == "missing_material":
            material_id = None
        elif case == "missing_quantity":
            quantity = None
        elif case == "missing_issued_at":
            issued_at = None
        elif case == "missing_operator":
            operator_id = None
        elif case == "insufficient_stock":
            quantity = available_quantity + 1

        command = lambda: issue_office_consumable(
            db,
            warehouse_asset_id=material_id,
            quantity=quantity,
            issued_at=issued_at,
            operator_id=operator_id,
        )
        if case == "valid":
            result = command()
            db.expire_all()
            persisted_material = db.get(models.WarehouseAsset, material.id)
            issues = (
                db.query(models.MaterialIssue)
                .filter(models.MaterialIssue.warehouse_asset_id == material.id)
                .all()
            )
            assert persisted_material is not None
            assert len(issues) == 1
            issue = issues[0]
            assert issue.id == result.issue.id
            assert result.specialized_issue is None
            assert issue.warehouse_asset_id == material.id
            assert issue.record_type == issue.issue_policy == "CONSUMABLE"
            assert issue.quantity == quantity
            assert issue.unreturned_quantity == 0
            assert issue.consumed_completed is True
            assert issue.issued_at == issued_at
            assert issue.operator_id == operator.id
            assert persisted_material.total_quantity == available_quantity
            assert persisted_material.available_quantity == available_quantity - quantity
            assert persisted_material.allocated_quantity == quantity
            assert result.audit_log.action == "issue_office_consumable"
            assert result.audit_log.resource_id == issue.id
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
