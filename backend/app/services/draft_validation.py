"""校验旅行草案是否符合原始旅行需求。"""

from datetime import timedelta

from app.models.requests import TripRequest
from app.models.trip_draft import TripDraft


class DraftRequestMismatchError(ValueError):
    """旅行草案与原始需求不一致时抛出的业务异常。"""

    def __init__(self, code: str, message: str) -> None:
        """
        创建业务异常。

        参数：
            code:
                稳定的错误标识，供调用方判断具体失败原因。
                它不是 HTTP 状态码。

            message:
                人可以直接阅读的错误说明。
        """
        # 让父类保存错误说明。
        # 后面调用 str(exc) 时，就能获得这个 message。
        super().__init__(message)

        # 保存机器可识别的错误代码。
        self.code = code


def validate_draft_matches_request(
    trip_request: TripRequest,
    draft: TripDraft,
) -> None:
    """
    校验草案的天数和每日日期是否符合原始需求。

    参数：
        trip_request:
            已经通过 Pydantic 校验的旅行需求对象。

        draft:
            已经通过 Pydantic 校验的旅行草案对象。

    返回值：
        校验通过时返回 None。

    异常：
        DraftRequestMismatchError:
            草案天数或日期与需求不一致。

    注意：
        本函数只读取两个对象，不修改请求或草案。
    """
    # 原始需求是判断旅行天数的依据。
    # day_count 已经包含开始日期和结束日期。
    expected_day_count = trip_request.day_count
    actual_day_count = len(draft.days)

    # 第一层：检查草案是否返回了正确的天数。
    if actual_day_count != expected_day_count:
        raise DraftRequestMismatchError(
            code="draft_day_count_mismatch",
            message=(
                f"旅行需求要求 {expected_day_count} 天，"
                f"草案返回 {actual_day_count} 天。"
            ),
        )

    # 根据原始需求，生成完整的预期日期列表。
    #
    # 例如：
    # start_date = 2026-11-01，expected_day_count = 3
    # 得到：
    # [2026-11-01, 2026-11-02, 2026-11-03]
    expected_dates = [
        trip_request.start_date + timedelta(days=offset)
        for offset in range(expected_day_count)
    ]

    # 从草案中提取实际日期。
    actual_dates = [day.date for day in draft.days]

    # 第二层：逐项比较日期及顺序。
    # 这样可以识别“天数正确，但日期整体偏移”的情况。
    if actual_dates != expected_dates:
        raise DraftRequestMismatchError(
            code="draft_date_range_mismatch",
            message=(
                f"请求日期为 {trip_request.start_date} "
                f"至 {trip_request.end_date}，"
                f"草案日期为 {draft.days[0].date} "
                f"至 {draft.days[-1].date}。"
            ),
        )

    # 校验函数通过正常返回表示成功。
    return None