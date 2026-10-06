"""LangGraph owns transitions and checkpoints. Nodes return state updates only."""

import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from repo_explorer.evidence_map import build_evidence_map
from repo_explorer.generation import AnswerGenerator
from repo_explorer.knowledge import KnowledgeIndex
from repo_explorer.schemas import Answerability, DraftAnswer


class RunState(TypedDict, total=False):
    question: str
    intent: str
    status: str
    answer: str
    answerability: Answerability
    limitations: list[str]
    sources: list[dict]
    citation_ids: list[str]
    steps: list[str]
    mode: str
    retrieval: str
    snapshot: str
    context_expansion: dict | None
    evidence_map: dict | None


def build_workflow(index: KnowledgeIndex, generator: AnswerGenerator, checkpointer):
    def retrieve(state: RunState):
        return {
            "sources": index.search(state["question"]),
            "steps": ["retrieve"],
            "snapshot": index.snapshot,
            "mode": index.settings.mode,
            "retrieval": index.retrieval,
            "context_expansion": None,
        }

    def expand_context(state: RunState):
        result = index.expand_context(state["sources"])
        return {
            "sources": result.sources,
            "context_expansion": result.trace.model_dump(),
            "steps": [*state["steps"], "expand_context"],
        }

    def after_retrieval(state: RunState):
        if not state["sources"]:
            return "abstain"
        return "expand_context" if index.settings.context_expander != "none" else "compose"

    def compose(state: RunState):
        draft = generator.generate(
            state["question"], state["intent"], state["sources"], index.policy
        )
        if "answerability" in draft or "limitations" in draft:
            draft = DraftAnswer.model_validate(draft).model_dump()
        else:
            # Extractive demo and legacy generators do not claim to assess completeness.
            draft = {**draft, "answerability": "not_assessed", "limitations": []}
        return {**draft, "steps": [*state["steps"], "compose"]}

    def validate(state: RunState):
        known = {source["id"] for source in state["sources"]}
        cited = set(state["citation_ids"])
        response_text = "\n".join([state["answer"], *state["limitations"]])
        inline = set(re.findall(r"\[(S\d+)\]", response_text))
        insufficient = state["answerability"] == "insufficient_evidence"
        valid = (bool(cited) or insufficient) and cited <= known and inline == cited
        # Structural citation validation is NOT a semantic factuality guarantee.
        result = {"steps": [*state["steps"], "validate"], "evidence_map": None}
        if not valid:
            return {
                **result,
                "status": "invalid_citations",
                "answer": "The draft did not provide valid source references. "
                "Try a narrower question.",
                "citation_ids": [],
                "answerability": "not_assessed",
                "limitations": [],
            }
        cited_sources = [source for source in state["sources"] if source["id"] in cited]
        return {
            **result,
            "status": "insufficient_evidence" if insufficient else "validated",
            "evidence_map": build_evidence_map(
                cited_sources, index.settings.evidence_map_node_limit
            ).model_dump()
            if cited_sources
            else None,
        }

    def abstain(state: RunState):
        return {
            "answer": "I could not find sufficient evidence in this repository snapshot. "
            "Try a more specific question about your configured sources.",
            "citation_ids": [],
            "status": "insufficient_evidence",
            "answerability": "insufficient_evidence",
            "limitations": ["No source passages matched this question in the indexed snapshot."],
            "steps": [*state["steps"], "abstain"],
        }

    def review(state: RunState):
        decision = interrupt({"kind": "review_brief", "answer": state["answer"]})
        return {
            "status": "approved" if decision["approved"] else "rejected",
            "steps": [*state["steps"], "review"],
        }

    def finish(state: RunState):
        return {"status": "completed", "steps": [*state["steps"], "finish"]}

    def after_validation(state: RunState):
        if state["status"] != "validated":
            return END
        return "review" if state["intent"] == "review" else "finish"

    graph = StateGraph(RunState)
    for name, node in [
        ("retrieve", retrieve),
        ("expand_context", expand_context),
        ("compose", compose),
        ("validate", validate),
        ("abstain", abstain),
        ("review", review),
        ("finish", finish),
    ]:
        graph.add_node(name, node)
    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        after_retrieval,
        ["compose", "abstain", "expand_context"],
    )
    graph.add_edge("expand_context", "compose")
    graph.add_edge("compose", "validate")
    graph.add_conditional_edges("validate", after_validation, ["review", "finish", END])
    for name in ("abstain", "review", "finish"):
        graph.add_edge(name, END)
    return graph.compile(checkpointer=checkpointer)
