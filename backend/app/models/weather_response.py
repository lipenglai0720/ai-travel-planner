"""天气接口的成功响应模型。"""

from pydantic import BaseModel, Field

from app.models.common import ResponseMeta
from app.models.forecast_lookup import ForecastLookupResult
from app.models.weather import CurrentWeather
from app.models.forecast_range import TripWeatherResult

class WeatherCurrentResponse(BaseModel):
    """实况天气接口的成功响应。"""

    data: CurrentWeather = Field(
        description="经过转换和校验的供应商实况天气。",
    )

    meta: ResponseMeta = Field(
        description="响应标识和业务提醒。",
    )


class WeatherForecastResponse(BaseModel):
    """短期预报接口的成功响应。"""

    data: ForecastLookupResult = Field(
        description="完整预报及目标日期检查结果。",
    )

    meta: ResponseMeta = Field(
        description="响应标识和业务提醒。",
    )

class WeatherForecastRangeResponse(BaseModel):
    """旅行区间天气接口的成功响应。"""

    data: TripWeatherResult = Field(
        description="旅行日期覆盖、每日天气与出行建议。",
    )

    meta: ResponseMeta = Field(
        description="响应标识及数据限制提醒。",
    )