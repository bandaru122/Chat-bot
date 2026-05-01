"""LCEL chat chain template.

Usage from a service:

    from app.ai.chains.chat_chain import build_chat_chain

    chain = build_chat_chain()
    async for chunk in chain.astream(
        {"history": history, "human_input": message},
        config={"metadata": {"user_email": current_user.email}},
    ):
        yield chunk
"""
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable

from app.ai.llm import get_chat_llm

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def build_chat_chain() -> Runnable:
    """Return an LCEL chain: prompt | llm | StrOutputParser."""
    prompt = PromptTemplate.from_template(_load_prompt("chat.txt"))
    return prompt | get_chat_llm() | StrOutputParser()
