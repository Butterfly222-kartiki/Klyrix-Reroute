"""LLM provider settings, read from environment variables.

Groq is used when GROQ_API_KEY is set (it exposes an OpenAI-compatible API).
The older REROUTE_LLM / REROUTE_LLM_KEY / REROUTE_LLM_MODEL variables still work
and point at OpenAI.
"""
from __future__ import annotations
import os

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"


def _use_groq() -> bool:
    return bool(os.environ.get("GROQ_API_KEY")) and not os.environ.get("REROUTE_LLM_KEY")


def llm_enabled() -> bool:
    return bool(os.environ.get("REROUTE_LLM")) or bool(os.environ.get("GROQ_API_KEY"))


def llm_key() -> str:
    return os.environ.get("REROUTE_LLM_KEY") or os.environ.get("GROQ_API_KEY", "")


def llm_base_url() -> str:
    return os.environ.get("GROQ_BASE_URL", GROQ_BASE_URL) if _use_groq() else OPENAI_BASE_URL


def llm_chat_url() -> str:
    return llm_base_url().rstrip("/") + "/chat/completions"


def llm_model() -> str:
    if os.environ.get("REROUTE_LLM_MODEL"):
        return os.environ["REROUTE_LLM_MODEL"]
    if _use_groq():
        return os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    return "gpt-4o-mini"


def load_dotenv(*paths: str) -> None:
    """Tiny .env loader (stdlib only). Never overrides variables already set."""
    for p in paths:
        if not os.path.isfile(p):
            continue
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if k.strip() and v:
                os.environ.setdefault(k.strip(), v)
