"""旅行生成接口测试：验证响应、异常映射和客户端清理。"""

import json
from collections.abc import Iterator
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.api.routes import trips
from app.core.config import Settings
from app.llm.client import LLMConfigurationError
from app.main import app
from app.models.requests import TripRequest
from app.models.trip_draft import TripDraft
from app.services.trip_generation_service import (
    TripGenerationError,
    TripGenerationService,
)


@pytest.fixture
def valid_payload() -> dict[str, object]:
    """为每个测试提供一份新的合法请求。"""

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


@pytest.fixture
def generation_service() -> Mock:
    """提供返回合法草案的生成服务替身。"""

    draft_payload = {
        "title": "北京三日旅行草案",
        "summary": "用于接口测试的旅行草案。",
        "days": [
            {
                "date": day_date,
                "theme": "文化体验",
                "activities": [
                    {
                        "period": "morning",
                        "title": "上午主题活动",
                        "description": "测试活动，具体地点待查询核实。",
                    }
                ],
            }
            for day_date in (
                "2026-11-01",
                "2026-11-02",
                "2026-11-03",
            )
        ],
    }

    # 沿用 JSON 校验路径，正确解析模型中的严格日期字段。
    draft = TripDraft.model_validate_json(
        json.dumps(draft_payload, ensure_ascii=False)
    )

    # spec 约束替身暴露的方法，减少方法名写错而未被发现的风险。
    service = Mock(spec=TripGenerationService)
    service.generate_draft.return_value = draft

    return service


@pytest.fixture
def client(
    generation_service: Mock,
) -> Iterator[TestClient]:
    """替换生成服务依赖，并在测试结束后恢复。"""

    def override_generation_service() -> TripGenerationService:
        """让本次测试使用同一个生成服务替身。"""
        return generation_service

    original_overrides = app.dependency_overrides.copy()

    app.dependency_overrides[
        trips.get_trip_generation_service
    ] = override_generation_service

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # 恢复原始映射，避免影响其他测试。
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


def test_generate_success(
    client: TestClient,
    generation_service: Mock,
    valid_payload: dict[str, object],
) -> None:
    """合法输入应返回统一成功响应，并调用一次生成服务。"""

    response = client.post(
        "/api/v1/trips/generate",
        json=valid_payload,
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert set(body) == {"data", "meta"}
    assert body["data"] == (
        generation_service.generate_draft.return_value
        .model_dump(mode="json")
    )

    assert len(body["meta"]["warnings"]) == 1
    assert "草案" in body["meta"]["warnings"][0]

    request_id = body["meta"]["request_id"]
    assert str(UUID(request_id)) == request_id

    generation_service.generate_draft.assert_called_once()

    # 检查传入服务的对象已经经过请求模型校验。
    actual_request = (
        generation_service.generate_draft.call_args.args[0]
    )

    assert isinstance(actual_request, TripRequest)
    assert actual_request.destination == "北京"
    assert actual_request.day_count == 3
    assert actual_request.budget_cents == 600000


@pytest.mark.parametrize(
    "changes, expected_field, expected_reason",
    [
        (
            {"travelers": 0},
            "travelers",
            "value_too_small",
        ),
        (
            {"end_date": "2026-10-31"},
            "end_date",
            "date_order_invalid",
        ),
    ],
)
def test_generate_rejects_invalid_input(
    client: TestClient,
    generation_service: Mock,
    valid_payload: dict[str, object],
    changes: dict[str, object],
    expected_field: str,
    expected_reason: str,
) -> None:
    """非法输入应返回 422，并且不执行生成业务方法。"""

    payload = valid_payload.copy()
    payload.update(changes)

    response = client.post(
        "/api/v1/trips/generate",
        json=payload,
    )

    assert response.status_code == 422, response.text

    body = response.json()

    assert set(body) == {"error", "meta"}
    assert body["error"] == {
        "code": "VALIDATION_ERROR",
        "message": "请求参数校验失败",
        "details": [
            {
                "field": expected_field,
                "reason": expected_reason,
            }
        ],
    }

    generation_service.generate_draft.assert_not_called()


@pytest.mark.parametrize(
    "error_code, expected_status",
    [
        ("llm_timeout", 504),
        ("llm_connection_error", 502),
        ("llm_http_error", 502),
        ("llm_output_truncated", 502),
        ("llm_output_invalid", 502),
        ("draft_day_count_mismatch", 502),
    ],
)
def test_generate_maps_service_errors(
    client: TestClient,
    generation_service: Mock,
    valid_payload: dict[str, object],
    error_code: str,
    expected_status: int,
) -> None:
    """已识别的生成错误应映射到约定的 HTTP 响应。"""

    internal_message = "内部模拟异常文本，不应直接进入接口响应。"

    # side_effect 指定该方法被调用时抛出异常。
    generation_service.generate_draft.side_effect = (
        TripGenerationError(
            code=error_code,
            message=internal_message,
        )
    )

    response = client.post(
        "/api/v1/trips/generate",
        json=valid_payload,
    )

    assert response.status_code == expected_status, response.text

    body = response.json()

    assert set(body) == {"error", "meta"}
    assert body["error"]["code"] == error_code
    assert body["error"]["details"] == []

    # HTTP 响应使用固定说明，保留明确的错误代码。
    assert internal_message not in response.text

    generation_service.generate_draft.assert_called_once()


def test_generate_reports_missing_configuration(
    client: TestClient,
    generation_service: Mock,
    valid_payload: dict[str, object],
) -> None:
    """依赖初始化中的配置异常也应返回统一结构。"""

    def unavailable_service() -> TripGenerationService:
        """模拟模型配置缺失。"""
        raise LLMConfigurationError("测试用配置错误。")

    app.dependency_overrides[
        trips.get_trip_generation_service
    ] = unavailable_service

    response = client.post(
        "/api/v1/trips/generate",
        json=valid_payload,
    )

    assert response.status_code == 503, response.text

    body = response.json()

    assert body["error"]["code"] == "llm_not_configured"
    assert body["error"]["details"] == []

    generation_service.generate_draft.assert_not_called()


@pytest.mark.parametrize(
    "valid_output",
    [True, False],
    ids=["valid-output", "invalid-output"],
)
def test_generation_dependency_closes_client(
    client: TestClient,
    generation_service: Mock,
    valid_payload: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    valid_output: bool,
) -> None:
    """真实依赖和服务在成功、输出校验失败时都应关闭客户端。"""

    chat_model = Mock()

    if valid_output:
        output_text = (
            generation_service.generate_draft.return_value
            .model_dump_json()
        )
        expected_status = 200
    else:
        # 不完整的 JSON 会被真实生成服务识别为输出校验失败。
        output_text = "{"
        expected_status = 502

    chat_model.invoke.return_value = AIMessage(
        content=output_text,
        response_metadata={"finish_reason": "stop"},
    )

    # 恢复使用真实的生成服务依赖函数。
    app.dependency_overrides.pop(
        trips.get_trip_generation_service,
        None,
    )

    # 替换配置读取和模型工厂。
    # 真实依赖仍会创建 TripGenerationService，
    # 但其中的模型调用由测试替身完成。
    monkeypatch.setattr(
        trips,
        "Settings",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        trips,
        "create_trip_chat_model",
        Mock(return_value=chat_model),
    )

    response = client.post(
        "/api/v1/trips/generate",
        json=valid_payload,
    )

    assert response.status_code == expected_status, response.text

    chat_model.invoke.assert_called_once()
    chat_model.root_client.close.assert_called_once_with()

    if not valid_output:
        assert response.json()["error"]["code"] == (
            "llm_output_invalid"
        )