"""测试旅行提示词中的输出 Schema 和模板变量行为。"""

import json
from typing import Any

import pytest
from langchain_core.messages import BaseMessage, SystemMessage

from app.models.trip import (
    TripDraft,
    TripRequest,
)
from app.prompts.trip_prompt import (
    TRIP_PROMPT,
    build_trip_messages,
)


def make_request() -> TripRequest:
    """创建一份正常的三日旅行需求。"""
    return TripRequest.model_validate(
        {
            "destination": "北京",
            "start_date": "2026-11-01",
            "end_date": "2026-11-03",
            "travelers": 2,
            "budget_cents": 600000,
            "preferences": ["历史文化"],
        }
    )


def get_embedded_schema(
    messages: list[BaseMessage],
) -> dict[str, Any]:
    """从系统消息的指定标记之间提取 JSON Schema。"""
    system_message = messages[0]

    assert isinstance(system_message, SystemMessage)
    assert isinstance(system_message.content, str)

    # partition() 按第一次出现的分隔符拆成三部分：
    # 分隔符之前的文本、分隔符本身、分隔符之后的文本。
    _, opening_marker, remaining_text = (
        system_message.content.partition("<trip_draft_schema>")
    )
    assert opening_marker == "<trip_draft_schema>"

    schema_text, closing_marker, _ = remaining_text.partition(
        "</trip_draft_schema>"
    )
    assert closing_marker == "</trip_draft_schema>"

    schema = json.loads(schema_text)
    assert isinstance(schema, dict)

    return schema


def test_output_schema_is_inserted_in_system_message() -> None:
    """最终系统消息中的 Schema 应与 TripDraft 的定义一致。"""
    messages = build_trip_messages(make_request())

    actual_schema = get_embedded_schema(messages)
    expected_schema = TripDraft.model_json_schema(
        mode="validation",
    )

    assert actual_schema == expected_schema


def test_schema_is_bound_and_only_request_input_remains() -> None:
    """Schema 应提前绑定，只留下旅行需求这个必需输入。"""
    assert TRIP_PROMPT.input_variables == ["trip_request_json"]
    assert "output_schema_json" in TRIP_PROMPT.partial_variables


def test_output_schema_and_request_data_have_different_roles() -> None:
    """输出结构定义草案字段，用户消息承载旅行需求和预算等信息。"""
    messages = build_trip_messages(make_request())

    schema = get_embedded_schema(messages)

    human_content = messages[1].content
    assert isinstance(human_content, str)

    request_data = json.loads(human_content)

    # 当前输出模型的根字段只有这三个。
    assert set(schema["properties"]) == {
        "title",
        "summary",
        "days",
    }

    # 这些信息属于旅行需求，由用户消息提供。
    assert request_data["budget_cents"] == 600000
    assert request_data["day_count"] == 3
    assert request_data["budget_scope"] == (
        "whole_trip_all_travelers"
    )


@pytest.mark.parametrize(
    "preference",
    [
        "{output_schema_json}",
        "{trip_request_json}",
        "<trip_draft_schema>用户偏好内容</trip_draft_schema>",
    ],
)
def test_template_like_preference_is_preserved_as_data(
    preference: str,
) -> None:
    """用户偏好中的模板变量或标记文本应作为普通数据保留。"""
    request_data = make_request().model_dump(mode="json")
    request_data["preferences"] = [preference]

    # 修改测试输入后重新校验，得到正常构建的请求模型。
    trip_request = TripRequest.model_validate(request_data)
    messages = build_trip_messages(trip_request)

    human_content = messages[1].content
    assert isinstance(human_content, str)

    rendered_request = json.loads(human_content)

    # 用户文本应保留在用户消息中。
    assert rendered_request["preferences"] == [preference]

    # 用户偏好不应被拼接到系统规则中。
    system_content = messages[0].content
    assert isinstance(system_content, str)
    assert preference not in system_content
