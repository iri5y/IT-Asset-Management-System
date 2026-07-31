"""
import_v2.validator
====================
Validator 层：对 AssetRecord.fields 执行业务规则校验。

职责（单一）：
  - 格式校验：asset_tag 格式（ZS-XXXX-NNNNNN）
  - 必填校验：asset_tag、category、status
  - 合法值校验：status 必须是系统支持的四个状态之一
  - 条件必填：status=使用中 时 employee_name 必填
  - 品类条件校验（对齐 schemas.AssetCreate）：
      笔记本电脑、台式机、服务器、移动设备 → SN 必填
      笔记本电脑、台式机 → PO号 必填且为纯数字
  - 文件内 asset_tag 重复检测（跨记录）

不做：
  - 不访问数据库（DB 唯一性检查由 Classifier 负责）
  - 不修改 record.fields

错误写入：record.add_validation_error(field_name, message)
"""

from __future__ import annotations

import re
from typing import Optional

from category_policy import is_fixed_asset_category
from .domain_models import AssetRecord, ImportContext


# ===========================================================================
# 常量
# ===========================================================================

# asset_tag 格式正则：ZS-XXXX-NNNNNN（如 ZS-PC26-000001）
_ASSET_TAG_PATTERN: re.Pattern = re.compile(r"^ZS-[A-Za-z0-9]{4}-\d{6}$")

# 合法状态值
_VALID_STATUSES: frozenset[str] = frozenset({"闲置", "使用中", "维修中", "报废"})

# 固定资产三层模型只允许 PC/NB/PD。
_SN_REQUIRED_CATEGORIES: frozenset[str] = frozenset(
    {"笔记本电脑", "台式机", "平板电脑"}
)

# 需要 PO 号的品类
_PO_REQUIRED_CATEGORIES: frozenset[str] = frozenset({"笔记本电脑", "台式机"})


# ===========================================================================
# Validator
# ===========================================================================

class Validator:
    """
    无状态的 Validator，可直接实例化复用。

    使用方式：
        validator = Validator()
        validator.validate_batch(records)
    """

    def validate(self, record: AssetRecord) -> None:
        """
        校验单条记录，错误写入 record.validation_errors。
        不改变 record.fields，不抛出异常。
        """
        self._check_required_fields(record)
        self._check_fixed_asset_category(record)
        self._check_asset_tag_format(record)
        self._check_status(record)
        self._check_sn_required(record)
        self._check_po_required(record)
        self._check_employee_when_in_use(record)

    def validate_batch(
        self,
        records: list[AssetRecord],
    ) -> None:
        """
        批量校验，同时执行文件内 asset_tag 去重检测。

        文件内去重在单条校验之后进行，因为只有 asset_tag 格式合法时
        才将其纳入去重集合，避免把多个格式错误的空值都误判为重复。
        """
        for record in records:
            self.validate(record)

        self._check_intra_file_duplicates(records)

    # ── 内部校验方法 ────────────────────────────────────────────────────────

    def _check_required_fields(self, record: AssetRecord) -> None:
        """必填字段：asset_tag、category、status"""
        for field_name, label in [
            ("asset_tag",  "资产编号"),
            ("category",   "品类"),
            ("status",     "状态"),
        ]:
            val = record.fields.get(field_name)
            if not val or not str(val).strip():
                record.add_validation_error(label, f"{label}为必填项，不能为空")

    def _check_fixed_asset_category(self, record: AssetRecord) -> None:
        """Asset 导入目标仅接受 PC、NB、PD 三类固定资产。"""
        category = record.fields.get("category")
        if category and not is_fixed_asset_category(str(category)):
            record.add_validation_error(
                "品类",
                "该物品不属于固定资产，请导入低值领用物品或仓储物料",
            )

    def _check_asset_tag_format(self, record: AssetRecord) -> None:
        """asset_tag 格式校验：ZS-XXXX-NNNNNN"""
        val: Optional[str] = record.fields.get("asset_tag")
        if not val:
            return  # 缺失已由 _check_required_fields 报告
        if not _ASSET_TAG_PATTERN.match(val):
            record.add_validation_error(
                "资产编号",
                f"格式错误「{val}」，应为 ZS-XXXX-NNNNNN（如 ZS-PC26-000001）",
            )

    def _check_status(self, record: AssetRecord) -> None:
        """status 合法值校验"""
        val: Optional[str] = record.fields.get("status")
        if not val:
            return  # 缺失已由 _check_required_fields 报告
        if val not in _VALID_STATUSES:
            record.add_validation_error(
                "状态",
                f"非法状态值「{val}」，允许: {', '.join(sorted(_VALID_STATUSES))}",
            )

    def _check_sn_required(self, record: AssetRecord) -> None:
        """部分品类 SN 必填"""
        category: Optional[str] = record.fields.get("category")
        if not category:
            return
        if category in _SN_REQUIRED_CATEGORIES:
            sn = record.fields.get("serial_number")
            if not sn or not str(sn).strip():
                record.add_validation_error(
                    "序列号",
                    f"品类为「{category}」时，序列号为必填项",
                )

    def _check_po_required(self, record: AssetRecord) -> None:
        """部分品类 PO 号必填，且必须为纯数字"""
        category: Optional[str] = record.fields.get("category")
        if not category:
            return

        po = record.fields.get("po_number")

        if category in _PO_REQUIRED_CATEGORIES:
            if not po or not str(po).strip():
                record.add_validation_error(
                    "PO号",
                    f"品类为「{category}」时，PO号为必填项",
                )
                return
            if not str(po).strip().isdigit():
                record.add_validation_error(
                    "PO号",
                    "PO号格式错误，必须为纯数字（例如：12000327）",
                )
        elif po and str(po).strip():
            # 非必填品类若填了 PO 号，也校验格式
            if not str(po).strip().isdigit():
                record.add_validation_error(
                    "PO号",
                    "PO号格式错误，必须为纯数字（例如：12000327）",
                )

    def _check_employee_when_in_use(self, record: AssetRecord) -> None:
        """status=使用中 时 employee_name 必填"""
        status = record.fields.get("status")
        if status == "使用中":
            emp = record.fields.get("employee_name")
            if not emp or not str(emp).strip():
                record.add_validation_error(
                    "使用人",
                    "状态为「使用中」时，使用人为必填项",
                )

    def _check_intra_file_duplicates(self, records: list[AssetRecord]) -> None:
        """
        文件内 asset_tag 去重检测。

        只对格式合法（未报 FORMAT 类 asset_tag 错误）的记录参与去重，
        避免多条格式错误的记录都把空/非法值当重复来报告。
        """
        seen: dict[str, int] = {}  # asset_tag → 首次出现行号

        for record in records:
            # 如果该记录已有 asset_tag 格式错误，跳过去重（不纳入 seen）
            has_tag_format_error = any(
                e.field == "资产编号" and "格式错误" in e.message
                for e in record.validation_errors
            )
            if has_tag_format_error:
                continue

            tag: Optional[str] = record.fields.get("asset_tag")
            if not tag:
                continue

            if tag in seen:
                record.add_validation_error(
                    "资产编号",
                    f"资产编号「{tag}」在文件中重复，首次出现于第 {seen[tag]} 行",
                )
            else:
                seen[tag] = record.row_number
