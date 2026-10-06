"""Retrieval composes corpus, embedding, and vector-store adapters."""

import hashlib

from repo_explorer.analysis import SourceAnalyzer
from repo_explorer.config import Settings
from repo_explorer.context import ContextExpander, ExpansionResult
from repo_explorer.plugins import PluginRegistry, default_registry
from repo_explorer.schemas import Citation


class KnowledgeIndex:
    def __init__(self, settings: Settings, registry: PluginRegistry | None = None):
        registry = registry or default_registry()
        self.settings = settings
        corpus = registry.build("sources", settings.source_provider, settings)
        self.documents, self.files, self.policy = corpus.documents, corpus.files, corpus.policy
        self.analyzer: SourceAnalyzer = registry.build(
            "analyzers", settings.source_analyzer, settings, corpus
        )
        self.expander: ContextExpander = registry.build(
            "expanders", settings.context_expander, settings, corpus
        )
        if not self.documents:
            raise ValueError("The corpus contains no supported text files.")
        if len(self.documents) > settings.max_chunks:
            raise ValueError("Index chunk limit exceeded.")
        self.snapshot = hashlib.sha256(str(self.files).encode()).hexdigest()[:12]
        self.embeddings = registry.build(
            "embeddings",
            settings.embedding_provider,
            settings,
            [doc.page_content for doc in self.documents],
        )
        self.retrieval = (
            "TF-IDF lexical baseline"
            if settings.embedding_provider == "tfidf"
            else f"{settings.embedding_provider} / {settings.embedding_model}"
        )
        if (
            settings.embedding_provider == "tfidf"
            and settings.lexical_tokenization == "code_identifiers"
        ):
            self.retrieval = "TF-IDF / code identifiers"
        self.store = registry.build("stores", settings.vector_store, settings, self.embeddings)
        self.store.add_documents(self.documents)

    def expand_context(self, sources: list[dict]) -> ExpansionResult:
        result = self.expander.expand(sources)
        # Expansion can cross definition boundaries. Never keep metadata for the old seed.
        result.sources = [self.annotate(source) for source in result.sources]
        return result

    def annotate(self, source: dict) -> dict:
        analysis = self.analyzer.analyze(source)
        return {**source, "source_analysis": analysis.model_dump() if analysis else None}

    def search(self, question: str) -> list[dict]:
        vector = self.embeddings.embed_query(question)
        if not any(vector):
            return []
        results = self.store.similarity_search_with_score_by_vector(
            vector, k=self.settings.retrieval_limit
        )
        return [
            self.annotate(
                Citation(
                    id=f"S{index + 1}",
                    excerpt=doc.page_content,
                    score=round(float(score), 4),
                    **doc.metadata,
                ).model_dump()
            )
            for index, (doc, score) in enumerate(results)
            if score >= self.settings.minimum_score
        ]
