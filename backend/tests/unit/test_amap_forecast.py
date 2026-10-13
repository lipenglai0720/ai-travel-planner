"""测试预报数据转换、日期集合校验和日期覆盖检查。"""

from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.clients.amap import AmapClient, AmapError
from app.models.weather import WeatherQuery
from app.models.weather_forecast import WeatherForecast


Handler = Callable[[httpx.Request], httpx.Response]
ClientFactory = Callable[[Handler], AmapClient]


def make_day(date_value: str) -> dict[str, Any]:
    """创建一条模拟逐日预报。"""

    return {
        "date": date_value,
        "dayweather": "晴",
        "nightweather": "多云",
        "daytemp": "24.5",
        "nighttemp": "18",
        "daywind": "北",
        "nightwind": "北",
        "daypower": "1-3",
        "nightpower": "≤3",
    }


@pytest.fixture
def valid_payload() -> dict[str, Any]:
    """提供逆序的模拟日期，检查客户端是否正确排序。"""

    return {
        "status": "1",
        "infocode": "10000",
        "count": "1",
        "forecasts": [
            {
                "province": "北京",
                "city": "北京",
                "adcode": "110000",
                "reporttime": "2026-10-12 08:00:00",
                "casts": [
                    make_day("2026-10-13"),
                    make_day("2026-10-12"),
                ],
            }
        ],
    }


@pytest.fixture
def client_factory() -> Iterator[ClientFactory]:
    """创建本地模拟客户端，并在结束后关闭。"""

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


def test_returns_normalized_sorted_forecast(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """合法响应转换为预报模型，并发送预报查询参数。"""

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=valid_payload)

    client = client_factory(handler)

    result = client.get_forecast(
        WeatherQuery(adcode="110000")
    )

    assert isinstance(result, WeatherForecast)
    assert result.adcode == "110000"
    assert result.source == "amap"
    assert result.data_kind == "forecast"

    assert result.reported_at == datetime(
        2026, 10, 12, 8, 0, 0
    )
    assert result.reported_at.tzinfo is None
    assert result.queried_at.utcoffset() == timedelta(0)

    assert [
        item.forecast_date for item in result.days
    ] == [
        date(2026, 10, 12),
        date(2026, 10, 13),
    ]

    first_day = result.days[0]

    assert first_day.day_weather == "晴"
    assert first_day.night_weather == "多云"
    assert first_day.day_temperature_c == pytest.approx(24.5)
    assert first_day.night_temperature_c == pytest.approx(18.0)
    assert first_day.day_wind_power == "1-3"

    assert len(requests) == 1

    request = requests[0]

    assert request.method == "GET"
    assert request.url.path == "/v3/weather/weatherInfo"
    assert request.url.params["city"] == "110000"
    assert request.url.params["extensions"] == "all"
    assert request.url.params["output"] == "JSON"


@pytest.mark.parametrize(
    "missing",
    [None, "", "   ", []],
)
def test_missing_optional_fields_become_none(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
    missing: object,
) -> None:
    """可选数值、风向和风力缺失时保留 None。"""

    raw_day = valid_payload["forecasts"][0]["casts"][0]

    for field in [
        "daytemp",
        "nighttemp",
        "daywind",
        "nightwind",
        "daypower",
        "nightpower",
    ]:
        raw_day[field] = missing

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    result = client.get_forecast(
        WeatherQuery(adcode="110000")
    )

    selected = result.find_day(date(2026, 10, 13))

    assert selected is not None
    assert selected.day_temperature_c is None
    assert selected.night_temperature_c is None
    assert selected.day_wind_direction is None
    assert selected.night_wind_direction is None
    assert selected.day_wind_power is None
    assert selected.night_wind_power is None


@pytest.mark.parametrize(
    "changes",
    [
        {"date": "2026-02-30"},
        {"date": "20261012"},
        {"date": None},
        {"daytemp": "abc"},
        {"nighttemp": "nan"},
        {"daytemp": "inf"},
        {"daytemp": True},
        {"dayweather": "   "},
        {"nightweather": None},
        {"daypower": ["1", "3"]},
    ],
)
def test_invalid_day_fields_are_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
    changes: dict[str, object],
) -> None:
    """日期、必要描述或可选字段损坏时拒绝整次结果。"""

    valid_payload["forecasts"][0]["casts"][0].update(changes)

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.get_forecast(
            WeatherQuery(adcode="110000")
        )

    assert caught.value.code == "amap_forecast_invalid"


def test_duplicate_dates_are_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """同一天出现两条预报时，集合验证器应拒绝结果。"""

    raw_days = valid_payload["forecasts"][0]["casts"]
    raw_days[1]["date"] = raw_days[0]["date"]

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.get_forecast(
            WeatherQuery(adcode="110000")
        )

    assert caught.value.code == "amap_forecast_invalid"


def test_region_mismatch_is_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """其他地区的预报不能作为目标地区数据使用。"""

    valid_payload["forecasts"][0]["adcode"] = "110108"

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.get_forecast(
            WeatherQuery(adcode="110000")
        )

    assert caught.value.code == "amap_forecast_region_mismatch"


@pytest.mark.parametrize(
    "changes",
    [
        {"reporttime": "invalid"},
        {"adcode": 110000},
        {"city": "   "},
    ],
)
def test_invalid_forecast_header_is_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
    changes: dict[str, object],
) -> None:
    """地区信息和发布时间也必须经过校验。"""

    valid_payload["forecasts"][0].update(changes)

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.get_forecast(
            WeatherQuery(adcode="110000")
        )

    assert caught.value.code == "amap_forecast_invalid"


@pytest.mark.parametrize(
    "empty_level",
    ["forecasts", "casts"],
)
def test_empty_forecast_is_unavailable(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
    empty_level: str,
) -> None:
    """没有地区预报或没有逐日记录时，报告数据不可用。"""

    if empty_level == "forecasts":
        valid_payload["forecasts"] = []
    else:
        valid_payload["forecasts"][0]["casts"] = []

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.get_forecast(
            WeatherQuery(adcode="110000")
        )

    assert caught.value.code == "forecast_not_available"


@pytest.mark.parametrize(
    "payload, expected_code",
    [
        (
            {"status": "1", "forecasts": {}},
            "amap_response_invalid",
        ),
        (
            {"status": "1", "forecasts": [None]},
            "amap_forecast_invalid",
        ),
        (
            {"status": "1", "forecasts": [{"casts": None}]},
            "amap_forecast_invalid",
        ),
        (
            {"status": "1", "forecasts": [{"casts": {}}]},
            "amap_forecast_invalid",
        ),
        (
            {"status": "1", "forecasts": [{}, {}]},
            "amap_forecast_invalid",
        ),
    ],
)
def test_invalid_structure_is_rejected(
    client_factory: ClientFactory,
    payload: dict[str, Any],
    expected_code: str,
) -> None:
    """错误的列表、对象或记录数量应被拒绝。"""

    client = client_factory(
        lambda request: httpx.Response(200, json=payload)
    )

    with pytest.raises(AmapError) as caught:
        client.get_forecast(
            WeatherQuery(adcode="110000")
        )

    assert caught.value.code == expected_code


def test_business_failure_uses_shared_handling(
    client_factory: ClientFactory,
) -> None:
    """预报查询也应使用共用的高德业务状态检查。"""

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
        client.get_forecast(
            WeatherQuery(adcode="110000")
        )

    assert caught.value.code == "amap_business_error"
    assert caught.value.provider_code == "10001"
    assert "test-key" not in str(caught.value)


@pytest.mark.parametrize(
    "target_date, expected_available",
    [
        (date(2026, 10, 12), True),
        (date(2026, 10, 13), False),
        (date(2030, 1, 1), False),
    ],
)
def test_find_day_checks_actual_dates(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
    target_date: date,
    expected_available: bool,
) -> None:
    """覆盖判断必须识别日期缺口，不能只看首尾范围。"""

    # 实际返回日期变成 10 月 12 日和 10 月 14 日。
    valid_payload["forecasts"][0]["casts"][0]["date"] = (
        "2026-10-14"
    )

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    result = client.get_forecast(
        WeatherQuery(adcode="110000")
    )

    selected = result.find_day(target_date)

    assert (selected is not None) == expected_available

    if selected is not None:
        assert selected.forecast_date == target_date