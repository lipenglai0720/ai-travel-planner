"""公共模型与规则：统一响应、错误、日期计算和 UTC 查询时间。"""

from datetime import date, datetime, timezone
from typing import Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# 旅行与天气区间共用的规则集中在此，避免业务模块相互导入。
MAX_TRIP_DAYS = 7


def calculate_day_count(start_date: date, end_date: date) -> int:
    """计算包含开始日和结束日的旅行天数。

    参数：
        start_date：已经解析完成的开始日期。
        end_date：已经解析完成的结束日期。

    返回：
        包含首尾两天的旅行天数。

    异常：
        结束日期早于开始日期时，抛出 ValueError。
    """

    # 必须先检查日期顺序，避免产生 0 天或负数天数。
    if end_date < start_date:
        raise ValueError("结束日期不能早于开始日期")

    # 两个 date 对象相减，得到 timedelta。
    # .days 取得相差的天数；加 1 后包含开始日和结束日。
    return (end_date - start_date).days + 1


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(timezone.utc)


class ResponseMeta(BaseModel):
    """响应元信息，用于标识本次请求并携带额外提醒。"""

    # 创建 ResponseMeta 对象时调用 uuid4，生成随机标识。
    # 输出为 JSON 时，UUID 会被转换为字符串。
    request_id: UUID = Field(
        default_factory=uuid4,
        description="本次请求的标识。",
    )

    # 每个响应独立创建自己的提醒列表。
    warnings: list[str] = Field(
        default_factory=list,
        description="与本次业务结果有关的提醒。",
    )


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一成功响应。

    T 表示具体的业务数据类型，例如 TripDraft 或 CurrentWeather。
    data 和 meta 都保持必填；每个接口通过类型别名绑定自己的数据模型。
    这里只复用响应外层，不改变各业务模型的校验配置。
    """

    data: T = Field(
        description="经过业务模型校验的响应数据。",
    )

    meta: ResponseMeta = Field(
        description="响应标识和业务提醒。",
    )


class ErrorDetail(BaseModel):
    """描述一个具体的输入错误。"""

    field: str = Field(
        min_length=1,
        description="发生错误的字段，例如 travelers 或 end_date。",
    )

    reason: str = Field(
        min_length=1,
        description="供程序判断的错误原因，例如 integer_required。",
    )


class ApiError(BaseModel):
    """描述一次 API 错误。"""

    code: str = Field(
        min_length=1,
        description="错误大类，例如 VALIDATION_ERROR。",
    )

    message: str = Field(
        min_length=1,
        description="供用户阅读的总体错误说明。",
    )

    details: list[ErrorDetail] = Field(
        default_factory=list,
        description="具体的错误字段和原因。",
    )


class ErrorResponse(BaseModel):
    """错误响应的最外层结构。"""

    error: ApiError = Field(
        description="本次请求的错误信息。",
    )

    meta: ResponseMeta = Field(
        default_factory=ResponseMeta,
        description="响应标识和提示信息。",
    )
