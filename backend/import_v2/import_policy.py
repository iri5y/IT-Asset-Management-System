"""
import_v2.import_policy
========================
ImportPolicy：封装重复数据的处理策略。

职责（单一）：
  - 根据策略类型，对 DUPLICATE 记录决定 PolicyDecision
  - VALID 记录固定决定为 INSERT
  - ERROR 记录固定决定为 SKIP
  - MAPPING_REQUIRED 记录在执行阶段前必须先完成 Mapping，
    若未完成则 SKIP，完成后重新 classify 再决策

支持的策略：
  INSERT_ONLY      — 默认策略，重复记录一律 SKIP
  UPDATE_EXISTING  — 重复记录执行 UPDATE（更新已有资产字段）
  REPLACE_EXISTING — 重复记录执行 REPLACE（覆盖所有字段）
  DRY_RUN          — 演习模式，所有记录均 SKIP，不真正写库

设计约定：
  - Policy 对象无状态，可跨多批 records 复用
  - Pipeline 在 Classifier 完成后调用 policy.decide_batch()
  - Executor 读取 record.policy_decision 执行对应操作
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from .domain_models import (
    AssetRecord,
    PolicyDecision,
    RecordClassification,
)


# ===========================================================================
# 策略类型枚举
# ===========================================================================

class ImportPolicyType(str, Enum):
    INSERT_ONLY      = "INSERT_ONLY"       # 默认：重复跳过
    UPDATE_EXISTING  = "UPDATE_EXISTING"   # 重复则更新
    REPLACE_EXISTING = "REPLACE_EXISTING"  # 重复则替换全字段
    DRY_RUN          = "DRY_RUN"           # 演习：全部跳过


# ===========================================================================
# ImportPolicy
# ===========================================================================

class ImportPolicy:
    """
    无状态的策略对象，封装 PolicyDecision 的判定逻辑。

    使用方式：
        policy = ImportPolicy(ImportPolicyType.INSERT_ONLY)
        policy.decide_batch(records)

    或单条：
        policy.decide(record)
    """

    def __init__(self, policy_type: ImportPolicyType = ImportPolicyType.INSERT_ONLY) -> None:
        self.policy_type = policy_type

    # ── 公开接口 ─────────────────────────────────────────────────────────

    def decide(self, record: AssetRecord) -> None:
        """
        为单条记录填充 policy_decision。

        决策矩阵：
          classification=ERROR            → SKIP（无论策略）
          classification=MAPPING_REQUIRED → SKIP（未完成 Mapping 前不执行）
          classification=VALID            → INSERT（无论策略）
          classification=DUPLICATE        → 由策略类型决定
          DRY_RUN 模式                    → 所有记录 SKIP
        """
        if self.policy_type == ImportPolicyType.DRY_RUN:
            record.policy_decision = PolicyDecision.SKIP
            return

        cls = record.classification

        if cls == RecordClassification.ERROR:
            record.policy_decision = PolicyDecision.SKIP

        elif cls == RecordClassification.MAPPING_REQUIRED:
            # Mapping 未完成前一律跳过，等待用户在 Wizard 中完成 Mapping 后
            # Pipeline 会重新 classify，再次调用 decide
            record.policy_decision = PolicyDecision.SKIP

        elif cls == RecordClassification.VALID:
            record.policy_decision = PolicyDecision.INSERT

        elif cls == RecordClassification.DUPLICATE:
            # 文件内重复没有可更新的数据库目标，任何重复策略都必须跳过。
            if (
                record.duplicate_info is not None
                and record.duplicate_info.conflict_scope == "FILE"
            ):
                record.policy_decision = PolicyDecision.SKIP
            else:
                record.policy_decision = self._decide_duplicate()

        else:
            # 防御：未知分类一律跳过
            record.policy_decision = PolicyDecision.SKIP

    def decide_batch(self, records: list[AssetRecord]) -> None:
        """批量决策"""
        for record in records:
            self.decide(record)

    # ── 内部方法 ─────────────────────────────────────────────────────────

    def _decide_duplicate(self) -> PolicyDecision:
        """根据策略类型决定 DUPLICATE 记录的处理方式"""
        mapping = {
            ImportPolicyType.INSERT_ONLY:      PolicyDecision.SKIP,
            ImportPolicyType.UPDATE_EXISTING:  PolicyDecision.UPDATE,
            ImportPolicyType.REPLACE_EXISTING: PolicyDecision.REPLACE,
        }
        return mapping.get(self.policy_type, PolicyDecision.SKIP)

    # ── 工厂方法 ─────────────────────────────────────────────────────────

    @classmethod
    def insert_only(cls) -> "ImportPolicy":
        """默认策略：重复记录跳过"""
        return cls(ImportPolicyType.INSERT_ONLY)

    @classmethod
    def update_existing(cls) -> "ImportPolicy":
        """重复记录执行更新"""
        return cls(ImportPolicyType.UPDATE_EXISTING)

    @classmethod
    def dry_run(cls) -> "ImportPolicy":
        """演习模式"""
        return cls(ImportPolicyType.DRY_RUN)
