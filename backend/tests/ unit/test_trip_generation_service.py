"""测试旅行草案生成服务，不调用真实云端模型。"""

import json
from datetime import date, timedelta
from typing import Any
from unittest.mock import Mock

import httpx
import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
)
from openai.types.chat import ChatCompletion

from app.models.requests import TripRequest
from app.models.trip_draft import TripDraft
from app.services.trip_generation_service import (
    TripGenerationError,
    TripGenerationService,
)


@pytest.fixture
def trip_request() -> TripRequest:
    """准备正常的三日旅行需求。"""
    return TripRequest.model_validate(
        {
            "destination": "北京",
            "start_date": "2026-11-01",
            "end_date": "2026-11-03",
            "travelers": 2,
            "budget_cents": 600000,
        }
    )


@pytest.fixture
def draft_data() -> dict[str, Any]:
    """准备内部结构合法、与需求日期一致的草案数据。"""
    start_date = date(2026, 11, 1)

    return {
        "title": "北京三日旅行草案",
        "summary": "围绕兴趣安排活动，具体地点待查询。",
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
            for offset in range(3)
        ],
    }


@pytest.fixture
def chat_model() -> Mock:
    """准备具有聊天模型调用接口的替身。"""
    return Mock(spec=BaseChatModel)


def make_reply(
    content: str,
    finish_reason: str | None = "stop",
) -> AIMessage:
    """构建用于测试的模型消息。"""
    return AIMessage(
        content=content,
        response_metadata={
            "finish_reason": finish_reason,
        },
    )


def make_call_error(error_kind: str) -> Exception:
    """构建网络或 SDK 异常；这里只创建对象，不发送请求。"""
    api_request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )

    if error_kind == "timeout":
        return APITimeoutError(request=api_request)

    if error_kind == "connection":
        return APIConnectionError(request=api_request)

    if error_kind == "sdk":
        return APIError(
            "测试 SDK 响应异常",
            request=api_request,
            body=None,
        )

    if error_kind == "invalid_response":
        return json.JSONDecodeError(
            "测试响应格式错误",
            "",
            0,
        )

    # 剩余测试参数为 HTTP 状态码，例如 401、429、503。
    response = httpx.Response(
        int(error_kind),
        request=api_request,
    )

    return APIStatusError(
        "测试 HTTP 错误",
        response=response,
        body=None,
    )


def test_valid_reply_returns_validated_draft(
    trip_request: TripRequest,
    draft_data: dict[str, Any],
    chat_model: Mock,
) -> None:
    """正常回复应该返回已经校验的 TripDraft。"""
    chat_model.invoke.return_value = make_reply(
        json.dumps(draft_data, ensure_ascii=False),
    )
    service = TripGenerationService(chat_model)

    draft = service.generate_draft(trip_request)

    assert isinstance(draft, TripDraft)
    assert len(draft.days) == trip_request.day_count
    assert draft.days[0].date == trip_request.start_date
    assert draft.days[-1].date == trip_request.end_date

    # 服务应只发起一次模型调用，并传入当前请求的消息。
    chat_model.invoke.assert_called_once()
    sent_messages = chat_model.invoke.call_args.args[0]

    assert len(sent_messages) == 2
    assert sent_messages[0].type == "system"
    assert isinstance(sent_messages[1].content, str)

    sent_request = json.loads(sent_messages[1].content)
    assert sent_request["destination"] == trip_request.destination


@pytest.mark.parametrize(
    ("content", "expected_code"),
    [
        ("", "llm_output_empty"),
        ("   ", "llm_output_empty"),
        ('{"title":', "llm_output_invalid"),
        ("{}", "llm_output_invalid"),
    ],
)
def test_unusable_content_is_rejected(
    trip_request: TripRequest,
    chat_model: Mock,
    content: str,
    expected_code: str,
) -> None:
    """空内容、错误 JSON 和缺少字段的 JSON 都应该被拒绝。"""
    chat_model.invoke.return_value = make_reply(content)
    service = TripGenerationService(chat_model)

    with pytest.raises(TripGenerationError) as exc_info:
        service.generate_draft(trip_request)

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    ("finish_reason", "expected_code"),
    [
        ("length", "llm_output_truncated"),
        ("tool_calls", "llm_response_incomplete"),
        (None, "llm_response_incomplete"),
    ],
)
def test_non_stop_finish_reason_is_rejected(
    trip_request: TripRequest,
    draft_data: dict[str, Any],
    chat_model: Mock,
    finish_reason: str | None,
    expected_code: str,
) -> None:
    """即使文本看起来合法，异常结束的回复也不能直接使用。"""
    chat_model.invoke.return_value = make_reply(
        json.dumps(draft_data, ensure_ascii=False),
        finish_reason=finish_reason,
    )
    service = TripGenerationService(chat_model)

    with pytest.raises(TripGenerationError) as exc_info:
        service.generate_draft(trip_request)

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("missing_day", "draft_day_count_mismatch"),
        ("shifted_dates", "draft_date_range_mismatch"),
    ],
)
def test_request_mismatch_is_rejected(
    trip_request: TripRequest,
    draft_data: dict[str, Any],
    chat_model: Mock,
    case: str,
    expected_code: str,
) -> None:
    """生成服务必须实际执行请求一致性校验。"""
    if case == "missing_day":
        draft_data["days"].pop()

    else:
        for day_data in draft_data["days"]:
            original_date = date.fromisoformat(day_data["date"])
            day_data["date"] = (
                original_date + timedelta(days=1)
            ).isoformat()

    chat_model.invoke.return_value = make_reply(
        json.dumps(draft_data, ensure_ascii=False),
    )
    service = TripGenerationService(chat_model)

    with pytest.raises(TripGenerationError) as exc_info:
        service.generate_draft(trip_request)

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    ("error_kind", "expected_code"),
    [
        ("timeout", "llm_timeout"),
        ("connection", "llm_connection_error"),
        ("401", "llm_http_error"),
        ("429", "llm_http_error"),
        ("503", "llm_http_error"),
        ("sdk", "llm_sdk_error"),
        ("invalid_response", "llm_response_invalid"),
    ],
)
def test_call_errors_are_converted(
    trip_request: TripRequest,
    chat_model: Mock,
    error_kind: str,
    expected_code: str,
) -> None:
    """外部调用失败应转换成项目定义的生成异常。"""
    chat_model.invoke.side_effect = make_call_error(error_kind)
    service = TripGenerationService(chat_model)

    with pytest.raises(TripGenerationError) as exc_info:
        service.generate_draft(trip_request)

    assert exc_info.value.code == expected_code
    chat_model.invoke.assert_called_once()


def test_sdk_length_error_is_converted(
    trip_request: TripRequest,
    chat_model: Mock,
) -> None:
    """SDK 在返回消息之前抛出的截断异常也必须被处理。"""
    completion = ChatCompletion(
        id="offline-test",
        created=0,
        model="deepseek-flash",
        object="chat.completion",
        usage=None,
        choices=[
            {
                "index": 0,
                "finish_reason": "length",
                "message": {
                    "role": "assistant",
                    "content": "{",
                },
            }
        ],
    )

    chat_model.invoke.side_effect = LengthFinishReasonError(
        completion=completion,
    )
    service = TripGenerationService(chat_model)

    with pytest.raises(TripGenerationError) as exc_info:
        service.generate_draft(trip_request)

    assert exc_info.value.code == "llm_output_truncated"


def test_sdk_content_filter_error_is_converted(
    trip_request: TripRequest,
    chat_model: Mock,
) -> None:
    """SDK 的内容过滤异常应转换成明确的生成失败。"""
    chat_model.invoke.side_effect = ContentFilterFinishReasonError()
    service = TripGenerationService(chat_model)

    with pytest.raises(TripGenerationError) as exc_info:
        service.generate_draft(trip_request)

    assert exc_info.value.code == "llm_response_incomplete"


def test_unexpected_message_type_is_rejected(
    trip_request: TripRequest,
    chat_model: Mock,
) -> None:
    """返回类型异常时，不能继续解析为旅行草案。"""
    chat_model.invoke.return_value = HumanMessage(content="{}")
    service = TripGenerationService(chat_model)

    with pytest.raises(TripGenerationError) as exc_info:
        service.generate_draft(trip_request)

    assert exc_info.value.code == "llm_response_invalid"