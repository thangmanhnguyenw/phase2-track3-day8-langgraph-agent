"""LLM factory helper.

Provides a simple interface to create LLM clients for use in nodes.
Students should use this helper so the lab works with any supported provider.

Usage in nodes:
    from .llm import get_llm
    llm = get_llm()
    response = llm.invoke("Hello")
"""

from __future__ import annotations

import os


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


_load_env()


def get_llm(model: str | None = None, temperature: float = 0.0):
    """Create an LLM client from environment configuration.

    Provider selection (first match wins):
    1. LLM_PROVIDER env var: openai | gemini | anthropic
    2. Otherwise: OPENAI_API_KEY → GEMINI_API_KEY → ANTHROPIC_API_KEY

    Override model with the `model` parameter or LLM_MODEL env var.
    """
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()

    if provider == "openai" or (not provider and os.getenv("OPENAI_API_KEY")):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set in .env")
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError("Install: pip install langchain-openai") from exc
        return ChatOpenAI(
            model=model or os.getenv("LLM_MODEL", "gpt-4o-mini"),
            api_key=api_key,
            temperature=temperature,
        )

    if provider == "gemini" or (not provider and os.getenv("GEMINI_API_KEY")):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set in .env")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError("Install: pip install langchain-google-genai") from exc
        return ChatGoogleGenerativeAI(
            model=model or os.getenv("LLM_MODEL", "gemini-2.5-flash"),
            google_api_key=api_key,
            temperature=temperature,
        )

    if provider == "anthropic" or (not provider and os.getenv("ANTHROPIC_API_KEY")):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set in .env")
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise RuntimeError("Install: pip install langchain-anthropic") from exc
        return ChatAnthropic(
            model=model or os.getenv("LLM_MODEL", "claude-sonnet-4-20250514"),
            api_key=api_key,
            temperature=temperature,
        )

    raise RuntimeError(
        "No LLM API key found. Set LLM_PROVIDER=openai and OPENAI_API_KEY in .env\n"
        "See .env.example for configuration."
    )
