"""定义 API 错误响应的数据结构。"""

from pydantic import BaseModel, Field

from app.models.common import ResponseMeta


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