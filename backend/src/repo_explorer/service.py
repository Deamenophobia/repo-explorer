"""Application service serializes mutations for the local single-process runtime."""

from threading import RLock
from uuid import uuid4

from langgraph.types import Command

from repo_explorer.schemas import RunRequest, RunView


class RunService:
    def __init__(self, graph):
        self.graph = graph
        self.lock = RLock()

    @staticmethod
    def config(run_id: str):
        return {"configurable": {"thread_id": run_id}}

    def create(self, request: RunRequest) -> RunView:
        run_id = str(uuid4())
        with self.lock:
            self.graph.invoke(request.model_dump(), self.config(run_id))
            return self.get(run_id)

    def get(self, run_id: str) -> RunView:
        with self.lock:
            snapshot = self.graph.get_state(self.config(run_id))
            state = snapshot.values
            if not state:
                raise KeyError(run_id)
            pending = any(task.interrupts for task in snapshot.tasks)
            citations = [
                s for s in state.get("sources", []) if s["id"] in state.get("citation_ids", [])
            ]
            return RunView(
                id=run_id,
                question=state["question"],
                intent=state["intent"],
                status="awaiting_review" if pending else state.get("status", "running"),
                answer=state.get("answer", ""),
                answerability=state.get("answerability", "not_assessed"),
                limitations=state.get("limitations", []),
                citations=citations,
                steps=state.get("steps", []),
                mode=state.get("mode", "demo"),
                retrieval=state.get("retrieval", ""),
                snapshot=state.get("snapshot", ""),
                context_expansion=state.get("context_expansion"),
                evidence_map=state.get("evidence_map"),
            )

    def decide(self, run_id: str, approved: bool) -> RunView:
        with self.lock:
            if self.get(run_id).status != "awaiting_review":
                raise ValueError("This run has no pending review.")
            self.graph.invoke(Command(resume={"approved": approved}), self.config(run_id))
            return self.get(run_id)
