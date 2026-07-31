"""
import_v2.pipeline
===================
ImportPipeline：编排 Source → Normalizer → Resolver → Validator →
                Classifier → Policy 的完整 Parse 流程。

职责（单一）：
  - 串联各处理层，按顺序执行
  - 收集并返回 PipelineResult（记录列表 + 摘要统计）
  - 不负责写库（那是 Executor 的职责，Phase 6 实现）
  - 兼容两种调用模式：
      * parse_only  — 只做 Parse + Normalize + Resolve + Validate + Classify
                      返回 PipelineResult，不执行写库，供 Wizard Preview 使用
      * run_legacy  — 旧接口兼容模式，接受 file_bytes 直接返回 PipelineResult，
                      调用方（main.py 旧路由）负责调用 Executor 写库

设计约定：
  - Pipeline 本身无状态，可重复调用
  - 各层实例由外部注入（便于测试替换）
  - 若 context.dry_run=True，Policy 会将所有 policy_decision 设为 SKIP，
    Executor 不会真正写库
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .classifier import Classifier
from .domain_models import (
    AssetRecord,
    ImportContext,
    RecordClassification,
    WarningType,
)
from .import_policy import ImportPolicy
from .normalizer import Normalizer
from .resolvers import BrandResolver, DepartmentResolver, LocationResolver
from .sources.excel_source import ExcelSource
from .validator import Validator


# ===========================================================================
# PipelineResult —— parse_only / run_legacy 的返回值
# ===========================================================================

@dataclass
class PreviewSummary:
    """各分类的记录数量摘要，供前端 Wizard 渲染 Preview 页面"""
    total: int = 0
    valid: int = 0
    mapping_required: int = 0
    duplicate: int = 0
    error: int = 0

    def to_dict(self) -> dict:
        return {
            "total":            self.total,
            "valid":            self.valid,
            "mapping_required": self.mapping_required,
            "duplicate":        self.duplicate,
            "error":            self.error,
        }


@dataclass
class PipelineWarning:
    """Pipeline 过程中产生的非致命警告"""
    row_number: int
    asset_tag: Optional[str]
    warning_type: WarningType
    message: str


@dataclass
class PipelineResult:
    """
    Pipeline.parse_only() 的完整返回值。

    records        — 经过所有层处理后的 AssetRecord 列表，
                     每条记录含 classification 和 policy_decision
    summary        — 分类计数摘要
    warnings       — 非致命警告列表
    inferred_category — 从文件名推断的品类（可为 None）
    request_id     — 来自 ImportContext，便于日志关联
    """
    records: list[AssetRecord] = field(default_factory=list)
    summary: PreviewSummary = field(default_factory=PreviewSummary)
    warnings: list[PipelineWarning] = field(default_factory=list)
    inferred_category: Optional[str] = None
    request_id: str = ""


# ===========================================================================
# ImportPipeline
# ===========================================================================

class ImportPipeline:
    """
    Import Pipeline 主编排器。

    使用方式（Wizard 模式）：
        pipeline = ImportPipeline()
        result = pipeline.parse_only(file_bytes, filename, context)

    使用方式（旧接口兼容）：
        result = ImportPipeline().parse_only(file_bytes, filename, context)
        # 然后由 Executor 处理 result.records
    """

    def __init__(
        self,
        source: Optional[ExcelSource] = None,
        normalizer: Optional[Normalizer] = None,
        department_resolver: Optional[DepartmentResolver] = None,
        brand_resolver: Optional[BrandResolver] = None,
        location_resolver: Optional[LocationResolver] = None,
        validator: Optional[Validator] = None,
        classifier: Optional[Classifier] = None,
    ) -> None:
        """
        各层可通过构造函数注入，方便单元测试 mock。
        默认使用各层的标准实现。
        """
        self._source     = source     or ExcelSource()
        self._normalizer = normalizer or Normalizer()
        self._dept_res   = department_resolver or DepartmentResolver()
        self._brand_res  = brand_resolver      or BrandResolver()
        self._loc_res    = location_resolver   or LocationResolver()
        self._validator  = validator  or Validator()
        self._classifier = classifier or Classifier()

    # ── 主要公开方法 ─────────────────────────────────────────────────────

    def parse_only(
        self,
        file_bytes: bytes,
        filename: str,
        context: ImportContext,
    ) -> PipelineResult:
        """
        完整执行 Parse → Normalize → Resolve → Validate → Classify → Policy。
        不写库，返回 PipelineResult 供调用方（Wizard Preview 或旧接口）使用。

        参数：
            file_bytes — .xlsx 文件二进制内容
            filename   — 原始文件名（用于品类推断）
            context    — 运行时上下文（含 db、current_user、import_policy 等）

        异常：
            ValueError — 文件解析失败或缺少必填列头（直接冒泡给 API 层）
        """
        result = PipelineResult(request_id=context.request_id)

        # ── Step 1: Source ──
        records, inferred_category = self._source.read(file_bytes, filename)
        result.inferred_category = inferred_category

        # 将 inferred_category 写入 context，供 Normalizer 使用
        if inferred_category and not context.inferred_category:
            context.inferred_category = inferred_category

        # ── Step 2: Normalize ──
        self._normalizer.normalize_batch(records, context)

        # ── Step 3: Resolve（批量 IN 查询优化） ──
        # 仅在有 DB 时执行（dry_run 也执行，只有 Executor 不写库）
        if context.db is not None:
            self._dept_res.resolve_batch(records, context)
            self._brand_res.resolve_batch(records, context)
            self._loc_res.resolve_batch(records, context)

        # ── Step 4: Validate ──
        # validate_batch 内含文件内 asset_tag 去重
        self._validator.validate_batch(records)

        # ── Step 5: Classify（批量 IN 查询优化） ──
        if context.db is not None:
            self._classifier.classify_batch(records, context)
        else:
            # 无 DB 时（单元测试场景），仅基于 has_errors / needs_mapping 分类
            self._classify_without_db(records)

        # ── Step 6: Policy 决策 ──
        policy: ImportPolicy = context.import_policy
        if policy is not None:
            policy.decide_batch(records)

        # ── Step 7: 收集摘要和警告 ──
        result.records = records
        result.summary = self._build_summary(records)
        result.warnings = self._collect_warnings(records, inferred_category)

        return result

    # ── 内部辅助 ─────────────────────────────────────────────────────────

    def _classify_without_db(self, records: list[AssetRecord]) -> None:
        """无 DB 场景下的简化分类（测试用）"""
        for record in records:
            if record.has_errors:
                record.classification = RecordClassification.ERROR
            elif record.needs_mapping:
                record.classification = RecordClassification.MAPPING_REQUIRED
            else:
                record.classification = RecordClassification.VALID

    def _build_summary(self, records: list[AssetRecord]) -> PreviewSummary:
        """统计各分类数量"""
        summary = PreviewSummary(total=len(records))
        for record in records:
            cls = record.classification
            if cls == RecordClassification.VALID:
                summary.valid += 1
            elif cls == RecordClassification.MAPPING_REQUIRED:
                summary.mapping_required += 1
            elif cls == RecordClassification.DUPLICATE:
                summary.duplicate += 1
            elif cls == RecordClassification.ERROR:
                summary.error += 1
        return summary

    def _collect_warnings(
        self,
        records: list[AssetRecord],
        inferred_category: Optional[str],
    ) -> list[PipelineWarning]:
        """
        收集非致命警告：
          - 品类来自文件名推断的记录
          - 有 extra_fields（未知列）的记录
        """
        warnings: list[PipelineWarning] = []

        for record in records:
            tag = record.fields.get("asset_tag")

            # 品类推断警告：字段中没有 category 列，品类来自文件名
            if inferred_category and not record.raw_fields.get("品类"):
                warnings.append(PipelineWarning(
                    row_number=record.row_number,
                    asset_tag=tag,
                    warning_type=WarningType.CATEGORY_INFERRED,
                    message=f"品类「{inferred_category}」来自文件名推断，非 Excel 中的显式填写",
                ))

            # 未知列警告
            if record.extra_fields:
                keys = ", ".join(record.extra_fields.keys())
                warnings.append(PipelineWarning(
                    row_number=record.row_number,
                    asset_tag=tag,
                    warning_type=WarningType.EXTRA_COLUMNS,
                    message=f"存在未识别列，将存入 additional_info: {keys}",
                ))

        return warnings
