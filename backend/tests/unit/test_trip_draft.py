"""验证旅行草案结构、活动时段和日期规则。"""

import json
from copy import deepcopy
from datetime import date as Date, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from app.models.trip_draft import (
    ActivityDraft,
    DayDraft,
    TripDraft,
)


@pytest.fixture
def valid_draft_data() -> dict[str, Any]:
    """为每个测试提供独立的合法草案数据。"""
    return {
        "title": "北京两日旅行草案",
        "summary": "以文化和美食为主题，具体地点待查询。",
        "days": [
            {
                "date": "2026-11-01",
                "theme": "历史文化",
                "activities": [
                    {
                        "period": "morning",
                        "title": "文化主题活动",
                        "description": "具体景点待查询。",
                    },
                    {
                        "period": "afternoon",
                        "title": "城市主题漫步",
                        "description": "具体路线待查询。",
                    },
                ],
            },
            {
                "date": "2026-11-02",
                "theme": "饮食文化",
                "activities": [
                    {
                        "period": "morning",
                        "title": "饮食文化体验",
                        "description": "具体商家和费用待查询。",
                    }
                ],
            },
        ],
    }


def parse_sample(data: dict[str, Any]) -> TripDraft:
    """将测试字典转成 JSON，使用本阶段约定的入口校验。"""
    return TripDraft.model_validate_json(
        json.dumps(data, ensure_ascii=False)
    )


def test_valid_json_creates_nested_models(
    valid_draft_data: dict[str, Any],
) -> None:
    """合法 JSON 应转换成完整的嵌套模型。"""
    draft = parse_sample(valid_draft_data)

    assert isinstance(draft, TripDraft)
    assert isinstance(draft.days[0], DayDraft)
    assert isinstance(
        draft.days[0].activities[0],
        ActivityDraft,
    )
    assert draft.days[0].date == Date(2026, 11, 1)
    assert len(draft.days) == 2

    # 序列化后，日期再次成为 JSON 兼容的字符串。
    dumped = draft.model_dump(mode="json")
    assert dumped["days"][0]["date"] == "2026-11-01"


def test_whitespace_only_activity_title_is_rejected(
    valid_draft_data: dict[str, Any],
) -> None:
    """只有空格的活动标题不能通过校验。"""
    valid_draft_data["days"][0]["activities"][0]["title"] = "   "

    with pytest.raises(ValidationError) as exc_info:
        parse_sample(valid_draft_data)

    error = exc_info.value.errors()[0]

    assert error["type"] == "string_too_short"
    assert error["loc"] == (
        "days",
        0,
        "activities",
        0,
        "title",
    )


def test_unknown_period_is_rejected(
    valid_draft_data: dict[str, Any],
) -> None:
    """活动时段必须属于声明的三个值。"""
    valid_draft_data["days"][0]["activities"][0]["period"] = "night"

    with pytest.raises(ValidationError) as exc_info:
        parse_sample(valid_draft_data)

    assert exc_info.value.errors()[0]["type"] == "literal_error"


def test_duplicate_activity_period_is_rejected(
    valid_draft_data: dict[str, Any],
) -> None:
    """同一天不能安排两个相同的时段。"""
    valid_draft_data["days"][0]["activities"][1]["period"] = "morning"

    with pytest.raises(ValidationError) as exc_info:
        parse_sample(valid_draft_data)

    assert (
        exc_info.value.errors()[0]["type"]
        == "duplicate_activity_period"
    )


def test_reversed_activity_order_is_rejected(
    valid_draft_data: dict[str, Any],
) -> None:
    """下午排在上午前面时，应拒绝草案。"""
    valid_draft_data["days"][0]["activities"].reverse()

    with pytest.raises(ValidationError) as exc_info:
        parse_sample(valid_draft_data)

    assert (
        exc_info.value.errors()[0]["type"]
        == "activity_period_order_invalid"
    )


@pytest.mark.parametrize(
    "second_date",
    [
        "2026-11-01",  # 重复日期。
        "2026-11-03",  # 跳过一天。
        "2026-10-31",  # 日期倒序。
    ],
)
def test_non_consecutive_dates_are_rejected(
    valid_draft_data: dict[str, Any],
    second_date: str,
) -> None:
    """日期重复、跳日、倒序均应失败。"""
    valid_draft_data["days"][1]["date"] = second_date

    with pytest.raises(ValidationError) as exc_info:
        parse_sample(valid_draft_data)

    assert (
        exc_info.value.errors()[0]["type"]
        == "draft_dates_not_consecutive"
    )


def test_extra_activity_field_is_rejected(
    valid_draft_data: dict[str, Any],
) -> None:
    """未声明的地址字段不能进入活动草案。"""
    valid_draft_data["days"][0]["activities"][0]["address"] = (
        "用于异常测试的自填地址"
    )

    with pytest.raises(ValidationError) as exc_info:
        parse_sample(valid_draft_data)

    error = exc_info.value.errors()[0]

    assert error["type"] == "extra_forbidden"
    assert error["loc"] == (
        "days",
        0,
        "activities",
        0,
        "address",
    )


def test_numeric_date_is_rejected(
    valid_draft_data: dict[str, Any],
) -> None:
    """严格日期字段不应把数字解释为日期。"""
    valid_draft_data["days"][0]["date"] = 0

    with pytest.raises(ValidationError) as exc_info:
        parse_sample(valid_draft_data)

    assert exc_info.value.errors()[0]["type"] == "date_type"


def test_more_than_seven_days_is_rejected(
    valid_draft_data: dict[str, Any],
) -> None:
    """日期连续的八天草案也应因长度超限而失败。"""
    first_day = valid_draft_data["days"][0]
    extended_days = []

    for offset in range(8):
        # 深复制避免不同日期的测试数据共享同一个嵌套对象。
        day_data = deepcopy(first_day)
        day_data["date"] = (
            Date(2026, 11, 1) + timedelta(days=offset)
        ).isoformat()
        extended_days.append(day_data)

    valid_draft_data["days"] = extended_days

    with pytest.raises(ValidationError) as exc_info:
        parse_sample(valid_draft_data)

    error = exc_info.value.errors()[0]

    assert error["type"] == "too_long"
    assert error["loc"] == ("days",)


def test_malformed_json_is_rejected() -> None:
    """不完整 JSON 应在解析阶段失败。"""
    with pytest.raises(ValidationError) as exc_info:
        TripDraft.model_validate_json('{"title":')

    assert exc_info.value.errors()[0]["type"] == "json_invalid"