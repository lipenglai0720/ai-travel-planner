"""公共响应模型：定义业务响应中的元信息。"""

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


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