"""编排一次 POI 查询，并管理高德客户端生命周期。"""

from pydantic import SecretStr

from app.clients.amap import AmapClient
from app.models.location import (
    PoiSearchQuery,
    PoiSearchResult,
)


class PoiService:
    """地点查询服务。"""

    def __init__(
        self,
        api_key: SecretStr | None,
        timeout_seconds: float = 10.0,
    ) -> None:
        """保存配置，暂不创建 HTTP 客户端或发送请求。"""

        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def search(
        self,
        query: PoiSearchQuery,
    ) -> PoiSearchResult:
        """执行查询，返回业务结果，并保证关闭客户端。

        参数：
            query:
                已经校验的城市和搜索关键词。

        返回值：
            PoiSearchResult:
                高德客户端转换和校验后的查询结果。

        异常：
            AmapError:
                由高德客户端抛出，交给 API 异常处理器处理。
        """

        # 只有真正执行查询业务时，才创建客户端。
        client = AmapClient(
            api_key=self._api_key,
            timeout_seconds=self._timeout_seconds,
        )

        try:
            return client.search_pois(query)
        finally:
            # 成功返回或查询失败时，都关闭已创建的客户端。
            client.close()
