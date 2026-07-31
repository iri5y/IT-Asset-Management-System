import json
import os
from datetime import datetime

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from transaction_audit import (
    AuditLogPersistenceError,
    AuditLogRequiredError,
    DomainTransaction,
    snapshot,
    utc8_now,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    user = models.User(
        username="transaction-audit-user",
        hashed_password="unused",
        role="MIS",
        is_active=True,
    )
    session.add(user)
    session.commit()
    yield session, user
    session.close()


def test_transaction_commits_domain_change_and_utc8_audit_snapshot(db):
    session, user = db

    with DomainTransaction(session) as transaction:
        warehouse = models.WarehouseAsset(
            name="网线",
            category="线缆与连接配件",
            total_quantity=5,
            available_quantity=5,
            allocated_quantity=0,
        )
        session.add(warehouse)
        transaction.flush()
        before = snapshot(warehouse, fields=["id", "available_quantity"])
        warehouse.available_quantity = 3
        warehouse.allocated_quantity = 2
        transaction.flush()
        after = snapshot(warehouse, fields=["id", "available_quantity"])
        audit = transaction.record_audit(
            user_id=user.id,
            action="issue",
            resource_type="warehouse_asset",
            resource_id=warehouse.id,
            before=before,
            after=after,
            related_records={"warehouse_asset_id": warehouse.id},
        )

    persisted = session.query(models.WarehouseAsset).one()
    operation = session.query(models.OperationLog).one()
    old_value = json.loads(operation.old_value)
    new_value = json.loads(operation.new_value)

    assert persisted.available_quantity == 3
    assert operation.id == audit.id
    assert old_value["values"]["available_quantity"] == 5
    assert new_value["values"]["available_quantity"] == 3
    assert new_value["related_records"] == {"warehouse_asset_id": warehouse.id}
    assert operation.created_at.tzinfo is None
    assert abs((operation.created_at - utc8_now()).total_seconds()) < 2


def test_audit_flush_failure_rolls_back_domain_change(db, monkeypatch):
    session, user = db
    warehouse = models.WarehouseAsset(
        name="维修硬盘",
        category="存储与维修备件",
        total_quantity=4,
        available_quantity=4,
        allocated_quantity=0,
    )
    session.add(warehouse)
    session.commit()

    original_flush = session.flush

    def fail_operation_log_flush(*args, **kwargs):
        if any(isinstance(item, models.OperationLog) for item in session.new):
            raise RuntimeError("injected audit persistence failure")
        return original_flush(*args, **kwargs)

    with pytest.raises(AuditLogPersistenceError, match="审计日志保存失败"):
        with DomainTransaction(session) as transaction:
            locked = transaction.lock_one(models.WarehouseAsset, warehouse.id)
            locked.available_quantity -= 1
            locked.allocated_quantity += 1
            transaction.flush()
            monkeypatch.setattr(session, "flush", fail_operation_log_flush)
            transaction.record_audit(
                user_id=user.id,
                action="issue",
                resource_type="warehouse_asset",
                resource_id=warehouse.id,
                before={"available_quantity": 4},
                after={"available_quantity": 3},
            )

    session.refresh(warehouse)
    assert warehouse.available_quantity == 4
    assert warehouse.allocated_quantity == 0
    assert session.query(models.OperationLog).count() == 0


def test_transaction_without_required_audit_rolls_back(db):
    session, _ = db

    with pytest.raises(AuditLogRequiredError, match="缺少审计日志"):
        with DomainTransaction(session) as transaction:
            session.add(
                models.WarehouseAsset(
                    name="未审计物料",
                    category="办公与通用耗材",
                    total_quantity=1,
                    available_quantity=1,
                    allocated_quantity=0,
                )
            )
            transaction.flush()

    assert session.query(models.WarehouseAsset).count() == 0


def test_lock_helpers_return_rows_in_stable_id_order(db):
    session, _ = db
    first = models.WarehouseAsset(
        name="工具一",
        category="IT工具与借用物品",
        total_quantity=1,
        available_quantity=1,
        allocated_quantity=0,
    )
    second = models.WarehouseAsset(
        name="工具二",
        category="IT工具与借用物品",
        total_quantity=1,
        available_quantity=1,
        allocated_quantity=0,
    )
    session.add_all([first, second])
    session.commit()

    transaction = DomainTransaction(session, require_audit=False)
    locked = transaction.lock_one(models.WarehouseAsset, first.id)
    rows = transaction.lock_many(
        models.WarehouseAsset,
        [second.id, first.id],
    )
    transaction.rollback()

    assert locked.id == first.id
    assert [row.id for row in rows] == [first.id, second.id]


def test_snapshot_converts_aware_datetime_to_project_utc8():
    aware = datetime(2026, 1, 1, 0, 0, tzinfo=models.CHINA_TZ)

    result = snapshot({"changed_at": aware, "labels": {"库存", "审计"}})

    assert result["changed_at"] == "2026-01-01T00:00:00"
    assert result["labels"] == ["审计", "库存"]
