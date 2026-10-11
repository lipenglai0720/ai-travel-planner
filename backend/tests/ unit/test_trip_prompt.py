"""验证旅行提示词中的需求数据和模板行为。"""

import json
from typing import Any

import pytest
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from app.models.requests import TripRequest
from app.prompts.trip_prompt import (
    TRIP_PROMPT,
    build_trip_messages,
)


@pytest.fixture
def valid_payload() -> dict[str, Any]:
    """为每个测试提供独立的合法输入字典。"""
    return {
        "destination": " 北京 ",
        "start_date": "2026-11-01",
        "end_date": "2026-11-03",
        "travelers": 2,
        "budget_cents": 600000,
        "transportation": "public_transit",
        "accommodation_preference": "economy",
        "room_count": 1,
        "preferences": ["历史文化", "美食"],
        "pace": "relaxed",
    }


def test_messages_preserve_complete_trip_request(
    valid_payload: dict[str, Any],
) -> None:
    """生成两种消息，并完整保留旅行需求。"""
    trip_request = TripRequest.model_validate(valid_payload)

    messages = build_trip_messages(trip_request)

    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)

    # 把用户消息中的 JSON 文本解析回来，
    # 检查传给模型的数据，而不是仅检查打印结果。
    prompt_data = json.loads(messages[1].text)

    assert prompt_data == {
        "destination": "北京",
        "start_date": "2026-11-01",
        "end_date": "2026-11-03",
        "travelers": 2,
        "budget_cents": 600000,
        "transportation": "public_transit",
        "accommodation_preference": "economy",
        "room_count": 1,
        "preferences": ["历史文化", "美食"],
        "pace": "relaxed",
        "day_count": 3,
        "currency": "CNY",
        "budget_scope": "whole_trip_all_travelers",
    }


@pytest.mark.parametrize(
    ("end_date", "expected_day_count"),
    [
        ("2026-11-01", 1),
        ("2026-11-03", 3),
        ("2026-11-07", 7),
    ],
)
def test_messages_use_inclusive_day_count(
    valid_payload: dict[str, Any],
    end_date: str,
    expected_day_count: int,
) -> None:
    """一天、三天、七天旅行均使用程序计算的天数。"""
    valid_payload["end_date"] = end_date

    trip_request = TripRequest.model_validate(valid_payload)
    messages = build_trip_messages(trip_request)
    prompt_data = json.loads(messages[1].text)

    assert prompt_data["day_count"] == expected_day_count


def test_budget_remains_integer_total_cents(
    valid_payload: dict[str, Any],
) -> None:
    """预算保留到分，不转换成浮点数或每人预算。"""
    # 使用不能被人数整除的数值，
    # 帮助发现误除以人数、取整等问题。
    valid_payload["budget_cents"] = 600001

    trip_request = TripRequest.model_validate(valid_payload)
    messages = build_trip_messages(trip_request)
    prompt_data = json.loads(messages[1].text)

    assert type(prompt_data["budget_cents"]) is int
    assert prompt_data["budget_cents"] == 600001
    assert prompt_data["currency"] == "CNY"
    assert (
        prompt_data["budget_scope"]
        == "whole_trip_all_travelers"
    )


def test_empty_preferences_are_preserved(
    valid_payload: dict[str, Any],
) -> None:
    """用户未指定兴趣时，保留空列表的含义。"""
    valid_payload["preferences"] = []

    trip_request = TripRequest.model_validate(valid_payload)
    messages = build_trip_messages(trip_request)
    prompt_data = json.loads(messages[1].text)

    assert prompt_data["preferences"] == []


def test_preferences_with_special_characters_are_preserved(
    valid_payload: dict[str, Any],
) -> None:
    """花括号、引号和换行属于用户数据，应原样保留。"""
    special_preferences = [
        "摄影 {budget_cents}",
        '美食 "探店"',
        "自然风光\n慢游",
    ]
    valid_payload["preferences"] = special_preferences

    trip_request = TripRequest.model_validate(valid_payload)
    messages = build_trip_messages(trip_request)
    prompt_data = json.loads(messages[1].text)

    assert prompt_data["preferences"] == special_preferences


def test_missing_template_variable_raises_key_error() -> None:
    """缺少必需变量时，模板应明确失败。"""
    # 故意不提供 trip_request_json。
    # pytest.raises 验证调用确实抛出指定异常。
    with pytest.raises(KeyError, match="trip_request_json"):
        TRIP_PROMPT.format_messages()