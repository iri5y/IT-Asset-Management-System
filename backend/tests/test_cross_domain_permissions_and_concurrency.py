"""跨领域只读权限、审计边界及 PostgreSQL 库存并发集成测试。"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from typing import Any

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from auth import get_current_active_user
from database import get_db

READONLY_WRITE_ERROR = "只读账号无权限执行修改或新增操作"
ISSUED_AT = "2025-01-02T09:30:00"


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _add_category(
    db: Session, code: str, name: str, suffix: str
) -> tuple[models.WarehousePrimaryCategory, models.WarehouseSecondaryCategory]:
    primary = models.WarehousePrimaryCategory(code=code, name=name, is_active=True)
    db.add(primary)
    db.flush()
    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id,
        code=f"CROSS-{suffix}",
        name=f"跨领域{name}",
        is_active=True,
    )
    db.add(secondary)
    db.flush()
    return primary, secondary


def _add_material(
    db: Session,
    primary: models.WarehousePrimaryCategory,
    secondary: models.WarehouseSecondaryCategory,
    name: str,
    *,
    quantity: int,
    policy: str = "CONSUMABLE",
    material_kind: str | None = "NON_FIXED",
) -> models.WarehouseAsset:
    material = models.WarehouseAsset(
        name=name,
        category=primary.name,
        subcategory=secondary.name,
        total_quantity=quantity,
        available_quantity=quantity,
        allocated_quantity=0,
        minimum_stock=0,
        low_stock_threshold=0,
        primary_category_id=primary.id,
        secondary_category_id=secondary.id,
        classification_status="ACTIVE",
        material_kind=material_kind,
        issue_policy=policy,
    )
    db.add(material)
    return material


@pytest.fixture
def cross_domain_api_env() -> Iterator[tuple[TestClient, Session, dict[str, Any]]]:
    """提供独立 SQLite 库中的真实跨领域 API 与可切换身份。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    writer = models.User(
        username="cross-domain-writer",
        hashed_password="not-used-by-api-test",
        full_name="跨领域测试经办人",
        role="MIS",
        is_active=True,
    )
    readonly = models.User(
        username="cross-domain-readonly",
        hashed_password="not-used-by-api-test",
        full_name="跨领域只读用户",
        role="readonly",
        is_active=True,
    )
    department = models.Department(name="跨领域测试部门")
    db.add_all((writer, readonly, department))
    db.flush()

    terminal_primary, terminal_secondary = _add_category(
        db, "TERMINAL_EQUIPMENT", "终端设备库存", "TERMINAL"
    )
    low_value_primary, low_value_secondary = _add_category(
        db, "DISPLAY_AUDIO_VIDEO", "显示与音视频设备", "LOW-VALUE"
    )
    repair_primary, repair_secondary = _add_category(
        db, "STORAGE_REPAIR_PARTS", "存储与维修备件", "REPAIR"
    )
    network_primary, network_secondary = _add_category(
        db, "NETWORK_SERVER_ROOM_CONSUMABLES", "网络与机房耗材", "NETWORK"
    )
    tool_primary, tool_secondary = _add_category(
        db, "IT_TOOLS_LOAN_ITEMS", "IT工具与借用物品", "TOOL"
    )
    office_primary, office_secondary = _add_category(
        db, "OFFICE_GENERAL_CONSUMABLES", "办公与通用耗材", "OFFICE"
    )

    terminal_inventory = _add_material(
        db,
        terminal_primary,
        terminal_secondary,
        "跨领域终端库存",
        quantity=0,
        material_kind=None,
    )
    low_value_material = _add_material(
        db, low_value_primary, low_value_secondary, "跨领域显示器", quantity=3,
        policy="RETURNABLE",
    )
    repair_material = _add_material(
        db, repair_primary, repair_secondary, "跨领域硬盘", quantity=3
    )
    network_material = _add_material(
        db, network_primary, network_secondary, "跨领域网线", quantity=3
    )
    tool_material = _add_material(
        db, tool_primary, tool_secondary, "跨领域万用表", quantity=3,
        policy="RETURNABLE",
    )
    office_material = _add_material(
        db, office_primary, office_secondary, "跨领域打印纸", quantity=3
    )
    db.commit()

    context: dict[str, Any] = {
        "writer": writer,
        "readonly": readonly,
        "current_user": writer,
        "department_id": department.id,
        "terminal_inventory_id": terminal_inventory.id,
        "low_value_material_id": low_value_material.id,
        "repair_material_id": repair_material.id,
        "network_material_id": network_material.id,
        "tool_material_id": tool_material.id,
        "office_material_id": office_material.id,
        "category_primary_id": office_primary.id,
        "category_secondary_id": office_secondary.id,
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


def _seed_cross_domain_records(
    client: TestClient, context: dict[str, Any]
) -> dict[str, int]:
    """仅经真实写端点创建可被只读用户查询的跨领域记录和审计日志。"""
    inbound = client.post(
        "/fixed-assets/inbound",
        json={
            "terminal_inventory_id": context["terminal_inventory_id"],
            "source": "MANUAL",
            "asset_category_code": "PC",
            "fixed_asset_number": "CROSS-FA-001",
            "serial_number": "CROSS-SN-001",
        },
    )
    assert inbound.status_code == 200
    asset_id = inbound.json()["asset"]["id"]

    fixed_issue = client.post(
        f"/fixed-assets/{asset_id}/issue",
        json={
            "recipient_name": "跨领域领用人",
            "recipient_employee_id": "CROSS-EMP-001",
            "recipient_department": "跨领域测试部门",
            "issued_at": ISSUED_AT,
        },
    )
    assert fixed_issue.status_code == 200

    ordinary = client.post(
        "/material-issues",
        json={
            "warehouse_asset_id": context["low_value_material_id"],
            "quantity": 1,
            "issued_at": ISSUED_AT,
        },
    )
    assert ordinary.status_code == 200
    ordinary_issue_id = ordinary.json()["material_issue"]["id"]

    repair = client.post(
        "/repair-parts/issues",
        json={
            "warehouse_asset_id": context["repair_material_id"],
            "quantity": 1,
            "issued_at": ISSUED_AT,
            "target_asset_id": asset_id,
            "disk_serial_number": "CROSS-DISK-001",
        },
    )
    assert repair.status_code == 200

    network = client.post(
        "/network-consumables/issues",
        json={
            "warehouse_asset_id": context["network_material_id"],
            "quantity": 1,
            "issued_at": ISSUED_AT,
            "department_id": context["department_id"],
        },
    )
    assert network.status_code == 200

    office = client.post(
        "/office-consumables/issues",
        json={
            "warehouse_asset_id": context["office_material_id"],
            "quantity": 1,
            "issued_at": ISSUED_AT,
        },
    )
    assert office.status_code == 200

    tool = client.post(
        "/tool-loans",
        json={
            "warehouse_asset_id": context["tool_material_id"],
            "borrower_ref": "CROSS-TOOL-USER",
            "quantity": 1,
            "borrowed_at": ISSUED_AT,
            "expected_return_at": "2025-01-10T09:30:00",
            "tool_identifier": "CROSS-TOOL-QR",
        },
    )
    assert tool.status_code == 200
    return {
        "asset_id": asset_id,
        "ordinary_issue_id": ordinary_issue_id,
        "repair_issue_id": repair.json()["domain_record"]["id"],
        "network_issue_id": network.json()["domain_record"]["id"],
        "office_issue_id": office.json()["material_issue"]["id"],
        "tool_loan_id": tool.json()["tool_loan"]["id"],
    }


def _cross_domain_state(db: Session, material_ids: tuple[int, ...]) -> tuple[object, ...]:
    """覆盖资产、库存、各领域记录及审计，验证权限拒绝绝无副作用。"""
    db.expire_all()
    inventories = tuple(
        (item.id, item.total_quantity, item.available_quantity, item.allocated_quantity)
        for item in db.query(models.WarehouseAsset)
        .filter(models.WarehouseAsset.id.in_(material_ids))
        .order_by(models.WarehouseAsset.id)
    )
    assets = tuple(
        (item.id, item.status, item.employee_name, item.employee_id, item.department)
        for item in db.query(models.Asset).order_by(models.Asset.id)
    )
    issues = tuple(
        (item.id, item.warehouse_asset_id, item.record_type, item.unreturned_quantity)
        for item in db.query(models.MaterialIssue).order_by(models.MaterialIssue.id)
    )
    repairs = tuple(
        (item.id, item.material_issue_id, item.target_asset_id)
        for item in db.query(models.RepairPartIssue).order_by(models.RepairPartIssue.id)
    )
    networks = tuple(
        (item.id, item.material_issue_id, item.department_id)
        for item in db.query(models.NetworkConsumableIssue).order_by(
            models.NetworkConsumableIssue.id
        )
    )
    loans = tuple(
        (item.id, item.warehouse_asset_id, item.unreturned_quantity, item.status)
        for item in db.query(models.ToolLoan).order_by(models.ToolLoan.id)
    )
    return (
        assets,
        inventories,
        issues,
        repairs,
        networks,
        loans,
        db.query(models.MaterialReturn).count(),
        db.query(models.ToolLoanReturnEvent).count(),
        db.query(models.FixedAssetIssuance).count(),
        db.query(models.AssetLifecycleEvent).count(),
        tuple(
            (item.action, item.resource_type, item.resource_id)
            for item in db.query(models.OperationLog).order_by(models.OperationLog.id)
        ),
    )


def test_readonly_user_can_read_cross_domain_records_and_writes_have_no_effect(
    cross_domain_api_env,
) -> None:
    """只读用户可查询各领域列表/详情，代表性写操作均以中文 403 且不写审计。"""
    client, db, context = cross_domain_api_env
    ids = _seed_cross_domain_records(client, context)
    actions = {item.action for item in db.query(models.OperationLog).all()}
    assert {
        "fixed_asset_inbound",
        "fixed_asset_issue",
        "issue_material",
        "issue_repair_part",
        "issue_network_consumable",
        "issue_office_consumable",
        "borrow_tool",
    } <= actions

    context["current_user"] = context["readonly"]
    read_paths = (
        "/assets/",
        f"/assets/{ids['asset_id']}",
        "/warehouse/categories",
        "/warehouse/categories/primary",
        f"/warehouse/categories/primary/{context['category_primary_id']}/secondary",
        "/warehouse/materials",
        f"/warehouse/materials/{context['office_material_id']}",
        "/repair-parts/issues",
        f"/repair-parts/issues/{ids['repair_issue_id']}",
        "/network-consumables/issues",
        f"/network-consumables/issues/{ids['network_issue_id']}",
        "/office-consumables/issues",
        f"/office-consumables/issues/{ids['office_issue_id']}",
        "/tool-loans",
        f"/tool-loans/{ids['tool_loan_id']}",
    )
    for path in read_paths:
        assert client.get(path).status_code == 200

    material_ids = (
        context["terminal_inventory_id"],
        context["low_value_material_id"],
        context["repair_material_id"],
        context["network_material_id"],
        context["tool_material_id"],
        context["office_material_id"],
    )
    before = _cross_domain_state(db, material_ids)
    denied_writes = (
        ("post", f"/fixed-assets/{ids['asset_id']}/return", {
            "recipient_name": "跨领域领用人",
            "recipient_employee_id": "CROSS-EMP-001",
            "recipient_department": "跨领域测试部门",
        }),
        ("put", f"/warehouse/materials/{context['office_material_id']}", {
            "location": "只读用户不可修改的位置",
        }),
        ("post", "/material-issues", {
            "warehouse_asset_id": context["low_value_material_id"],
            "quantity": 1,
            "issued_at": ISSUED_AT,
        }),
        ("post", f"/material-issues/{ids['ordinary_issue_id']}/returns", {
            "quantity": 1,
            "returned_at": "2025-01-03T09:30:00",
        }),
        ("post", "/repair-parts/issues", {
            "warehouse_asset_id": context["repair_material_id"],
            "quantity": 1,
            "issued_at": ISSUED_AT,
            "target_asset_id": ids["asset_id"],
        }),
        ("post", "/network-consumables/issues", {
            "warehouse_asset_id": context["network_material_id"],
            "quantity": 1,
            "issued_at": ISSUED_AT,
        }),
        ("post", "/office-consumables/issues", {
            "warehouse_asset_id": context["office_material_id"],
            "quantity": 1,
            "issued_at": ISSUED_AT,
        }),
        ("post", "/tool-loans", {
            "warehouse_asset_id": context["tool_material_id"],
            "borrower_ref": "只读用户",
            "quantity": 1,
            "borrowed_at": ISSUED_AT,
            "expected_return_at": "2025-01-10T09:30:00",
        }),
        ("post", f"/tool-loans/{ids['tool_loan_id']}/returns", {
            "quantity": 1,
            "returned_at": "2025-01-03T09:30:00",
        }),
    )
    for method, path, payload in denied_writes:
        response = getattr(client, method)(path, json=payload)
        assert response.status_code == 403
        assert response.json()["detail"] == READONLY_WRITE_ERROR
        assert _cross_domain_state(db, material_ids) == before


def test_postgresql_concurrent_office_issues_commit_only_one_legal_transaction(
    postgresql_session_factory: sessionmaker,
) -> None:
    """两个独立 HTTP 请求竞争最后一件办公耗材时，行锁只允许一个事务提交。"""
    setup = postgresql_session_factory()
    try:
        writer_a = models.User(
            username="pg-concurrency-writer-a",
            hashed_password="not-used-by-test",
            full_name="并发经办人甲",
            role="MIS",
            is_active=True,
        )
        writer_b = models.User(
            username="pg-concurrency-writer-b",
            hashed_password="not-used-by-test",
            full_name="并发经办人乙",
            role="MIS",
            is_active=True,
        )
        setup.add_all((writer_a, writer_b))
        primary, secondary = _add_category(
            setup, "OFFICE_GENERAL_CONSUMABLES", "办公与通用耗材", "PG-OFFICE"
        )
        material = _add_material(
            setup, primary, secondary, "PostgreSQL 并发打印纸", quantity=1
        )
        setup.commit()
        writer_ids = (writer_a.id, writer_b.id)
        material_id = material.id
    finally:
        setup.close()

    users = {
        writer_id: type("TestUser", (), {"id": writer_id, "role": "MIS"})()
        for writer_id in writer_ids
    }

    def get_postgresql_db() -> Iterator[Session]:
        db = postgresql_session_factory()
        try:
            yield db
        finally:
            db.close()

    def concurrent_user(request: Request) -> Any:
        return users[int(request.headers["x-test-user-id"])]

    main.app.dependency_overrides[get_db] = get_postgresql_db
    main.app.dependency_overrides[get_current_active_user] = concurrent_user
    barrier = Barrier(2)
    try:
        with TestClient(main.app) as client:
            def issue_last_item(writer_id: int) -> int:
                barrier.wait(timeout=5)
                response = client.post(
                    "/office-consumables/issues",
                    headers={"x-test-user-id": str(writer_id)},
                    json={
                        "warehouse_asset_id": material_id,
                        "quantity": 1,
                        "issued_at": ISSUED_AT,
                    },
                )
                return response.status_code

            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = list(executor.map(issue_last_item, writer_ids))
    finally:
        main.app.dependency_overrides.clear()

    assert sorted(statuses) == [200, 409]
    check = postgresql_session_factory()
    try:
        material = check.get(models.WarehouseAsset, material_id)
        assert material is not None
        assert (material.total_quantity, material.available_quantity, material.allocated_quantity) == (
            1,
            0,
            1,
        )
        assert check.query(models.MaterialIssue).count() == 1
        assert check.query(models.OperationLog).filter(
            models.OperationLog.action == "issue_office_consumable"
        ).count() == 1
    finally:
        check.close()
