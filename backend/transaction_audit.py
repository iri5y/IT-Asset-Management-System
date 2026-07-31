"""领域写操作的统一事务、行锁与审计基础设施。"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Type
from uuid import UUID

from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

import models


class DomainTransactionError(RuntimeError):
    """领域事务未能持久化时抛出的基础异常。"""

    detail = "业务操作保存失败，事务已回滚"

    def __init__(self, detail: Optional[str] = None):
        super().__init__(detail or self.detail)


class AuditLogRequiredError(DomainTransactionError):
    """业务写操作缺少审计日志时拒绝提交。"""

    detail = "业务写操作缺少审计日志，事务已回滚"


class AuditLogPersistenceError(DomainTransactionError):
    """审计日志保存失败时触发整笔领域事务回滚。"""

    detail = "审计日志保存失败，业务操作已回滚"


def utc8_now() -> datetime:
    """返回项目约定的 UTC+8 无时区时间。"""
    return models.china_now()


def _json_value(value: Any) -> Any:
    """将 ORM 字段和值对象转换为可稳定序列化的 JSON 值。"""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(models.CHINA_TZ).replace(tzinfo=None)
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID, Enum)):
        return str(value.value if isinstance(value, Enum) else value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, set):
        return sorted((_json_value(item) for item in value), key=str)
    return value


def snapshot(
    record: Any,
    *,
    fields: Optional[Iterable[str]] = None,
) -> Optional[dict[str, Any]]:
    """提取 ORM 记录或字典的字段快照，不读取关系属性。"""
    if record is None:
        return None

    if isinstance(record, Mapping):
        values = dict(record)
    else:
        mapper = inspect(record).mapper
        allowed_fields = set(fields) if fields is not None else None
        values = {
            attribute.key: getattr(record, attribute.key)
            for attribute in mapper.column_attrs
            if allowed_fields is None or attribute.key in allowed_fields
        }

    return _json_value(values)


def snapshot_json(record: Any, *, fields: Optional[Iterable[str]] = None) -> str:
    """将记录快照编码为审计字段可直接使用的 JSON 文本。"""
    return json.dumps(snapshot(record, fields=fields), ensure_ascii=False, sort_keys=True)


class DomainTransaction:
    """统一管理一笔领域写操作的锁、审计、flush、提交和回滚。

    使用方式：先锁定并更新领域记录，调用 :meth:`flush` 验证业务写入，
    再调用 :meth:`record_audit`。上下文正常退出时才会提交；任一步失败均
    回滚同一 Session，因此库存、状态、绑定、历史记录与审计日志同成同败。
    """

    def __init__(self, db: Session, *, require_audit: bool = True):
        self.db = db
        self.require_audit = require_audit
        self._audit_recorded = False
        self._completed = False
        self._rolled_back = False

    def __enter__(self) -> "DomainTransaction":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        if exc_type is not None:
            self.rollback()
            return False
        self.commit()
        return False

    def flush(self) -> None:
        """在提交前立即验证当前领域写入，失败时回滚整笔事务。"""
        self._ensure_open()
        try:
            self.db.flush()
        except Exception as exc:
            self.rollback()
            raise DomainTransactionError() from exc

    def lock_one(
        self,
        model: Type[Any],
        record_id: Any,
        *,
        id_column: Any = None,
    ) -> Any:
        """按主键读取并加行锁；不存在时返回 ``None`` 由领域服务映射错误。"""
        self._ensure_open()
        column = id_column if id_column is not None else model.id
        return (
            self.db.query(model)
            .filter(column == record_id)
            .with_for_update()
            .one_or_none()
        )

    def lock_many(
        self,
        model: Type[Any],
        record_ids: Iterable[Any],
        *,
        id_column: Any = None,
    ) -> list[Any]:
        """按稳定主键顺序锁定多行，降低并发事务相互等待的机会。"""
        self._ensure_open()
        ids = sorted(set(record_ids))
        if not ids:
            return []
        column = id_column if id_column is not None else model.id
        return (
            self.db.query(model)
            .filter(column.in_(ids))
            .order_by(column)
            .with_for_update()
            .all()
        )


    def record_audit(
        self,
        *,
        user_id: int,
        action: str,
        resource_type: str,
        resource_id: Optional[int] = None,
        description: Optional[str] = None,
        before: Any = None,
        after: Any = None,
        related_records: Any = None,
        ip_address: Optional[str] = None,
    ) -> models.OperationLog:
        """写入并立即 flush 审计日志；审计失败会回滚所有已写领域数据。"""
        self._ensure_open()
        if self._audit_recorded:
            raise DomainTransactionError("同一领域事务只能保存一条操作审计日志")

        changed_at = utc8_now()
        old_value = self._audit_json(before, related_records, changed_at)
        new_value = self._audit_json(after, related_records, changed_at)
        log = models.OperationLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            created_at=changed_at,
        )
        try:
            self.db.add(log)
            # 此处的 flush 是审计日志失败的明确边界；此前业务数据仍未提交。
            self.db.flush()
        except Exception as exc:
            self.rollback()
            raise AuditLogPersistenceError() from exc

        self._audit_recorded = True
        return log

    def commit(self) -> None:
        """仅在领域数据和必需审计均已 flush 后提交当前会话。"""
        self._ensure_open()
        if self.require_audit and not self._audit_recorded:
            self.rollback()
            raise AuditLogRequiredError()
        try:
            self.db.flush()
            self.db.commit()
            self._completed = True
        except Exception as exc:
            self.rollback()
            raise DomainTransactionError() from exc

    def rollback(self) -> None:
        """幂等回滚当前会话中的全部领域数据和审计数据。"""
        if not self._completed and not self._rolled_back:
            self.db.rollback()
            self._rolled_back = True

    def _ensure_open(self) -> None:
        if self._completed:
            raise DomainTransactionError("领域事务已经提交，不能继续写入")
        if self._rolled_back:
            raise DomainTransactionError("领域事务已经回滚，不能继续写入")

    @staticmethod
    def _audit_json(
        values: Any,
        related_records: Any,
        changed_at: datetime,
    ) -> Optional[str]:
        if values is None and related_records is None:
            return None
        payload = {
            "snapshot_at": changed_at.isoformat(),
            "values": snapshot(values),
        }
        if related_records is not None:
            payload["related_records"] = _json_value(related_records)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def domain_transaction(db: Session, *, require_audit: bool = True) -> DomainTransaction:
    """创建领域事务上下文，供服务层以 ``with`` 方式使用。"""
    return DomainTransaction(db, require_audit=require_audit)
