"""专业物料 API 集成测试。"""

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
ISSUED_AT = "2025-01-02T09:30:00"


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


@pytest.fixture
def specialized_material_api_env() -> Iterator[tuple[TestClient, Session, dict[str, Any]]]:
    """提供四类专业物料、有效关联和可切换角色的隔离 API 环境。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    writer = models.User(
        username="specialized-api-writer",
        hashed_password="not-used-by-api-test",
        full_name="专业物料测试经办人",
        role="MIS",
        is_active=True,
    )
    readonly = models.User(
        username="specialized-api-readonly",
        hashed_password="not-used-by-api-test",
        full_name="专业物料只读用户",
        role="readonly",
        is_active=True,
    )
    department = models.Department(name="专业物料测试部门")
    db.add_all((writer, readonly, department))
    db.flush()

    def add_category(code: str, name: str, suffix: str) -> tuple[Any, Any]:
        primary = models.WarehousePrimaryCategory(
            code=code, name=name, is_active=True
        )
        db.add(primary)
        db.flush()
        secondary = models.WarehouseSecondaryCategory(
            primary_category_id=primary.id,
            code=f"API-{suffix}",
            name=f"API {name}",
            is_active=True,
        )
        db.add(secondary)
        db.flush()
        return primary, secondary

    repair_primary, repair_secondary = add_category(
        "STORAGE_REPAIR_PARTS", "存储与维修备件", "REPAIR"
    )
    network_primary, network_secondary = add_category(
        "NETWORK_SERVER_ROOM_CONSUMABLES", "网络与机房耗材", "NETWORK"
    )
    tool_primary, tool_secondary = add_category(
        "IT_TOOLS_LOAN_ITEMS", "IT工具与借用物品", "TOOL"
    )
    office_primary, office_secondary = add_category(
        "OFFICE_GENERAL_CONSUMABLES", "办公与通用耗材", "OFFICE"
    )
    terminal_primary, terminal_secondary = add_category(
        "TERMINAL_EQUIPMENT", "终端设备库存", "TERMINAL"
    )

    def add_material(
        name: str,
        primary: Any,
        secondary: Any,
        *,
        quantity: int = 10,
        threshold: int = 0,
        policy: str = "CONSUMABLE",
    ) -> models.WarehouseAsset:
        material = models.WarehouseAsset(
            name=name,
            category=primary.name,
            subcategory=secondary.name,
            total_quantity=quantity,
            available_quantity=quantity,
            allocated_quantity=0,
            minimum_stock=threshold,
            low_stock_threshold=threshold,
            primary_category_id=primary.id,
            secondary_category_id=secondary.id,
            classification_status="ACTIVE",
            material_kind="NON_FIXED",
            issue_policy=policy,
        )
        db.add(material)
        return material

    repair_material = add_material("API 硬盘", repair_primary, repair_secondary)
    network_material = add_material("API 网线", network_primary, network_secondary)
    tool_material = add_material(
        "API 万用表", tool_primary, tool_secondary, policy="RETURNABLE"
    )
    office_material = add_material(
        "API 打印纸", office_primary, office_secondary, quantity=3, threshold=3
    )
    terminal_inventory = add_material(
        "API 维修目标终端", terminal_primary, terminal_secondary, quantity=1
    )
    db.flush()
    target_asset = models.Asset(
        asset_tag="API-REPAIR-ASSET-001",
        category="台式机",
        status="维修中",
        fixed_asset_number="API-REPAIR-FA-001",
        serial_number="API-REPAIR-SN-001",
        asset_category_code="PC",
        inbound_source="MANUAL",
        terminal_inventory_id=terminal_inventory.id,
        is_deleted=False,
    )
    db.add(target_asset)
    db.flush()
    db.add(models.FixedAssetInbound(
        asset_id=target_asset.id,
        terminal_inventory_id=terminal_inventory.id,
        source="MANUAL",
        operator_id=writer.id,
    ))
    db.commit()

    context: dict[str, Any] = {
        "writer": writer,
        "readonly": readonly,
        "current_user": writer,
        "department_id": department.id,
        "target_asset_id": target_asset.id,
        "repair_material_id": repair_material.id,
        "network_material_id": network_material.id,
        "tool_material_id": tool_material.id,
        "office_material_id": office_material.id,
    }
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[get_current_active_user] = (
        lambda: context["current_user"]
    )
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
        "issued_at": ISSUED_AT,
    }


def _tool_payload(material_id: int, quantity: int = 5) -> dict[str, object]:
    return {
        "warehouse_asset_id": material_id,
        "borrower_ref": "TOOL-BORROWER-001",
        "quantity": quantity,
        "borrowed_at": ISSUED_AT,
        "expected_return_at": "2025-01-10T09:30:00",
        "tool_identifier": "QR-API-TOOL-001",
    }


def _specialized_state(db: Session, material_ids: tuple[int, ...]) -> tuple[object, ...]:
    """捕获专业记录、库存和审计，供故障与权限无副作用断言复用。"""
    db.expire_all()
    inventories = tuple(
        (item.id, item.total_quantity, item.available_quantity, item.allocated_quantity)
        for item in db.query(models.WarehouseAsset)
        .filter(models.WarehouseAsset.id.in_(material_ids))
        .order_by(models.WarehouseAsset.id)
    )
    issues = tuple(
        (item.id, item.warehouse_asset_id, item.quantity, item.unreturned_quantity)
        for item in db.query(models.MaterialIssue).order_by(models.MaterialIssue.id)
    )
    repair_issues = tuple(
        (item.id, item.material_issue_id, item.target_asset_id, item.repair_order_ref)
        for item in db.query(models.RepairPartIssue).order_by(models.RepairPartIssue.id)
    )
    network_issues = tuple(
        (item.id, item.material_issue_id, item.department_id, item.project_ref)
        for item in db.query(models.NetworkConsumableIssue).order_by(
            models.NetworkConsumableIssue.id
        )
    )
    loans = tuple(
        (item.id, item.warehouse_asset_id, item.unreturned_quantity, item.status)
        for item in db.query(models.ToolLoan).order_by(models.ToolLoan.id)
    )
    returns = tuple(
        (item.id, item.tool_loan_id, item.quantity, item.is_partial)
        for item in db.query(models.ToolLoanReturnEvent).order_by(
            models.ToolLoanReturnEvent.id
        )
    )
    audits = tuple(
        (item.id, item.action, item.resource_type, item.resource_id)
        for item in db.query(models.OperationLog).order_by(models.OperationLog.id)
    )
    return inventories, issues, repair_issues, network_issues, loans, returns, audits


def test_specialized_issue_apis_persist_associations_optional_fields_and_low_stock(
    specialized_material_api_env,
) -> None:
    """维修、网络和办公端点保存关联；空选填项合法，且低库存按严格阈值标记。"""
    client, _db, context = specialized_material_api_env

    repair_by_asset = client.post(
        "/repair-parts/issues",
        json={
            **_issue_payload(context["repair_material_id"], 2),
            "target_asset_id": context["target_asset_id"],
            "disk_serial_number": "DISK-SN-API-001",
        },
    )
    assert repair_by_asset.status_code == 200
    repair_payload = repair_by_asset.json()
    assert repair_payload["material_issue"]["record_type"] == "CONSUMABLE"
    assert repair_payload["domain_record"] == {
        "id": repair_payload["domain_record"]["id"],
        "type": "repair_part_issues",
        "material_issue_id": repair_payload["material_issue"]["id"],
        "target_asset_id": context["target_asset_id"],
        "repair_order_ref": None,
        "disk_serial_number": "DISK-SN-API-001",
    }
    assert repair_payload["inventory"]["available_quantity"] == 8
    assert repair_payload["inventory"]["allocated_quantity"] == 2
    assert repair_payload["audit_log_id"] > 0

    repair_by_order = client.post(
        "/repair-parts/issues",
        json={
            **_issue_payload(context["repair_material_id"], 1),
            "repair_order_ref": "REPAIR-ORDER-API-001",
        },
    )
    assert repair_by_order.status_code == 200
    assert repair_by_order.json()["domain_record"]["target_asset_id"] is None
    assert repair_by_order.json()["domain_record"]["disk_serial_number"] is None

    network_without_purpose = client.post(
        "/network-consumables/issues",
        json=_issue_payload(context["network_material_id"], 1),
    )
    assert network_without_purpose.status_code == 200
    assert network_without_purpose.json()["domain_record"] == {
        "id": network_without_purpose.json()["domain_record"]["id"],
        "type": "network_consumable_issues",
        "material_issue_id": network_without_purpose.json()["material_issue"]["id"],
        "department_id": None,
        "project_ref": None,
        "server_room_ref": None,
        "work_order_ref": None,
    }

    network_with_purpose = client.post(
        "/network-consumables/issues",
        json={
            **_issue_payload(context["network_material_id"], 2),
            "department_id": context["department_id"],
            "project_ref": "NETWORK-PROJECT-001",
            "server_room_ref": "SERVER-ROOM-A",
            "work_order_ref": "NETWORK-WO-001",
        },
    )
    assert network_with_purpose.status_code == 200
    assert network_with_purpose.json()["domain_record"] == {
        "id": network_with_purpose.json()["domain_record"]["id"],
        "type": "network_consumable_issues",
        "material_issue_id": network_with_purpose.json()["material_issue"]["id"],
        "department_id": context["department_id"],
        "project_ref": "NETWORK-PROJECT-001",
        "server_room_ref": "SERVER-ROOM-A",
        "work_order_ref": "NETWORK-WO-001",
    }
    assert network_with_purpose.json()["inventory"]["available_quantity"] == 7

    office = client.post(
        "/office-consumables/issues",
        json=_issue_payload(context["office_material_id"], 1),
    )
    assert office.status_code == 200
    office_issue = office.json()["material_issue"]
    assert office_issue["record_type"] == office_issue["issue_policy"] == "CONSUMABLE"
    assert office_issue["consumed_completed"] is True
    assert office.json()["domain_record"] is None
    assert office.json()["inventory"]["available_quantity"] == 2
    assert office.json()["inventory"]["low_stock"] is True
    assert office.json()["inventory"]["low_stock_message"] == "低库存预警"


def test_tool_loan_api_preserves_partial_and_full_return_balances(
    specialized_material_api_env,
) -> None:
    """借出、部分归还和全量归还必须精确维护 BORROWED/RETURNED 与库存余额。"""
    client, _db, context = specialized_material_api_env
    borrowed = client.post("/tool-loans", json=_tool_payload(context["tool_material_id"]))
    assert borrowed.status_code == 200
    loan = borrowed.json()["tool_loan"]
    assert loan["quantity"] == loan["unreturned_quantity"] == 5
    assert loan["status"] == "BORROWED"
    assert loan["tool_identifier"] == "QR-API-TOOL-001"
    assert borrowed.json()["inventory"]["available_quantity"] == 5
    assert borrowed.json()["inventory"]["allocated_quantity"] == 5

    partial = client.post(
        f"/tool-loans/{loan['id']}/returns",
        json={"quantity": 2, "returned_at": "2025-01-03T09:30:00"},
    )
    assert partial.status_code == 200
    assert partial.json()["return_event"]["is_partial"] is True
    assert partial.json()["tool_loan"]["status"] == "BORROWED"
    assert partial.json()["tool_loan"]["unreturned_quantity"] == 3
    assert partial.json()["inventory"]["available_quantity"] == 7
    assert partial.json()["inventory"]["allocated_quantity"] == 3

    full = client.post(
        f"/tool-loans/{loan['id']}/returns",
        json={"quantity": 3, "returned_at": "2025-01-04T09:30:00"},
    )
    assert full.status_code == 200
    assert full.json()["return_event"]["is_partial"] is False
    assert full.json()["tool_loan"]["status"] == "RETURNED"
    assert full.json()["tool_loan"]["unreturned_quantity"] == 0
    assert full.json()["inventory"]["available_quantity"] == 10
    assert full.json()["inventory"]["allocated_quantity"] == 0

    detail = client.get(f"/tool-loans/{loan['id']}")
    assert detail.status_code == 200
    assert [(item["quantity"], item["is_partial"]) for item in detail.json()["return_events"]] == [
        (2, True),
        (3, False),
    ]


@pytest.mark.parametrize("operation", ("repair", "network", "office", "tool"))
def test_specialized_write_audit_failure_rolls_back_every_domain_transaction(
    specialized_material_api_env,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    """四类专业写操作的审计持久化失败均不得留下领域记录或库存扣减。"""
    client, db, context = specialized_material_api_env
    material_ids = (
        context["repair_material_id"],
        context["network_material_id"],
        context["office_material_id"],
        context["tool_material_id"],
    )
    before = _specialized_state(db, material_ids)
    requests = {
        "repair": (
            "/repair-parts/issues",
            {**_issue_payload(context["repair_material_id"], 1),
             "target_asset_id": context["target_asset_id"]},
        ),
        "network": (
            "/network-consumables/issues",
            _issue_payload(context["network_material_id"], 1),
        ),
        "office": (
            "/office-consumables/issues",
            _issue_payload(context["office_material_id"], 1),
        ),
        "tool": ("/tool-loans", _tool_payload(context["tool_material_id"], 1)),
    }

    def fail_audit(*_args: Any, **_kwargs: Any) -> None:
        raise AuditLogPersistenceError()

    monkeypatch.setattr(
        material_issuance_service.DomainTransaction, "record_audit", fail_audit
    )
    path, payload = requests[operation]
    response = client.post(path, json=payload)

    assert response.status_code == 500
    assert "审计日志保存失败" in response.json()["detail"]
    assert _specialized_state(db, material_ids) == before


def test_readonly_user_can_query_specialized_records_but_cannot_write(
    specialized_material_api_env,
) -> None:
    """只读角色可查询四类领域记录及工具详情，但所有代表性写操作均被拒绝。"""
    client, db, context = specialized_material_api_env
    repair = client.post(
        "/repair-parts/issues",
        json={
            **_issue_payload(context["repair_material_id"], 1),
            "target_asset_id": context["target_asset_id"],
        },
    )
    network = client.post(
        "/network-consumables/issues",
        json=_issue_payload(context["network_material_id"], 1),
    )
    office = client.post(
        "/office-consumables/issues",
        json=_issue_payload(context["office_material_id"], 1),
    )
    tool = client.post("/tool-loans", json=_tool_payload(context["tool_material_id"], 2))
    assert all(response.status_code == 200 for response in (repair, network, office, tool))
    repair_id = repair.json()["domain_record"]["id"]
    network_id = network.json()["domain_record"]["id"]
    office_issue_id = office.json()["material_issue"]["id"]
    tool_loan_id = tool.json()["tool_loan"]["id"]

    context["current_user"] = context["readonly"]
    query_paths = (
        "/repair-parts/issues",
        f"/repair-parts/issues/{repair_id}",
        "/network-consumables/issues",
        f"/network-consumables/issues/{network_id}",
        "/office-consumables/issues",
        f"/office-consumables/issues/{office_issue_id}",
        "/tool-loans",
        f"/tool-loans/{tool_loan_id}",
    )
    for path in query_paths:
        assert client.get(path).status_code == 200

    material_ids = (
        context["repair_material_id"],
        context["network_material_id"],
        context["office_material_id"],
        context["tool_material_id"],
    )
    before = _specialized_state(db, material_ids)
    writes = (
        ("/repair-parts/issues", {
            **_issue_payload(context["repair_material_id"], 1),
            "target_asset_id": context["target_asset_id"],
        }),
        ("/network-consumables/issues", _issue_payload(context["network_material_id"], 1)),
        ("/office-consumables/issues", _issue_payload(context["office_material_id"], 1)),
        ("/tool-loans", _tool_payload(context["tool_material_id"], 1)),
        (f"/tool-loans/{tool_loan_id}/returns", {
            "quantity": 1, "returned_at": "2025-01-03T09:30:00"
        }),
    )
    for path, payload in writes:
        response = client.post(path, json=payload)
        assert response.status_code == 403
        assert response.json()["detail"] == READONLY_WRITE_ERROR
        assert _specialized_state(db, material_ids) == before
