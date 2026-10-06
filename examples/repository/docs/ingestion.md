# Repository ingestion

## From files to cited passages
The ingestion pipeline reads Markdown and supported source files from a configured
directory. A recursive text splitter creates overlapping chunks so neighboring
context remains available near chunk boundaries. Each chunk retains its relative
file path, starting line, ending line, and a content revision hash.

The local demo uses TF-IDF vectors. TF-IDF weights words by how distinctive they
are across the corpus; cosine similarity ranks passages sharing useful terms.
It is a lexical baseline and does not understand semantic paraphrases like a
learned embedding model. Live mode can use a configured embedding model instead.

## Snapshot lifecycle
The index is rebuilt when the API starts or workspace settings are applied. A
snapshot fingerprint identifies indexed file revisions. After editing a source,
apply settings again before asking new questions. Existing run evidence stays in
its checkpoint.
