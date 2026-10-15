"""测试实况天气的数据转换、缺失值和异常处理。"""

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.clients.amap import AmapClient, AmapError
from app.models.weather import (
    CurrentWeather,
    WeatherQuery,
)


Handler = Callable[[httpx.Request], httpx.Response]
ClientFactory = Callable[[Handler], AmapClient]


@pytest.fixture
def valid_payload() -> dict[str, Any]:
    """提供一份独立的高德格式模拟天气响应。"""
    return {
        "status": "1",
        "infocode": "10000",
        "count": "1",
        "lives": [
            {
                "province": "北京",
                "city": "北京",
                "adcode": "110000",
                "weather": "晴",
                "temperature": "-2.5",
                "winddirection": "北",
                "windpower": "≤3",
                "humidity": "45",
                "reporttime": "2026-10-12 09:00:00",
            }
        ],
    }


@pytest.fixture
def client_factory() -> Iterator[ClientFactory]:
    """创建本地模拟客户端，并在测试结束后关闭。"""

    clients: list[AmapClient] = []

    def create_client(handler: Handler) -> AmapClient:
        client = AmapClient(
            api_key=SecretStr("test-key"),
            transport=httpx.MockTransport(handler),
        )
        clients.append(client)
        return client

    try:
        yield create_client
    finally:
        for client in clients:
            client.close()


def test_returns_normalized_current_weather(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """合法响应应转换为业务模型，并发送正确参数。"""

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=valid_payload)

    client = client_factory(handler)

    result = client.get_current_weather(
        WeatherQuery(adcode=" 110000 ")
    )

    assert isinstance(result, CurrentWeather)
    assert result.adcode == "110000"
    assert result.city == "北京"
    assert result.weather == "晴"
    assert result.temperature_c == pytest.approx(-2.5)
    assert result.humidity_percent == pytest.approx(45.0)
    assert result.wind_direction == "北"
    assert result.wind_power == "≤3"

    assert result.reported_at == datetime(
        2026, 10, 12, 9, 0, 0
    )
    assert result.reported_at.tzinfo is None
    assert result.reported_at_timezone == "not_provided"
    assert result.queried_at.utcoffset() == timedelta(0)
    assert result.source == "amap"
    assert result.data_kind == "current_conditions"

    assert len(requests) == 1

    request = requests[0]
    params = request.url.params

    assert request.method == "GET"
    assert request.url.host == "restapi.amap.com"
    assert request.url.path == "/v3/weather/weatherInfo"
    assert params["city"] == "110000"
    assert params["extensions"] == "base"
    assert params["output"] == "JSON"


def test_accepts_json_numbers(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """适配器也能处理正常的 JSON 数字。"""

    valid_payload["lives"][0]["temperature"] = 24.5
    valid_payload["lives"][0]["humidity"] = 40

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    result = client.get_current_weather(
        WeatherQuery(adcode="110000")
    )

    assert result.temperature_c == pytest.approx(24.5)
    assert result.humidity_percent == pytest.approx(40.0)


@pytest.mark.parametrize(
    "missing",
    [None, "", "   ", []],
)
def test_missing_optional_fields_become_none(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
    missing: object,
) -> None:
    """约定的缺失形式转换为 None，不填默认天气值。"""

    record = valid_payload["lives"][0]

    for field in [
        "temperature",
        "humidity",
        "winddirection",
        "windpower",
    ]:
        record[field] = missing

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    result = client.get_current_weather(
        WeatherQuery(adcode="110000")
    )

    assert result.temperature_c is None
    assert result.humidity_percent is None
    assert result.wind_direction is None
    assert result.wind_power is None


@pytest.mark.parametrize(
    "changes",
    [
        {"temperature": "abc"},
        {"temperature": "nan"},
        {"temperature": "inf"},
        {"temperature": True},
        {"humidity": "101"},
        {"humidity": "-1"},
        {"adcode": 110000},
        {"weather": "   "},
        {"windpower": ["1", "3"]},
        {"reporttime": "2026-02-30 09:00:00"},
        {"reporttime": "2026-10-12T09:00:00Z"},
    ],
)
def test_invalid_weather_fields_are_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
    changes: dict[str, object],
) -> None:
    """错误数值、字段类型或时间格式应明确报错。"""

    valid_payload["lives"][0].update(changes)

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.get_current_weather(
            WeatherQuery(adcode="110000")
        )

    assert caught.value.code == "amap_weather_invalid"


def test_region_mismatch_is_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """返回了其他地区的记录，不能作为目标地区天气使用。"""

    valid_payload["lives"][0]["adcode"] = "110108"

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.get_current_weather(
            WeatherQuery(adcode="110000")
        )

    assert (
        caught.value.code
        == "amap_weather_region_mismatch"
    )


@pytest.mark.parametrize(
    "bad_lives",
    [None, {}, "not-a-list"],
)
def test_invalid_lives_container_is_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
    bad_lives: object,
) -> None:
    """lives 必须是列表。"""

    valid_payload["lives"] = bad_lives

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.get_current_weather(
            WeatherQuery(adcode="110000")
        )

    assert caught.value.code == "amap_response_invalid"


def test_empty_weather_result_is_unavailable(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """没有实况记录时，应报告暂不可用。"""

    valid_payload["lives"] = []

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.get_current_weather(
            WeatherQuery(adcode="110000")
        )

    assert caught.value.code == "weather_not_available"


def test_multiple_records_are_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """意外返回多条记录时，不直接取第一条。"""

    valid_payload["lives"].append(
        valid_payload["lives"][0].copy()
    )

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.get_current_weather(
            WeatherQuery(adcode="110000")
        )

    assert caught.value.code == "amap_weather_invalid"


def test_invalid_record_is_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """列表中的天气记录必须是对象。"""

    valid_payload["lives"] = [None]

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.get_current_weather(
            WeatherQuery(adcode="110000")
        )

    assert caught.value.code == "amap_weather_invalid"


def test_business_failure_uses_shared_error_handling(
    client_factory: ClientFactory,
) -> None:
    """天气方法应沿用客户端的高德业务错误处理。"""

    client = client_factory(
        lambda request: httpx.Response(
            200,
            json={
                "status": "0",
                "infocode": "10001",
                "info": "INVALID_USER_KEY",
            },
        )
    )

    with pytest.raises(AmapError) as caught:
        client.get_current_weather(
            WeatherQuery(adcode="110000")
        )

    assert caught.value.code == "amap_business_error"
    assert caught.value.provider_code == "10001"
    assert "test-key" not in str(caught.value)


@pytest.mark.parametrize(
    "adcode",
    [
        "",
        "11000",
        110000,
        "１１００００",
    ],
)
def test_invalid_weather_query_is_rejected(
    adcode: object,
) -> None:
    """输入必须是六位 ASCII 数字字符串。"""

    with pytest.raises(ValidationError):
        WeatherQuery(adcode=adcode)
