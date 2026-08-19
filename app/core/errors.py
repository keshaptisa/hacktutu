"""Application error types.

Every error carries a *user-facing* message in Russian. The API layer never
leaks a stack trace: it maps these to clean JSON payloads and logs the details
server-side.
"""

from __future__ import annotations


class EscapeError(Exception):
    """Base class for everything the product raises on purpose."""

    status_code: int = 500
    code: str = "internal_error"
    user_message: str = "Что-то пошло не так. Попробуйте ещё раз."

    def __init__(self, detail: str | None = None, *, user_message: str | None = None):
        super().__init__(detail or self.user_message)
        self.detail = detail or self.user_message
        if user_message:
            self.user_message = user_message


class MCPUnavailableError(EscapeError):
    """Tutu MCP did not answer in time or answered with a transport error."""

    status_code = 503
    code = "mcp_unavailable"
    user_message = "Туту сейчас не отвечает. Попробуйте ещё раз через минуту."


class MCPProtocolError(EscapeError):
    """MCP answered, but the payload does not match the protocol."""

    status_code = 502
    code = "mcp_protocol_error"
    user_message = "Не удалось разобрать ответ Туту. Мы уже знаем об этом."


class LLMUnavailableError(EscapeError):
    """The language model timed out or returned unusable output."""

    status_code = 503
    code = "llm_unavailable"
    user_message = "Планировщик перегружен. Попробуйте ещё раз."


class NoResultsError(EscapeError):
    """Nothing satisfies the constraints — this is a product state, not a bug."""

    status_code = 200
    code = "no_results"
    user_message = "Мы не нашли вариант, который укладывается в эти ограничения."


class EscapeNotFoundError(EscapeError):
    """The requested escape id expired or never existed."""

    status_code = 404
    code = "escape_not_found"
    user_message = "Этот побег уже остыл. Соберите новый — это 10 секунд."


class EmailDeliveryError(EscapeError):
    """SMTP refused the message."""

    status_code = 502
    code = "email_failed"
    user_message = "Письмо не ушло. Маршрут сохранён — можно скачать его целиком."


class ValidationFailedError(EscapeError):
    """Input did not pass validation."""

    status_code = 422
    code = "invalid_input"
    user_message = "Проверьте введённые значения."
