"""LangChain chains for the coaching plan and follow-up chat.

Two chains, both consumed with .astream():

  plan chain — prompt | model | JsonOutputParser
      JsonOutputParser is used rather than with_structured_output() because it
      parses partial JSON, yielding a progressively more complete CoachPlan
      object on every chunk. with_structured_output() only resolves once the
      whole response has arrived, which would defeat streaming.

  chat chain — prompt | model | StrOutputParser
      Follow-up answers stream as markdown text.

The model is constructed per call so tests can patch the factory.

`astream_plan` yields `(kind, payload)` tuples:
  ('plan', <partial dict>)   — one per parse tick
  ('metadata', {model, prompt_tokens, completion_tokens}) — once at the end,
      captured from LangChain's `usage_metadata` via a callback handler.
"""

import os
from typing import AsyncIterator, Optional, Tuple

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser

from app.config import (
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_SECONDS,
    OPENAI_MODEL,
)
from app.schemas import LLMError


def build_model(
    model: str = OPENAI_MODEL,
    temperature: float = LLM_TEMPERATURE,
    timeout: int = LLM_TIMEOUT_SECONDS,
    max_tokens: int = LLM_MAX_TOKENS,
    json_mode: bool = False,
):
    """Construct the chat model.

    Isolated in one function so tests can patch it without touching the chains.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMError("OPENAI_API_KEY not set in environment")

    # Imported lazily so the module can be imported without the dependency
    # being configured.
    from langchain_openai import ChatOpenAI

    kwargs = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
        "api_key": api_key,
    }
    if json_mode:
        # Guarantees syntactically valid JSON, which keeps partial parsing sane.
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

    return ChatOpenAI(**kwargs)


class _UsageCapture(BaseCallbackHandler):
    """Captures the final LLM usage so the SSE stream can surface token counts.

    LangChain populates `AIMessage.usage_metadata` for OpenAI Chat Completions
    with `input_tokens` / `output_tokens` / `total_tokens`. The model name lives
    on `AIMessage.response_metadata['model_name']`. We read both in `on_llm_end`,
    which fires once per chain invocation.
    """

    def __init__(self) -> None:
        self.usage: Optional[dict] = None
        self.model_name: Optional[str] = None

    def on_llm_end(self, response, **kwargs) -> None:  # type: ignore[override]
        try:
            generation = response.generations[0][0]
            message = getattr(generation, "message", None)
            if message is not None:
                usage = getattr(message, "usage_metadata", None)
                if isinstance(usage, dict) and usage:
                    self.usage = usage
                response_meta = getattr(message, "response_metadata", None) or {}
                if isinstance(response_meta, dict):
                    name = response_meta.get("model_name")
                    if isinstance(name, str) and name:
                        self.model_name = name
        except (IndexError, AttributeError):
            # Stream returned no generations; leave usage as None.
            pass


async def astream_plan(
    system_prompt: str,
    user_message: str,
    model=None,
) -> AsyncIterator[Tuple[str, dict]]:
    """Stream the coaching plan, then a final metadata frame.

    Each yielded item is a `(kind, payload)` tuple:

      ('plan', <partial dict>)           — from JsonOutputParser as it parses
      ('metadata', {model, prompt_tokens, completion_tokens})  — captured from
                                            LangChain's usage_metadata on the
                                            final AIMessage.

    The frontend's /api/analyze handler turns each tuple into an SSE event with
    the matching event name.
    """
    chain_model = model if model is not None else build_model(json_mode=True)
    chain = chain_model | JsonOutputParser()

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    capture = _UsageCapture()

    try:
        async for partial in chain.astream(messages, config={"callbacks": [capture]}):
            if isinstance(partial, dict):
                yield ("plan", partial)
    except Exception as exc:
        raise LLMError(f"Plan streaming failed: {exc}") from exc

    if capture.usage:
        prompt_tokens = int(capture.usage.get("input_tokens", 0) or 0)
        completion_tokens = int(capture.usage.get("output_tokens", 0) or 0)
        yield (
            "metadata",
            {
                "model": capture.model_name or OPENAI_MODEL,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        )


async def astream_chat(
    system_prompt: str,
    user_message: str,
    model=None,
) -> AsyncIterator[str]:
    """Stream a follow-up answer as markdown text chunks."""
    chain_model = model if model is not None else build_model()
    chain = chain_model | StrOutputParser()

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    try:
        async for chunk in chain.astream(messages):
            if chunk:
                yield chunk
    except Exception as exc:
        raise LLMError(f"Chat streaming failed: {exc}") from exc
