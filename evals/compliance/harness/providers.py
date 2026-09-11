"""Provider adapters: one call shape in, (text, usage, error) out.

Anthropic's Messages API and the OpenAI-compatible chat-completions shape
(DeepSeek, and anything else that speaks it) differ enough — prefix caching
via `cache_control` blocks, an explicit `thinking` param, how system content
is structured — that they need separate request builders. Everything after
the response comes back (grading, JSONL rows, the report) is provider-
agnostic on purpose: a `model` string and a `provider` string are the only
fields that vary per row.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Usage:
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None = None


@dataclass
class CallResult:
    text: str
    usage: Usage
    error: str | None = None


def call_anthropic(client, model: str, effort: str, stable_system: str, doctrine_system: str,
                    user_prompt: str, max_tokens: int) -> CallResult:
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[
            {"type": "text", "text": stable_system, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": doctrine_system, "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user", "content": user_prompt}],
        thinking={"type": "adaptive"},
    )
    if response.stop_reason == "refusal":
        return CallResult("", Usage(None, None), f"refusal: {getattr(response.stop_details, 'category', None)}")
    text = "\n".join(b.text for b in response.content if b.type == "text")
    return CallResult(
        text,
        Usage(
            response.usage.input_tokens,
            response.usage.output_tokens,
            getattr(response.usage, "cache_read_input_tokens", None),
        ),
    )


def call_openai_compatible(client, model: str, stable_system: str, doctrine_system: str,
                            user_prompt: str, max_tokens: int) -> CallResult:
    """DeepSeek (and anything else exposing the same chat-completions shape).

    No prefix-caching control, no separate `thinking` param — DeepSeek's own
    reasoning models (e.g. `deepseek-reasoner`) do that internally and expose
    it via `message.reasoning_content`, not a request-time switch, so nothing
    here needs to select it explicitly.
    """
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": stable_system + "\n\n" + doctrine_system},
            {"role": "user", "content": user_prompt},
        ],
    )
    choice = response.choices[0]
    if choice.finish_reason == "content_filter":
        return CallResult("", Usage(None, None), "refusal: content_filter")
    text = choice.message.content or ""
    usage = response.usage
    return CallResult(
        text,
        Usage(
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
            None,
        ),
    )


# provider name -> (env var carrying the API key, base_url for an OpenAI-compatible client)
OPENAI_COMPATIBLE_PROVIDERS = {
    "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com"),
}
