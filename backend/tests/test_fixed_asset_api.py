"""固定资产受控入库与生命周期 API 集成测试。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from auth import get_current_active_user
from database import get_db

READONLY_WRITE_ERROR = "只读账号无权限执行修改或新增操作"


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


@pytest.fixture
def fixed_asset_api_env() -> Iterator[tuple[TestClient, Session, dict[str, object]]]:
    """提供带终端设备库存、可切换经办人的隔离 API 环境。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    admin = models.User(
        username="fixed-asset-api-admin",
        hashed_password="not-used-by-api-test",
        full_name="固定资产测试管理员",
        role="admin",
        is_active=True,
    )
    writer = models.User(
        username="fixed-asset-api-writer",
        hashed_password="not-used-by-api-test",
        full_name="固定资产测试经办人",
        role="MIS",
        is_active=True,
    )
    readonly = models.User(
        username="fixed-asset-api-readonly",
        hashed_password="not-used-by-api-test",
        full_name="固定资产只读用户",
        role="readonly",
        is_active=True,
    )
    primary = models.WarehousePrimaryCategory(
        code="TERMINAL_EQUIPMENT",
        name="终端设备库存",
        is_active=True,
    )
    db.add_all((admin, writer, readonly, primary))
    db.flush()
    secondary = models.WarehouseSecondaryCategory(
        primary_category_id=primary.id,
        code="API_TERMINAL",
        name="API 终端设备",
        is_active=True,
    )
    db.add(secondary)
    db.flush()
    inventory = models.WarehouseAsset(
        name="API 固定资产终端库存",
        category=primary.name,
        subcategory=secondary.name,
        total_quantity=0,
        available_quantity=0,
        allocated_quantity=0,
        minimum_stock=0,
        low_stock_threshold=0,
        primary_category_id=primary.id,
        secondary_category_id=secondary.id,
        classification_status="ACTIVE",
        issue_policy="CONSUMABLE",
    )
    db.add(inventory)
    db.commit()

    context: dict[str, object] = {
        "writer": writer,
        "readonly": readonly,
        "current_user": writer,
        "inventory_id": inventory.id,
    }
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[get_current_active_user] = lambda: context["current_user"]
    with TestClient(main.app) as client:
        yield client, db, context
    main.app.dependency_overrides.clear()
    db.close()
    models.Base.metadata.drop_all(engine)
    engine.dispose()


def _inbound_payload(
    inventory_id: int,
    fixed_asset_number: str,
    serial_number: str,
    *,
    category: str = "PC",
    source: str = "SCAN",
) -> dict[str, object]:
    return {
        "terminal_inventory_id": inventory_id,
        "source": source,
        "asset_category_code": category,
        "fixed_asset_number": fixed_asset_number,
        "serial_number": serial_number,
    }


def _fixed_asset_state(db: Session, inventory_id: int) -> tuple[object, ...]:
    """快照固定资产、库存及生命周期记录，供权限和失败无副作用断言复用。"""
    db.expire_all()
    inventory = db.get(models.WarehouseAsset, inventory_id)
    assert inventory is not None
    return (
        tuple(
            (
                asset.id,
                asset.fixed_asset_number,
                asset.serial_number,
                asset.status,
                asset.employee_name,
                asset.employee_id,
                asset.department,
                asset.issue_date,
            )
            for asset in db.query(models.Asset).order_by(models.Asset.id)
        ),
        (inventory.total_quantity, inventory.available_quantity, inventory.allocated_quantity),
        db.query(models.FixedAssetInbound).count(),
        db.query(models.FixedAssetIssuance).count(),
        tuple(
            (event.asset_id, event.event_type)
            for event in db.query(models.AssetLifecycleEvent).order_by(
                models.AssetLifecycleEvent.id
            )
        ),
    )


def test_batch_inbound_returns_per_item_results_and_keeps_successes(
    fixed_asset_api_env,
) -> None:
    """批量入库中重复序列号失败时，其他有效项目仍独立入库。"""
    client, db, context = fixed_asset_api_env
    inventory_id = context["inventory_id"]
    assert isinstance(inventory_id, int)
    response = client.post(
        "/fixed-assets/inbound/batch",
        json={
            "items": [
                _inbound_payload(inventory_id, "FA-BATCH-001", "SN-BATCH-001"),
                _inbound_payload(inventory_id, "FA-BATCH-002", "SN-BATCH-001"),
                _inbound_payload(
                    inventory_id,
                    "FA-BATCH-003",
                    "SN-BATCH-003",
                    category="PD",
                    source="MANUAL",
                ),
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert (payload["success_count"], payload["failed_count"]) == (2, 1)
    assert [(item["index"], item["status"], item["success"]) for item in payload["results"]] == [
        (0, "SUCCESS", True),
        (1, "FAILED", False),
        (2, "SUCCESS", True),
    ]
    failed = payload["results"][1]
    assert failed["status_code"] == 409
    assert "资产编号或序列号已存在" in failed["message"]
    assert payload["results"][0]["result"]["asset"]["status"] == "闲置"
    assert payload["results"][2]["result"]["asset"]["category"] == "平板电脑"

    inventory = db.get(models.WarehouseAsset, inventory_id)
    assert inventory is not None
    assert (inventory.total_quantity, inventory.available_quantity, inventory.allocated_quantity) == (2, 2, 0)
    assert db.query(models.Asset).count() == 2
    assert db.query(models.FixedAssetInbound).count() == 2


def test_lifecycle_endpoints_atomically_update_status_binding_and_inventory(
    fixed_asset_api_env,
) -> None:
    """发放、转移、送修、维修完成和归还应保持状态、绑定与库存同步。"""
    client, db, context = fixed_asset_api_env
    inventory_id = context["inventory_id"]
    assert isinstance(inventory_id, int)
    inbound = client.post(
        "/fixed-assets/inbound",
        json=_inbound_payload(inventory_id, "FA-LIFE-001", "SN-LIFE-001", category="NB"),
    )
    assert inbound.status_code == 200
    asset_id = inbound.json()["asset"]["id"]
    assert inbound.json()["terminal_inventory"] == {
        "id": inventory_id,
        "total_quantity": 1,
        "available_quantity": 1,
        "allocated_quantity": 0,
    }

    first_binding = {
        "recipient_name": "领用人甲",
        "recipient_employee_id": "EMP-001",
        "recipient_department": "信息部",
        "issued_at": "2025-01-01T09:30:00",
    }
    issued = client.post(f"/fixed-assets/{asset_id}/issue", json=first_binding)
    assert issued.status_code == 200
    assert issued.json()["issuance_id"] is not None
    assert issued.json()["lifecycle_event_id"] is not None
    assert issued.json()["asset"]["status"] == "使用中"
    assert issued.json()["asset"]["employee_id"] == "EMP-001"
    assert issued.json()["terminal_inventory"]["available_quantity"] == 0
    assert issued.json()["terminal_inventory"]["allocated_quantity"] == 1

    transferred = client.post(
        f"/fixed-assets/{asset_id}/transfer",
        json={
            "recipient_name": "领用人乙",
            "recipient_employee_id": "EMP-002",
            "recipient_department": "研发部",
            "issued_at": "2025-01-02T09:30:00",
        },
    )
    assert transferred.status_code == 200
    assert transferred.json()["asset"]["status"] == "使用中"
    assert transferred.json()["asset"]["employee_id"] == "EMP-002"
    assert transferred.json()["terminal_inventory"]["available_quantity"] == 0
    assert transferred.json()["terminal_inventory"]["allocated_quantity"] == 1

    repaired = client.post(f"/fixed-assets/{asset_id}/repair")
    assert repaired.status_code == 200
    assert repaired.json()["asset"]["status"] == "维修中"
    assert repaired.json()["asset"]["employee_name"] is None
    assert repaired.json()["terminal_inventory"]["available_quantity"] == 0
    assert repaired.json()["terminal_inventory"]["allocated_quantity"] == 1

    repair_completed = client.post(
        f"/fixed-assets/{asset_id}/repair-complete",
        json={
            "recipient_name": "领用人丙",
            "recipient_employee_id": "EMP-003",
            "recipient_department": "财务部",
            "issued_at": "2025-01-03T09:30:00",
        },
    )
    assert repair_completed.status_code == 200
    assert repair_completed.json()["asset"]["status"] == "使用中"
    assert repair_completed.json()["asset"]["employee_id"] == "EMP-003"
    assert repair_completed.json()["terminal_inventory"]["available_quantity"] == 0
    assert repair_completed.json()["terminal_inventory"]["allocated_quantity"] == 1

    returned = client.post(
        f"/fixed-assets/{asset_id}/return",
        json={
            "recipient_name": "领用人丙",
            "recipient_employee_id": "EMP-003",
            "recipient_department": "财务部",
        },
    )
    assert returned.status_code == 200
    assert returned.json()["asset"]["status"] == "闲置"
    assert returned.json()["asset"]["employee_name"] is None
    assert returned.json()["terminal_inventory"]["available_quantity"] == 1
    assert returned.json()["terminal_inventory"]["allocated_quantity"] == 0
    assert [
        event.event_type
        for event in db.query(models.AssetLifecycleEvent)
        .filter(models.AssetLifecycleEvent.asset_id == asset_id)
        .order_by(models.AssetLifecycleEvent.id)
    ] == ["ISSUE", "TRANSFER", "REPAIR_SENT", "REPAIR_COMPLETED", "RETURN"]


def test_duplicate_inbound_and_old_asset_entry_return_chinese_errors_without_cards(
    fixed_asset_api_env,
) -> None:
    """唯一性冲突和旧通用入口均返回中文错误，且不得创建额外固定资产卡。"""
    client, db, context = fixed_asset_api_env
    inventory_id = context["inventory_id"]
    assert isinstance(inventory_id, int)
    initial = client.post(
        "/fixed-assets/inbound",
        json=_inbound_payload(inventory_id, "FA-UNIQUE-001", "SN-UNIQUE-001"),
    )
    assert initial.status_code == 200
    before = _fixed_asset_state(db, inventory_id)

    duplicate = client.post(
        "/fixed-assets/inbound",
        json=_inbound_payload(inventory_id, "FA-UNIQUE-002", "SN-UNIQUE-001"),
    )
    assert duplicate.status_code == 409
    assert "资产编号或序列号已存在" in duplicate.json()["detail"]
    assert _fixed_asset_state(db, inventory_id) == before

    legacy = client.post(
        "/assets/",
        json={
            "asset_tag": "LEGACY-PC-001",
            "category": "台式机",
            "serial_number": "LEGACY-SN-001",
            "fixed_asset_number": "LEGACY-FA-001",
            "po_number": "2025001",
            "status": "闲置",
        },
    )
    assert legacy.status_code == 400
    assert legacy.json()["detail"] == "台式机、笔记本电脑和平板电脑仅可通过受控固定资产入库创建"
    assert _fixed_asset_state(db, inventory_id) == before


def test_readonly_user_can_query_assets_but_cannot_execute_fixed_asset_writes(
    fixed_asset_api_env,
) -> None:
    """只读用户可读取资产列表/详情，但所有受控入库和生命周期写操作均被拒绝。"""
    client, db, context = fixed_asset_api_env
    inventory_id = context["inventory_id"]
    assert isinstance(inventory_id, int)
    inbound = client.post(
        "/fixed-assets/inbound",
        json=_inbound_payload(inventory_id, "FA-READ-001", "SN-READ-001"),
    )
    assert inbound.status_code == 200
    asset_id = inbound.json()["asset"]["id"]
    context["current_user"] = context["readonly"]

    listed = client.get("/assets/")
    assert listed.status_code == 200
    assert any(item["id"] == asset_id for item in listed.json())
    detail = client.get(f"/assets/{asset_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == asset_id

    before = _fixed_asset_state(db, inventory_id)
    write_requests = (
        ("post", "/fixed-assets/inbound", _inbound_payload(inventory_id, "FA-READ-002", "SN-READ-002")),
        ("post", f"/fixed-assets/{asset_id}/issue", {
            "recipient_name": "禁止发放", "recipient_employee_id": "EMP-R1",
            "recipient_department": "信息部", "issued_at": "2025-01-01T08:00:00",
        }),
        ("post", f"/fixed-assets/{asset_id}/return", {
            "recipient_name": "禁止归还", "recipient_employee_id": "EMP-R1", "recipient_department": "信息部",
        }),
        ("post", f"/fixed-assets/{asset_id}/transfer", {
            "recipient_name": "禁止转移", "recipient_employee_id": "EMP-R2",
            "recipient_department": "研发部", "issued_at": "2025-01-02T08:00:00",
        }),
        ("post", f"/fixed-assets/{asset_id}/repair", None),
        ("post", f"/fixed-assets/{asset_id}/repair-complete", {}),
    )
    for method, path, payload in write_requests:
        response = getattr(client, method)(path, json=payload)
        assert response.status_code == 403
        assert response.json()["detail"] == READONLY_WRITE_ERROR
        assert _fixed_asset_state(db, inventory_id) == before


def _use_admin(db: Session, context: dict[str, object]) -> None:
    """将当前 API 身份切换为夹具中的管理员。"""
    admin = db.query(models.User).filter(models.User.role == "admin").one()
    context["current_user"] = admin


def test_delete_in_use_fixed_asset_returns_409_without_side_effects(
    fixed_asset_api_env,
) -> None:
    """使用中的 NB001 不得删除，且失败请求不能产生任何副作用。"""
    client, db, context = fixed_asset_api_env
    inventory_id = context["inventory_id"]
    assert isinstance(inventory_id, int)
    inbound = client.post(
        "/fixed-assets/inbound",
        json=_inbound_payload(inventory_id, "NB001", "SN-DELETE-IN-USE", category="NB"),
    )
    assert inbound.status_code == 200
    asset_id = inbound.json()["asset"]["id"]
    issued = client.post(
        f"/fixed-assets/{asset_id}/issue",
        json={
            "recipient_name": "领用人甲",
            "recipient_employee_id": "EMP-DELETE-001",
            "recipient_department": "信息部",
            "issued_at": "2025-01-01T09:30:00",
        },
    )
    assert issued.status_code == 200
    before = _fixed_asset_state(db, inventory_id)
    _use_admin(db, context)

    response = client.request(
        "DELETE", f"/assets/{asset_id}", json={"reason": "不应成功的删除"}
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "当前资产处于使用中或维修中状态，请先归还、完成维修或执行报废流程"
    )
    assert _fixed_asset_state(db, inventory_id) == before
    db.expire_all()
    asset = db.get(models.Asset, asset_id)
    assert asset is not None and asset.is_deleted is False
    assert db.query(models.AssetDeletionRecord).count() == 0
    assert db.query(models.OperationLog).filter(
        models.OperationLog.resource_id == asset_id,
        models.OperationLog.action == "delete",
    ).count() == 0


def test_delete_idle_fixed_asset_soft_deletes_and_reconciles_inventory(
    fixed_asset_api_env,
) -> None:
    """闲置 NB001 允许软删除，并从准确关联的终端库存移除一张可用卡。"""
    client, db, context = fixed_asset_api_env
    inventory_id = context["inventory_id"]
    assert isinstance(inventory_id, int)
    inbound = client.post(
        "/fixed-assets/inbound",
        json=_inbound_payload(inventory_id, "NB001", "SN-DELETE-IDLE", category="NB"),
    )
    assert inbound.status_code == 200
    asset_id = inbound.json()["asset"]["id"]
    _use_admin(db, context)

    response = client.request(
        "DELETE", f"/assets/{asset_id}", json={"reason": "闲置资产清理"}
    )

    assert response.status_code == 200
    db.expire_all()
    asset = db.get(models.Asset, asset_id)
    inventory = db.get(models.WarehouseAsset, inventory_id)
    assert asset is not None and asset.is_deleted is True and asset.deleted_at is not None
    assert inventory is not None
    assert (inventory.total_quantity, inventory.available_quantity, inventory.allocated_quantity) == (0, 0, 0)
    assert client.get(f"/assets/{asset_id}").status_code == 404
    assert db.query(models.FixedAssetInbound).filter_by(asset_id=asset_id).count() == 1
    assert db.query(models.AssetDeletionRecord).filter_by(asset_id=asset_id).count() == 1
    assert db.query(models.OperationLog).filter_by(
        resource_type="asset", resource_id=asset_id, action="delete"
    ).count() == 1
    assert db.query(models.AssetLog).filter_by(
        asset_id=asset_id, action="删除资产"
    ).count() == 1
    assert db.query(models.WarehouseAssetLog).filter_by(
        asset_id=inventory_id, action="固定资产删除出库"
    ).count() == 1


def test_delete_returned_fixed_asset_preserves_issuance_and_lifecycle_history(
    fixed_asset_api_env,
) -> None:
    """发放后归还的闲置资产删除后，领用和生命周期历史必须保持一致。"""
    client, db, context = fixed_asset_api_env
    inventory_id = context["inventory_id"]
    assert isinstance(inventory_id, int)
    inbound = client.post(
        "/fixed-assets/inbound",
        json=_inbound_payload(inventory_id, "NB001", "SN-DELETE-HISTORY", category="NB"),
    )
    assert inbound.status_code == 200
    asset_id = inbound.json()["asset"]["id"]
    binding = {
        "recipient_name": "领用人乙",
        "recipient_employee_id": "EMP-DELETE-002",
        "recipient_department": "研发部",
        "issued_at": "2025-01-02T09:30:00",
    }
    issued = client.post(f"/fixed-assets/{asset_id}/issue", json=binding)
    assert issued.status_code == 200
    returned = client.post(
        f"/fixed-assets/{asset_id}/return",
        json={key: binding[key] for key in (
            "recipient_name", "recipient_employee_id", "recipient_department"
        )},
    )
    assert returned.status_code == 200
    issuance_ids = [
        row.id for row in db.query(models.FixedAssetIssuance)
        .filter_by(asset_id=asset_id).order_by(models.FixedAssetIssuance.id)
    ]
    lifecycle_rows = [
        (row.id, row.event_type) for row in db.query(models.AssetLifecycleEvent)
        .filter_by(asset_id=asset_id).order_by(models.AssetLifecycleEvent.id)
    ]
    assert issuance_ids
    assert [event_type for _, event_type in lifecycle_rows] == ["ISSUE", "RETURN"]
    _use_admin(db, context)

    response = client.request(
        "DELETE", f"/assets/{asset_id}", json={"reason": "归还后清理"}
    )

    assert response.status_code == 200
    db.expire_all()
    asset = db.get(models.Asset, asset_id)
    inventory = db.get(models.WarehouseAsset, inventory_id)
    assert asset is not None and asset.is_deleted is True
    assert (asset.employee_name, asset.employee_id, asset.department, asset.issue_date) == (
        None, None, None, None
    )
    assert inventory is not None
    assert (inventory.total_quantity, inventory.available_quantity, inventory.allocated_quantity) == (0, 0, 0)
    assert [
        row.id for row in db.query(models.FixedAssetIssuance)
        .filter_by(asset_id=asset_id).order_by(models.FixedAssetIssuance.id)
    ] == issuance_ids
    assert [
        (row.id, row.event_type) for row in db.query(models.AssetLifecycleEvent)
        .filter_by(asset_id=asset_id).order_by(models.AssetLifecycleEvent.id)
    ] == lifecycle_rows
    assert db.query(models.FixedAssetInbound).filter_by(asset_id=asset_id).count() == 1