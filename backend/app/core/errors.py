"""将请求校验错误转换为项目统一的 API 错误响应。"""

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.models.common import (
    ApiError,
    ErrorDetail,
    ErrorResponse,
)


# 左侧是 Pydantic 或自定义验证器提供的错误类型。
# 右侧是本项目对外提供的错误原因标识。
#
# 通过这层映射，前端可以依赖项目自己的错误契约。
ERROR_REASON_MAP: dict[str, str] = {
    "missing": "required",
    "extra_forbidden": "unexpected_field",
    "int_type": "integer_required",
    "greater_than": "value_too_small",
    "greater_than_equal": "value_too_small",
    "less_than": "value_too_large",
    "less_than_equal": "value_too_large",
    "string_too_short": "text_too_short",
    "string_too_long": "text_too_long",
    "literal_error": "invalid_choice",
    "json_invalid": "invalid_json",
    "date_order_invalid": "date_order_invalid",
    "trip_too_long": "trip_too_long",
    "room_count_exceeds_travelers": "room_count_exceeds_travelers",
}


def _get_error_field(error: dict[str, Any]) -> str:
    """从一条内部校验错误中提取对外显示的字段位置。"""

    # JSON 语法错误属于整个请求体。
    # 框架提供的位置可能包含字符偏移量，
    # 这里统一表达为 body，方便调用方理解。
    if error["type"] == "json_invalid":
        return "body"

    # 自定义跨字段验证器通过 ctx 提供对应字段。
    # 例如 {"field": "end_date"}。
    context = error.get("ctx") or {}
    custom_field = context.get("field")

    if isinstance(custom_field, str) and custom_field:
        return custom_field

    # 普通字段错误的位置通常类似：
    # ("body", "travelers")
    #
    # 先转换为列表，方便移除最前面的来源标识。
    location = list(error.get("loc", ()))

    if location and location[0] in (
        "body",
        "query",
        "path",
        "header",
        "cookie",
    ):
        source = location.pop(0)
    else:
        source = "body"

    # ("body", "travelers") 最终转换为 "travelers"。
    # 嵌套字段可以转换为 "preferences.0" 这样的路径。
    # 如果没有具体字段，就使用来源名称，例如 "body"。
    return ".".join(str(part) for part in location) or source


def request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """处理请求输入校验失败，返回统一的 422 JSON 响应。"""

    details: list[ErrorDetail] = []

    # 一个请求可能同时存在多个字段错误，
    # 因此逐条转换并保留完整的错误列表。
    for error in exc.errors():
        reason = ERROR_REASON_MAP.get(
            error["type"],
            "invalid_value",
        )

        details.append(
            ErrorDetail(
                field=_get_error_field(error),
                reason=reason,
            )
        )

    # 只使用我们明确选择的字段组装响应。
    # 原始输入值、内部异常对象等信息不进入接口响应。
    response = ErrorResponse(
        error=ApiError(
            code="VALIDATION_ERROR",
            message="请求参数校验失败",
            details=details,
        )
    )

    # JSONResponse 接收可转换为 JSON 的内容。
    # mode="json" 会把 UUID 等对象转换为 JSON 兼容类型，
    # 返回值仍然是字典。
    return JSONResponse(
        status_code=422,
        content=response.model_dump(mode="json"),
    )
