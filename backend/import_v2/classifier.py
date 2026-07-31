"""
import_v2.classifier
======================
Classifier 层：根据 Validator 结果 + DB 唯一性查询，为每条记录打分类标签。

职责（单一）：
  - 若 record.has_errors       → ERROR
  - 若 record.needs_mapping    → MAPPING_REQUIRED
  - 查询 DB asset_tag 唯一性   → DUPLICATE（填充 duplicate_info）
  - 查询 DB serial_number 唯一性 → DUPLICATE（填充 duplicate_info）
  - 全部通过                   → VALID

优先级（从高到低）：
  ERROR > DUPLICATE > MAPPING_REQUIRED > VALID

  原因：
    - ERROR 表示数据本身有硬错误，无论是否重复都不能导入
    - DUPLICATE 优先于 MAPPING_REQUIRED：若重复且有未映射主数据，
      Policy 层可以决定 SKIP，不需要用户再去完成 Mapping
    - MAPPING_REQUIRED 在无格式错误、无重复时才标记

不做：
  - 不修改 record.fields
  - 不做数据写库

DB 查询优化：
  - classify_batch 使用两次 IN 查询（asset_tags 和 serial_numbers），
    而非逐条单独查询，大幅减少 DB 往返次数
"""

from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session

import models
from .domain_models import (
    AssetRecord,
    DuplicateInfo,
    ImportContext,
    RecordClassification,
)


class Classifier:
    """
    无状态的 Classifier，可直接实例化复用。

    使用方式：
        classifier = Classifier()
        classifier.classify_batch(records, context)
    """

    def classify(self, record: AssetRecord, context: ImportContext) -> None:
        """
        单条分类，直接查 DB（适用于少量记录或单步模式）。
        结果写入 record.classification 和 record.duplicate_info。
        """
        db: Session = context.db

        # ── 1. 有校验错误 → ERROR ──
        if record.has_errors:
            record.classification = RecordClassification.ERROR
            return

        # ── 2. DB asset_tag 唯一性 ──
        tag: Optional[str] = record.fields.get("asset_tag")
        if tag:
            existing = (
                db.query(models.Asset)
                .filter(
                    models.Asset.asset_tag == tag,
                    models.Asset.is_deleted == False,
                )
                .first()
            )
            if existing:
                record.classification = RecordClassification.DUPLICATE
                record.duplicate_info = DuplicateInfo(
                    asset_id=existing.id,
                    asset_tag=existing.asset_tag,
                    serial_number=existing.serial_number,
                    status=existing.status,
                    conflict_field="asset_tag",
                )
                return

        # ── 3. DB serial_number 唯一性 ──
        sn: Optional[str] = record.fields.get("serial_number")
        if sn:
            existing_sn = (
                db.query(models.Asset)
                .filter(
                    models.Asset.serial_number == sn,
                    models.Asset.is_deleted == False,
                )
                .first()
            )
            if existing_sn:
                record.classification = RecordClassification.DUPLICATE
                record.duplicate_info = DuplicateInfo(
                    asset_id=existing_sn.id,
                    asset_tag=existing_sn.asset_tag,
                    serial_number=existing_sn.serial_number,
                    status=existing_sn.status,
                    conflict_field="serial_number",
                )
                return

        # ── 4. 有 Resolver 问题（主数据未匹配）→ MAPPING_REQUIRED ──
        if record.needs_mapping:
            record.classification = RecordClassification.MAPPING_REQUIRED
            return

        # ── 5. 全部通过 → VALID ──
        record.classification = RecordClassification.VALID

    def classify_batch(
        self,
        records: list[AssetRecord],
        context: ImportContext,
    ) -> None:
        """
        批量分类，使用两次 IN 查询优化 DB 访问。

        流程：
          1. 先对 has_errors 的记录直接标 ERROR，跳过 DB 查询
          2. 收集其余记录的 asset_tag 和 serial_number
          3. 两次 IN 查询，构建冲突 map
          4. 逐记录判断 DUPLICATE / MAPPING_REQUIRED / VALID
        """
        db: Session = context.db

        # ── 第一轮：标记 ERROR，收集需查 DB 的记录 ──
        need_db_check: list[AssetRecord] = []
        for record in records:
            if record.has_errors:
                record.classification = RecordClassification.ERROR
            else:
                need_db_check.append(record)

        if not need_db_check:
            return

        # Excel 文件内 SN 重复必须在预览阶段识别；同一重复组的所有行均标记。
        file_sn_rows: dict[str, list[int]] = {}
        for record in need_db_check:
            sn = record.fields.get("serial_number")
            if sn:
                file_sn_rows.setdefault(sn, []).append(record.row_number)
        file_duplicate_sns = {
            sn: rows for sn, rows in file_sn_rows.items() if len(rows) > 1
        }

        # ── 收集待查询的 asset_tags 和 serial_numbers ──
        tags_to_check: set[str] = set()
        sns_to_check: set[str] = set()
        for record in need_db_check:
            tag = record.fields.get("asset_tag")
            sn  = record.fields.get("serial_number")
            if tag:
                tags_to_check.add(tag)
            if sn:
                sns_to_check.add(sn)

        # ── 两次 IN 查询 ──
        tag_conflict_map: dict[str, models.Asset] = {}
        if tags_to_check:
            existing_by_tag = (
                db.query(models.Asset)
                .filter(
                    models.Asset.asset_tag.in_(tags_to_check),
                    models.Asset.is_deleted == False,
                )
                .all()
            )
            tag_conflict_map = {a.asset_tag: a for a in existing_by_tag}

        sn_conflict_map: dict[str, models.Asset] = {}
        if sns_to_check:
            existing_by_sn = (
                db.query(models.Asset)
                .filter(
                    models.Asset.serial_number.in_(sns_to_check),
                    models.Asset.is_deleted == False,
                )
                .all()
            )
            sn_conflict_map = {a.serial_number: a for a in existing_by_sn if a.serial_number}

        # ── 第二轮：逐记录分类 ──
        for record in need_db_check:
            tag = record.fields.get("asset_tag")
            sn  = record.fields.get("serial_number")

            # asset_tag 冲突
            if tag and tag in tag_conflict_map:
                conflicting = tag_conflict_map[tag]
                record.classification = RecordClassification.DUPLICATE
                record.duplicate_info = DuplicateInfo(
                    asset_id=conflicting.id,
                    asset_tag=conflicting.asset_tag,
                    serial_number=conflicting.serial_number,
                    status=conflicting.status,
                    conflict_field="asset_tag",
                )
                continue

            # 文件内 serial_number 冲突优先于数据库 SN 冲突；没有可更新目标。
            if sn and sn in file_duplicate_sns:
                record.classification = RecordClassification.DUPLICATE
                record.duplicate_info = DuplicateInfo(
                    asset_id=None,
                    asset_tag=tag,
                    serial_number=sn,
                    status=None,
                    conflict_field="serial_number",
                    conflict_scope="FILE",
                    first_row_number=file_duplicate_sns[sn][0],
                )
                continue

            # serial_number 数据库冲突
            if sn and sn in sn_conflict_map:
                conflicting = sn_conflict_map[sn]
                record.classification = RecordClassification.DUPLICATE
                record.duplicate_info = DuplicateInfo(
                    asset_id=conflicting.id,
                    asset_tag=conflicting.asset_tag,
                    serial_number=conflicting.serial_number,
                    status=conflicting.status,
                    conflict_field="serial_number",
                )
                continue

            # 有 Resolver 问题 → MAPPING_REQUIRED
            if record.needs_mapping:
                record.classification = RecordClassification.MAPPING_REQUIRED
                continue

            # 全部通过
            record.classification = RecordClassification.VALID
