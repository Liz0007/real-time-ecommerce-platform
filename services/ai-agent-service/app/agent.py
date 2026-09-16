import os
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

from app.tools import TOOL_REGISTRY
from app.prompts import SYSTEM_PROMPT

llm = ChatAnthropic(
        model="claude-sonnet-5",
        api_key=os.environ["ANTHROPIC_API_KEY"],
    )

def _extract_text(content) -> str:
    """Anthropic responses can return content as a plain string or as a
    list of content blocks (text, thinking, signature, etc.) depending on
    the model and request — normalize to plain text either way."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)

def run_agent(question: str, enabled_tools: list[str] | None = None) -> dict:
    """
    Runs the agent and returns both the answer and which tools were
    actually invoked — the tool-call trace is what evals check against,
    not just the final text.
    """
    if enabled_tools:
        selected = [TOOL_REGISTRY[name] for name in enabled_tools if name in TOOL_REGISTRY]
    else:
        selected = list(TOOL_REGISTRY.values())
 
    agent = create_react_agent(llm, selected, prompt=SYSTEM_PROMPT)
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    messages = result["messages"]
 
    tools_called = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            tools_called.append(tc["name"])
 
    return {"answer": _extract_text(messages[-1].content), "tools_called": tools_called}
 
 
def ask_agent(question: str, enabled_tools: list[str] | None = None) -> str:
    """Thin wrapper used by the API — just the answer text."""
    return run_agent(question, enabled_tools)["answer"]
