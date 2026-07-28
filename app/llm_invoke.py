"""LLM Invocation — synchronous, single-shot call to the model.

Replaced the LangChain wrapper with the direct OpenAI SDK to eliminate the
langchain-openai / langchain-core dependency tree from the Vercel bundle.
Public interface (invoke_llm) is unchanged.
"""

import os
from typing import Optional

from app.schemas import LLMError
from app.config import OPENAI_MODEL, LLM_TEMPERATURE, LLM_TIMEOUT_SECONDS, LLM_MAX_TOKENS


def invoke_llm(
    system_prompt: str,
    user_message: str,
    model: str = OPENAI_MODEL,
    temperature: float = LLM_TEMPERATURE,
    timeout: int = LLM_TIMEOUT_SECONDS,
    max_tokens: int = LLM_MAX_TOKENS,
) -> str:
    """Call the LLM and return the generated response.

    Args:
      system_prompt: System instructions
      user_message: The query / facts to analyse
      model: Model name (default from config)
      temperature: Sampling temperature (default 0.3 for low randomness)
      timeout: Request timeout in seconds
      max_tokens: Maximum tokens to generate

    Returns:
      The raw model output (analysis + reasoning + improvement plan).

    Raises:
      LLMError if the invocation fails.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMError("OPENAI_API_KEY not set in environment")

    try:
        from openai import OpenAI  # imported lazily so tests can mock

        client = OpenAI(api_key=api_key, timeout=timeout)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    except Exception as exc:
        raise LLMError(f"LLM invocation failed: {exc}") from exc
