"""整合旅行草案与天气，生成可降级的旅行规划结果。"""

from app.models.trip import (
    PlannedDay,
    TripPlan,
    TripPlanRequest,
    TripRequest,
    WeatherFetchStatus,
)
from app.models.weather import (
    DailyWeatherItem,
    ForecastRangeQuery,
    TripWeatherResult,
)
from app.services.trip_generation_service import TripGenerationService
from app.services.weather_service import WeatherService, WeatherServiceError


class TripPlanningService:
    """按固定顺序编排草案生成、天气查询和结果合并。"""

    def __init__(
        self,
        generation_service: TripGenerationService,
        weather_service: WeatherService,
    ) -> None:
        """接收已有服务；构造函数本身不发起网络请求。"""
        self._generation_service = generation_service
        self._weather_service = weather_service

    def create_plan(self, request: TripPlanRequest) -> TripPlan:
        """根据旅行需求生成规划。

        参数：
            request：已经通过字段与跨字段校验的规划请求。

        返回：
            TripPlan：每日活动、天气记录、查询状态和覆盖结果。

        异常：
            TripGenerationError：草案生成失败时继续向上抛出，
            由已有异常处理器转换为 502 或 504 响应。
            已识别的天气业务失败在本方法内降级处理。
        """

        # 只提取基础旅行字段，重新构造真正的 TripRequest。
        # include_weather、province_adcode 是服务控制参数，
        # 不应被已有提示词的 model_dump() 一起发送给大模型。
        trip_request = TripRequest.model_validate(
            request.model_dump(
                include=set(TripRequest.model_fields),
            ),
        )

        # 先完成草案生成与原有的结构、日期一致性校验。
        # 草案是核心结果；失败时不继续查询天气。
        draft = self._generation_service.generate_draft(trip_request)

        weather_status: WeatherFetchStatus = "skipped"
        weather_error_code: str | None = None
        weather_result: TripWeatherResult | None = None
        unavailable_suggestion = (
            "本次未开启天气查询，请在出发前另行确认天气。"
        )

        if request.include_weather:
            try:
                weather_result = self._weather_service.get_forecast_range(
                    ForecastRangeQuery(
                        city=request.destination,
                        province_adcode=request.province_adcode,
                        start_date=request.start_date,
                        end_date=request.end_date,
                    ),
                )

                # loaded 只表示查询成功；具体日期可能仍缺少预报。
                weather_status = "loaded"

            except WeatherServiceError as exc:
                # 天气属于可选增强能力。已识别的业务失败保留草案，
                # 只记录稳定错误标识，不返回异常原文或上游请求信息。
                weather_status = "failed"
                weather_error_code = exc.code
                unavailable_suggestion = (
                    "本次天气查询暂不可用，请在出发前重新确认天气。"
                )

        # 建立“日期 -> 每日天气”映射，按日期关联活动与天气。
        # 已有天气服务会为整个旅行区间逐日生成记录，
        # 没有预报的日期也有 availability="unavailable" 的条目。
        weather_by_date = (
            {
                item.travel_date: item
                for item in weather_result.daily_weather
            }
            if weather_result is not None
            else {}
        )

        planned_days: list[PlannedDay] = []

        for day in draft.days:
            if weather_result is None:
                # 查询跳过或失败时，明确表示没有预报。
                # 建议来自项目规则，不填入虚构天气。
                daily_weather = DailyWeatherItem(
                    travel_date=day.date,
                    availability="unavailable",
                    forecast=None,
                    suggestions=[unavailable_suggestion],
                )
            else:
                # 按日期取出已校验的数据，保留来源与缺失状态。
                daily_weather = weather_by_date[day.date]

            planned_days.append(
                PlannedDay(
                    date=day.date,
                    theme=day.theme,
                    activities=day.activities,
                    weather=daily_weather,
                ),
            )

        # 使用模型正常构造路径，继续执行日期对应和天气状态校验。
        return TripPlan(
            title=draft.title,
            summary=draft.summary,
            days=planned_days,
            weather_status=weather_status,
            weather_coverage=(
                weather_result.coverage
                if weather_result is not None
                else None
            ),
            weather_error_code=weather_error_code,
        )