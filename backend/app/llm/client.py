"""创建用于旅行草案生成的 DeepSeek 聊天模型。"""

from langchain_deepseek import ChatDeepSeek

from app.core.config import Settings


class LLMConfigurationError(ValueError):
    """大模型调用所需配置缺失时抛出的异常。"""


def create_trip_chat_model(settings: Settings) -> ChatDeepSeek:
    """
    根据配置创建旅行草案生成模型。

    参数：
        settings:
            项目已有的配置对象，提供密钥、地址、模型名和超时配置。

    返回值：
        配置好的 ChatDeepSeek 对象。

    异常：
        LLMConfigurationError:
            没有配置有效的非空 API Key。

    注意：
        创建模型对象只完成客户端初始化。
        真正调用云端模型发生在 invoke() 执行时。
    """
    if settings.llm_api_key is None:
        raise LLMConfigurationError(
            "未配置 LLM_API_KEY，请检查 backend/.env。",
        )

    # SecretStr 默认隐藏密钥。
    # 只有创建客户端时，才取出真实值。
    api_key = settings.llm_api_key.get_secret_value().strip()

    if not api_key:
        raise LLMConfigurationError(
            "LLM_API_KEY 不能为空，请检查 backend/.env。",
        )

    return ChatDeepSeek(
        api_key=api_key,
        base_url=str(settings.llm_base_url).rstrip("/"),
        model=settings.llm_model,

        # 使用较低温度，使输出相对集中。
        # 较低温度仍然不保证每次生成完全相同的内容。
        temperature=0.2,

        # 行程 JSON 比之前的连通性测试回复更长，
        # 因此提高输出上限。
        max_tokens=8192,

        # 沿用项目配置中的 HTTP 超时参数。
        timeout=settings.llm_timeout_seconds,

        # 先关闭 SDK 自动重试，便于观察单次调用的真实结果。
        max_retries=0,

        # 本步一次接收完整结果。
        streaming=False,

        # 明确使用 Chat Completions 调用方式。
        use_responses_api=False,

        # response_format 属于标准请求参数，
        # 通过 model_kwargs 配置 JSON 输出模式。
        model_kwargs={
            "response_format": {
                "type": "json_object",
            },
        },

        # thinking 是 DeepSeek 的专用参数。
        # 本步使用非思考模式生成草案。
        extra_body={
            "thinking": {
                "type": "disabled",
            },
        },
    )