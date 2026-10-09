"""旅行业务服务：根据已经校验的请求生成需求摘要。"""

from app.models.requests import TripRequest
from app.models.trip import TripPreview


class TripService:
    """组织旅行相关的业务处理。"""

    def preview(self, request: TripRequest) -> TripPreview:
        """将经过校验的请求转换为旅行需求摘要。

        参数：
            request：已经完成字段和跨字段校验的旅行请求。

        返回：
            TripPreview：包含日期、人数、房间数和预算的摘要。
        """

        return TripPreview(
            destination=request.destination,
            start_date=request.start_date,
            end_date=request.end_date,

            # 读取上一小步定义的计算属性。
            # 天数由程序根据日期决定。
            day_count=request.day_count,

            travelers=request.travelers,
            room_count=request.room_count,
            requested_budget_cents=request.budget_cents,
            currency="CNY",
        )