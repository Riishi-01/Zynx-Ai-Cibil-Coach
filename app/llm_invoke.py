"""LLM Invocation — call the model and collect the output.

This is Phase 9: uses LangChain to call the LLM with the assembled prompt.
Returns the raw generated analysis, reasoning, and recommendations.
"""

import os
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

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
        # Initialise the LLM
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            api_key=api_key,
        )
        
        # Build the message list
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
        
        # Invoke
        response = llm.invoke(messages)
        
        # Extract the text
        output = response.content
        
        return output
    
    except Exception as exc:
        raise LLMError(f"LLM invocation failed: {exc}") from exc
