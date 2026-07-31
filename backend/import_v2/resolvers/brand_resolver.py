"""
import_v2.resolvers.brand_resolver
=====================================
BrandResolver：将品牌名文本解析为数据库 Brand 记录引用。

职责（单一）：
  - 查询 brands 表，精确匹配品牌名
  - 精确唯一匹配 → 返回 BrandRef（含 id、name）
  - 无匹配 → 返回 None，记录 UNKNOWN 问题
  - 多匹配 → 返回 None，记录 MULTIPLE_MATCH 问题

不做：
  - 不创建新品牌
  - 不做模糊字符串相似度匹配
"""

from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session

import models
from ..domain_models import (
    AssetRecord,
    BrandRef,
    ImportContext,
    IssueType,
)


class BrandResolver:
    """
    无状态的 BrandResolver。

    使用方式：
        resolver = BrandResolver()
        resolver.resolve_batch(records, context)
    """

    def resolve(self, record: AssetRecord, context: ImportContext) -> None:
        """解析单条记录的品牌字段"""
        raw_brand: Optional[str] = record.fields.get("brand")
        if not raw_brand:
            return

        db: Session = context.db
        matches = (
            db.query(models.Brand)
            .filter(models.Brand.name == raw_brand)
            .all()
        )

        if len(matches) == 1:
            b = matches[0]
            record.resolved.brand = BrandRef(id=b.id, name=b.name)
        elif len(matches) == 0:
            record.add_resolver_issue(
                field_name="brand",
                raw_value=raw_brand,
                issue_type=IssueType.UNKNOWN,
            )
        else:
            record.add_resolver_issue(
                field_name="brand",
                raw_value=raw_brand,
                issue_type=IssueType.MULTIPLE_MATCH,
                candidates=[m.name for m in matches],
            )

    def resolve_batch(
        self,
        records: list[AssetRecord],
        context: ImportContext,
    ) -> None:
        """
        批量解析品牌字段，使用单次 IN 查询。
        """
        db: Session = context.db

        brand_names: set[str] = set()
        for record in records:
            raw = record.fields.get("brand")
            if raw:
                brand_names.add(raw)

        if not brand_names:
            return

        all_brands = (
            db.query(models.Brand)
            .filter(models.Brand.name.in_(brand_names))
            .all()
        )

        name_map: dict[str, list[models.Brand]] = {}
        for brand in all_brands:
            name_map.setdefault(brand.name, []).append(brand)

        for record in records:
            raw_brand: Optional[str] = record.fields.get("brand")
            if not raw_brand:
                continue

            matches = name_map.get(raw_brand, [])
            if len(matches) == 1:
                b = matches[0]
                record.resolved.brand = BrandRef(id=b.id, name=b.name)
            elif len(matches) == 0:
                record.add_resolver_issue(
                    field_name="brand",
                    raw_value=raw_brand,
                    issue_type=IssueType.UNKNOWN,
                )
            else:
                record.add_resolver_issue(
                    field_name="brand",
                    raw_value=raw_brand,
                    issue_type=IssueType.MULTIPLE_MATCH,
                    candidates=[m.name for m in matches],
                )
