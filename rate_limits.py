from collections.abc import Mapping


DAILY_LIMIT_MESSAGE = (
    "Limit for the day reached. Please try again after the daily quota resets."
)
TEMPORARY_RATE_LIMIT_MESSAGE = (
    "Groq is temporarily rate-limited. Please try again shortly."
)


def groq_rate_limit_message(headers: Mapping[str, str]) -> str:
    if headers.get("x-ratelimit-remaining-requests", "").strip() == "0":
        return DAILY_LIMIT_MESSAGE
    return TEMPORARY_RATE_LIMIT_MESSAGE
