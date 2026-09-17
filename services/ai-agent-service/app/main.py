from fastapi import FastAPI
from pydantic import BaseModel

from app.agent import run_agent
from app.tools import TOOL_REGISTRY

app = FastAPI(title="AI Agent Service")

# Maps a tool's function name (what LangGraph reports as actually called)
# back to its registry key (what the UI's dropdown uses) — so the response
# can say "payment" instead of the raw function name "get_payment_status".
TOOL_NAME_TO_KEY = {tool.name: key for key, tool in TOOL_REGISTRY.items()}

class AskRequest(BaseModel):
    question: str
    enabled_tools: list[str] | None = None  # e.g. ["order", "payment"]


class AskResponse(BaseModel):
    answer: str
    tools_used: list[str]  # what the agent actually called, not what the user enabled


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/agent/tools")
def list_tools():
    """Let the UI populate its multi-select dropdown dynamically."""
    return {"available_tools": list(TOOL_REGISTRY.keys())}


@app.post("/agent/ask", response_model=AskResponse)
def ask(req: AskRequest):
    result = run_agent(req.question, req.enabled_tools)
    tools_used = [TOOL_NAME_TO_KEY.get(name, name) for name in result["tools_called"]]
    return AskResponse(answer=result["answer"], tools_used=tools_used)
