"""分类、命名与领用策略的属性测试。"""

import pytest
from hypothesis import given, settings, strategies as st

from category_policy import (
    ASSET_CATEGORY_NAMES,
    INVALID_ISSUE_POLICY_ERROR,
    NON_FIXED_ASSET_CARD_ERROR,
    AssetCategoryCode,
    CategoryPolicyError,
    IssuePolicy,
    PrimaryCategoryCode,
    allowed_issue_policies,
    asset_category_code,
    is_fixed_asset_category,
    normalize_asset_category,
    require_fixed_asset_category,
    require_issue_policy,
)

FIXED_CATEGORY_INPUTS = st.sampled_from(
    ("PC", "pc", "NB", "nb", "PD", "pd", "台式机", "笔记本电脑", "平板电脑", "移动设备")
)
NON_FIXED_CATEGORY_INPUTS = st.one_of(
    st.sampled_from(("显示器", "鼠标", "网线", "打印机", "服务器", "")),
    st.text(max_size=24).map(lambda value: f"非固定-{value}"),
)
MATERIAL_NAMES = st.sampled_from(
    ("显示器", "扬声器", "扩展坞", "摄像头", "鼠标", "键盘", "鼠标垫", "线材", "小配件", "无线鼠标", "有线键鼠", "无线键鼠", "网线", "数据线", "办公纸")
)


# Feature: asset-category-and-issuance-management, Property 1: 分类、命名与领用策略受限
# Validates: Requirements 1.1, 1.2, 1.4, 5.3, 5.5, 5.8, 11.1
@settings(max_examples=100)
@given(
    category=st.one_of(FIXED_CATEGORY_INPUTS, NON_FIXED_CATEGORY_INPUTS),
    padding=st.text(alphabet=" \t\n", max_size=3),
    material_name=MATERIAL_NAMES,
    office_consumable=st.booleans(),
)
def test_property_1_category_naming_and_issue_policy_constraints(
    category: str,
    padding: str,
    material_name: str,
    office_consumable: bool,
) -> None:
    normalized = normalize_asset_category(category)
    expected = next(
        (
            code
            for code, name in ASSET_CATEGORY_NAMES.items()
            if normalized == name or normalized.upper() == code.value
        ),
        None,
    )
    assert asset_category_code(category) is expected
    assert is_fixed_asset_category(category) is (expected is not None)
    if expected is None:
        with pytest.raises(CategoryPolicyError, match=NON_FIXED_ASSET_CARD_ERROR):
            require_fixed_asset_category(category)

    assert normalize_asset_category(f"{padding}移动设备{padding}") == "平板电脑"
    assert not is_fixed_asset_category(material_name)
    with pytest.raises(CategoryPolicyError, match=NON_FIXED_ASSET_CARD_ERROR):
        require_fixed_asset_category(material_name)

    primary_category = (
        PrimaryCategoryCode.OFFICE_GENERAL_CONSUMABLES
        if office_consumable
        else PrimaryCategoryCode.INPUT_OFFICE_PERIPHERALS
    )
    allowed = allowed_issue_policies(primary_category, material_name)
    assert allowed <= frozenset(IssuePolicy)
    assert allowed
    if office_consumable:
        assert allowed == frozenset({IssuePolicy.CONSUMABLE})
    for policy in IssuePolicy:
        if policy in allowed:
            assert require_issue_policy(
                policy.value,
                primary_category=primary_category,
                material_name=material_name,
            ) is policy
        else:
            with pytest.raises(CategoryPolicyError):
                require_issue_policy(
                    policy.value,
                    primary_category=primary_category,
                    material_name=material_name,
                )
    with pytest.raises(CategoryPolicyError, match=INVALID_ISSUE_POLICY_ERROR):
        require_issue_policy(
            "invalid-policy",
            primary_category=primary_category,
            material_name=material_name,
        )
