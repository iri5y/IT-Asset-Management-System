"""IT 工具借还余额状态机的属性测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import models
from material_issuance_service import (
    MaterialIssuanceError,
    borrow_tool,
    return_tool,
)
from transaction_audit import AuditLogPersistenceError


TOOL_LOAN_CASES = st.sampled_from(
    (
        "partial_return",
        "full_return",
        "invalid_borrower",
        "non_positive_borrow_quantity",
        "insufficient_borrow_stock",
        "invalid_expected_return_date",
        "borrow_persistence_failure",
        "non_positive_return_quantity",
        "excessive_return_quantity",
        "missing_loan",
        "returned_loan",
        "return_persistence_failure",
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
    available_quantity: int,
) -> tuple[models.User, models.WarehouseAsset]:
    """创建有效 IT 工具物料、目录和经办人。"""
    operator = models.User(
        username=f"property14-operator-{token}",
        hashed_password="not-used-by-property-test",
        full_name="Property 14 经办人",
        is_active=True,
    )
    primary = models.WarehousePrimaryCategory(
        code="IT_TOOLS_LOAN_ITEMS",
        name=f"P14 IT工具与借用物品 {token}",
        is_active=True,
    )
    db.add_all((operator, primary))
    db.flush()
    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id,
        code=f"P14-TOOLS-{token}",
        name=f"P14 工具 {token}",
        is_active=True,
    )
    db.add(secondary)
    db.flush()
    material = models.WarehouseAsset(
        name=f"P14 工具箱 {token}",
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
        issue_policy="RETURNABLE",
    )
    db.add(material)
    db.commit()
    return operator, material


def _state(db: Session, material_id: int) -> tuple[Any, ...]:
    """返回失败借还命令必须完整保持不变的库存、借用、归还及审计状态。"""
    db.expire_all()
    material = db.get(models.WarehouseAsset, material_id)
    assert material is not None
    loans = tuple(
        (
            loan.id,
            loan.warehouse_asset_id,
            loan.borrower_ref,
            loan.quantity,
            loan.unreturned_quantity,
            loan.status,
            loan.borrowed_at,
            loan.expected_return_at,
            loan.returned_at,
            loan.operator_id,
        )
        for loan in db.query(models.ToolLoan)
        .filter(models.ToolLoan.warehouse_asset_id == material_id)
        .order_by(models.ToolLoan.id)
    )
    return_events = tuple(
        (
            event.id,
            event.tool_loan_id,
            event.quantity,
            event.is_partial,
            event.returned_at,
            event.operator_id,
        )
        for event in db.query(models.ToolLoanReturnEvent)
        .join(models.ToolLoan)
        .filter(models.ToolLoan.warehouse_asset_id == material_id)
        .order_by(models.ToolLoanReturnEvent.id)
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
        loans,
        return_events,
        audits,
    )


def _assert_audit_flush_failure(
    db: Session,
    command: Callable[[], Any],
) -> None:
    """仅在审计写入时注入失败，确认领域写入和库存事务会整体回滚。"""
    original_flush = db.flush

    def fail_audit_flush(*args: Any, **kwargs: Any) -> Any:
        if any(isinstance(item, models.OperationLog) for item in db.new):
            raise RuntimeError("injected tool loan audit persistence failure")
        return original_flush(*args, **kwargs)

    db.flush = fail_audit_flush  # type: ignore[method-assign]
    try:
        with pytest.raises(AuditLogPersistenceError, match="审计日志保存失败"):
            command()
    finally:
        db.flush = original_flush  # type: ignore[method-assign]


# Feature: asset-category-and-issuance-management, Property 14: 工具借还余额状态机
# **Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.7**
@settings(max_examples=100, deadline=None)
@given(
    case=TOOL_LOAN_CASES,
    token=st.integers(min_value=1, max_value=1_000_000),
    available_quantity=st.integers(min_value=2, max_value=100),
    requested_quantity=st.integers(min_value=2, max_value=100),
    partial_candidate=st.integers(min_value=1, max_value=100),
    non_positive_quantity=st.integers(min_value=-100, max_value=0),
    excessive_quantity=st.integers(min_value=1, max_value=100),
    borrowed_offset_minutes=st.integers(min_value=0, max_value=525_600),
    return_offset_minutes=st.integers(min_value=0, max_value=525_600),
)
def test_property_14_tool_loan_balance_state_machine(
    case: str,
    token: int,
    available_quantity: int,
    requested_quantity: int,
    partial_candidate: int,
    non_positive_quantity: int,
    excessive_quantity: int,
    borrowed_offset_minutes: int,
    return_offset_minutes: int,
) -> None:
    """合格借还精确维护余额；非法输入和审计故障不留下任何部分结果。"""
    db, engine = _new_session()
    try:
        operator, material = _create_context(
            db,
            token=token,
            available_quantity=available_quantity,
        )
        borrowed_at = datetime(2025, 1, 1, 8, 0) + timedelta(
            minutes=borrowed_offset_minutes
        )
        expected_return_at = borrowed_at + timedelta(days=1)
        returned_at = borrowed_at + timedelta(
            minutes=return_offset_minutes + 1
        )
        borrowed_quantity = min(requested_quantity, available_quantity)

        def borrow_command(
            *,
            borrower_ref: str = f"P14-BORROWER-{token}",
            quantity: int = borrowed_quantity,
            expected_at: datetime = expected_return_at,
            material_id: int = material.id,
        ) -> Any:
            return borrow_tool(
                db,
                warehouse_asset_id=material_id,
                borrower_ref=borrower_ref,
                quantity=quantity,
                borrowed_at=borrowed_at,
                expected_return_at=expected_at,
                operator_id=operator.id,
            )

        if case in {
            "invalid_borrower",
            "non_positive_borrow_quantity",
            "insufficient_borrow_stock",
            "invalid_expected_return_date",
            "borrow_persistence_failure",
        }:
            before = _state(db, material.id)
            if case == "invalid_borrower":
                command = lambda: borrow_command(borrower_ref=" ")
            elif case == "non_positive_borrow_quantity":
                command = lambda: borrow_command(quantity=non_positive_quantity)
            elif case == "insufficient_borrow_stock":
                command = lambda: borrow_command(quantity=available_quantity + 1)
            elif case == "invalid_expected_return_date":
                command = lambda: borrow_command(
                    expected_at=borrowed_at - timedelta(seconds=1)
                )
            else:
                command = borrow_command

            if case == "borrow_persistence_failure":
                _assert_audit_flush_failure(db, command)
            else:
                with pytest.raises(MaterialIssuanceError):
                    command()
            assert _state(db, material.id) == before
            return

        loan_result = borrow_command()
        db.expire_all()
        loan = db.get(models.ToolLoan, loan_result.loan.id)
        borrowed_material = db.get(models.WarehouseAsset, material.id)
        assert loan is not None and borrowed_material is not None
        assert loan.warehouse_asset_id == material.id
        assert loan.borrower_ref == f"P14-BORROWER-{token}"
        assert loan.quantity == borrowed_quantity
        assert loan.unreturned_quantity == borrowed_quantity
        assert loan.status == "BORROWED"
        assert loan.borrowed_at == borrowed_at
        assert loan.expected_return_at == expected_return_at
        assert loan.returned_at is None
        assert borrowed_material.total_quantity == available_quantity
        assert borrowed_material.available_quantity == available_quantity - borrowed_quantity
        assert borrowed_material.allocated_quantity == borrowed_quantity
        assert loan_result.audit_log.action == "borrow_tool"
        assert loan_result.audit_log.resource_id == loan.id

        if case == "partial_return":
            return_quantity = min(partial_candidate, borrowed_quantity - 1)
        elif case == "full_return":
            return_quantity = borrowed_quantity
        elif case == "non_positive_return_quantity":
            return_quantity = non_positive_quantity
        elif case == "excessive_return_quantity":
            return_quantity = borrowed_quantity + excessive_quantity
        else:
            return_quantity = borrowed_quantity

        if case == "returned_loan":
            return_tool(
                db,
                tool_loan_id=loan.id,
                quantity=borrowed_quantity,
                returned_at=returned_at,
                operator_id=operator.id,
            )

        before = _state(db, material.id)
        if case in {"partial_return", "full_return"}:
            result = return_tool(
                db,
                tool_loan_id=loan.id,
                quantity=return_quantity,
                returned_at=returned_at,
                operator_id=operator.id,
            )
            db.expire_all()
            persisted_loan = db.get(models.ToolLoan, loan.id)
            persisted_event = db.get(models.ToolLoanReturnEvent, result.return_event.id)
            persisted_material = db.get(models.WarehouseAsset, material.id)
            assert persisted_loan is not None
            assert persisted_event is not None
            assert persisted_material is not None
            assert persisted_event.tool_loan_id == loan.id
            assert persisted_event.quantity == return_quantity
            assert persisted_event.returned_at == returned_at
            assert persisted_event.operator_id == operator.id
            assert persisted_event.is_partial is (case == "partial_return")
            assert persisted_loan.unreturned_quantity == borrowed_quantity - return_quantity
            assert persisted_material.total_quantity == available_quantity
            assert persisted_material.available_quantity == (
                available_quantity - borrowed_quantity + return_quantity
            )
            assert persisted_material.allocated_quantity == borrowed_quantity - return_quantity
            assert result.audit_log.action == "return_tool"
            assert result.audit_log.resource_id == persisted_event.id
            if case == "partial_return":
                assert persisted_loan.status == "BORROWED"
                assert 0 < persisted_loan.unreturned_quantity < borrowed_quantity
                assert persisted_loan.returned_at is None
            else:
                assert persisted_loan.status == "RETURNED"
                assert persisted_loan.unreturned_quantity == 0
                assert persisted_loan.returned_at == returned_at
            return

        invalid_loan_id = loan.id + 100_000 if case == "missing_loan" else loan.id
        command = lambda: return_tool(
            db,
            tool_loan_id=invalid_loan_id,
            quantity=return_quantity,
            returned_at=returned_at,
            operator_id=operator.id,
        )
        if case == "return_persistence_failure":
            _assert_audit_flush_failure(db, command)
        else:
            with pytest.raises(MaterialIssuanceError):
                command()
        assert _state(db, material.id) == before
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
