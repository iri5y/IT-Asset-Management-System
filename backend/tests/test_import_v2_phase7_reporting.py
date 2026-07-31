import json
import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
import schemas
from import_v2.domain_models import (
    AssetRecord,
    DuplicateInfo,
    ImportContext,
    IssueType,
    PolicyDecision,
    RecordClassification,
    ResolverIssue,
    ValidationError,
)
from import_v2.executor import Executor, ImportExecutionError
from import_v2.import_policy import ImportPolicy
from import_v2.reporting import skip_message


@pytest.fixture
def db_env():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    user = models.User(
        username="phase7-user",
        hashed_password="unused",
        full_name="Phase 7 用户",
        role="MIS",
        is_active=True,
    )
    db.add(user)
    db.commit()
    yield db, user, factory
    db.close()


def make_record(tag, decision, *, row_number=2, category="平板电脑", status="闲置"):
    return AssetRecord(
        row_number=row_number,
        source_filename="phase7.xlsx",
        fields={
            "asset_tag": tag,
            "category": category,
            "serial_number": f"SN-{tag}",
            "status": status,
        },
        classification=(
            RecordClassification.DUPLICATE
            if decision in {PolicyDecision.UPDATE, PolicyDecision.REPLACE}
            else RecordClassification.VALID
        ),
        policy_decision=decision,
    )


def context(db, user, *, dry_run=False):
    return ImportContext.create(
        db,
        user,
        ImportPolicy.insert_only(),
        session_id="phase7-session",
        dry_run=dry_run,
    )


def attach_duplicate(record, asset):
    record.duplicate_info = DuplicateInfo(
        asset_id=asset.id,
        asset_tag=asset.asset_tag,
        serial_number=asset.serial_number,
        status=asset.status,
        conflict_field="asset_tag",
    )


def test_report_counts_distributions_inventory_and_enhanced_audit(db_env):
    db, user, factory = db_env
    update_asset = models.Asset(
        asset_tag="ZS-MR26-710001", category="显示器", status="使用中"
    )
    replace_asset = models.Asset(
        asset_tag="ZS-MR26-710002", category="显示器", status="闲置"
    )
    display_stock = models.WarehouseAsset(
        name="显示器库存",
        category="显示设备",
        total_quantity=10,
        available_quantity=2,
        allocated_quantity=8,
    )
    mobile_stock = models.WarehouseAsset(
        name="移动设备库存",
        category="移动设备",
        total_quantity=10,
        available_quantity=0,
        allocated_quantity=10,
    )
    db.add_all([update_asset, replace_asset, display_stock, mobile_stock])
    db.commit()

    inserted = make_record("ZS-MR26-710003", PolicyDecision.INSERT)
    updated = make_record("ZS-MR26-710001", PolicyDecision.UPDATE, row_number=3)
    replaced = make_record(
        "ZS-PD26-710004",
        PolicyDecision.REPLACE,
        row_number=4,
        category="平板电脑",
    )
    attach_duplicate(updated, update_asset)
    attach_duplicate(replaced, replace_asset)

    duplicate_skip = make_record(
        "ZS-MR26-710001", PolicyDecision.SKIP, row_number=5
    )
    duplicate_skip.classification = RecordClassification.DUPLICATE
    attach_duplicate(duplicate_skip, update_asset)
    invalid_skip = make_record("INVALID", PolicyDecision.SKIP, row_number=6)
    invalid_skip.classification = RecordClassification.ERROR
    invalid_skip.validation_errors = [
        ValidationError(field="资产编号", message="格式错误「INVALID」")
    ]
    mapping_skip = make_record(
        "ZS-MR26-710005", PolicyDecision.SKIP, row_number=7
    )
    mapping_skip.classification = RecordClassification.MAPPING_REQUIRED
    mapping_skip.resolver_issues = [
        ResolverIssue(
            field="department",
            raw_value="未知部门",
            issue_type=IssueType.UNKNOWN,
        )
    ]

    result = Executor(factory).execute(
        [inserted, updated, replaced, duplicate_skip, invalid_skip, mapping_skip],
        context(db, user),
    )

    assert result["success_count"] == 3
    assert result["fail_count"] == 0
    assert result["skip_count"] == 3
    assert result["total_rows"] == 6
    assert result["inserted_count"] == 1
    assert result["updated_count"] == 1
    assert result["replaced_count"] == 1
    assert result["skipped_count"] == 3
    assert result["failed_count"] == 0
    assert result["statistics"]["by_category"] == {"平板电脑": 6}
    assert result["statistics"]["by_status"] == {"闲置": 6}
    assert result["statistics"]["by_error_type"] == {
        "CONFLICT": 1,
        "FORMAT": 1,
        "MAPPING": 1,
    }
    assert result["statistics"]["total_rows"] == 6
    assert result["statistics"]["decision_counts"] == {
        "INSERT": 1,
        "UPDATE": 1,
        "REPLACE": 1,
        "SKIP": 3,
    }
    assert result["statistics"]["by_decision"] == result["statistics"]["decision_counts"]
    assert result["statistics"]["inserted_count"] == 1
    assert result["statistics"]["updated_count"] == 1
    assert result["statistics"]["replaced_count"] == 1
    assert result["statistics"]["skipped_count"] == 3
    assert result["statistics"]["failed_count"] == 0
    assert [item["row_number"] for item in result["errors"]] == [6, 7]
    assert result["errors"][0]["request_id"] == result["request_id"]
    assert result["errors"][1]["field"] == "department"
    assert [item["row_number"] for item in result["warnings"]] == [5]
    assert result["warnings"][0]["warning_type"] == "CONFLICT"

    synced = result["statistics"]["warehouse_synced"]
    assert synced == [
        {
            "warehouse_asset_id": display_stock.id,
            "warehouse_asset_name": "显示器库存",
            "warehouse_category": "显示设备",
            "before_available": 2,
            "after_available": 1,
            "before_allocated": 8,
            "after_allocated": 9,
            "delta": -1,
            "committed": True,
            "dry_run": False,
            "rolled_back": False,
        },
        {
            "warehouse_asset_id": mobile_stock.id,
            "warehouse_asset_name": "移动设备库存",
            "warehouse_category": "移动设备",
            "before_available": 0,
            "after_available": 3,
            "before_allocated": 10,
            "after_allocated": 7,
            "delta": 3,
            "committed": True,
            "dry_run": False,
            "rolled_back": False,
        },
    ]
    assert "重复数据按 INSERT_ONLY 策略跳过" in result["records"][3]["message"]
    assert result["records"][4]["message"].startswith("数据校验失败：")
    assert result["records"][5]["message"].startswith("主数据待映射，已跳过：")
    assert result["records"][4]["category"] == "平板电脑"
    assert result["records"][4]["asset_status"] == "闲置"
    assert result["records"][4]["error_type"] == "FORMAT"

    operation = db.query(models.OperationLog).filter_by(action="import").one()
    payload = json.loads(operation.new_value)
    assert payload["request_id"] == result["request_id"]
    assert payload["session_id"] == "phase7-session"
    assert payload["source_filename"] == "phase7.xlsx"
    assert payload["source_filenames"] == ["phase7.xlsx"]
    assert payload["operator_name"] == "Phase 7 用户"
    assert payload["operator"] == "Phase 7 用户"
    assert payload["strategy"] == "INSERT_ONLY"
    assert payload["total"] == 6
    assert payload["success"] == 3
    assert payload["skip"] == 3
    assert payload["fail"] == 0
    assert payload["decision_counts"] == {
        "INSERT": 1,
        "REPLACE": 1,
        "SKIP": 3,
        "UPDATE": 1,
    }
    assert payload["statistics"] == result["statistics"]
    assert payload["warehouse_sync_summary"] == {
        "item_count": 2,
        "net_available_delta": 2,
        "committed_count": 2,
    }
    assert "审计摘要" in operation.description


def test_dry_run_returns_full_statistics_with_zero_persistence(db_env):
    db, user, factory = db_env
    warehouse = models.WarehouseAsset(
        name="演练库存",
        category="移动设备",
        total_quantity=3,
        available_quantity=1,
        allocated_quantity=2,
    )
    db.add(warehouse)
    db.commit()

    result = Executor(factory).execute(
        [make_record("ZS-MR26-720001", PolicyDecision.INSERT)],
        context(db, user, dry_run=True),
    )

    assert result["dry_run"] is True
    assert result["inserted_count"] == 1
    assert result["statistics"]["inserted_count"] == 1
    sync = result["statistics"]["warehouse_synced"][0]
    assert sync["delta"] == 1
    assert sync["dry_run"] is True
    assert sync["committed"] is False
    assert sync["rolled_back"] is False
    assert db.query(models.Asset).count() == 0
    assert db.query(models.AssetLog).count() == 0
    assert db.query(models.WarehouseAssetLog).count() == 0
    assert db.query(models.OperationLog).count() == 0
    db.refresh(warehouse)
    assert warehouse.available_quantity == 1


def test_old_wizard_result_fields_still_validate_with_compatible_defaults():
    result = schemas.WizardImportResult(
        success_count=1,
        fail_count=0,
        skip_count=2,
        dry_run=False,
        records=[],
    ).model_dump()

    assert result["success_count"] == 1
    assert result["fail_count"] == 0
    assert result["skip_count"] == 2
    assert result["dry_run"] is False
    assert result["records"] == []
    assert result["errors"] == []
    assert result["warnings"] == []
    assert result["statistics"]["warehouse_synced"] == []
    assert result["statistics"]["decision_counts"] == {}
    assert result["inserted_count"] == 0


def test_skip_messages_distinguish_policy_validation_and_mapping():
    duplicate = make_record("ZS-MR26-730001", PolicyDecision.SKIP)
    duplicate.classification = RecordClassification.DUPLICATE
    invalid = make_record("INVALID", PolicyDecision.SKIP, row_number=3)
    invalid.classification = RecordClassification.ERROR
    invalid.validation_errors = [
        ValidationError(field="资产编号", message="资产编号格式错误")
    ]
    mapping = make_record("ZS-MR26-730002", PolicyDecision.SKIP, row_number=4)
    mapping.classification = RecordClassification.MAPPING_REQUIRED
    mapping.resolver_issues = [
        ResolverIssue(
            field="brand",
            raw_value="未知品牌",
            issue_type=IssueType.UNKNOWN,
        )
    ]

    assert "策略跳过" in skip_message(duplicate, "INSERT_ONLY")
    assert skip_message(invalid, "INSERT_ONLY") == "数据校验失败：资产编号格式错误"
    assert "brand「未知品牌」" in skip_message(mapping, "INSERT_ONLY")


def test_rollback_persists_only_enhanced_failure_audit(db_env):
    db, user, factory = db_env
    warehouse = models.WarehouseAsset(
        name="失败演练库存",
        category="显示设备",
        total_quantity=4,
        available_quantity=1,
        allocated_quantity=3,
    )
    db.add(warehouse)
    db.commit()
    first = make_record("ZS-MR26-740001", PolicyDecision.INSERT)
    first.fields["fixed_asset_number"] = "PHASE7-DUP"
    second = make_record(
        "ZS-PD26-740002", PolicyDecision.INSERT, row_number=3
    )
    second.fields["fixed_asset_number"] = "PHASE7-DUP"

    with pytest.raises(ImportExecutionError):
        Executor(factory).execute([first, second], context(db, user))

    assert db.query(models.Asset).count() == 0
    assert db.query(models.OperationLog).filter_by(action="import").count() == 0
    failure = db.query(models.OperationLog).filter_by(action="import_failed").one()
    payload = json.loads(failure.new_value)
    assert payload["rolled_back"] is True
    assert payload["success_count"] == 0
    assert payload["fail_count"] == 2
    assert payload["decision_counts"]["INSERT"] == 2
    assert payload["statistics"]["by_category"] == {"平板电脑": 2}
    assert payload["statistics"]["by_error_type"]["SYSTEM"] == 2
    assert payload["statistics"]["inserted_count"] == 0
    assert payload["statistics"]["failed_count"] == 2
    assert payload["statistics"]["warehouse_synced"] == []
    db.refresh(warehouse)
    assert warehouse.available_quantity == 1
    assert payload["request_id"]
    assert payload["session_id"] == "phase7-session"


def test_missing_warehouse_item_is_warning_not_failure(db_env):
    db, user, factory = db_env
    record = make_record(
        "ZS-PD26-750001",
        PolicyDecision.INSERT,
    )

    result = Executor(factory).execute([record], context(db, user))

    assert result["success_count"] == 1
    assert result["fail_count"] == 0
    assert result["statistics"]["warehouse_synced"] == []
    assert result["warnings"] == [{
        "row_number": 2,
        "asset_tag": "ZS-PD26-750001",
        "warning_type": "WAREHOUSE_NOT_FOUND",
        "message": "未找到品类「移动设备」的库存条目，资产处理继续，未同步库存",
    }]
    assert db.query(models.Asset).filter_by(asset_tag="ZS-PD26-750001").one()


def test_enhanced_result_is_response_model_serializable(db_env):
    db, user, factory = db_env
    warehouse = models.WarehouseAsset(
        name="序列化库存",
        category="移动设备",
        total_quantity=2,
        available_quantity=0,
        allocated_quantity=2,
    )
    db.add(warehouse)
    db.commit()
    result = Executor(factory).execute(
        [make_record("ZS-MR26-760001", PolicyDecision.INSERT)],
        context(db, user),
    )

    serialized = schemas.ImportExecuteResponse.model_validate({
        "request_id": result["request_id"],
        "result": result,
    }).model_dump(mode="json")

    assert serialized["result"]["statistics"]["by_decision"]["INSERT"] == 1
    sync = serialized["result"]["statistics"]["warehouse_synced"][0]
    assert sync["before_allocated"] == 2
    assert sync["after_allocated"] == 1
    assert serialized["result"]["warnings"] == []
