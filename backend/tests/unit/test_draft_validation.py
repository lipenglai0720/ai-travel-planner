"""测试旅行草案与原始需求的一致性规则。"""

import json
from datetime import date, timedelta

import pytest

from app.models.requests import TripRequest
from app.models.trip_draft import TripDraft
from app.services.draft_validation import (
    DraftRequestMismatchError,
    validate_draft_matches_request,
)


def make_request(
    start_date: date,
    day_count: int,
) -> TripRequest:
    """创建一份经过正常模型校验的旅行需求。"""
    end_date = start_date + timedelta(days=day_count - 1)

    return TripRequest.model_validate(
        {
            "destination": "北京",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "travelers": 2,
            "budget_cents": 600000,
            "room_count": 1,
        }
    )


def make_draft(
    start_date: date,
    day_count: int,
) -> TripDraft:
    """创建日期连续、内部结构合法的旅行草案。"""
    draft_data = {
        "title": "旅行测试草案",
        "summary": "用于校验日期一致性，具体地点待查询。",
        "days": [
            {
                "date": (
                    start_date + timedelta(days=offset)
                ).isoformat(),
                "theme": f"第 {offset + 1} 天主题",
                "activities": [
                    {
                        "period": "morning",
                        "title": "主题游览",
                        "description": "具体景点和开放信息待查询。",
                    }
                ],
            }
            for offset in range(day_count)
        ],
    }

    # 使用 JSON 校验路径，与将来解析模型 JSON 输出的方式一致。
    return TripDraft.model_validate_json(
        json.dumps(draft_data, ensure_ascii=False),
    )


@pytest.mark.parametrize("day_count", [1, 3, 7])
def test_matching_draft_passes(day_count: int) -> None:
    """相同日期范围的 1、3、7 日草案都应该通过。"""
    start_date = date(2026, 11, 1)
    trip_request = make_request(start_date, day_count)
    draft = make_draft(start_date, day_count)

    result = validate_draft_matches_request(
        trip_request,
        draft,
    )

    assert result is None


@pytest.mark.parametrize("actual_day_count", [2, 4])
def test_wrong_day_count_is_rejected(
    actual_day_count: int,
) -> None:
    """少一天和多一天都应该被明确拒绝。"""
    start_date = date(2026, 11, 1)
    trip_request = make_request(start_date, 3)
    draft = make_draft(start_date, actual_day_count)

    with pytest.raises(DraftRequestMismatchError) as exc_info:
        validate_draft_matches_request(
            trip_request,
            draft,
        )

    assert exc_info.value.code == "draft_day_count_mismatch"


@pytest.mark.parametrize(
    "draft_start_date",
    [
        date(2026, 10, 31),
        date(2026, 11, 2),
    ],
)
def test_shifted_dates_are_rejected(
    draft_start_date: date,
) -> None:
    """天数相同，但日期提前或推后，都应该被拒绝。"""
    trip_request = make_request(date(2026, 11, 1), 3)
    draft = make_draft(draft_start_date, 3)

    with pytest.raises(DraftRequestMismatchError) as exc_info:
        validate_draft_matches_request(
            trip_request,
            draft,
        )

    assert exc_info.value.code == "draft_date_range_mismatch"


def test_matching_dates_across_year_pass() -> None:
    """跨年的日期计算和匹配也应该正确。"""
    start_date = date(2026, 12, 31)
    trip_request = make_request(start_date, 3)
    draft = make_draft(start_date, 3)

    result = validate_draft_matches_request(
        trip_request,
        draft,
    )

    assert result is None
    assert draft.days[-1].date == date(2027, 1, 2)


def test_failed_validation_does_not_modify_objects() -> None:
    """校验失败时，应保留原始需求和草案。"""
    trip_request = make_request(date(2026, 11, 1), 3)
    draft = make_draft(date(2026, 11, 2), 3)

    request_before = trip_request.model_dump(mode="json")
    draft_before = draft.model_dump(mode="json")

    with pytest.raises(DraftRequestMismatchError):
        validate_draft_matches_request(
            trip_request,
            draft,
        )

    assert trip_request.model_dump(mode="json") == request_before
    assert draft.model_dump(mode="json") == draft_before