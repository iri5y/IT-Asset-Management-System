import io
import os
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from auth import get_current_active_user
from database import get_db
from import_v2.import_session import InMemorySessionStore, SessionStatus


def make_xlsx(headers, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


@pytest.fixture
def api_env():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = models.User(
        username="phase4-user",
        hashed_password="not-used",
        full_name="Phase 4 User",
        role="MIS",
        is_active=True,
    )
    db.add(user)
    db.add_all([
        models.Department(name="研发部"),
        models.Brand(name="联想"),
        models.WarehouseLocation(name="A仓"),
    ])
    db.commit()
    store = InMemorySessionStore()

    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[get_current_active_user] = lambda: user
    main.app.dependency_overrides[main.get_session_store] = lambda: store
    with TestClient(main.app) as client:
        yield client, db, user, store
    main.app.dependency_overrides.clear()
    db.close()


def parse_file(client, tag="ZS-PD26-000001", department=None):
    headers = ["资产编号", "品类", "状态", "序列号"]
    row = [tag, "平板电脑", "闲置", f"SN-{tag}"]
    if department is not None:
        headers.append("部门")
        row.append(department)
    return client.post(
        "/assets/import/parse",
        files={"file": ("平板清单.xlsx", make_xlsx(headers, [row]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )


def test_parse_returns_preview_session_and_traceable_errors(api_env):
    client, _, _, store = api_env
    response = parse_file(client)
    assert response.status_code == 200
    body = response.json()
    assert body["preview_summary"] == {
        "total": 1,
        "valid": 1,
        "mapping_required": 0,
        "duplicate": 0,
        "error": 0,
    }
    assert body["records"][0]["classification"] == "VALID"
    assert body["request_id"]
    assert store.get(body["session_id"]).parsed_records

    rejected = client.post(
        "/assets/import/parse",
        files={"file": ("bad.csv", b"x", "text/csv")},
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "仅支持 .xlsx 格式文件"
    assert rejected.json()["request_id"]


def test_parse_header_only_file_returns_empty_preview(api_env):
    client, _, _, _ = api_env
    content = make_xlsx(["资产编号", "状态"], [])
    response = client.post(
        "/assets/import/parse",
        files={"file": ("empty.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200
    assert response.json()["preview_summary"]["total"] == 0
    assert response.json()["records"] == []


def test_session_owner_ttl_and_mapping_state_are_enforced(api_env):
    client, _, user, store = api_env
    parsed = parse_file(client).json()
    session = store.get(parsed["session_id"])

    session.owner_user_id = user.id + 1
    forbidden = client.post(
        "/assets/import/apply-mapping",
        json={"session_id": session.session_id, "mapping_entries": []},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "无权访问此导入会话"

    session.owner_user_id = user.id
    session.expire_at = datetime.now() - timedelta(seconds=1)
    expired = client.post(
        "/assets/import/apply-mapping",
        json={"session_id": session.session_id, "mapping_entries": []},
    )
    assert expired.status_code == 404

    parsed = parse_file(client, "ZS-MR26-000002").json()
    applied = client.post(
        "/assets/import/apply-mapping",
        json={"session_id": parsed["session_id"], "mapping_entries": []},
    )
    assert applied.status_code == 200
    repeated = client.post(
        "/assets/import/apply-mapping",
        json={"session_id": parsed["session_id"], "mapping_entries": []},
    )
    assert repeated.status_code == 409


def test_mapping_applies_refs_updates_policy_and_executes_update(api_env):
    client, db, _, store = api_env
    existing = models.Asset(
        asset_tag="ZS-PD26-009999",
        category="平板电脑",
        status="闲置",
        serial_number="EXISTING-SN",
    )
    db.add(existing)
    db.commit()

    content = make_xlsx(
        ["资产编号", "品类", "状态", "序列号", "部门"],
        [
            ["ZS-PD26-000010", "平板电脑", "闲置", "NEW-SN-001", "未知部门"],
            ["ZS-PD26-009999", "平板电脑", "闲置", "EXISTING-SN", "研发部"],
        ],
    )
    parsed = client.post(
        "/assets/import/parse",
        files={"file": ("mapping.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()
    department_id = db.query(models.Department).filter_by(name="研发部").one().id
    mapped = client.post(
        "/assets/import/apply-mapping",
        json={
            "session_id": parsed["session_id"],
            "duplicate_policy": "UPDATE_EXISTING",
            "mapping_entries": [{
                "raw_value": "未知部门",
                "field_type": "DEPARTMENT",
                "resolved_id": department_id,
                "resolved_name": "研发部",
                "action": "map_existing",
            }],
        },
    )
    assert mapped.status_code == 200
    assert mapped.json()["preview_summary"]["valid"] == 1
    assert mapped.json()["preview_summary"]["duplicate"] == 1
    assert mapped.json()["ready_to_execute"] is True

    session = store.get(parsed["session_id"])
    assert session.parsed_records[0].resolved.department.name == "研发部"
    assert session.parsed_records[0].resolver_issues == []
    assert session.parsed_records[1].policy_decision.value == "UPDATE"

    executed = client.post(
        "/assets/import/execute", json={"session_id": parsed["session_id"]}
    )
    assert executed.status_code == 200
    assert executed.json()["result"]["success_count"] == 2
    assert executed.json()["result"]["records"][1]["decision"] == "UPDATE"
    assert store.get(parsed["session_id"]).status == SessionStatus.COMPLETED
    assert db.query(models.Asset).count() == 2


def test_invalid_mapping_target_and_skip_do_not_become_ready(api_env):
    client, _, _, store = api_env
    parsed = parse_file(client, "ZS-MR26-000020", "未知部门").json()
    invalid = client.post(
        "/assets/import/apply-mapping",
        json={
            "session_id": parsed["session_id"],
            "mapping_entries": [{
                "raw_value": "未知部门",
                "field_type": "DEPARTMENT",
                "resolved_id": 999999,
                "action": "map_existing",
            }],
        },
    )
    assert invalid.status_code == 400
    assert store.get(parsed["session_id"]).mapping == {}

    skipped = client.post(
        "/assets/import/apply-mapping",
        json={
            "session_id": parsed["session_id"],
            "mapping_entries": [{
                "raw_value": "未知部门",
                "field_type": "DEPARTMENT",
                "action": "skip",
            }],
        },
    )
    assert skipped.status_code == 200
    assert skipped.json()["ready_to_execute"] is False
    assert skipped.json()["preview_summary"]["mapping_required"] == 1


def test_insert_only_execute_is_atomic_and_protected_from_replay(api_env):
    client, db, _, store = api_env
    parsed = parse_file(client, "ZS-MR26-000030").json()

    premature = client.post(
        "/assets/import/execute", json={"session_id": parsed["session_id"]}
    )
    assert premature.status_code == 409
    assert premature.json()["detail"] == "请先完成主数据映射步骤再执行导入"

    applied = client.post(
        "/assets/import/apply-mapping",
        json={"session_id": parsed["session_id"], "mapping_entries": []},
    )
    assert applied.json()["ready_to_execute"] is True
    executed = client.post(
        "/assets/import/execute", json={"session_id": parsed["session_id"]}
    )
    assert executed.status_code == 200
    assert executed.json()["result"]["success_count"] == 1
    assert executed.json()["result"]["skip_count"] == 0
    assert db.query(models.Asset).filter_by(asset_tag="ZS-MR26-000030").one()
    assert store.get(parsed["session_id"]).status == SessionStatus.COMPLETED

    replay = client.post(
        "/assets/import/execute", json={"session_id": parsed["session_id"]}
    )
    assert replay.status_code == 409
    assert replay.json()["detail"] == "导入已完成，请勿重复提交"
    assert db.query(models.Asset).filter_by(asset_tag="ZS-MR26-000030").count() == 1


def test_legacy_import_and_template_routes_remain_compatible(api_env):
    client, _, _, _ = api_env
    content = make_xlsx(
        ["资产编号", "品类", "状态", "序列号"],
        [["ZS-PD26-000040", "平板电脑", "闲置", "LEGACY-PD-SN-040"]],
    )
    legacy = client.post(
        "/assets/import",
        files={"file": ("legacy.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert legacy.status_code == 200
    assert set(legacy.json()) == {
        "total_rows", "success_count", "failed_count", "errors", "message"
    }
    assert legacy.json()["success_count"] == 1

    template = client.get("/assets/import-template")
    assert template.status_code == 200
    assert template.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_all_wizard_routes_require_write_permission(api_env):
    client, _, user, _ = api_env
    user.role = "readonly"
    for path in (
        "/assets/import/parse",
        "/assets/import/apply-mapping",
        "/assets/import/execute",
    ):
        if path.endswith("parse"):
            response = client.post(
                path,
                files={"file": ("x.xlsx", b"x", "application/octet-stream")},
            )
        else:
            response = client.post(path, json={"session_id": "missing"})
        assert response.status_code == 403
        assert response.json()["detail"] == "只读账号无权限执行修改或新增操作"


def test_preview_rejects_mouse_targeting_asset_table(api_env):
    """鼠标不能通过固定资产导入向 Asset 表写入。"""
    client, _, _, _ = api_env
    content = make_xlsx(
        ["资产编号", "品类", "状态"],
        [["ZS-MS26-000001", "Wireless Mouse", "闲置"]],
    )

    response = client.post(
        "/assets/import/parse",
        files={"file": (
            "mouse.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["preview_summary"]["error"] == 1
    assert body["records"][0]["classification"] == "ERROR"
    assert body["records"][0]["validation_errors"] == [{
        "field": "品类",
        "message": "该物品不属于固定资产，请导入低值领用物品或仓储物料",
    }]


def test_preview_marks_all_rows_with_duplicate_nb_serial_number(api_env):
    """同一 Excel 内两个 NB 使用相同 SN 时，预览即标记为 DUPLICATE。"""
    client, _, _, _ = api_env
    content = make_xlsx(
        ["资产编号", "品类", "状态", "序列号", "PO号"],
        [
            ["ZS-NB26-000001", "NB", "闲置", " abc123 ", "12000327"],
            ["ZS-NB26-000002", "笔记本电脑", "闲置", "ABC123", "12000328"],
        ],
    )

    response = client.post(
        "/assets/import/parse",
        files={"file": (
            "nb-duplicate-sn.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["preview_summary"]["duplicate"] == 2
    assert [record["classification"] for record in body["records"]] == [
        "DUPLICATE", "DUPLICATE"
    ]
    for record in body["records"]:
        duplicate = record["duplicate_info"]
        assert duplicate["conflict_field"] == "serial_number"
        assert duplicate["conflict_scope"] == "FILE"
        assert duplicate["serial_number"] == "ABC123"
        assert duplicate["first_row_number"] == 2
        assert duplicate["asset_id"] is None