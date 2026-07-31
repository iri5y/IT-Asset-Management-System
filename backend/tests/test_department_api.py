"""部门删除保护 API 测试。"""

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


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


@pytest.fixture
def department_api_env() -> Iterator[tuple[TestClient, Session, models.User]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    admin = models.User(
        username="department-delete-admin",
        hashed_password="not-used",
        full_name="部门测试管理员",
        role="admin",
        is_active=True,
    )
    db.add(admin)
    db.commit()
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[get_current_active_user] = lambda: admin
    with TestClient(main.app) as client:
        yield client, db, admin
    main.app.dependency_overrides.clear()
    db.close()
    models.Base.metadata.drop_all(engine)
    engine.dispose()


def test_delete_department_referenced_by_asset_returns_409(
    department_api_env,
) -> None:
    """部门仍被资产引用时不得删除，且资产与部门数据均保持不变。"""
    client, db, _ = department_api_env
    department = models.Department(name="研发部")
    db.add(department)
    db.flush()
    asset = models.Asset(
        asset_tag="ZS-PC26-DEP001",
        category="台式机",
        status="闲置",
        department=department.name,
    )
    db.add(asset)
    db.commit()

    response = client.delete(f"/departments/{department.id}")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "该部门仍被资产或历史记录引用，请停用部门或迁移资产后再删除"
    )
    db.expire_all()
    assert db.get(models.Department, department.id) is not None
    assert db.get(models.Asset, asset.id) is not None