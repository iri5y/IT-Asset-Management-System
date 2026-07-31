"""
import_v2.resolvers.location_resolver
========================================
LocationResolver：将位置名文本解析为数据库位置记录引用。

职责（单一）：
  - 先查 warehouse_locations（库房位置），再查 office_locations（办公室位置）
  - 精确唯一匹配 → 返回 LocationRef（含 id、name、location_type）
  - 两表都无匹配 → 记录 UNKNOWN 问题
  - 跨表或单表多匹配 → 记录 MULTIPLE_MATCH 问题

查找策略：
  - 若 warehouse_locations 和 office_locations 各有一条同名记录，
    优先标记为 MULTIPLE_MATCH，由用户在 Mapping 阶段明确选择类型。
  - 只在一张表中唯一匹配 → 直接使用。

不做：
  - 不创建新位置
"""

from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session

import models
from ..domain_models import (
    AssetRecord,
    ImportContext,
    IssueType,
    LocationRef,
    LocationType,
)


class LocationResolver:
    """
    无状态的 LocationResolver。

    使用方式：
        resolver = LocationResolver()
        resolver.resolve_batch(records, context)
    """

    def resolve(self, record: AssetRecord, context: ImportContext) -> None:
        """解析单条记录的位置字段"""
        raw_location: Optional[str] = record.fields.get("location")
        if not raw_location:
            return

        db: Session = context.db
        ref = self._lookup(db, raw_location)

        if ref is not None:
            record.resolved.location = ref
        else:
            # _lookup 返回 None 表示无匹配或多匹配，issue 已在内部追加
            # 此处补充一次兜底（若调用方单独调用 resolve）
            if not any(
                i.field == "location" and i.raw_value == raw_location
                for i in record.resolver_issues
            ):
                record.add_resolver_issue(
                    field_name="location",
                    raw_value=raw_location,
                    issue_type=IssueType.UNKNOWN,
                )

    def resolve_batch(
        self,
        records: list[AssetRecord],
        context: ImportContext,
    ) -> None:
        """
        批量解析位置字段，对两张位置表各做一次 IN 查询。
        """
        db: Session = context.db

        location_names: set[str] = set()
        for record in records:
            raw = record.fields.get("location")
            if raw:
                location_names.add(raw)

        if not location_names:
            return

        # 两张表各查一次
        wh_locs = (
            db.query(models.WarehouseLocation)
            .filter(models.WarehouseLocation.name.in_(location_names))
            .all()
        )
        off_locs = (
            db.query(models.OfficeLocation)
            .filter(models.OfficeLocation.name.in_(location_names))
            .all()
        )

        # 构建映射
        wh_map: dict[str, list] = {}
        for loc in wh_locs:
            wh_map.setdefault(loc.name, []).append(loc)

        off_map: dict[str, list] = {}
        for loc in off_locs:
            off_map.setdefault(loc.name, []).append(loc)

        # 逐记录填充
        for record in records:
            raw_loc: Optional[str] = record.fields.get("location")
            if not raw_loc:
                continue

            wh_matches = wh_map.get(raw_loc, [])
            off_matches = off_map.get(raw_loc, [])
            total = len(wh_matches) + len(off_matches)

            if total == 0:
                record.add_resolver_issue(
                    field_name="location",
                    raw_value=raw_loc,
                    issue_type=IssueType.UNKNOWN,
                )
            elif total == 1:
                if wh_matches:
                    loc = wh_matches[0]
                    record.resolved.location = LocationRef(
                        id=loc.id,
                        name=loc.name,
                        location_type=LocationType.WAREHOUSE,
                    )
                else:
                    loc = off_matches[0]
                    record.resolved.location = LocationRef(
                        id=loc.id,
                        name=loc.name,
                        location_type=LocationType.OFFICE,
                    )
            else:
                # 多个匹配（跨表或同表重名），列出所有候选
                candidates = (
                    [f"[库房] {l.name}" for l in wh_matches]
                    + [f"[办公室] {l.name}" for l in off_matches]
                )
                record.add_resolver_issue(
                    field_name="location",
                    raw_value=raw_loc,
                    issue_type=IssueType.MULTIPLE_MATCH,
                    candidates=candidates,
                )

    def _lookup(self, db: Session, name: str) -> Optional[LocationRef]:
        """
        单条记录的位置查找（供 resolve() 调用）。
        返回 LocationRef 或 None（多匹配 / 无匹配时返回 None）。
        """
        wh = db.query(models.WarehouseLocation).filter(
            models.WarehouseLocation.name == name
        ).all()
        off = db.query(models.OfficeLocation).filter(
            models.OfficeLocation.name == name
        ).all()
        total = len(wh) + len(off)

        if total == 1:
            if wh:
                return LocationRef(id=wh[0].id, name=wh[0].name, location_type=LocationType.WAREHOUSE)
            return LocationRef(id=off[0].id, name=off[0].name, location_type=LocationType.OFFICE)
        return None
