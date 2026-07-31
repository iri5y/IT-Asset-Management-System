import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from auth import get_current_active_user
from database import get_db
from import_v2.domain_models import (
    AssetRecord,
    DuplicateInfo,
    ImportContext,
    PolicyDecision,
    RecordClassification,
)
from import_v2.executor import Executor, ImportExecutionError
from import_v2.import_policy import ImportPolicy
from import_v2.import_session import InMemorySessionStore, SessionStatus


@pytest.fixture
def db_env():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    user = models.User(
        username="phase6-user",
        hashed_password="unused",
        full_name="Phase 6 用户",
        role="MIS",
        is_active=True,
    )
    db.add(user)
    db.commit()
    yield db, user, session_factory
    db.close()


def make_record(tag, decision, **fields):
    return AssetRecord(
        row_number=fields.pop("row_number", 2),
        source_filename="phase6.xlsx",
        fields={
            "asset_tag": tag,
            "category": "平板电脑",
            "serial_number": f"SN-{tag}",
            "status": "闲置",
            **fields,
        },
        classification=(
            RecordClassification.DUPLICATE
            if decision in {PolicyDecision.UPDATE, PolicyDecision.REPLACE}
            else RecordClassification.VALID
        ),
        policy_decision=decision,
    )


def make_context(db, user, *, dry_run=False):
    return ImportContext.create(
        db,
        user,
        ImportPolicy.insert_only(),
        dry_run=dry_run,
    )
def test_insert_skip_inventory_and_audit_logs(db_env):
    db, user, session_factory = db_env
    warehouse = models.WarehouseAsset(
        name="平板电脑库存",
        category="移动设备",
        total_quantity=10,
        available_quantity=2,
        allocated_quantity=8,
    )
    db.add(warehouse)
    db.commit()
    records = [
        make_record("ZS-MR26-000101", PolicyDecision.INSERT, model="M1"),
        make_record("INVALID", PolicyDecision.SKIP, status="非法状态", row_number=3),
    ]

    result = Executor(session_factory).execute(records, make_context(db, user))

    assert result["success_count"] == 1
    assert result["skip_count"] == 1
    assert db.query(models.Asset).one().model == "M1"
    assert db.query(models.WarehouseAsset).one().available_quantity == 3
    asset_log = db.query(models.AssetLog).one()
    assert asset_log.action == "批量导入"
    assert asset_log.description == "INSERT: ZS-MR26-000101"
    assert db.query(models.WarehouseAssetLog).count() == 1
    operation = db.query(models.OperationLog).one()
    assert operation.action == "import"
    assert "success=1, skip=1, fail=0" in operation.description


def test_update_uses_duplicate_id_preserves_tag_and_updates_imported_fields(db_env):
    db, user, session_factory = db_env
    asset = models.Asset(
        asset_tag="ZS-MR26-000201",
        category="显示器",
        status="使用中",
        model="旧型号",
        notes="保留备注",
        employee_name="旧用户",
    )
    warehouse = models.WarehouseAsset(
        name="平板电脑库存",
        category="移动设备",
        total_quantity=5,
        available_quantity=1,
        allocated_quantity=4,
    )
    db.add_all([asset, warehouse])
    db.commit()
    record = make_record(
        "ZS-MR26-999999",
        PolicyDecision.UPDATE,
        model="新型号",
        employee_name=None,
    )
    record.duplicate_info = DuplicateInfo(
        asset_id=asset.id,
        asset_tag=asset.asset_tag,
        serial_number=None,
        status=asset.status,
        conflict_field="serial_number",
    )

    Executor(session_factory).execute([record], make_context(db, user))

    db.refresh(asset)
    assert asset.asset_tag == "ZS-MR26-000201"
    assert asset.model == "新型号"
    assert asset.status == "闲置"
    assert asset.employee_name is None
    assert asset.notes == "保留备注"
    assert warehouse.available_quantity == 2
    assert db.query(models.AssetLog).one().description == "UPDATE: ZS-MR26-000201"


def test_replace_overwrites_tag_and_all_import_fields_safely(db_env):
    db, user, session_factory = db_env
    asset = models.Asset(
        asset_tag="ZS-MR26-000301",
        category="显示器",
        status="闲置",
        serial_number="OLD-SN",
        model="旧型号",
        notes="旧备注",
    )
    old_stock = models.WarehouseAsset(
        name="显示器库存",
        category="显示设备",
        total_quantity=4,
        available_quantity=1,
        allocated_quantity=3,
    )
    new_stock = models.WarehouseAsset(
        name="手机库存",
        category="移动设备",
        total_quantity=4,
        available_quantity=0,
        allocated_quantity=4,
    )
    db.add_all([asset, old_stock, new_stock])
    db.commit()
    original_id = asset.id
    record = make_record(
        "ZS-PD26-000302",
        PolicyDecision.REPLACE,
        category="平板电脑",
        serial_number="NEW-SN",
    )
    record.duplicate_info = DuplicateInfo(
        asset_id=asset.id,
        asset_tag=asset.asset_tag,
        serial_number=asset.serial_number,
        status=asset.status,
        conflict_field="serial_number",
    )

    Executor(session_factory).execute([record], make_context(db, user))

    db.refresh(asset)
    assert asset.id == original_id
    assert asset.asset_tag == "ZS-PD26-000302"
    assert asset.category == "平板电脑"
    assert asset.model is None
    assert asset.notes is None
    assert old_stock.available_quantity == 0
    assert new_stock.available_quantity == 1
    assert db.query(models.AssetLog).one().description == "REPLACE: ZS-PD26-000302"
def test_dry_run_executes_then_rolls_back_everything(db_env):
    db, user, session_factory = db_env
    warehouse = models.WarehouseAsset(
        name="显示器库存",
        category="显示设备",
        total_quantity=3,
        available_quantity=1,
        allocated_quantity=2,
    )
    db.add(warehouse)
    db.commit()
    record = make_record("ZS-MR26-000401", PolicyDecision.INSERT)

    result = Executor(session_factory).execute(
        [record],
        make_context(db, user, dry_run=True),
    )

    assert result["dry_run"] is True
    assert result["success_count"] == 1
    assert result["records"][0]["status"] == "SUCCESS"
    assert db.query(models.Asset).count() == 0
    assert db.query(models.AssetLog).count() == 0
    assert db.query(models.WarehouseAssetLog).count() == 0
    assert db.query(models.OperationLog).count() == 0
    db.refresh(warehouse)
    assert warehouse.available_quantity == 1


def test_mid_batch_failure_rolls_back_all_and_audits_with_new_session(db_env):
    db, user, session_factory = db_env
    created_audit_sessions = []

    def audit_factory():
        audit_db = session_factory()
        created_audit_sessions.append(audit_db)
        return audit_db

    records = [
        make_record(
            "ZS-MR26-000501",
            PolicyDecision.INSERT,
            fixed_asset_number="DUPLICATE-FA",
        ),
        make_record(
            "ZS-MR26-000502",
            PolicyDecision.INSERT,
            fixed_asset_number="DUPLICATE-FA",
            row_number=3,
        ),
    ]

    with pytest.raises(ImportExecutionError):
        Executor(audit_factory).execute(records, make_context(db, user))

    assert created_audit_sessions
    assert all(audit_db is not db for audit_db in created_audit_sessions)
    assert db.query(models.Asset).count() == 0
    assert db.query(models.AssetLog).count() == 0
    assert db.query(models.WarehouseAssetLog).count() == 0
    failure_log = db.query(models.OperationLog).one()
    assert failure_log.action == "import_failed"
    assert failure_log.resource_type == "asset"
    assert "影响行数: 2" in failure_log.description
    assert "request_id" in failure_log.new_value


def test_inventory_decrement_never_goes_below_zero(db_env):
    db, user, session_factory = db_env
    asset = models.Asset(
        asset_tag="ZS-MR26-000601",
        category="显示器",
        status="闲置",
    )
    warehouse = models.WarehouseAsset(
        name="空库存",
        category="显示设备",
        total_quantity=0,
        available_quantity=0,
        allocated_quantity=0,
    )
    db.add_all([asset, warehouse])
    db.commit()
    record = make_record(
        asset.asset_tag,
        PolicyDecision.UPDATE,
        status="维修中",
    )
    record.duplicate_info = DuplicateInfo(
        asset_id=asset.id,
        asset_tag=asset.asset_tag,
        serial_number=None,
        status=asset.status,
        conflict_field="asset_tag",
    )

    Executor(session_factory).execute([record], make_context(db, user))

    db.refresh(warehouse)
    assert warehouse.available_quantity == 0
    assert warehouse.allocated_quantity == 0
@pytest.fixture
def api_env(db_env):
    db, user, session_factory = db_env
    store = InMemorySessionStore()
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[get_current_active_user] = lambda: user
    main.app.dependency_overrides[main.get_session_store] = lambda: store
    main.app.dependency_overrides[main.get_import_executor] = lambda: Executor(
        session_factory
    )
    with TestClient(main.app) as client:
        yield client, db, user, store
    main.app.dependency_overrides.clear()


def ready_session(store, user, record, policy):
    session = store.create(user.id, "phase6-api.xlsx", "parse-request")
    session.parsed_records = [record]
    session.duplicate_policy_type = policy
    session.transition_to(SessionStatus.MAPPING_APPLIED)
    store.save(session)
    return session


@pytest.mark.parametrize(
    ("policy", "dry_run", "decision"),
    [
        ("UPDATE_EXISTING", False, "UPDATE"),
        ("REPLACE_EXISTING", False, "REPLACE"),
        ("INSERT_ONLY", True, "INSERT"),
    ],
)
def test_execute_api_supports_update_replace_and_dry_run(
    api_env,
    policy,
    dry_run,
    decision,
):
    client, db, user, store = api_env
    if decision == "INSERT":
        record = make_record("ZS-MR26-000701", PolicyDecision.INSERT)
    else:
        asset = models.Asset(
            asset_tag="ZS-MR26-000702",
            category="显示器",
            status="闲置",
            model="旧型号",
        )
        db.add(asset)
        db.commit()
        incoming_tag = (
            asset.asset_tag if decision == "UPDATE" else "ZS-MR26-000703"
        )
        record = make_record(
            incoming_tag,
            PolicyDecision.SKIP,
            model="API 新型号",
        )
        record.classification = RecordClassification.DUPLICATE
        record.duplicate_info = DuplicateInfo(
            asset_id=asset.id,
            asset_tag=asset.asset_tag,
            serial_number=None,
            status=asset.status,
            conflict_field="asset_tag",
        )
    session = ready_session(store, user, record, policy)

    response = client.post(
        "/assets/import/execute",
        json={"session_id": session.session_id, "dry_run": dry_run},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    assert body["result"]["dry_run"] is dry_run
    assert body["result"]["records"][0]["decision"] == decision
    assert store.get(session.session_id).status == SessionStatus.COMPLETED
    if dry_run:
        assert db.query(models.Asset).count() == 0
        assert db.query(models.OperationLog).count() == 0


def test_execute_api_failure_returns_session_to_parsed(api_env):
    client, db, user, store = api_env
    first = make_record(
        "ZS-MR26-000801",
        PolicyDecision.INSERT,
        fixed_asset_number="API-DUP-FA",
    )
    second = make_record(
        "ZS-MR26-000802",
        PolicyDecision.INSERT,
        fixed_asset_number="API-DUP-FA",
        row_number=3,
    )
    session = store.create(user.id, "phase6-failure.xlsx", "parse-request")
    session.parsed_records = [first, second]
    session.duplicate_policy_type = "INSERT_ONLY"
    session.transition_to(SessionStatus.MAPPING_APPLIED)
    store.save(session)

    response = client.post(
        "/assets/import/execute",
        json={"session_id": session.session_id},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["request_id"]
    assert body["detail"]["message"] == "导入数据存在唯一性冲突"
    assert body["detail"]["errors"] == [{
        "row_number": 3,
        "field": "固定资产编号",
        "reason": "固定资产编号「API-DUP-FA」在导入文件中重复，首次出现于第 2 行",
    }]
    assert store.get(session.session_id).status == SessionStatus.PARSED
    assert db.query(models.Asset).count() == 0
    assert db.query(models.OperationLog).filter_by(action="import_failed").count() == 1
