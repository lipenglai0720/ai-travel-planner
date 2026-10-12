"""天气接口的成功响应模型。"""

from pydantic import BaseModel, Field

from app.models.common import ResponseMeta
from app.models.weather import CurrentWeather


class WeatherCurrentResponse(BaseModel):
    """实况天气接口的成功响应。"""

    data: CurrentWeather = Field(
        description="经过转换和校验的供应商实况天气。",
    )

    meta: ResponseMeta = Field(
        description="响应标识和业务提醒。",
    )