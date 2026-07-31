"""非固定资产物料发放输入验证与补充信息保真的属性测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import models
from material_issuance_service import MaterialIssuanceError, issue_material


INVALID_ISSUANCE_CASES = st.sampled_from(
    (
        "valid",
        "invalid_material",
        "invalid_quantity",
        "invalid_datetime",
        "inactive_operator",
        "insufficient_stock",
        "inactive_category",
    )
)
_OPTIONAL_TEXT_ALPHABET = tuple("领用人部门用途甲乙丙员工A B-01")
OPTIONAL_TEXT = st.one_of(
    st.none(),
    st.text(alphabet=_OPTIONAL_TEXT_ALPHABET, min_size=1, max_size=24),
)


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
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
    available_quantity: int,
) -> tuple[models.User, models.WarehouseSecondaryCategory, models.WarehouseAsset]:
    """创建一个具备有效两级目录关联的活动非固定物料。"""
    operator = models.User(
        username="property6-operator",
        hashed_password="not-used-by-property-test",
        full_name="Property 6 经办人",
        is_active=True,
    )
    primary = models.WarehousePrimaryCategory(
        code="INPUT_OFFICE_PERIPHERALS",
        name="P6 输入与办公外设",
        is_active=True,
    )
    db.add_all((operator, primary))
    db.flush()
    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id,
        code="P6-GENERAL-MATERIAL",
        name="P6 通用低值物料",
        is_active=True,
    )
    db.add(secondary)
    db.flush()
    material = models.WarehouseAsset(
        name="P6 通用物料",
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
    return operator, secondary, material


def _state(db: Session, material_id: int) -> tuple[Any, ...]:
    """记录拒绝前后应保持不变的发放记录、审计和库存状态。"""
    material = db.get(models.WarehouseAsset, material_id)
    assert material is not None
    return (
        material.total_quantity,
        material.available_quantity,
        material.allocated_quantity,
        db.query(models.MaterialIssue).count(),
        db.query(models.OperationLog).count(),
    )


# Feature: asset-category-and-issuance-management, Property 6: 非固定资产发放验证与可选信息保真
# Validates: Requirements 6.1, 6.2, 6.3
@settings(max_examples=100, deadline=None)
@given(
    case=INVALID_ISSUANCE_CASES,
    available_quantity=st.integers(min_value=1, max_value=50),
    requested_quantity=st.integers(min_value=1, max_value=50),
    invalid_quantity=st.integers(min_value=-50, max_value=0),
    issued_offset_minutes=st.integers(min_value=0, max_value=525_600),
    all_optional_empty=st.booleans(),
    recipient_name=OPTIONAL_TEXT,
    recipient_employee_id=OPTIONAL_TEXT,
    recipient_department=OPTIONAL_TEXT,
    purpose=OPTIONAL_TEXT,
)
def test_property_6_material_issue_validation_and_optional_data_fidelity(
    case: str,
    available_quantity: int,
    requested_quantity: int,
    invalid_quantity: int,
    issued_offset_minutes: int,
    all_optional_empty: bool,
    recipient_name: str | None,
    recipient_employee_id: str | None,
    recipient_department: str | None,
    purpose: str | None,
) -> None:
    """只有全部必填前置条件有效时可发放，补充字段永不被清洗或作为必填项。"""
    db, engine = _new_session()
    try:
        operator, secondary, material = _create_context(
            db, available_quantity=available_quantity
        )
        issued_at = datetime(2025, 1, 1, 8, 0) + timedelta(
            minutes=issued_offset_minutes
        )
        valid_quantity = min(requested_quantity, available_quantity)
        if all_optional_empty:
            recipient_name = None
            recipient_employee_id = None
            recipient_department = None
            purpose = None

        warehouse_asset_id = material.id
        quantity: int = valid_quantity
        submitted_issued_at: datetime | None = issued_at
        if case == "invalid_material":
            warehouse_asset_id = material.id + 100_000
        elif case == "invalid_quantity":
            quantity = invalid_quantity
        elif case == "invalid_datetime":
            submitted_issued_at = None
        elif case == "inactive_operator":
            operator.is_active = False
            db.commit()
        elif case == "insufficient_stock":
            quantity = available_quantity + 1
        elif case == "inactive_category":
            secondary.is_active = False
            db.commit()

        before = _state(db, material.id)
        if case != "valid":
            with pytest.raises(MaterialIssuanceError):
                issue_material(
                    db,
                    warehouse_asset_id=warehouse_asset_id,
                    quantity=quantity,
                    issued_at=submitted_issued_at,  # type: ignore[arg-type]
                    operator_id=operator.id,
                    recipient_name=recipient_name,
                    recipient_employee_id=recipient_employee_id,
                    recipient_department=recipient_department,
                    purpose=purpose,
                )
            assert _state(db, material.id) == before
            return

        result = issue_material(
            db,
            warehouse_asset_id=warehouse_asset_id,
            quantity=quantity,
            issued_at=issued_at,
            operator_id=operator.id,
            recipient_name=recipient_name,
            recipient_employee_id=recipient_employee_id,
            recipient_department=recipient_department,
            purpose=purpose,
        )
        persisted_issue = db.get(models.MaterialIssue, result.issue.id)
        persisted_material = db.get(models.WarehouseAsset, material.id)
        assert persisted_issue is not None
        assert persisted_material is not None
        assert persisted_issue.warehouse_asset_id == material.id
        assert persisted_issue.quantity == quantity
        assert persisted_issue.issued_at == issued_at
        assert persisted_issue.operator_id == operator.id
        assert persisted_issue.recipient_name == recipient_name
        assert persisted_issue.recipient_employee_id == recipient_employee_id
        assert persisted_issue.recipient_department == recipient_department
        assert persisted_issue.purpose == purpose
        assert persisted_material.available_quantity == available_quantity - quantity
        assert persisted_material.allocated_quantity == quantity
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
