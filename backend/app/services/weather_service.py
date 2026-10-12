"""编排行政区解析和天气查询，并管理客户端生命周期。"""

from pydantic import SecretStr

from app.clients.amap import AmapClient, AmapError
from app.models.district import DistrictQuery
from app.models.weather import (
    CurrentWeather,
    WeatherLookupQuery,
    WeatherQuery,
)


class WeatherServiceError(RuntimeError):
    """天气服务能够明确识别的业务失败。"""

    def __init__(
        self,
        code: str,
        message: str = "天气查询失败。",
    ) -> None:
        """保存稳定错误标识与内部说明。

        API 层根据 code 选择固定的对外提示，
        不直接返回这里的异常文本。
        """
        super().__init__(message)
        self.code = code


class WeatherService:
    """提供按城市或区县查询实况天气的业务流程。"""

    def __init__(
        self,
        api_key: SecretStr | None,
        timeout_seconds: float = 10.0,
    ) -> None:
        """保存配置，暂不创建客户端或发送请求。"""
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def get_current_weather(
        self,
        query: WeatherLookupQuery,
    ) -> CurrentWeather:
        """解析地区，再查询该地区的实况天气。

        参数：
            query：
                已经过校验的城市或区县查询条件。

        返回值：
            CurrentWeather：
                高德客户端校验后的实况天气记录。

        异常：
            WeatherServiceError：
                由已识别的高德客户端异常转换而来。
        """

        # 初始化失败时，这个变量仍为 None。
        # finally 只关闭成功创建的客户端。
        client: AmapClient | None = None

        try:
            client = AmapClient(
                api_key=self._api_key,
                timeout_seconds=self._timeout_seconds,
            )

            district = client.resolve_district(
                DistrictQuery(
                    keyword=query.city,
                    province_adcode=query.province_adcode,
                )
            )

            # adcode 必须来自本次行政区解析结果。
            weather_query = WeatherQuery(
                adcode=district.region.adcode,
            )

            return client.get_current_weather(
                weather_query
            )

        except AmapError as exc:
            # 转换成天气业务异常。
            # 不把高德原始异常文本带入 API 响应。
            raise WeatherServiceError(
                code=exc.code,
            ) from None

        finally:
            if client is not None:
                client.close()