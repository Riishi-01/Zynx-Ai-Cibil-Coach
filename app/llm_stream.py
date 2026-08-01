"""LLM streaming for the coaching plan and follow-up chat.

Replaced the LangChain wrapper (langchain-openai + langchain-core) with the
direct OpenAI async SDK to eliminate ~60-80 MB of transitive dependencies
(langchain, langsmith, langchain-text-splitters, tiktoken, numpy, aiohttp …)
from the Vercel function bundle.

Two async generators, both consumed with `async for`:

  astream_plan  — streams and partial-parses JSON incrementally, yielding
                  ('plan', <partial dict>) tuples as the JSON is built up,
                  then a final ('metadata', {...}) tuple.

  astream_chat  — streams markdown text as raw string chunks.

Public interface is unchanged from the LangChain version so web.py and tests
need no modifications.
"""

import json
import os
from typing import AsyncIterator, Optional, Tuple

from app.config import (
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_SECONDS,
    OPENAI_MODEL,
)
from app.schemas import LLMError


def _get_client():
    """Return a configured AsyncOpenAI client.

    Imported lazily so the module stays importable without OPENAI_API_KEY set
    (e.g. tests that mock the function).
    """
    from openai import AsyncOpenAI  # ~8 MB, already required

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMError("OPENAI_API_KEY not set in environment")
    return AsyncOpenAI(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS)


def _build_messages(system_prompt: str, user_message: str) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]


def _try_parse_partial_json(buf: str) -> Optional[dict]:
    """Attempt to parse the accumulated buffer as JSON.

    OpenAI streams the JSON object token-by-token; each chunk extends the
    buffer. We try a full parse first; if that fails we use a stack-based
    heuristic that appends the minimum closing characters in correct nesting
    order — giving the frontend progressive updates even before the full
    object arrives.

    A naive brace-count approach (`"}" * opens + "]" * opens`) produces the
    wrong closing sequence for mixed `{[{` nesting — it would emit `}}}]`
    instead of the correct `}]}`. The stack tracks insertion order so the
    closing is always innermost-first.
    """
    buf = buf.strip()
    if not buf:
        return None

    # Fast path: complete JSON.
    try:
        return json.loads(buf)
    except json.JSONDecodeError:
        pass

    # Stack-based closing: walk the buffer respecting string quoting.
    stack: list[str] = []
    in_string = False
    escape_next = False
    for ch in buf:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]" and stack:
            stack.pop()

    if not stack:
        return None

    candidate = buf + "".join(reversed(stack))
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


async def astream_plan(
    system_prompt: str,
    user_message: str,
    model=None,  # kept for test compatibility (model param ignored; use config)
) -> AsyncIterator[Tuple[str, dict]]:
    """Stream the coaching plan, then a final metadata frame.

    Yields (kind, payload) tuples:
      ('plan', <partial dict>)                         — progressive JSON parse
      ('metadata', {model, prompt_tokens, completion_tokens})  — once at end
    """
    client = _get_client()
    messages = _build_messages(system_prompt, user_message)

    buf = ""
    last_emitted: Optional[dict] = None
    usage_data: Optional[dict] = None
    model_name: Optional[str] = None

    try:
        stream = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            response_format={"type": "json_object"},
            stream=True,
            stream_options={"include_usage": True},
        )

        async for chunk in stream:
            # Capture usage from the final chunk (stream_options include_usage)
            if chunk.usage:
                usage_data = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                }
                if chunk.model:
                    model_name = chunk.model

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            if delta.content:
                buf += delta.content

            if chunk.model and not model_name:
                model_name = chunk.model

            # Emit a partial parse on every chunk so the frontend gets updates
            parsed = _try_parse_partial_json(buf)
            if parsed is not None and parsed != last_emitted:
                last_emitted = parsed
                yield ("plan", parsed)

    except Exception as exc:
        raise LLMError(f"Plan streaming failed: {exc}") from exc

    # Emit final complete parse if it differs from the last partial
    if buf:
        try:
            final = json.loads(buf)
            if final != last_emitted:
                yield ("plan", final)
        except json.JSONDecodeError:
            pass

    if usage_data:
        yield (
            "metadata",
            {
                "model": model_name or OPENAI_MODEL,
                "prompt_tokens": usage_data["prompt_tokens"],
                "completion_tokens": usage_data["completion_tokens"],
            },
        )


async def astream_chat(
    system_prompt: str,
    user_message: str,
    model=None,  # kept for test compatibility
) -> AsyncIterator[str]:
    """Stream a follow-up answer as markdown text chunks.

    Mirrors ``astream_plan`` shape so the chat SSE handler can emit a
    matching ``metadata`` frame when usage is reported. Yields string
    fragments interleaved with a ``("metadata", {model, prompt_tokens,
    completion_tokens})`` tuple at the end if OpenAI returned usage.
    """
    client = _get_client()
    messages = _build_messages(system_prompt, user_message)

    usage_data: Optional[dict] = None
    model_name: Optional[str] = None

    try:
        stream = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            stream=True,
            stream_options={"include_usage": True},
        )

        async for chunk in stream:
            if chunk.usage:
                usage_data = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                }
                if chunk.model:
                    model_name = chunk.model

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            content = delta.content if delta else None
            if content:
                yield content

            if chunk.model and not model_name:
                model_name = chunk.model

    except Exception as exc:
        raise LLMError(f"Chat streaming failed: {exc}") from exc

    if usage_data is not None:
        yield ("metadata", {
            "model": model_name or OPENAI_MODEL,
            "prompt_tokens": usage_data["prompt_tokens"],
            "completion_tokens": usage_data["completion_tokens"],
        })
