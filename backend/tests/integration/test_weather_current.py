"""测试实况天气接口、服务编排和客户端生命周期。"""

from collections.abc import Iterator
from datetime import datetime
from unittest.mock import Mock, call
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.routes.weather import get_weather_service
from app.clients.amap import AmapClient, AmapError
from app.main import app
from app.models.district import (
    DistrictInfo,
    DistrictQuery,
    DistrictResult,
)
from app.models.weather import (
    CurrentWeather,
    WeatherLookupQuery,
    WeatherQuery,
)
from app.services import weather_service as weather_service_module
from app.services.weather_service import (
    WeatherService,
    WeatherServiceError,
)


@pytest.fixture
def weather_data() -> CurrentWeather:
    """提供经过模型校验的模拟天气数据。"""
    return CurrentWeather(
        province="北京",
        city="海淀区",
        adcode="110108",
        weather="晴",
        temperature_c=24.5,
        humidity_percent=45.0,
        wind_direction="北",
        wind_power="≤3",
        reported_at=datetime(2026, 10, 12, 9, 0, 0),
    )


@pytest.fixture
def mock_service(
    weather_data: CurrentWeather,
) -> Mock:
    """默认使用服务替身，避免真实高德请求。"""

    service = Mock(spec=WeatherService)
    service.get_current_weather.return_value = weather_data

    return service


@pytest.fixture
def client(
    mock_service: Mock,
) -> Iterator[TestClient]:
    """替换天气服务依赖，并在结束时恢复原始状态。"""

    def override_weather_service() -> WeatherService:
        return mock_service

    original_overrides = app.dependency_overrides.copy()

    app.dependency_overrides[
        get_weather_service
    ] = override_weather_service

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


def test_current_weather_success(
    client: TestClient,
    mock_service: Mock,
    weather_data: CurrentWeather,
) -> None:
    """合法查询返回统一成功响应，并传递规范化的查询条件。"""

    response = client.get(
        "/api/v1/weather/current",
        params={
            "city": " 海淀区 ",
            "province_adcode": "110000",
        },
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert set(body) == {"data", "meta"}
    assert body["data"] == weather_data.model_dump(mode="json")

    request_id = body["meta"]["request_id"]
    assert str(UUID(request_id)) == request_id

    warnings = body["meta"]["warnings"]
    assert any("实况" in item for item in warnings)
    assert any("时区" in item for item in warnings)

    mock_service.get_current_weather.assert_called_once()

    actual_query = (
        mock_service.get_current_weather.call_args.args[0]
    )

    assert isinstance(actual_query, WeatherLookupQuery)
    assert actual_query.city == "海淀区"
    assert actual_query.province_adcode == "110000"


def test_missing_weather_fields_have_warning(
    client: TestClient,
    mock_service: Mock,
    weather_data: CurrentWeather,
) -> None:
    """可选字段缺失时保留 null，并提供业务提醒。"""

    data = weather_data.model_dump()
    data.update(
        temperature_c=None,
        humidity_percent=None,
        wind_direction=None,
        wind_power=None,
    )

    mock_service.get_current_weather.return_value = (
        CurrentWeather(**data)
    )

    response = client.get(
        "/api/v1/weather/current",
        params={"city": "海淀区"},
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert body["data"]["temperature_c"] is None
    assert body["data"]["humidity_percent"] is None
    assert body["data"]["wind_direction"] is None
    assert body["data"]["wind_power"] is None

    assert any(
        "暂缺" in item and "温度" in item and "湿度" in item
        for item in body["meta"]["warnings"]
    )


@pytest.mark.parametrize(
    "params, expected_field, expected_reason",
    [
        ({}, "city", "required"),
        (
            {"city": ""},
            "city",
            "text_too_short",
        ),
        (
            {"city": "   "},
            "city",
            "text_too_short",
        ),
        (
            {"city": "测" * 51},
            "city",
            "text_too_long",
        ),
        (
            {
                "city": "海淀区",
                "province_adcode": "110108",
            },
            "province_adcode",
            "invalid_value",
        ),
        (
            {"city": "海淀区", "days": "7"},
            "days",
            "unexpected_field",
        ),
    ],
)
def test_invalid_query_is_rejected(
    client: TestClient,
    mock_service: Mock,
    params: dict[str, str],
    expected_field: str,
    expected_reason: str,
) -> None:
    """非法输入返回统一 422，且不执行天气业务。"""

    response = client.get(
        "/api/v1/weather/current",
        params=params,
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

    mock_service.get_current_weather.assert_not_called()


@pytest.mark.parametrize(
    "error_code, expected_status",
    [
        ("district_not_found", 404),
        ("district_ambiguous", 422),
        ("district_query_too_broad", 422),
        ("district_level_unsupported", 422),
        ("weather_not_available", 503),
        ("amap_not_configured", 503),
        ("amap_configuration_invalid", 503),
        ("amap_timeout", 504),
        ("amap_connection_error", 502),
        ("amap_http_error", 502),
        ("amap_business_error", 502),
        ("amap_response_invalid", 502),
        ("amap_district_invalid", 502),
        ("amap_weather_invalid", 502),
        ("amap_weather_region_mismatch", 502),
    ],
)
def test_weather_errors_are_mapped(
    client: TestClient,
    mock_service: Mock,
    error_code: str,
    expected_status: int,
) -> None:
    """天气业务错误应转换为约定状态，且不返回内部异常文本。"""

    internal_message = "模拟内部消息，含 test-secret，不应对外返回。"

    mock_service.get_current_weather.side_effect = (
        WeatherServiceError(
            code=error_code,
            message=internal_message,
        )
    )

    response = client.get(
        "/api/v1/weather/current",
        params={"city": "海淀区"},
    )

    assert response.status_code == expected_status, response.text

    body = response.json()

    assert set(body) == {"error", "meta"}
    assert body["error"]["code"] == error_code
    assert body["error"]["details"] == []
    assert body["error"]["message"]
    assert internal_message not in response.text
    assert "test-secret" not in response.text

    request_id = body["meta"]["request_id"]
    assert str(UUID(request_id)) == request_id


@pytest.mark.parametrize(
    "stage, expected_status",
    [
        ("success", 200),
        ("district_failure", 422),
        ("weather_failure", 504),
    ],
)
def test_real_service_orders_calls_and_closes_client(
    client: TestClient,
    weather_data: CurrentWeather,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    expected_status: int,
) -> None:
    """真实服务应按顺序编排，并在各条路径关闭客户端。"""

    amap_client = Mock(spec=AmapClient)

    amap_client.resolve_district.return_value = DistrictResult(
        keyword="海淀区",
        province_adcode="110000",
        region=DistrictInfo(
            name="海淀区",
            adcode="110108",
            level="district",
        ),
    )

    amap_client.get_current_weather.return_value = weather_data

    internal_message = "模拟上游内部文本，不应进入 HTTP 响应。"

    if stage == "district_failure":
        amap_client.resolve_district.side_effect = AmapError(
            code="district_ambiguous",
            message=internal_message,
        )

    elif stage == "weather_failure":
        amap_client.get_current_weather.side_effect = AmapError(
            code="amap_timeout",
            message=internal_message,
        )

    constructor = Mock(return_value=amap_client)

    monkeypatch.setattr(
        weather_service_module,
        "AmapClient",
        constructor,
    )

    real_service = WeatherService(api_key=None)

    app.dependency_overrides[
        get_weather_service
    ] = lambda: real_service

    response = client.get(
        "/api/v1/weather/current",
        params={
            "city": "海淀区",
            "province_adcode": "110000",
        },
    )

    assert response.status_code == expected_status, response.text
    assert internal_message not in response.text

    constructor.assert_called_once_with(
        api_key=None,
        timeout_seconds=10.0,
    )

    expected_calls = [
        call.resolve_district(
            DistrictQuery(
                keyword="海淀区",
                province_adcode="110000",
            )
        )
    ]

    # 行政区解析失败后，不应继续查询天气。
    if stage != "district_failure":
        expected_calls.append(
            call.get_current_weather(
                WeatherQuery(adcode="110108")
            )
        )

    expected_calls.append(call.close())

    # 同时检查调用参数、调用顺序和 close 的执行。
    assert amap_client.method_calls == expected_calls


def test_client_initialization_failure_is_mapped(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """客户端未能创建时，也应转换成天气业务错误。"""

    internal_message = "模拟初始化错误，含 test-secret。"

    constructor = Mock(
        side_effect=AmapError(
            code="amap_not_configured",
            message=internal_message,
        )
    )

    monkeypatch.setattr(
        weather_service_module,
        "AmapClient",
        constructor,
    )

    real_service = WeatherService(api_key=None)

    app.dependency_overrides[
        get_weather_service
    ] = lambda: real_service

    response = client.get(
        "/api/v1/weather/current",
        params={"city": "海淀区"},
    )

    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "amap_not_configured"
    assert internal_message not in response.text
    assert "test-secret" not in response.text

    constructor.assert_called_once()


def test_invalid_query_does_not_create_client(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非法输入应阻止真实服务创建高德客户端。"""

    constructor = Mock()

    monkeypatch.setattr(
        weather_service_module,
        "AmapClient",
        constructor,
    )

    real_service = WeatherService(api_key=None)

    app.dependency_overrides[
        get_weather_service
    ] = lambda: real_service

    response = client.get(
        "/api/v1/weather/current",
        params={},
    )

    assert response.status_code == 422, response.text
    constructor.assert_not_called()