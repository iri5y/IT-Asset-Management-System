"""
import_v2.import_session
=========================
ImportSession：管理 Wizard 多步导入流程的中间状态。

职责：
  - 存储 Parse 阶段产生的 AssetRecord 列表，避免重复解析文件
  - 保存用户在 Mapping 步骤中的选择
  - 维护 Session 生命周期（TTL、状态机）
  - 提供安全校验（owner_user_id 防跨用户访问）

实现：
  - 内存存储（Python 字典），适合单 worker 部署
  - TTL = 30 分钟，懒清理（访问时检查）
  - SessionStore 是单例，通过 get_session_store() 获取

扩展接口：
  - SessionStore 实现了抽象接口 AbstractSessionStore
  - 未来切换 Redis 时，只需实现 AbstractSessionStore 并替换注入

状态机：
  PARSED → MAPPING_APPLIED → EXECUTING → COMPLETED
                                    ↓（失败回滚）
                               PARSED（允许重试）
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from .domain_models import AssetRecord
from .pipeline import PreviewSummary


# ===========================================================================
# 枚举
# ===========================================================================

class SessionStatus(str, Enum):
    PARSED           = "PARSED"            # Parse 完成，等待用户确认 Mapping
    MAPPING_APPLIED  = "MAPPING_APPLIED"   # 用户已提交 Mapping 配置
    EXECUTING        = "EXECUTING"         # 正在执行写库（中间态，防重复提交）
    COMPLETED        = "COMPLETED"         # 写库完成
    EXPIRED          = "EXPIRED"           # Session 已过期


# ===========================================================================
# Mapping 数据结构
# ===========================================================================

class MappingFieldType(str, Enum):
    """用户需要 Mapping 的字段类型"""
    DEPARTMENT = "department"
    BRAND      = "brand"
    LOCATION   = "location"


@dataclass
class MappingEntry:
    """
    单条 Mapping 记录：用户将原始文本映射到系统中已有的主数据。

    示例：
        原始值 "研发中心" → 系统中的 Department(id=3, name="IT研发部")

    字段：
        raw_value      — Excel 中的原始文本
        field_type     — 字段类型（DEPARTMENT / BRAND / LOCATION）
        resolved_id    — 用户选择的目标主数据 ID（写库时使用此 ID）
        resolved_name  — 用户选择的目标主数据名称（展示用）
        action         — "map_existing"（映射到已有）或 "skip"（跳过此字段）
    """
    raw_value:     str
    field_type:    MappingFieldType
    resolved_id:   Optional[int]   = None
    resolved_name: Optional[str]   = None
    action:        str             = "map_existing"   # "map_existing" | "skip"


# ===========================================================================
# ImportSession 数据对象
# ===========================================================================

# TTL 常量
_DEFAULT_TTL_MINUTES = 30
_POST_EXECUTE_TTL_MINUTES = 10   # 执行完成后延长 10 分钟供用户下载报告


@dataclass
class ImportSession:
    """
    Wizard 多步导入流程的会话数据容器。

    不直接实例化，通过 SessionStore.create() 创建。
    """

    # ── 标识与安全 ──
    session_id:      str
    owner_user_id:   int                    # 安全校验：只有创建者可操作此 Session
    last_request_id: str = ""               # 最后一次操作的 request_id，便于日志关联

    # ── 文件信息 ──
    source_filename: str = ""

    # ── Parse 阶段数据 ──
    parsed_records:  list[AssetRecord] = field(default_factory=list)
    preview_summary: Optional[PreviewSummary] = None

    # ── Mapping 阶段数据 ──
    # Key: f"{field_type}:{raw_value}"，例如 "department:研发中心"
    mapping: dict[str, MappingEntry] = field(default_factory=dict)

    # ── Policy 选择（用户在 Wizard Step 4 选择） ──
    duplicate_policy_type: str = "INSERT_ONLY"   # 与 ImportPolicyType 值对应

    # ── Execute 结果 ──
    execute_result: Optional[Any] = None         # PipelineResult 或 ImportResult

    # ── 生命周期 ──
    status:          SessionStatus = SessionStatus.PARSED
    created_at:      datetime = field(default_factory=datetime.now)
    last_accessed_at: datetime = field(default_factory=datetime.now)
    expire_at:       datetime = field(
        default_factory=lambda: datetime.now() + timedelta(minutes=_DEFAULT_TTL_MINUTES)
    )

    # ── 属性 ──────────────────────────────────────────────────────────────

    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expire_at

    @property
    def mapping_key(self) -> str:
        """Mapping 字典的 key 格式规范"""
        ...  # 由外部工具函数生成，见 make_mapping_key()

    def touch(self, request_id: str = "") -> None:
        """刷新访问时间，每次 API 调用都应调用此方法"""
        self.last_accessed_at = datetime.now()
        if request_id:
            self.last_request_id = request_id

    def update_mapping(self, entries: list[MappingEntry]) -> None:
        """
        合并用户提交的 Mapping 条目。
        允许多次调用（追加 + 覆盖），不会清空已有 Mapping。
        """
        for entry in entries:
            key = make_mapping_key(entry.field_type, entry.raw_value)
            self.mapping[key] = entry

    def get_mapping(
        self,
        field_type: MappingFieldType,
        raw_value: str,
    ) -> Optional[MappingEntry]:
        """查询某个原始值的 Mapping 结果"""
        key = make_mapping_key(field_type, raw_value)
        return self.mapping.get(key)

    def transition_to(self, new_status: SessionStatus) -> None:
        """
        状态机转换，校验合法转换路径。

        允许的转换：
          PARSED          → MAPPING_APPLIED
          MAPPING_APPLIED → EXECUTING
          EXECUTING       → COMPLETED
          EXECUTING       → PARSED  （执行失败回滚，允许重试）
          任意状态        → EXPIRED
        """
        allowed: dict[SessionStatus, set[SessionStatus]] = {
            SessionStatus.PARSED:          {SessionStatus.MAPPING_APPLIED},
            SessionStatus.MAPPING_APPLIED: {SessionStatus.EXECUTING},
            SessionStatus.EXECUTING:       {SessionStatus.COMPLETED, SessionStatus.PARSED},
            SessionStatus.COMPLETED:       {SessionStatus.EXPIRED},
        }
        if new_status == SessionStatus.EXPIRED:
            self.status = new_status
            return
        valid_targets = allowed.get(self.status, set())
        if new_status not in valid_targets:
            raise ValueError(
                f"非法 Session 状态转换: {self.status} → {new_status}，"
                f"允许: {', '.join(s.value for s in valid_targets)}"
            )
        self.status = new_status

    def extend_after_execute(self) -> None:
        """
        执行完成后，将过期时间延长到 now + 10min（供用户下载报告）。
        使用 max 确保只延长不缩短（防止 Session 刚创建就调用此方法时反而缩短时间）。
        """
        new_expire = datetime.now() + timedelta(minutes=_POST_EXECUTE_TTL_MINUTES)
        self.expire_at = max(self.expire_at, new_expire)


def make_mapping_key(field_type: MappingFieldType, raw_value: str) -> str:
    """生成 Mapping 字典的 key，格式：'department:研发中心'"""
    return f"{field_type.value}:{raw_value}"


# ===========================================================================
# 抽象存储接口（便于未来替换 Redis）
# ===========================================================================

class AbstractSessionStore(ABC):
    """
    Session 存储的抽象接口。

    当前实现：InMemorySessionStore（内存字典）
    未来实现：RedisSessionStore（待 Phase N）

    所有方法签名保持不变，替换时只需换注入的实例。
    """

    @abstractmethod
    def create(
        self,
        owner_user_id: int,
        source_filename: str,
        request_id: str = "",
    ) -> ImportSession:
        """创建新 Session，返回 ImportSession 对象"""
        ...

    @abstractmethod
    def get(self, session_id: str) -> Optional[ImportSession]:
        """
        按 session_id 获取 Session。
        若 Session 不存在或已过期，返回 None。
        """
        ...

    @abstractmethod
    def save(self, session: ImportSession) -> None:
        """持久化（或更新）Session 对象"""
        ...

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """主动删除 Session（Execute 完成后 10min 超时清理，或用户手动取消）"""
        ...

    @abstractmethod
    def purge_expired(self) -> int:
        """清理所有已过期 Session，返回清理数量"""
        ...


# ===========================================================================
# 内存实现
# ===========================================================================

class InMemorySessionStore(AbstractSessionStore):
    """
    基于内存字典的 Session 存储。

    特性：
      - 单进程内存，重启丢失（符合 v2.0 Non-Goals）
      - 懒清理：在 get() 时检查过期，purge_expired() 主动清理
      - 线程安全说明：FastAPI 单 worker + asyncio 场景下无并发写冲突；
        若未来切换多线程 worker，需加 threading.Lock

    注意：
      - 生产部署必须使用 Uvicorn 单 worker，否则不同 worker 的内存隔离
        会导致 session_id 跨 worker 查不到
    """

    def __init__(self) -> None:
        self._store: dict[str, ImportSession] = {}

    def create(
        self,
        owner_user_id: int,
        source_filename: str,
        request_id: str = "",
    ) -> ImportSession:
        """创建新 Session，自动生成 session_id，写入存储后返回"""
        session_id = str(uuid.uuid4())
        session = ImportSession(
            session_id=session_id,
            owner_user_id=owner_user_id,
            source_filename=source_filename,
            last_request_id=request_id,
        )
        self._store[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[ImportSession]:
        """
        获取 Session。

        返回 None 的情况：
          1. session_id 不存在
          2. Session 已过期（同时从内存清除）
        """
        session = self._store.get(session_id)
        if session is None:
            return None
        if session.is_expired:
            # 懒清理：访问时发现过期，立即移除
            del self._store[session_id]
            return None
        return session

    def get_and_verify(
        self,
        session_id: str,
        user_id: int,
    ) -> ImportSession:
        """
        获取 Session 并验证 owner。

        异常：
          ValueError — Session 不存在或已过期
          PermissionError — Session 不属于当前用户
        """
        session = self.get(session_id)
        if session is None:
            raise ValueError(f"导入会话 {session_id} 不存在或已过期，请重新上传文件")
        if session.owner_user_id != user_id:
            raise PermissionError("无权访问此导入会话")
        return session

    def save(self, session: ImportSession) -> None:
        """更新 Session（内存中直接覆盖，内存实现中对象引用即为同一个）"""
        self._store[session.session_id] = session

    def delete(self, session_id: str) -> None:
        """删除 Session"""
        self._store.pop(session_id, None)

    def purge_expired(self) -> int:
        """
        主动清理所有已过期 Session。
        可由 FastAPI lifespan 事件或后台任务定期调用。
        返回清理的数量。
        """
        expired_ids = [
            sid for sid, session in self._store.items()
            if session.is_expired
        ]
        for sid in expired_ids:
            del self._store[sid]
        return len(expired_ids)

    def count(self) -> int:
        """当前存活（未过期）Session 数量，用于监控"""
        return sum(1 for s in self._store.values() if not s.is_expired)

    def __repr__(self) -> str:
        return f"InMemorySessionStore(sessions={len(self._store)})"


# ===========================================================================
# 单例访问点
# ===========================================================================

_default_store: Optional[InMemorySessionStore] = None


def get_session_store() -> InMemorySessionStore:
    """
    获取全局单例 SessionStore。

    在 FastAPI 应用中，通过 Depends(get_session_store) 注入到路由处理函数。

    示例：
        @app.post("/assets/import/parse")
        async def import_parse(
            ...,
            store: InMemorySessionStore = Depends(get_session_store),
        ):
            session = store.create(user.id, filename, request_id)
            ...
    """
    global _default_store
    if _default_store is None:
        _default_store = InMemorySessionStore()
    return _default_store
