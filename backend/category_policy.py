"""资产分类、领用策略与中文业务校验的唯一规则来源。"""

from enum import Enum
from typing import Final, Iterable


class CategoryPolicyError(ValueError):
    """分类、策略或状态不符合业务规则时抛出的中文错误。"""


class AssetCategoryCode(str, Enum):
    PC = "PC"
    NB = "NB"
    PD = "PD"


class IssuePolicy(str, Enum):
    CONSUMABLE = "CONSUMABLE"


class FixedAssetStatus(str, Enum):
    IDLE = "闲置"
    IN_USE = "使用中"
    IN_REPAIR = "维修中"
    RETIRED = "报废"


class PrimaryCategoryCode(str, Enum):
    DISPLAY_DEVICES = "DISPLAY_DEVICES"
    AUDIO_DEVICES = "AUDIO_DEVICES"
    PHONES = "PHONES"
    INPUT_DEVICES = "INPUT_DEVICES"
    STORAGE_DEVICES = "STORAGE_DEVICES"
    CABLES_CONNECTORS = "CABLES_CONNECTORS"
    TOOLS = "TOOLS"
    OFFICE_GENERAL_CONSUMABLES = "OFFICE_GENERAL_CONSUMABLES"


ASSET_CATEGORY_NAMES: Final[dict[AssetCategoryCode, str]] = {
    AssetCategoryCode.PC: "台式机",
    AssetCategoryCode.NB: "笔记本电脑",
    AssetCategoryCode.PD: "平板电脑",
}
LEGACY_ASSET_CATEGORY_ALIASES: Final[dict[str, str]] = {"移动设备": "平板电脑"}
NON_FIXED_ASSET_CARD_ERROR: Final[str] = "固定资产仅支持台式机、笔记本电脑和平板电脑"
INVALID_ISSUE_POLICY_ERROR: Final[str] = "库房物料只支持一次性消耗品领用策略"
INVALID_FIXED_ASSET_STATUS_ERROR: Final[str] = "固定资产状态仅支持“闲置、使用中、维修中、报废”"

PRIMARY_CATEGORY_NAMES: Final[dict[PrimaryCategoryCode, str]] = {
    PrimaryCategoryCode.DISPLAY_DEVICES: "显示设备",
    PrimaryCategoryCode.AUDIO_DEVICES: "音频设备",
    PrimaryCategoryCode.PHONES: "手机",
    PrimaryCategoryCode.INPUT_DEVICES: "输入设备",
    PrimaryCategoryCode.STORAGE_DEVICES: "存储设备",
    PrimaryCategoryCode.CABLES_CONNECTORS: "线缆与连接配件",
    PrimaryCategoryCode.TOOLS: "工具",
    PrimaryCategoryCode.OFFICE_GENERAL_CONSUMABLES: "办公与通用耗材",
}
CONSUMABLE_CATEGORY_NAMES: Final[frozenset[str]] = frozenset(
    PRIMARY_CATEGORY_NAMES.values()
)
ISSUE_POLICY_NAMES: Final[dict[IssuePolicy, str]] = {
    IssuePolicy.CONSUMABLE: "一次性消耗品",
}
FIXED_ASSET_CATEGORY_OPTIONS: Final[tuple[AssetCategoryCode, ...]] = tuple(
    AssetCategoryCode
)
FIXED_ASSET_STATUSES: Final[tuple[FixedAssetStatus, ...]] = tuple(
    FixedAssetStatus
)
PRIMARY_CATEGORY_SEEDS: Final[tuple[tuple[str, str], ...]] = tuple(
    (category.value, PRIMARY_CATEGORY_NAMES[category])
    for category in PrimaryCategoryCode
)


def _clean(value: str) -> str:
    return value.strip()


def normalize_asset_category(value: str | AssetCategoryCode) -> str:
    """规范化历史分类；未知分类保留原值，由调用方决定是否允许。"""
    if isinstance(value, AssetCategoryCode):
        return ASSET_CATEGORY_NAMES[value]
    normalized = _clean(value)
    return LEGACY_ASSET_CATEGORY_ALIASES.get(normalized, normalized)


def asset_category_code(value: str | AssetCategoryCode) -> AssetCategoryCode | None:
    """将固定资产代码、中文名称或历史名称解析为固定资产代码。"""
    if isinstance(value, AssetCategoryCode):
        return value
    category_name = normalize_asset_category(value)
    for code, name in ASSET_CATEGORY_NAMES.items():
        if category_name == name or category_name.upper() == code.value:
            return code
    return None


def is_fixed_asset_category(value: str | AssetCategoryCode) -> bool:
    return asset_category_code(value) is not None


def require_fixed_asset_category(value: str | AssetCategoryCode) -> AssetCategoryCode:
    category = asset_category_code(value)
    if category is None:
        raise CategoryPolicyError(NON_FIXED_ASSET_CARD_ERROR)
    return category


def is_consumable_category(value: str) -> bool:
    return _clean(value) in CONSUMABLE_CATEGORY_NAMES


def require_consumable_category(value: str) -> str:
    category = _clean(value)
    if category not in CONSUMABLE_CATEGORY_NAMES:
        allowed = "、".join(PRIMARY_CATEGORY_NAMES.values())
        raise CategoryPolicyError(f"消耗品品类仅支持：{allowed}")
    return category


def require_fixed_asset_status(value: str | FixedAssetStatus) -> FixedAssetStatus:
    if isinstance(value, FixedAssetStatus):
        return value
    try:
        return FixedAssetStatus(_clean(value))
    except ValueError as error:
        raise CategoryPolicyError(INVALID_FIXED_ASSET_STATUS_ERROR) from error


def _primary_category_code(
    value: str | PrimaryCategoryCode,
) -> PrimaryCategoryCode | None:
    if isinstance(value, PrimaryCategoryCode):
        return value
    normalized = _clean(value)
    for code, name in PRIMARY_CATEGORY_NAMES.items():
        if normalized == name or normalized.upper() == code.value:
            return code
    return None


def allowed_issue_policies(
    primary_category: str | PrimaryCategoryCode | None,
    material_name: str | None = None,
) -> frozenset[IssuePolicy]:
    """八类库房物料统一按一次性消耗品管理。"""
    if primary_category is None or _primary_category_code(primary_category) is None:
        return frozenset()
    return frozenset({IssuePolicy.CONSUMABLE})


def require_issue_policy(
    value: str | IssuePolicy,
    *,
    primary_category: str | PrimaryCategoryCode | None = None,
    material_name: str | None = None,
) -> IssuePolicy:
    try:
        policy = value if isinstance(value, IssuePolicy) else IssuePolicy(_clean(value).upper())
    except ValueError as error:
        raise CategoryPolicyError(INVALID_ISSUE_POLICY_ERROR) from error

    if policy not in allowed_issue_policies(primary_category, material_name):
        if _primary_category_code(primary_category or "") == (
            PrimaryCategoryCode.OFFICE_GENERAL_CONSUMABLES
        ):
            raise CategoryPolicyError("办公与通用耗材仅支持“一次性消耗品”领用策略")
        raise CategoryPolicyError("该库房物料不支持所选领用策略")
    return policy


def category_options(
    categories: Iterable[AssetCategoryCode] = FIXED_ASSET_CATEGORY_OPTIONS,
) -> list[dict[str, str]]:
    """生成供中文界面直接使用的固定资产分类选项。"""
    return [{"code": item.value, "name": ASSET_CATEGORY_NAMES[item]} for item in categories]
