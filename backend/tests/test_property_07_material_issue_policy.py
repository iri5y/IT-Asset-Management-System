"""低值物料按领用策略发放的属性测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from hypothesis import given, settings, strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import models
from category_policy import IssuePolicy
from material_issuance_service import issue_material


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
    policy: IssuePolicy,
) -> tuple[models.User, models.WarehouseAsset]:
    """创建策略有效、分类组合有效且库存充足的低值物料。"""
    operator = models.User(
        username=f"property7-operator-{token}",
        hashed_password="not-used-by-property-test",
        full_name="Property 7 经办人",
        is_active=True,
    )
    primary = models.WarehousePrimaryCategory(
        code=f"P7-PRIMARY-{token}",
        name=f"P7 一级分类 {token}",
        is_active=True,
    )
    db.add_all((operator, primary))
    db.flush()
    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id,
        code=f"P7-SECONDARY-{token}",
        name=f"P7 二级分类 {token}",
        is_active=True,
    )
    db.add(secondary)
    db.flush()
    material = models.WarehouseAsset(
        name=f"P7 低值物料 {token}",
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
        issue_policy=policy.value,
    )
    db.add(material)
    db.commit()
    return operator, material


# Feature: asset-category-and-issuance-management, Property 7: 低值发放按策略创建互斥记录并原子扣库
# **Validates: Requirements 6.4, 6.5, 6.6**
@settings(max_examples=100, deadline=None)
@given(
    policy=st.sampled_from((IssuePolicy.RETURNABLE, IssuePolicy.CONSUMABLE)),
    available_quantity=st.integers(min_value=1, max_value=100),
    data=st.data(),
    token=st.integers(min_value=1, max_value=1_000_000),
    issued_offset_minutes=st.integers(min_value=0, max_value=525_600),
)
def test_property_7_issue_policy_creates_exclusive_record_and_atomically_deducts_stock(
    policy: IssuePolicy,
    available_quantity: int,
    data: st.DataObject,
    token: int,
    issued_offset_minutes: int,
) -> None:
    """任意有效策略和充足库存都恰好提交匹配记录及对应的库存扣减。"""
    quantity = data.draw(
        st.integers(min_value=1, max_value=available_quantity),
        label="quantity",
    )
    db, engine = _new_session()
    try:
        operator, material = _create_context(
            db,
            token=token,
            available_quantity=available_quantity,
            policy=policy,
        )
        issued_at = datetime(2025, 1, 1, 8, 0) + timedelta(
            minutes=issued_offset_minutes
        )

        result = issue_material(
            db,
            warehouse_asset_id=material.id,
            quantity=quantity,
            issued_at=issued_at,
            operator_id=operator.id,
        )

        db.expire_all()
        persisted_material = db.get(models.WarehouseAsset, material.id)
        persisted_issues = (
            db.query(models.MaterialIssue)
            .filter(models.MaterialIssue.warehouse_asset_id == material.id)
            .all()
        )
        persisted_audits = (
            db.query(models.OperationLog)
            .filter(models.OperationLog.resource_type == "material_issue")
            .all()
        )
        assert persisted_material is not None
        assert len(persisted_issues) == 1
        assert len(persisted_audits) == 1

        issue = persisted_issues[0]
        assert issue.id == result.issue.id
        assert issue.quantity == quantity
        assert issue.warehouse_asset_id == material.id
        assert issue.operator_id == operator.id
        assert issue.issued_at == issued_at
        assert persisted_audits[0].resource_id == issue.id
        assert persisted_material.total_quantity == available_quantity
        assert persisted_material.available_quantity == available_quantity - quantity
        assert persisted_material.allocated_quantity == quantity

        if policy is IssuePolicy.RETURNABLE:
            assert issue.record_type == IssuePolicy.RETURNABLE.value
            assert issue.issue_policy == IssuePolicy.RETURNABLE.value
            assert issue.unreturned_quantity == quantity
            assert issue.consumed_completed is False
        else:
            assert issue.record_type == IssuePolicy.CONSUMABLE.value
            assert issue.issue_policy == IssuePolicy.CONSUMABLE.value
            assert issue.unreturned_quantity == 0
            assert issue.consumed_completed is True
    finally:
        db.close()
        models.Base.metadata.drop_all(engine)
        engine.dispose()
