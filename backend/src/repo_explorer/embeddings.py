"""Optional local learned embeddings behind LangChain's standard interface."""

from langchain_core.embeddings import Embeddings

from repo_explorer.config import Settings


class FastEmbedEmbeddings(Embeddings):
    def __init__(self, settings: Settings, texts: list[str]):
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise ValueError("Install the fastembed extra: pip install -e '.[fastembed]'") from exc

        self.model = TextEmbedding(
            model_name=settings.embedding_model,
            cache_dir=str(settings.fastembed_cache_dir),
            threads=settings.fastembed_threads,
            local_files_only=settings.fastembed_local_files_only,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # Use the model's retrieval-specific passage/query transforms, not a shared prefix.
        return [vector.tolist() for vector in self.model.passage_embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self.model.query_embed(text))).tolist()
