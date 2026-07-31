"""
import_v2.normalizer
====================
Normalizer 层：对 AssetRecord.fields 中的原始字符串进行标准化处理。

职责（单一）：
  - 去除首尾空格和全角空格
  - 将 n/a 类占位符统一转为 None
  - 品类名称标准化（"台式"→"台式机"、"laptop"→"笔记本电脑" 等）
  - 序列号大写标准化
  - 品类推断填充（行内无 category 时使用 inferred_category）

不做：
  - 不访问数据库（无 DB 依赖）
  - 不做业务规则校验（那是 Validator 的职责）
  - 不修改 raw_fields（只读快照）
"""

from typing import Optional

from category_policy import ASSET_CATEGORY_NAMES, asset_category_code
from .domain_models import AssetRecord, ImportContext


# ===========================================================================
# 常量映射表（从 import_service.py 迁移，保持原有覆盖范围）
# ===========================================================================

# n/a 类占位符，导入时统一转为 None
_NA_VALUES: frozenset[str] = frozenset({
    "n/a", "na", "none", "null", "-", "无", "暂无", "不适用",
})

# 品类名称标准化映射（Excel 中的变体 → 系统标准值）
_CATEGORY_NORMALIZE: dict[str, str] = {
    "台式电脑": "台式机",
    "台式":     "台式机",
    "desktop":  "台式机",
    "笔记本":   "笔记本电脑",
    "laptop":   "笔记本电脑",
    "notebook": "笔记本电脑",
    "平板":     "平板电脑",
    "ipad":     "平板电脑",
    "tablet":   "平板电脑",
    "pad":      "平板电脑",
}

# 需要大写标准化的字段
_UPPERCASE_FIELDS: frozenset[str] = frozenset({"serial_number"})

# 需要去除空格的字符串字段（全量）
_STRING_FIELDS: frozenset[str] = frozenset({
    "asset_tag", "category", "brand", "model", "serial_number",
    "status", "employee_name", "employee_id", "department",
    "hostname", "mac_address", "ip_address", "fixed_asset_number",
    "system_version", "antivirus_software", "lock_number",
    "supervisor", "location", "po_number", "notes",
})


# ===========================================================================
# 公开接口
# ===========================================================================

class Normalizer:
    """
    无状态的 Normalizer，可直接实例化复用。

    使用方式：
        normalizer = Normalizer()
        normalizer.normalize(record, context)
    """

    def normalize(self, record: AssetRecord, context: ImportContext) -> None:
        """
        原地修改 record.fields，完成标准化。不修改 record.raw_fields。

        处理顺序：
          1. 所有字符串字段：去空格、NA→None
          2. 大写标准化（serial_number）
          3. 品类标准化（CATEGORY_NORMALIZE 映射）
          4. 品类推断填充（来自 context.inferred_category）
        """
        self._clean_string_fields(record)
        self._uppercase_fields(record)
        self._normalize_category(record)
        self._infer_category(record, context.inferred_category)

    def normalize_batch(
        self,
        records: list[AssetRecord],
        context: ImportContext,
    ) -> None:
        """批量标准化，原地修改每条记录"""
        for record in records:
            self.normalize(record, context)

    # ── 内部方法 ────────────────────────────────────────────────────────────

    def _clean_string_fields(self, record: AssetRecord) -> None:
        """
        对 fields 中所有已知字符串字段：
          - 去除首尾空格和全角空格（\u3000）
          - 将 NA 占位符转为 None
          - 空字符串转为 None
        """
        for key in list(record.fields.keys()):
            val = record.fields[key]
            if val is None:
                continue
            if not isinstance(val, str):
                continue

            # 去空格
            cleaned = val.strip().replace("\u3000", "")

            # 空字符串 → None
            if not cleaned:
                record.fields[key] = None
                continue

            # NA 占位符 → None
            if cleaned.lower() in _NA_VALUES:
                record.fields[key] = None
                continue

            record.fields[key] = cleaned

    def _uppercase_fields(self, record: AssetRecord) -> None:
        """序列号等字段统一转大写"""
        for key in _UPPERCASE_FIELDS:
            val = record.fields.get(key)
            if isinstance(val, str):
                record.fields[key] = val.upper()

    def _normalize_category(self, record: AssetRecord) -> None:
        """
        品类名称标准化：将常见变体映射为系统标准值。
        大小写不敏感匹配（先小写查，再原值查）。
        """
        raw_category: Optional[str] = record.fields.get("category")
        if not raw_category:
            return

        mapped = (
            _CATEGORY_NORMALIZE.get(raw_category)
            or _CATEGORY_NORMALIZE.get(raw_category.lower())
            or raw_category
        )
        category_code = asset_category_code(mapped)
        record.fields["category"] = (
            ASSET_CATEGORY_NAMES[category_code] if category_code else mapped
        )

    def _infer_category(
        self,
        record: AssetRecord,
        inferred_category: Optional[str],
    ) -> None:
        """
        若 fields 中没有 category（或值为 None），
        且 context 提供了从文件名推断的品类，则自动填充。
        """
        if not record.fields.get("category") and inferred_category:
            record.fields["category"] = inferred_category
