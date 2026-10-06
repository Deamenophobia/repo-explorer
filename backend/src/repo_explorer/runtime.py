"""Validate, prepare, persist, then swap settings under the run-service lock."""

import os
import tempfile

from repo_explorer.config import Settings, WorkspaceConfig
from repo_explorer.generation import ExtractiveGenerator
from repo_explorer.knowledge import KnowledgeIndex
from repo_explorer.plugins import PluginRegistry
from repo_explorer.service import RunService
from repo_explorer.workflow import build_workflow


class WorkspaceRuntime:
    def __init__(self, settings: Settings, registry: PluginRegistry, saver):
        self.settings, self.registry, self.saver = settings, registry, saver
        self.index, graph = self.prepare(settings)
        self.runs = RunService(graph)

    def prepare(self, settings: Settings):
        selections = {
            "sources": settings.source_provider,
            "stores": settings.vector_store,
            "embeddings": settings.embedding_provider,
            "chat": settings.chat_provider,
            "generators": settings.generator,
            "expanders": settings.context_expander,
            "analyzers": settings.source_analyzer,
        }
        for kind, name in selections.items():
            if name not in self.registry.factories[kind]:
                raise ValueError(f"Unknown {kind} adapter: {name}")
        # Initialize the generator before remote indexing, so missing credentials fail early.
        generator = (
            ExtractiveGenerator(settings.demo_excerpt_limit)
            if settings.mode == "demo"
            else self.registry.build("generators", settings.generator, settings, self.registry)
        )
        index = KnowledgeIndex(settings, self.registry)
        return index, build_workflow(index, generator, self.saver)

    def describe(self):
        with self.runs.lock:
            return {
                "values": self.settings.public().model_dump(mode="json"),
                "schema": WorkspaceConfig.model_json_schema(),
                "adapters": self.registry.catalog(),
            }

    def apply(self, public: WorkspaceConfig):
        with self.runs.lock:
            settings = Settings(**{**self.settings.model_dump(), **public.model_dump()})
            index, graph = self.prepare(settings)
            destination = settings.config_file
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".tmp")
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                    output.write(public.model_dump_json(indent=2))
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, destination)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            self.settings, self.index, self.runs.graph = settings, index, graph
            return self.describe()
