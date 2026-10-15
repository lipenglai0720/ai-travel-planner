"""评估预报日期覆盖，并整理每日天气与出行建议。"""

from datetime import date, timedelta

from app.models.weather import (
    DailyWeatherItem,
    ForecastCoverageStatus,
    ForecastDateRange,
    ForecastDay,
    ForecastRangeResult,
    TripWeatherResult,
    WeatherForecast,
)


# 这两个温度阈值属于当前项目的提示规则。
HOT_DAY_THRESHOLD_C = 30.0
COLD_THRESHOLD_C = 10.0


def assess_forecast_coverage(
    forecast: WeatherForecast,
    date_range: ForecastDateRange,
) -> ForecastRangeResult:
    """根据实际预报记录检查旅行日期覆盖情况。"""

    forecast_dates = {
        item.forecast_date
        for item in forecast.days
    }

    covered_dates: list[date] = []
    missing_dates: list[date] = []

    for offset in range(date_range.day_count):
        travel_date = (
            date_range.start_date
            + timedelta(days=offset)
        )

        if travel_date in forecast_dates:
            covered_dates.append(travel_date)
        else:
            missing_dates.append(travel_date)

    coverage_status: ForecastCoverageStatus

    if not missing_dates:
        coverage_status = "full"
    elif not covered_dates:
        coverage_status = "none"
    else:
        coverage_status = "partial"

    return ForecastRangeResult(
        forecast=forecast,
        date_range=date_range,
        coverage_status=coverage_status,
        covered_dates=covered_dates,
        missing_dates=missing_dates,
    )


def _build_suggestions(
    day: ForecastDay | None,
) -> list[str]:
    """根据一条预报记录生成项目规则建议。"""

    if day is None:
        return [
            "该日暂无预报，可保留室内备选活动，"
            "并在出发前重新确认天气。"
        ]

    suggestions: list[str] = []

    # 同时检查白天和夜间的天气描述。
    weather_description = (
        f"{day.day_weather} {day.night_weather}"
    )

    if "雨" in weather_description:
        suggestions.append(
            "预报中包含降雨描述，建议携带雨具，"
            "并为户外活动准备室内备选。"
        )

    if "雪" in weather_description:
        suggestions.append(
            "预报中包含降雪描述，建议根据出发前的"
            "天气和交通信息调整户外活动安排。"
        )

    # 缺少温度时，不执行对应的温度规则。
    if (
        day.day_temperature_c is not None
        and day.day_temperature_c >= HOT_DAY_THRESHOLD_C
    ):
        suggestions.append(
            "白天预报温度较高，可优先把长时间"
            "户外活动安排在早晚。"
        )

    available_temperatures = [
        temperature
        for temperature in (
            day.day_temperature_c,
            day.night_temperature_c,
        )
        if temperature is not None
    ]

    if (
        available_temperatures
        and min(available_temperatures) <= COLD_THRESHOLD_C
    ):
        suggestions.append(
            "预报温度较低，建议根据自身需要准备保暖衣物。"
        )

    if not suggestions:
        suggestions.append(
            "建议在出发前复查天气，户外活动保留调整余地。"
        )

    return suggestions


def build_trip_weather(
    coverage: ForecastRangeResult,
) -> TripWeatherResult:
    """按旅行日期整理每日预报、缺失字段和出行建议。

    参数：
        coverage：已经完成的旅行日期区间覆盖结果。

    返回：
        保留覆盖信息，并包含每个旅行日期的天气结果。

    说明：
        天气记录直接取自可信预报模型；
        建议由项目规则生成；
        缺少预报的日期保留为 None。
    """

    daily_weather: list[DailyWeatherItem] = []

    for offset in range(coverage.date_range.day_count):
        travel_date = (
            coverage.date_range.start_date
            + timedelta(days=offset)
        )

        # 复用已有方法，寻找这个旅行日期对应的真实记录。
        selected_day = coverage.forecast.find_day(
            travel_date,
        )

        missing_fields: list[str] = []

        if selected_day is not None:
            for attribute, label in [
                ("day_temperature_c", "白天温度"),
                ("night_temperature_c", "夜间温度"),
                ("day_wind_direction", "白天风向"),
                ("night_wind_direction", "夜间风向"),
                ("day_wind_power", "白天风力"),
                ("night_wind_power", "夜间风力"),
            ]:
                if getattr(selected_day, attribute) is None:
                    missing_fields.append(label)

        daily_weather.append(
            DailyWeatherItem(
                travel_date=travel_date,
                availability=(
                    "available"
                    if selected_day is not None
                    else "unavailable"
                ),
                forecast=selected_day,
                suggestions=_build_suggestions(selected_day),
                missing_fields=missing_fields,
            )
        )

    return TripWeatherResult(
        coverage=coverage,
        daily_weather=daily_weather,
    )
