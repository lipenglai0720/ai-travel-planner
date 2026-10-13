"""测试预报接口、目标日期状态和服务编排。"""

from collections.abc import Iterator
from datetime import date, datetime
from unittest.mock import Mock, call
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.routes.weather import get_weather_service
from app.clients.amap import AmapClient, AmapError
from app.main import app
from app.models.district import (
    DistrictInfo,
    DistrictQuery,
    DistrictResult,
)
from app.models.forecast_lookup import (
    ForecastLookupQuery,
    ForecastLookupResult,
)
from app.models.weather import WeatherQuery
from app.models.weather_forecast import (
    ForecastDay,
    WeatherForecast,
)
from app.services import weather_service as weather_service_module
from app.services.weather_service import (
    WeatherService,
    WeatherServiceError,
)


@pytest.fixture
def forecast_data() -> WeatherForecast:
    """提供有日期缺口的模拟预报。"""

    return WeatherForecast(
        province="北京",
        city="海淀区",
        adcode="110108",
        reported_at=datetime(2026, 10, 13, 8, 0, 0),
        days=[
            ForecastDay(
                forecast_date=date(2026, 10, 13),
                day_weather="晴",
                night_weather="多云",
                day_temperature_c=24.5,
                night_temperature_c=18.0,
                day_wind_direction="北",
                night_wind_direction="北",
                day_wind_power="1-3",
                night_wind_power="≤3",
            ),
            ForecastDay(
                forecast_date=date(2026, 10, 15),
                day_weather="多云",
                night_weather="阴",
                day_temperature_c=23.0,
                night_temperature_c=17.0,
                day_wind_direction="东",
                night_wind_direction="东",
                day_wind_power="1-3",
                night_wind_power="≤3",
            ),
        ],
    )


@pytest.fixture
def mock_service(
    forecast_data: WeatherForecast,
) -> Mock:
    """默认只查询完整预报，不指定日期。"""

    service = Mock(spec=WeatherService)

    service.get_forecast.return_value = ForecastLookupResult(
        forecast=forecast_data,
        target_date=None,
        coverage_status="not_requested",
        selected_day=None,
    )

    return service


@pytest.fixture
def client(
    mock_service: Mock,
) -> Iterator[TestClient]:
    """替换天气服务依赖，并在结束后恢复。"""

    original_overrides = app.dependency_overrides.copy()

    app.dependency_overrides[
        get_weather_service
    ] = lambda: mock_service

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


def test_forecast_without_target_date(
    client: TestClient,
    mock_service: Mock,
    forecast_data: WeatherForecast,
) -> None:
    """未指定日期时，返回完整预报与 not_requested。"""

    response = client.get(
        "/api/v1/weather/forecast",
        params={
            "city": " 海淀区 ",
            "province_adcode": "110000",
        },
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert set(body) == {"data", "meta"}
    assert body["data"]["forecast"] == (
        forecast_data.model_dump(mode="json")
    )
    assert body["data"]["target_date"] is None
    assert body["data"]["coverage_status"] == "not_requested"
    assert body["data"]["selected_day"] is None

    request_id = body["meta"]["request_id"]
    assert str(UUID(request_id)) == request_id

    assert any(
        "预报" in item
        for item in body["meta"]["warnings"]
    )

    mock_service.get_forecast.assert_called_once()

    actual_query = mock_service.get_forecast.call_args.args[0]

    assert isinstance(actual_query, ForecastLookupQuery)
    assert actual_query.city == "海淀区"
    assert actual_query.province_adcode == "110000"
    assert actual_query.target_date is None


@pytest.mark.parametrize(
    "target_date, expected_coverage",
    [
        (date(2026, 10, 13), "available"),
        (date(2026, 10, 14), "unavailable"),
    ],
)
def test_target_date_is_parsed_and_serialized(
    client: TestClient,
    mock_service: Mock,
    forecast_data: WeatherForecast,
    target_date: date,
    expected_coverage: str,
) -> None:
    """URL 日期文本应转换为 date，并输出对应覆盖状态。"""

    mock_service.get_forecast.return_value = ForecastLookupResult(
        forecast=forecast_data,
        target_date=target_date,
        coverage_status=expected_coverage,
        selected_day=forecast_data.find_day(target_date),
    )

    response = client.get(
        "/api/v1/weather/forecast",
        params={
            "city": "海淀区",
            "target_date": f" {target_date.isoformat()} ",
        },
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert body["data"]["target_date"] == target_date.isoformat()
    assert body["data"]["coverage_status"] == expected_coverage

    actual_query = mock_service.get_forecast.call_args.args[0]
    assert actual_query.target_date == target_date

    if expected_coverage == "available":
        assert (
            body["data"]["selected_day"]["forecast_date"]
            == target_date.isoformat()
        )
    else:
        assert body["data"]["selected_day"] is None
        assert any(
            target_date.isoformat() in item and "没有" in item
            for item in body["meta"]["warnings"]
        )


def test_missing_forecast_fields_have_warning(
    client: TestClient,
    mock_service: Mock,
    forecast_data: WeatherForecast,
) -> None:
    """缺失字段保留 null，并提供带日期的提醒。"""

    data = forecast_data.model_dump()
    data["days"][0]["day_temperature_c"] = None

    missing_forecast = WeatherForecast(**data)
    target_date = date(2026, 10, 13)

    mock_service.get_forecast.return_value = ForecastLookupResult(
        forecast=missing_forecast,
        target_date=target_date,
        coverage_status="available",
        selected_day=missing_forecast.find_day(target_date),
    )

    response = client.get(
        "/api/v1/weather/forecast",
        params={
            "city": "海淀区",
            "target_date": target_date.isoformat(),
        },
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert (
        body["data"]["selected_day"]["day_temperature_c"]
        is None
    )

    assert any(
        "2026-10-13" in item and "白天温度" in item
        for item in body["meta"]["warnings"]
    )


@pytest.mark.parametrize(
    "params, expected_field, expected_reason",
    [
        ({}, "city", "required"),
        ({"city": ""}, "city", "text_too_short"),
        ({"city": "   "}, "city", "text_too_short"),
        ({"city": "测" * 51}, "city", "text_too_long"),
        (
            {"city": "海淀区", "province_adcode": "110108"},
            "province_adcode",
            "invalid_value",
        ),
        (
            {"city": "海淀区", "target_date": "2026-02-30"},
            "target_date",
            "invalid_value",
        ),
        (
            {"city": "海淀区", "target_date": "20261013"},
            "target_date",
            "invalid_value",
        ),
        (
            {
                "city": "海淀区",
                "target_date": "2026-10-13T00:00:00",
            },
            "target_date",
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
    """非法参数返回统一 422，并阻止业务执行。"""

    response = client.get(
        "/api/v1/weather/forecast",
        params=params,
    )

    assert response.status_code == 422, response.text

    body = response.json()

    assert set(body) == {"error", "meta"}
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"] == [
        {
            "field": expected_field,
            "reason": expected_reason,
        }
    ]

    mock_service.get_forecast.assert_not_called()


@pytest.mark.parametrize(
    "error_code, expected_status",
    [
        ("district_not_found", 404),
        ("district_ambiguous", 422),
        ("forecast_not_available", 503),
        ("amap_not_configured", 503),
        ("amap_timeout", 504),
        ("amap_connection_error", 502),
        ("amap_response_invalid", 502),
        ("amap_forecast_invalid", 502),
        ("amap_forecast_region_mismatch", 502),
        ("amap_business_error", 502),
    ],
)
def test_forecast_errors_are_mapped(
    client: TestClient,
    mock_service: Mock,
    error_code: str,
    expected_status: int,
) -> None:
    """预报错误使用统一响应，且不暴露内部异常文本。"""

    internal_message = "模拟内部文本，含 test-secret。"

    mock_service.get_forecast.side_effect = WeatherServiceError(
        code=error_code,
        message=internal_message,
    )

    response = client.get(
        "/api/v1/weather/forecast",
        params={"city": "海淀区"},
    )

    assert response.status_code == expected_status, response.text

    body = response.json()

    assert set(body) == {"error", "meta"}
    assert body["error"]["code"] == error_code
    assert body["error"]["details"] == []
    assert internal_message not in response.text
    assert "test-secret" not in response.text


@pytest.mark.parametrize(
    "target_date, stage, expected_status, expected_coverage",
    [
        (None, "success", 200, "not_requested"),
        (date(2026, 10, 13), "success", 200, "available"),
        (date(2026, 10, 14), "success", 200, "unavailable"),
        (date(2099, 1, 1), "success", 200, "unavailable"),
        (date(2026, 10, 13), "district_failure", 422, None),
        (date(2026, 10, 13), "forecast_failure", 504, None),
    ],
)
def test_real_service_flow_and_cleanup(
    client: TestClient,
    forecast_data: WeatherForecast,
    monkeypatch: pytest.MonkeyPatch,
    target_date: date | None,
    stage: str,
    expected_status: int,
    expected_coverage: str | None,
) -> None:
    """执行真实服务，检查日期选择、调用顺序和客户端关闭。"""

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

    amap_client.get_forecast.return_value = forecast_data

    if stage == "district_failure":
        amap_client.resolve_district.side_effect = AmapError(
            code="district_ambiguous",
            message="内部模拟地区错误。",
        )
    elif stage == "forecast_failure":
        amap_client.get_forecast.side_effect = AmapError(
            code="amap_timeout",
            message="内部模拟预报超时。",
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

    params = {
        "city": "海淀区",
        "province_adcode": "110000",
    }

    if target_date is not None:
        params["target_date"] = target_date.isoformat()

    response = client.get(
        "/api/v1/weather/forecast",
        params=params,
    )

    assert response.status_code == expected_status, response.text

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

    if stage != "district_failure":
        expected_calls.append(
            call.get_forecast(
                WeatherQuery(adcode="110108")
            )
        )

    expected_calls.append(call.close())
    assert amap_client.method_calls == expected_calls

    if stage == "success":
        body = response.json()
        assert body["data"]["coverage_status"] == expected_coverage

        if expected_coverage == "available":
            assert (
                body["data"]["selected_day"]["forecast_date"]
                == target_date.isoformat()
            )
        else:
            assert body["data"]["selected_day"] is None


def test_constructor_failure_is_mapped(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """客户端初始化失败时仍返回天气业务错误。"""

    constructor = Mock(
        side_effect=AmapError(
            code="amap_not_configured",
            message="内部初始化错误，含 test-secret。",
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
        "/api/v1/weather/forecast",
        params={"city": "海淀区"},
    )

    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "amap_not_configured"
    assert "test-secret" not in response.text
    constructor.assert_called_once()


def test_invalid_date_does_not_create_client(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """日期验证失败时，不应创建高德客户端。"""

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
        "/api/v1/weather/forecast",
        params={
            "city": "海淀区",
            "target_date": "2026-02-30",
        },
    )

    assert response.status_code == 422, response.text
    constructor.assert_not_called()


@pytest.mark.parametrize(
    "target_date, coverage_status, selected_index",
    [
        (None, "available", None),
        (date(2026, 10, 14), "available", 0),
        (date(2026, 10, 13), "unavailable", None),
    ],
)
def test_result_requires_consistent_selection(
    forecast_data: WeatherForecast,
    target_date: date | None,
    coverage_status: str,
    selected_index: int | None,
) -> None:
    """错误状态组合或借用其他日期记录应被结果模型拒绝。"""

    selected_day = (
        forecast_data.days[selected_index]
        if selected_index is not None
        else None
    )

    with pytest.raises(ValidationError):
        ForecastLookupResult(
            forecast=forecast_data,
            target_date=target_date,
            coverage_status=coverage_status,
            selected_day=selected_day,
        )