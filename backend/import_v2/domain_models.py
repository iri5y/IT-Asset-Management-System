"""
import_v2.domain_models
=======================
Import Pipeline 全生命周期的核心数据对象定义。

遵循 Phase 0 设计文档规范：
  - AssetRecord     : 流经 Pipeline 的数据载体，采用容器设计
  - ResolvedRefs    : Resolver 层输出的强类型主数据引用（含 ID）
  - ImportContext   : Pipeline 运行时共享上下文
  - 所有枚举类型

设计原则：
  - Pipeline 框架不硬编码业务字段名，通过 fields dict 传递
  - raw_fields 全程只读，用于调试和错误追溯
  - Resolver 返回 Ref 对象（含 id），Executor 直接使用，零重复查询
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    # 避免循环导入：仅类型检查时引入
    from sqlalchemy.orm import Session
    import models as db_models


# ===========================================================================
# 枚举类型
# ===========================================================================

class RecordClassification(str, Enum):
    """Classifier 对每条记录的分类结果"""
    VALID = "VALID"                         # 可直接导入
    MAPPING_REQUIRED = "MAPPING_REQUIRED"   # 主数据未匹配，需用户 Mapping
    DUPLICATE = "DUPLICATE"                 # 与已有记录冲突
    ERROR = "ERROR"                         # 格式/必填错误，禁止导入


class PolicyDecision(str, Enum):
    """ImportPolicy 对每条记录的处理决定"""
    INSERT = "INSERT"       # 新插入
    UPDATE = "UPDATE"       # 更新已有记录
    REPLACE = "REPLACE"     # 替换已有记录
    SKIP = "SKIP"           # 跳过


class IssueType(str, Enum):
    """Resolver 遇到主数据无法匹配时的问题类型"""
    UNKNOWN = "UNKNOWN"                 # 数据库无此记录
    MULTIPLE_MATCH = "MULTIPLE_MATCH"   # 模糊匹配到多个候选


class LocationType(str, Enum):
    """位置类型：库房位置 或 办公室位置"""
    WAREHOUSE = "WAREHOUSE"
    OFFICE = "OFFICE"


class ErrorType(str, Enum):
    """ImportResult 中错误条目的类型。"""
    FORMAT = "FORMAT"           # 格式错误（asset_tag 格式、日期格式等）
    VALIDATION = "VALIDATION"   # 业务规则校验失败（必填、状态非法等）
    MAPPING = "MAPPING"         # 主数据尚未映射或映射无效
    CONFLICT = "CONFLICT"       # 唯一性冲突（asset_tag/SN 重复）
    SYSTEM = "SYSTEM"           # 系统级异常（DB 错误、并发等）


class WarningType(str, Enum):
    """ImportResult 中警告条目的类型（非致命）。"""
    CATEGORY_INFERRED = "CATEGORY_INFERRED"     # 品类来自文件名推断
    EXTRA_COLUMNS = "EXTRA_COLUMNS"             # 存在未知列，存入 additional_info
    MAPPING_FALLBACK = "MAPPING_FALLBACK"       # 使用了模糊匹配
    POLICY_SKIP = "POLICY_SKIP"                 # 记录因用户策略被跳过
    WAREHOUSE_NOT_FOUND = "WAREHOUSE_NOT_FOUND" # 找不到对应库存条目


# ===========================================================================
# Resolver Ref 对象（强类型，含数据库 ID）
# ===========================================================================

@dataclass
class DepartmentRef:
    """已解析的部门主数据引用"""
    id: int
    name: str
    parent_id: Optional[int] = None


@dataclass
class BrandRef:
    """已解析的品牌主数据引用"""
    id: int
    name: str


@dataclass
class LocationRef:
    """已解析的位置主数据引用"""
    id: int
    name: str
    location_type: LocationType = LocationType.WAREHOUSE


@dataclass
class ResolvedRefs:
    """
    Resolver 层输出的强类型主数据引用集合。

    每个字段：
      - 精确唯一匹配 → 对应 Ref 对象
      - 无匹配或多匹配 → None（同时在 AssetRecord.resolver_issues 中记录原因）

    Executor 使用 resolved 中的 id/name，不再二次查库。
    """
    department: Optional[DepartmentRef] = None
    brand: Optional[BrandRef] = None
    location: Optional[LocationRef] = None


# ===========================================================================
# 问题与错误条目
# ===========================================================================

@dataclass
class ValidationError:
    """Validator 报告的单条校验错误"""
    field: str      # 中文字段名，如 "序列号"
    message: str    # 面向用户的错误描述


@dataclass
class ResolverIssue:
    """Resolver 无法解析主数据时的问题记录"""
    field: str              # 字段名，如 "department"
    raw_value: str          # 原始文本值
    issue_type: IssueType
    candidates: list[str] = field(default_factory=list)  # MULTIPLE_MATCH 时的候选列表


@dataclass
class DuplicateInfo:
    """Classifier 检测到重复时记录冲突来源和关键信息。"""
    asset_id: Optional[int]
    asset_tag: Optional[str]
    serial_number: Optional[str]
    status: Optional[str]
    conflict_field: str     # "asset_tag"、"serial_number" 等
    conflict_scope: str = "DATABASE"  # DATABASE 或 FILE
    first_row_number: Optional[int] = None


# ===========================================================================
# AssetRecord —— Pipeline 核心数据载体
# ===========================================================================

@dataclass
class AssetRecord:
    """
    贯穿整个 Import Pipeline 的数据载体。

    生命周期：
      ExcelSource  → 填充 raw_fields（只读）、fields、extra_fields
      Normalizer   → 修改 fields（标准化）
      Resolver     → 填充 resolved（Ref 对象，含 ID）
      Validator    → 填充 validation_errors
      Classifier   → 填充 classification、duplicate_info
      ImportPolicy → 填充 policy_decision
      Executor     → 读取并写库，record 本身不再变化

    设计约定：
      - raw_fields 全程只读（Source 填充后不得修改）
      - Pipeline 框架不硬编码 fields 中的 key
      - Executor 优先使用 resolved 中的 ID，fallback 到 fields 文本
    """

    # ── 控制字段（Pipeline 框架层，强类型） ──
    row_number: int
    source_filename: str

    # ── 原始快照（只读，Source 填充后不可修改） ──
    raw_fields: dict[str, Any] = field(default_factory=dict)

    # ── 标准化字段容器（Normalizer 修改） ──
    fields: dict[str, Any] = field(default_factory=dict)

    # ── 未知列数据（Executor 写入 additional_info） ──
    extra_fields: dict[str, Any] = field(default_factory=dict)

    # ── Resolver 解析结果（强类型） ──
    resolved: ResolvedRefs = field(default_factory=ResolvedRefs)

    # ── 分类标签层（Classifier 填充） ──
    classification: Optional[RecordClassification] = None
    duplicate_info: Optional[DuplicateInfo] = None

    # ── Policy 决定（ImportPolicy 填充） ──
    policy_decision: Optional[PolicyDecision] = None

    # ── 校验与 Resolve 问题列表 ──
    validation_errors: list[ValidationError] = field(default_factory=list)
    resolver_issues: list[ResolverIssue] = field(default_factory=list)

    def get_field(self, key: str, default: Any = None) -> Any:
        """安全读取 fields 中的值，不存在时返回 default"""
        return self.fields.get(key, default)

    def set_field(self, key: str, value: Any) -> None:
        """写入 fields 容器"""
        self.fields[key] = value

    def add_validation_error(self, field_name: str, message: str) -> None:
        """追加一条校验错误"""
        self.validation_errors.append(ValidationError(field=field_name, message=message))

    def add_resolver_issue(
        self,
        field_name: str,
        raw_value: str,
        issue_type: IssueType,
        candidates: Optional[list[str]] = None,
    ) -> None:
        """追加一条 Resolver 问题"""
        self.resolver_issues.append(
            ResolverIssue(
                field=field_name,
                raw_value=raw_value,
                issue_type=issue_type,
                candidates=candidates or [],
            )
        )

    @property
    def has_errors(self) -> bool:
        """是否存在校验错误"""
        return len(self.validation_errors) > 0

    @property
    def needs_mapping(self) -> bool:
        """是否存在需要用户手动处理的 Resolver 问题"""
        return len(self.resolver_issues) > 0


# ===========================================================================
# ImportContext —— Pipeline 运行时共享上下文
# ===========================================================================

@dataclass
class ImportContext:
    """
    Pipeline 执行时的运行时上下文，通过依赖注入传入各层。

    字段说明：
      request_id        — 每次 API 请求在入口处生成的 UUID4，
                          贯穿 Pipeline 全生命周期，写入所有日志条目，
                          错误响应中透传给前端，供运维查日志。
      db                — SQLAlchemy Session，Resolver/Classifier/Executor 共用，
                          保证在同一事务范围内。
      current_user      — 当前操作用户，写日志时记录操作人，权限校验依据。
      import_policy     — 导入策略实例，封装 DUPLICATE 的处理逻辑。
      session_id        — 关联的 ImportSession ID，Wizard 多步流程时有值，
                          单步旧接口调用时为 None。
      inferred_category — 从文件名推断的品类，Normalizer 在行内 category
                          为空时使用此值填充。
      dry_run           — True 时 Pipeline 完整走完验证但 Executor 不提交事务。
      operator_name     — current_user.full_name or username 的缓存，
                          避免每条记录重复计算。
    """

    request_id: str
    db: Any                         # sqlalchemy.orm.Session（避免循环导入用 Any）
    current_user: Any               # models.User
    import_policy: Any              # ImportPolicy 实例（Phase 2 定义）
    operator_name: str
    session_id: Optional[str] = None
    inferred_category: Optional[str] = None
    dry_run: bool = False

    @classmethod
    def create(
        cls,
        db: Any,
        current_user: Any,
        import_policy: Any,
        session_id: Optional[str] = None,
        inferred_category: Optional[str] = None,
        dry_run: bool = False,
    ) -> "ImportContext":
        """
        工厂方法：创建 ImportContext，自动生成 request_id 和 operator_name。
        API 层调用此方法，无需手动填充 request_id。
        """
        return cls(
            request_id=str(uuid.uuid4()),
            db=db,
            current_user=current_user,
            import_policy=import_policy,
            operator_name=(
                current_user.full_name or current_user.username
                if current_user else "unknown"
            ),
            session_id=session_id,
            inferred_category=inferred_category,
            dry_run=dry_run,
        )
