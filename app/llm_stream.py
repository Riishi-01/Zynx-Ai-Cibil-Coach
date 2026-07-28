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
"""

import os
from typing import AsyncIterator, Optional

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


async def astream_plan(
    system_prompt: str,
    user_message: str,
    model=None,
) -> AsyncIterator[dict]:
    """Stream the coaching plan as progressively complete dictionaries.

    Each yielded value is the whole plan as parsed so far, not a delta, so the
    frontend can render straight from the latest object.
    """
    chain_model = model if model is not None else build_model(json_mode=True)
    chain = chain_model | JsonOutputParser()

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    try:
        async for partial in chain.astream(messages):
            if isinstance(partial, dict):
                yield partial
    except Exception as exc:
        raise LLMError(f"Plan streaming failed: {exc}") from exc


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
