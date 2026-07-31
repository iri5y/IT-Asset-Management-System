"""低值待归还物料归还余额和拒绝语义的属性测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import models
from category_policy import IssuePolicy
from material_issuance_service import MaterialIssuanceError, issue_material, return_material
from transaction_audit import AuditLogPersistenceError


RETURN_CASES = st.sampled_from(
    (
        "partial_return",
        "full_return",
        "consumable_issue",
        "excessive_quantity",
        "non_positive_quantity",
        "invalid_association",
        "persistence_failure",
    )
)


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
    issued_quantity: int,
    reserve_quantity: int,
    policy: IssuePolicy,
) -> tuple[models.User, models.WarehouseAsset, models.MaterialIssue]:
    """创建有效目录、库存和已发放的低值记录，作为归还的真实前置状态。"""
    operator = models.User(
        username=f"property8-operator-{token}",
        hashed_password="not-used-by-property-test",
        full_name="Property 8 经办人",
        is_active=True,
    )
    primary = models.WarehousePrimaryCategory(
        code=f"P8-PRIMARY-{token}",
        name=f"P8 一级分类 {token}",
        is_active=True,
    )
    db.add_all((operator, primary))
    db.flush()
    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id,
        code=f"P8-SECONDARY-{token}",
        name=f"P8 二级分类 {token}",
        is_active=True,
    )
    db.add(secondary)
    db.flush()
    initial_quantity = issued_quantity + reserve_quantity
    material = models.WarehouseAsset(
        name=f"P8 低值物料 {token}",
        category=primary.name,
        subcategory=secondary.name,
        total_quantity=initial_quantity,
        available_quantity=initial_quantity,
        allocated_quantity=0,
        minimum_stock=0,
        low_stock_threshold=0,
        primary_category_id=primary.id,
        secondary_category_id=secondary.id,
        classification_status="ACTIVE",
        material_kind="NON_FIXED",
        issue_policy=policy.value,
    )
    db.add(material)
    db.commit()
    issue = issue_material(
        db,
        warehouse_asset_id=material.id,
        quantity=issued_quantity,
        issued_at=datetime(2025, 1, 1, 8, 0),
        operator_id=operator.id,
    ).issue
    return operator, material, issue


def _state(
    db: Session,
    *,
    material_id: int,
    issue_id: int,
) -> tuple[Any, ...]:
    """返回归还失败时必须保持不变的物料、领用、归还和审计状态。"""
    db.expire_all()
    material = db.get(models.WarehouseAsset, material_id)
    issue = db.get(models.MaterialIssue, issue_id)
    assert material is not None
    assert issue is not None
    returns = tuple(
        (
            item.id,
            item.material_issue_id,
            item.quantity,
            item.returned_at,
            item.operator_id,
        )
        for item in db.query(models.MaterialReturn)
        .filter(models.MaterialReturn.material_issue_id == issue_id)
        .order_by(models.MaterialReturn.id)
    )
    audits = tuple(
        (item.id, item.action, item.resource_type, item.resource_id)
        for item in db.query(models.OperationLog).order_by(models.OperationLog.id)
    )
    return (
        (
            material.total_quantity,
            material.available_quantity,
            material.allocated_quantity,
        ),
        (
            issue.warehouse_asset_id,
            issue.record_type,
            issue.issue_policy,
            issue.quantity,
            issue.unreturned_quantity,
            issue.consumed_completed,
        ),
        returns,
        audits,
    )


def _assert_audit_flush_failure(
    db: Session,
    command: Callable[[], Any],
) -> None:
    """只在写入归还审计日志时注入故障，覆盖真实事务的整体回滚。"""
    original_flush = db.flush

    def fail_audit_flush(*args: Any, **kwargs: Any) -> Any:
        if any(isinstance(item, models.OperationLog) for item in db.new):
            raise RuntimeError("injected material return audit persistence failure")
        return original_flush(*args, **kwargs)

    db.flush = fail_audit_flush  # type: ignore[method-assign]
    try:
        with pytest.raises(AuditLogPersistenceError, match="审计日志保存失败"):
            command()
    finally:
        db.flush = original_flush  # type: ignore[method-assign]


# Feature: asset-category-and-issuance-management, Property 8: 待归还余额与消耗品禁止归还
# **Validates: Requirements 6.7, 6.8, 6.9, 6.10**
@settings(max_examples=100, deadline=None)
@given(
    case=RETURN_CASES,
    token=st.integers(min_value=1, max_value=1_000_000),
    issued_quantity=st.integers(min_value=2, max_value=100),
    reserve_quantity=st.integers(min_value=0, max_value=100),
    partial_candidate=st.integers(min_value=1, max_value=100),
    excessive_quantity=st.integers(min_value=1, max_value=100),
    non_positive_quantity=st.integers(min_value=-100, max_value=0),
    returned_offset_minutes=st.integers(min_value=0, max_value=525_600),
)
def test_property_8_returnable_balance_and_consumable_return_rejection(
    case: str,
    token: int,
    issued_quantity: int,
    reserve_quantity: int,
    partial_candidate: int,
    excessive_quantity: int,
    non_positive_quantity: int,
    returned_offset_minutes: int,
) -> None:
    """合法部分/全量归还精确回补库存；所有无效归还或持久化故障均无副作用。"""
    policy = (
        IssuePolicy.CONSUMABLE
        if case == "consumable_issue"
        else IssuePolicy.RETURNABLE
    )
    db, engine = _new_session()
    try:
        operator, material, issue = _create_context(
            db,
            token=token,
            issued_quantity=issued_quantity,
            reserve_quantity=reserve_quantity,
            policy=policy,
        )
        returned_at = datetime(2025, 1, 2, 8, 0) + timedelta(
            minutes=returned_offset_minutes
        )
        if case == "partial_return":
            return_quantity = min(partial_candidate, issued_quantity - 1)
        elif case == "full_return":
            return_quantity = issued_quantity
        elif case == "excessive_quantity":
            return_quantity = issued_quantity + excessive_quantity
        elif case == "non_positive_quantity":
            return_quantity = non_positive_quantity
        else:
            return_quantity = min(partial_candidate, issued_quantity)

        if case in {"partial_return", "full_return"}:
            result = return_material(
                db,
                material_issue_id=issue.id,
                quantity=return_quantity,
                returned_at=returned_at,
                operator_id=operator.id,
            )
            db.expire_all()
            persisted_material = db.get(models.WarehouseAsset, material.id)
            persisted_issue = db.get(models.MaterialIssue, issue.id)
            persisted_return = db.get(models.MaterialReturn, result.material_return.id)
            assert persisted_material is not None
            assert persisted_issue is not None
            assert persisted_return is not None
            assert persisted_return.material_issue_id == issue.id
            assert persisted_return.quantity == return_quantity
            assert persisted_return.returned_at == returned_at
            assert persisted_return.operator_id == operator.id
            assert persisted_issue.unreturned_quantity == issued_quantity - return_quantity
            assert persisted_material.total_quantity == issued_quantity + reserve_quantity
            assert persisted_material.available_quantity == reserve_quantity + return_quantity
            assert persisted_material.allocated_quantity == issued_quantity - return_quantity
            assert result.audit_log.action == "return_material"
            assert result.audit_log.resource_id == persisted_return.id
            if case == "partial_return":
                assert 0 < persisted_issue.unreturned_quantity < issued_quantity
            else:
                assert persisted_issue.unreturned_quantity == 0
            return

        before = _state(db, material_id=material.id, issue_id=issue.id)
        if case == "persistence_failure":
            _assert_audit_flush_failure(
                db,
                lambda: return_material(
                    db,
                    material_issue_id=issue.id,
                    quantity=return_quantity,
                    returned_at=returned_at,
                    operator_id=operator.id,
                ),
            )
        else:
            invalid_issue_id = issue.id + 100_000 if case == "invalid_association" else issue.id
            with pytest.raises(MaterialIssuanceError):
                return_material(
                    db,
                    material_issue_id=invalid_issue_id,
                    quantity=return_quantity,
                    returned_at=returned_at,
                    operator_id=operator.id,
                )
        assert _state(db, material_id=material.id, issue_id=issue.id) == before
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
