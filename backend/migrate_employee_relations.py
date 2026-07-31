"""建立员工主数据关系并安全回填历史引用。

运行方式：
    cd backend && python migrate_employee_relations.py
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from database import engine


@dataclass
class MigrationStats:
    """迁移结果；冲突和歧义只统计，不进行猜测性关联。"""

    employees_created: int = 0
    assets_backfilled: int = 0
    issuances_backfilled: int = 0
    tool_loans_backfilled: int = 0
    conflicts: int = 0
    ambiguities: int = 0
    unmatched_tool_loans: int = 0
    incomplete_employee_records: int = 0


def _china_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


def _clean(value) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _key(value) -> Optional[str]:
    normalized = _clean(value)
    return normalized.casefold() if normalized else None


def _create_employee_table(conn: Connection) -> None:
    if conn.dialect.name == "postgresql":
        id_column = "id SERIAL PRIMARY KEY"
        datetime_type = "TIMESTAMP"
    else:
        id_column = "id INTEGER PRIMARY KEY AUTOINCREMENT"
        datetime_type = "DATETIME"

    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS employees (
            {id_column},
            employee_no VARCHAR(100) NOT NULL,
            name VARCHAR(100) NOT NULL,
            department VARCHAR(100) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
            departure_date {datetime_type} NULL,
            created_at {datetime_type} NOT NULL,
            updated_at {datetime_type} NOT NULL,
            CONSTRAINT ck_employees_nonblank_identity CHECK (
                TRIM(employee_no) <> '' AND TRIM(name) <> ''
                AND TRIM(department) <> ''
            ),
            CONSTRAINT ck_employees_status CHECK (
                status IN ('ACTIVE', 'DEPARTED')
            ),
            CONSTRAINT ck_employees_status_departure_date CHECK (
                (status = 'ACTIVE' AND departure_date IS NULL) OR
                (status = 'DEPARTED' AND departure_date IS NOT NULL)
            )
        )
    """))


def _add_column_if_missing(
    conn: Connection, table_name: str, column_name: str
) -> None:
    columns = {column["name"] for column in inspect(conn).get_columns(table_name)}
    if column_name not in columns:
        conn.execute(text(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} INTEGER NULL"
        ))


def _create_indexes(conn: Connection) -> None:
    statements = (
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_employees_employee_no "
        "ON employees (employee_no)",
        "CREATE INDEX IF NOT EXISTS ix_employees_name ON employees (name)",
        "CREATE INDEX IF NOT EXISTS ix_employees_department "
        "ON employees (department)",
        "CREATE INDEX IF NOT EXISTS ix_employees_status ON employees (status)",
        "CREATE INDEX IF NOT EXISTS ix_employees_departure_date "
        "ON employees (departure_date)",
        "CREATE INDEX IF NOT EXISTS ix_assets_employee_ref_id "
        "ON assets (employee_ref_id)",
        "CREATE INDEX IF NOT EXISTS ix_fixed_asset_issuances_recipient_id "
        "ON fixed_asset_issuances (recipient_id)",
        "CREATE INDEX IF NOT EXISTS ix_tool_loans_borrower_id "
        "ON tool_loans (borrower_id)",
    )
    for statement in statements:
        conn.execute(text(statement))


def _add_postgresql_foreign_keys(conn: Connection) -> None:
    if conn.dialect.name != "postgresql":
        return
    constraints = (
        ("fk_assets_employee_ref_id", "assets", "employee_ref_id"),
        (
            "fk_fixed_asset_issuances_recipient_id",
            "fixed_asset_issuances",
            "recipient_id",
        ),
        ("fk_tool_loans_borrower_id", "tool_loans", "borrower_id"),
    )
    for name, table_name, column_name in constraints:
        exists = conn.execute(text(
            "SELECT 1 FROM pg_constraint WHERE conname = :name"
        ), {"name": name}).scalar()
        if not exists:
            conn.execute(text(
                f"ALTER TABLE {table_name} ADD CONSTRAINT {name} "
                f"FOREIGN KEY ({column_name}) REFERENCES employees(id) "
                "ON DELETE SET NULL"
            ))


def _prepare_schema(conn: Connection) -> None:
    _create_employee_table(conn)
    _add_column_if_missing(conn, "assets", "employee_ref_id")
    _add_column_if_missing(conn, "fixed_asset_issuances", "recipient_id")
    _add_column_if_missing(conn, "tool_loans", "borrower_id")
    _create_indexes(conn)
    _add_postgresql_foreign_keys(conn)


def _employee_source_rows(conn: Connection) -> Iterable[dict]:
    queries = (
        (
            "asset",
            "SELECT id, employee_id AS employee_no, employee_name AS name, "
            "department FROM assets WHERE employee_id IS NOT NULL",
        ),
        (
            "issuance",
            "SELECT id, recipient_employee_id AS employee_no, "
            "recipient_name AS name, recipient_department AS department "
            "FROM fixed_asset_issuances "
            "WHERE recipient_employee_id IS NOT NULL",
        ),
    )
    for source, statement in queries:
        for row in conn.execute(text(statement)).mappings():
            yield {"source": source, **dict(row)}


def _load_employees(conn: Connection) -> Dict[str, list]:
    result: Dict[str, list] = defaultdict(list)
    rows = conn.execute(text(
        "SELECT id, employee_no, name, department FROM employees ORDER BY id"
    )).mappings()
    for row in rows:
        employee_key = _key(row["employee_no"])
        if employee_key:
            result[employee_key].append(dict(row))
    return result


def _seed_employees(conn: Connection, stats: MigrationStats) -> Dict[str, list]:
    candidates: Dict[str, dict] = {}
    for row in _employee_source_rows(conn):
        employee_no = _clean(row["employee_no"])
        name = _clean(row["name"])
        department = _clean(row["department"])
        if not employee_no or not name or not department:
            stats.incomplete_employee_records += 1
            continue
        employee_key = employee_no.casefold()
        candidate = candidates.setdefault(employee_key, {
            "employee_no": employee_no,
            "names": set(),
            "departments": set(),
        })
        candidate["names"].add(name)
        candidate["departments"].add(department)

    employees = _load_employees(conn)
    now = _china_now()
    for employee_key, candidate in candidates.items():
        if len(candidate["names"]) != 1 or len(candidate["departments"]) != 1:
            stats.conflicts += 1
            continue
        name = next(iter(candidate["names"]))
        department = next(iter(candidate["departments"]))
        existing = employees.get(employee_key, [])
        if len(existing) > 1:
            stats.ambiguities += 1
            continue
        if existing:
            current = existing[0]
            if _key(current["name"]) != _key(name) or _key(
                current["department"]
            ) != _key(department):
                stats.conflicts += 1
            continue
        conn.execute(text(
            "INSERT INTO employees "
            "(employee_no, name, department, status, departure_date, "
            "created_at, updated_at) VALUES "
            "(:employee_no, :name, :department, 'ACTIVE', NULL, :now, :now)"
        ), {
            "employee_no": candidate["employee_no"],
            "name": name,
            "department": department,
            "now": now,
        })
        stats.employees_created += 1
    return _load_employees(conn)


def _same_employee_snapshot(row, employee: dict) -> bool:
    return (
        _key(row["employee_no"]) == _key(employee["employee_no"])
        and _key(row["name"]) == _key(employee["name"])
        and _key(row["department"]) == _key(employee["department"])
    )


def _backfill_structured_references(
    conn: Connection,
    employees: Dict[str, list],
    stats: MigrationStats,
) -> None:
    targets = (
        (
            "assets",
            "employee_ref_id",
            "employee_id",
            "employee_name",
            "department",
            "assets_backfilled",
        ),
        (
            "fixed_asset_issuances",
            "recipient_id",
            "recipient_employee_id",
            "recipient_name",
            "recipient_department",
            "issuances_backfilled",
        ),
    )
    for table_name, ref_column, no_column, name_column, dept_column, stat_name in targets:
        rows = conn.execute(text(
            f"SELECT id, {no_column} AS employee_no, {name_column} AS name, "
            f"{dept_column} AS department FROM {table_name} "
            f"WHERE {ref_column} IS NULL AND {no_column} IS NOT NULL"
        )).mappings()
        for row in rows:
            matches = employees.get(_key(row["employee_no"]), [])
            if len(matches) > 1:
                stats.ambiguities += 1
                continue
            if not matches:
                continue
            employee = matches[0]
            if not _same_employee_snapshot(row, employee):
                stats.conflicts += 1
                continue
            conn.execute(text(
                f"UPDATE {table_name} SET {ref_column} = :employee_id "
                "WHERE id = :record_id AND "
                f"{ref_column} IS NULL"
            ), {"employee_id": employee["id"], "record_id": row["id"]})
            setattr(stats, stat_name, getattr(stats, stat_name) + 1)


def _backfill_tool_loans(
    conn: Connection,
    employees: Dict[str, list],
    stats: MigrationStats,
) -> None:
    employees_by_name: Dict[str, list] = defaultdict(list)
    for matches in employees.values():
        for employee in matches:
            name_key = _key(employee["name"])
            if name_key:
                employees_by_name[name_key].append(employee)

    rows = conn.execute(text(
        "SELECT id, borrower_ref FROM tool_loans "
        "WHERE borrower_id IS NULL AND borrower_ref IS NOT NULL "
        "AND TRIM(borrower_ref) <> ''"
    )).mappings()
    for row in rows:
        borrower_key = _key(row["borrower_ref"])
        matches = employees.get(borrower_key, [])
        if not matches:
            matches = employees_by_name.get(borrower_key, [])
        unique_ids = {employee["id"] for employee in matches}
        if len(unique_ids) > 1:
            stats.ambiguities += 1
            continue
        if not unique_ids:
            stats.unmatched_tool_loans += 1
            continue
        employee_id = next(iter(unique_ids))
        conn.execute(text(
            "UPDATE tool_loans SET borrower_id = :employee_id "
            "WHERE id = :record_id AND borrower_id IS NULL"
        ), {"employee_id": employee_id, "record_id": row["id"]})
        stats.tool_loans_backfilled += 1


def _record_counts(conn: Connection) -> Dict[str, int]:
    return {
        table_name: conn.execute(
            text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar_one()
        for table_name in ("assets", "fixed_asset_issuances", "tool_loans")
    }


def run_migration(database_engine: Engine = engine) -> MigrationStats:
    """幂等执行建表、加列、索引、外键及安全回填。"""

    stats = MigrationStats()
    with database_engine.begin() as conn:
        before_counts = _record_counts(conn)
        _prepare_schema(conn)
        employees = _seed_employees(conn, stats)
        _backfill_structured_references(conn, employees, stats)
        _backfill_tool_loans(conn, employees, stats)
        after_counts = _record_counts(conn)
        if before_counts != after_counts:
            raise RuntimeError("迁移前后原业务表记录数不一致，已回滚")
    return stats


def main() -> None:
    try:
        stats = run_migration()
    except Exception as exc:
        print(f"❌ 员工关系迁移失败，事务已回滚：{exc}")
        raise

    print("✅ 员工关系迁移完成")
    print(f"  新建员工：{stats.employees_created}")
    print(f"  资产引用回填：{stats.assets_backfilled}")
    print(f"  固定资产发放引用回填：{stats.issuances_backfilled}")
    print(f"  工具借用引用回填：{stats.tool_loans_backfilled}")
    print(f"  冲突记录：{stats.conflicts}")
    print(f"  歧义记录：{stats.ambiguities}")
    print(f"  未匹配工具借用：{stats.unmatched_tool_loans}")
    print(f"  信息不完整员工来源：{stats.incomplete_employee_records}")
    print("  旧文本、旧日期及原业务表记录数均未修改")


if __name__ == "__main__":
    main()
