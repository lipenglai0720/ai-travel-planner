"""调用大模型生成旅行草案，并执行完整的结果校验。"""

from json import JSONDecodeError

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
)
from pydantic import ValidationError

from app.models.requests import TripRequest
from app.models.trip_draft import TripDraft
from app.prompts.trip_prompt import build_trip_messages
from app.services.draft_validation import (
    DraftRequestMismatchError,
    validate_draft_matches_request,
)


class TripGenerationError(RuntimeError):
    """旅行草案生成过程中可以明确识别的失败。"""

    def __init__(self, code: str, message: str) -> None:
        """
        创建生成异常。

        参数：
            code:
                稳定的错误标识，供调用方区分失败原因。

            message:
                可以直接展示的错误说明。
                不包含 API Key、完整上游响应或原始模型输出。
        """
        super().__init__(message)
        self.code = code


class TripGenerationService:
    """编排一次旅行草案生成。"""

    def __init__(self, chat_model: BaseChatModel) -> None:
        """
        接收模型对象。

        正常运行时传入 ChatDeepSeek。
        自动化测试时可以传入具有相同调用方法的替身对象。
        """
        self._chat_model = chat_model

    def generate_draft(self, trip_request: TripRequest) -> TripDraft:
        """
        根据已经校验的旅行需求生成草案。

        参数：
            trip_request:
                已经通过 TripRequest 校验的旅行需求。

        返回值：
            同时通过草案模型校验和请求一致性校验的 TripDraft。

        异常：
            TripGenerationError:
                模型调用失败、响应不可用或生成结果不符合要求。
        """
        messages = build_trip_messages(trip_request)

        try:
            # 本步的云端请求发生在这里。
            reply = self._chat_model.invoke(messages)

        # APITimeoutError 是连接异常的一种，
        # 因此应在 APIConnectionError 之前处理。
        except APITimeoutError as exc:
            raise TripGenerationError(
                code="llm_timeout",
                message="模型请求超时，请检查网络或稍后重试。",
            ) from exc

        except APIConnectionError as exc:
            raise TripGenerationError(
                code="llm_connection_error",
                message="无法连接模型服务，请检查网络、代理和服务地址。",
            ) from exc

        except APIStatusError as exc:
            raise TripGenerationError(
                code="llm_http_error",
                message=(
                    f"模型服务返回 HTTP {exc.status_code}，"
                    "请根据状态码检查配置或服务状态。"
                ),
            ) from exc

        # 在当前 SDK 的 JSON 解析调用中，
        # 截断可能直接表现为异常，而不是返回一条 AIMessage。
        except LengthFinishReasonError as exc:
            raise TripGenerationError(
                code="llm_output_truncated",
                message="模型输出达到长度上限，不能使用被截断的草案。",
            ) from exc

        except ContentFilterFinishReasonError as exc:
            raise TripGenerationError(
                code="llm_response_incomplete",
                message="模型响应被内容过滤拒绝，本次结果不可用。",
            ) from exc

        except JSONDecodeError as exc:
            raise TripGenerationError(
                code="llm_response_invalid",
                message="模型服务返回了无法解析的响应。",
            ) from exc

        except APIError as exc:
            raise TripGenerationError(
                code="llm_sdk_error",
                message="模型调用发生 SDK 异常，本次结果不可用。",
            ) from exc

        # 第一层：检查模型返回的消息是否可用。
        if not isinstance(reply, AIMessage):
            raise TripGenerationError(
                code="llm_response_invalid",
                message="模型没有返回预期的 AIMessage。",
            )

        finish_reason = reply.response_metadata.get("finish_reason")

        if finish_reason == "length":
            raise TripGenerationError(
                code="llm_output_truncated",
                message="模型输出达到长度上限，不能使用被截断的草案。",
            )

        if finish_reason != "stop":
            raise TripGenerationError(
                code="llm_response_incomplete",
                message=(
                    "模型未正常结束："
                    f"finish_reason={finish_reason!r}。"
                ),
            )

        # .text 提取消息中的文本；strip() 去除首尾空白。
        draft_json = reply.text.strip()

        if not draft_json:
            raise TripGenerationError(
                code="llm_output_empty",
                message="模型返回了空内容，无法生成旅行草案。",
            )

        # 第二层：直接使用 JSON 校验路径。
        # 这样可以按 JSON 规则解析上一步的严格日期字段。
        try:
            draft = TripDraft.model_validate_json(draft_json)

        except ValidationError as exc:
            # 只展示第一个错误的字段位置和错误类型，
            # 帮助定位问题，同时避免打印完整模型输出。
            first_error = exc.errors(
                include_input=False,
                include_context=False,
            )[0]

            field_path = ".".join(
                str(part) for part in first_error["loc"]
            ) or "draft"

            raise TripGenerationError(
                code="llm_output_invalid",
                message=(
                    "模型返回的草案未通过校验："
                    f"{field_path}（{first_error['type']}）。"
                ),
            ) from exc

        # 第三层：检查草案是否满足原始旅行需求。
        try:
            validate_draft_matches_request(trip_request, draft)

        except DraftRequestMismatchError as exc:
            raise TripGenerationError(
                code=exc.code,
                message=str(exc),
            ) from exc

        return draft