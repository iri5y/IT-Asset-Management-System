"""
import_v2.resolvers.department_resolver
========================================
DepartmentResolver：将部门名文本解析为数据库 Department 记录引用。

职责（单一）：
  - 查询 departments 表，尝试精确匹配
  - 精确唯一匹配 → 返回 DepartmentRef（含 id、name、parent_id）
  - 无匹配 → 返回 None，记录 UNKNOWN 问题
  - 多匹配 → 返回 None，记录 MULTIPLE_MATCH 问题（列出候选）

不做：
  - 不创建新部门（Resolver 只读）
  - 不修改 record.fields 中的原始文本
  - 不做模糊字符串匹配（名称需精确或经 Normalizer 预处理后匹配）
"""

from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session

import models
from ..domain_models import (
    AssetRecord,
    DepartmentRef,
    ImportContext,
    IssueType,
)


class DepartmentResolver:
    """
    无状态的 DepartmentResolver。

    使用方式：
        resolver = DepartmentResolver()
        resolver.resolve(record, context)
    """

    def resolve(self, record: AssetRecord, context: ImportContext) -> None:
        """
        解析单条记录的部门字段，结果写入 record.resolved.department。
        若解析失败，追加 resolver_issue，record.resolved.department 保持 None。
        """
        raw_dept: Optional[str] = record.fields.get("department")

        # 无部门字段，视为合法（部门非强制），直接跳过
        if not raw_dept:
            return

        db: Session = context.db
        matches = (
            db.query(models.Department)
            .filter(models.Department.name == raw_dept)
            .all()
        )

        if len(matches) == 1:
            dept = matches[0]
            record.resolved.department = DepartmentRef(
                id=dept.id,
                name=dept.name,
                parent_id=dept.parent_id,
            )
        elif len(matches) == 0:
            record.add_resolver_issue(
                field_name="department",
                raw_value=raw_dept,
                issue_type=IssueType.UNKNOWN,
            )
        else:
            # 多个同名部门（理论上因 unique 约束不应发生，但做防御处理）
            record.add_resolver_issue(
                field_name="department",
                raw_value=raw_dept,
                issue_type=IssueType.MULTIPLE_MATCH,
                candidates=[m.name for m in matches],
            )

    def resolve_batch(
        self,
        records: list[AssetRecord],
        context: ImportContext,
    ) -> None:
        """
        批量解析部门字段，使用单次 IN 查询降低 DB 请求数。

        优化策略：
          1. 收集所有不重复的部门名
          2. 一次 IN 查询取回所有匹配记录
          3. 遍历 records 填充结果
        """
        db: Session = context.db

        # 收集需要 resolve 的部门名（去重）
        dept_names: set[str] = set()
        for record in records:
            raw = record.fields.get("department")
            if raw:
                dept_names.add(raw)

        if not dept_names:
            return

        # 单次 IN 查询
        all_depts = (
            db.query(models.Department)
            .filter(models.Department.name.in_(dept_names))
            .all()
        )

        # 构建 name → [Department] 映射
        name_map: dict[str, list[models.Department]] = {}
        for dept in all_depts:
            name_map.setdefault(dept.name, []).append(dept)

        # 逐记录填充
        for record in records:
            raw_dept: Optional[str] = record.fields.get("department")
            if not raw_dept:
                continue

            matches = name_map.get(raw_dept, [])
            if len(matches) == 1:
                dept = matches[0]
                record.resolved.department = DepartmentRef(
                    id=dept.id,
                    name=dept.name,
                    parent_id=dept.parent_id,
                )
            elif len(matches) == 0:
                record.add_resolver_issue(
                    field_name="department",
                    raw_value=raw_dept,
                    issue_type=IssueType.UNKNOWN,
                )
            else:
                record.add_resolver_issue(
                    field_name="department",
                    raw_value=raw_dept,
                    issue_type=IssueType.MULTIPLE_MATCH,
                    candidates=[m.name for m in matches],
                )
