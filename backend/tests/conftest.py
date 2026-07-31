"""后端测试共用数据库夹具。"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

# 必须在导入 models 前覆盖本地 .env，避免测试收集阶段连接生产数据库。
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import models

POSTGRES_TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"


def _sqlite_url(database_path: Path) -> str:
    return database_path.resolve().as_uri().replace(
        "file:", "sqlite+pysqlite:", 1
    )


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _postgres_test_database_url() -> str:
    database_url = os.getenv(POSTGRES_TEST_DATABASE_URL_ENV)
    if not database_url:
        pytest.skip(
            f"未设置 {POSTGRES_TEST_DATABASE_URL_ENV}，跳过 PostgreSQL 集成测试"
        )

    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise pytest.UsageError(
            f"{POSTGRES_TEST_DATABASE_URL_ENV} 必须是 PostgreSQL 连接字符串"
        )
    if not url.database or "test" not in url.database.lower():
        raise pytest.UsageError(
            f"{POSTGRES_TEST_DATABASE_URL_ENV} 必须指向名称含 test 的独立测试数据库"
        )
    return database_url


@pytest.fixture
def sqlite_engine(tmp_path: Path) -> Iterator[Engine]:
    """提供每个测试独享、已开启外键约束的 SQLite 临时数据库。"""
    engine = create_engine(_sqlite_url(tmp_path / "backend-test.sqlite3"))
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    models.Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        models.Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def sqlite_session_factory(sqlite_engine: Engine) -> sessionmaker:
    return sessionmaker(bind=sqlite_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db_session(sqlite_session_factory: sessionmaker) -> Iterator[Session]:
    """提供与 SQLite 临时库绑定的测试会话。"""
    session = sqlite_session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def postgresql_engine() -> Iterator[Engine]:
    """提供可选的、每例清理的 PostgreSQL 集成测试数据库。"""
    engine = create_engine(_postgres_test_database_url(), pool_pre_ping=True)
    models.Base.metadata.drop_all(engine)
    models.Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        models.Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def postgresql_session_factory(postgresql_engine: Engine) -> sessionmaker:
    return sessionmaker(
        bind=postgresql_engine,
        autoflush=False,
        expire_on_commit=False,
    )


@pytest.fixture
def postgresql_session(
    postgresql_session_factory: sessionmaker,
) -> Iterator[Session]:
    """提供与可选 PostgreSQL 集成库绑定的测试会话。"""
    session = postgresql_session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
