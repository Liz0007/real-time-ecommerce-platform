from fastapi import FastAPI
from pydantic import BaseModel

from app.agent import ask_agent
from app.tools import TOOL_REGISTRY

app = FastAPI(title="AI Agent Service")


class AskRequest(BaseModel):
    question: str
    enabled_tools: list[str] | None = None  # e.g. ["order", "payment"]


class AskResponse(BaseModel):
    answer: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/agent/tools")
def list_tools():
    """Lets the UI populate its multi-select dropdown dynamically."""
    return {"available_tools": list(TOOL_REGISTRY.keys())}


@app.post("/agent/ask", response_model=AskResponse)
def ask(req: AskRequest):
    answer = ask_agent(req.question, req.enabled_tools)
    return AskResponse(answer=answer)
