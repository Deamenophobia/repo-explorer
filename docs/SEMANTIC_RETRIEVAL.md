# Comparing lexical and local learned retrieval

The observed problem is a vocabulary mismatch: identifier-aware TF-IDF finds
`cache_lookup`, but not “How are remembered objects recovered?” This experiment
asks whether learned embeddings recover useful source evidence and whether the
same generation pipeline uses it responsibly.

## Fixed experiment design

The comparison uses identifier-aware TF-IDF and the optional FastEmbed adapter with
`BAAI/bge-small-en-v1.5`. [FastEmbed's model catalog](https://qdrant.github.io/fastembed/examples/Supported_Models/)
describes this as a small English text embedding model. It is a convenient CPU
baseline, not a claim that it is optimal for code or multilingual repositories.

Both methods use the same pinned text, 1,100-character chunks, 150-character overlap,
two returned passages, in-memory cosine search, and no context expansion. The
similarity cutoff is disabled with `minimum_score=-1`. This compares ranking at a
fixed passage limit without treating scores from different models as interchangeable.
TF-IDF still abstains when a query has no vocabulary in the index and produces a
zero vector. Equal passage limits do not guarantee equal context characters.

Generation uses Codex CLI 0.160.0 with requested model `gpt-6-astra`, medium reasoning,
and the same structured prompt and answerability contract. There is one response per
case and configuration, with no provider retries. This does not control model
variation. The reference answers and gold spans never enter retrieval or prompting.

The authored identifier suite supplies exact-name, paraphrase, and missing-deployment
controls. A transfer check uses [Cachetools v6.2.1](https://github.com/tkem/cachetools/tree/ca7508fd56103a1b6d6f17c8e93e36c60b44ca25),
commit `ca7508fd56103a1b6d6f17c8e93e36c60b44ca25`, and all five package Python files
under `src/cachetools`. Questions and source-inspected annotations were saved before
retrieving with either method. The repository was selected for its caching domain;
it is not a random sample, and tests/docs are excluded. This is a bounded package-source
check, not a whole-repository benchmark or evidence about massive systems.

## Observed results

These runs were made on 6 October 2026 (Singapore time). The only workspace
configuration differences within each pair were `embedding_provider` and
`embedding_model`; source identities, implementation fingerprints, and policy hashes
matched. Model tokenization found no selected source chunk above the embedding
model's 512-token limit, so document truncation did not explain these outcomes.

| Case | Identifier-aware TF-IDF | Local learned retrieval |
| --- | --- | --- |
| Authored exact-name question | Retrieves both cache implementations; explanation cites each. | Retrieves the same implementations; explanation cites each. |
| Authored paraphrase | No vocabulary match; no generation call. | Retrieves the local mapping first. The explanation is supported but explicitly conditional on what “remembered objects” means. |
| Cachetools recency eviction | Retrieves time-aware cache fragments; gives a partial explanation and identifies missing eviction logic. | Retrieves a locking wrapper and an insertion fragment; declines to explain the missing eviction logic. Neither recovers the annotated full path. |
| Cachetools concurrent computation | Retrieves decorator entry points, missing the coordination implementation; abstains. | Retrieves a method-level condition wrapper and explains pending keys, waiting, and cleanup. The annotated function variant is still absent. |
| Cachetools `TTLCache.expire` | Retrieves imports/decorator code, missing the method; abstains. | Retrieves the method and explains expiration cutoff and returned key/value pairs. |
| Missing production region, in either corpus | Related code is retrieved; the model says the region cannot be determined. | Related code is retrieved; the model also declines to invent a region. |

The concurrency case is not a clean win against the gold annotation. The question
does not explicitly distinguish a function from a method. The model says which
method-level wrapper it is explaining, and its claims follow that source, while
the original annotation expects `_cached._condition`. Strict span coverage misses
a useful analogous explanation. The method wrapper also has a `cache(self) is None`
bypass, so its coordination claim assumes an enabled cache. Preserve the original
annotation and result; a future independently reviewed suite should clarify the
intended target and acceptable alternatives before running comparisons.

The eviction annotation similarly chooses the ordinary LRU path, although the
question leaves room for time-aware variants. Regardless of that annotation choice,
neither returned context contains the capacity check plus the access-order/eviction
implementation needed for a full explanation. This is a concrete remaining retrieval
failure. A larger passage limit or structural context could help; this experiment
did not evaluate either change.

Source inspection supports the paraphrase's mapping lookup and the expiration
answer's cutoff and returned pairs. However, the expiration chunk omits its owning
class header; ownership was checked against the pinned full source. This illustrates
why source-path citations and similarity alone are weaker than explicit symbol
provenance when implementations share names.

That observation prompted the optional [source-analysis adapter](SOURCE_ANALYSIS.md).
A later run preserves these excerpts and attaches their qualified definition names.
It is separate from the lexical/learned comparison above; the original reports are
unchanged.

The useful conclusion is bounded: this local embedding model recovered evidence
for the authored paraphrase and one external method question. It did not reliably
recover complete implementation paths. We retain TF-IDF as the default and offer
FastEmbed as an optional adapter. No universal retrieval-quality improvement or
practical advantage over ordinary assistant use has been established.

The ignored report directories are `identifiers-lexical-v2`,
`identifiers-semantic-v2`, `cachetools-lexical-v2`, and `cachetools-semantic-v2` under
`.repo-explorer/evaluations/`. They retain copied sources, effective configurations,
ranked context, drafts, final outcomes, and runtime versions. Separate
`assistant-review.json` files record the source inspections against report hashes;
the original `review.json` files remain pending for independent review. Embedding
file identities are recorded in the shared model manifest.

## Reproduce the comparison

Install the optional adapter in the existing project environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[fastembed]'
```

`requirements-semantic.lock` records the optional dependency versions exercised on
Windows with Python 3.12. Install it after `requirements.lock` when matching that
environment. The model weights are downloaded separately, not committed.
The [recorded model manifest](../evaluations/semantic-model-manifest.json) contains
the actual ONNX and tokenizer file hashes used here. Model names alone are not
immutable versions: compare downloaded files with this manifest when reproducing
the experiment. The adapter does not automatically enforce these experiment hashes.

Copy [lexical.example.json](../evaluations/lexical.example.json) and
[semantic.example.json](../evaluations/semantic.example.json) into ignored local
configuration files. Set the same accessible chat model in both; chat provider and
embedding provider remain independent choices. For the identifier comparison, set
`case_ids` to `exact-identifiers`, `paraphrase`, and `missing-deployment`. Leave it
empty for all Cachetools questions. Credentials and proxies belong in the process
environment, not these files; follow [the live runner setup](LIVE_EVALUATION.md).

For each configuration, run a preflight into a new directory before enabling provider
calls. For example, after editing `.repo-explorer/semantic-local.json`:

```powershell
.\.venv\Scripts\python.exe -m repo_explorer.evaluation.live --suite evaluations/identifiers.json --repository examples/identifier-repository --config .repo-explorer/semantic-local.json --output .repo-explorer/evaluations/semantic-preflight
.\.venv\Scripts\python.exe -m repo_explorer.evaluation.live --suite evaluations/identifiers.json --repository examples/identifier-repository --config .repo-explorer/semantic-local.json --output .repo-explorer/evaluations/semantic-run --execute
```

Repeat with the lexical config and distinct output directories. Preflight validates
configuration and pinned source text; it does not download embeddings or verify
provider access. The first semantic execution downloads the chosen model, then
embeds locally. After downloading it, set
`REPO_EXPLORER_FASTEMBED_LOCAL_FILES_ONLY=true` to require cached files on repeat
runs. See [local embedding settings](CONFIGURATION.md#local-learned-embeddings-with-fastembed)
for the cache location, thread controls, and download proxy behavior.

For the external-source check:

```powershell
git clone --no-checkout --depth 1 --branch v6.2.1 https://github.com/tkem/cachetools.git .repo-explorer/external/cachetools-v6.2.1
.\.venv\Scripts\python.exe -m repo_explorer.evaluation.live --suite evaluations/cachetools.json --repository .repo-explorer/external/cachetools-v6.2.1 --config .repo-explorer/semantic-local.json --output .repo-explorer/evaluations/cachetools-semantic-run --execute
```

Use an already fetched matching checkout if it exists. The suite reads the pinned
Git objects, checks file hashes, and copies the selected text into the report
directory. It does not execute Cachetools or change its checkout. Repeat with the
lexical configuration. The [annotation manifest](../evaluations/cachetools.json)
records the scope and evidence spans; [the upstream MIT notice](../evaluations/cachetools-LICENSE.txt)
accompanies its source quote anchors.

## Interpret the evidence

Inspect retrieved code before inspecting the answer. Check whether the expected
operation is present, whether a chunk lost its owning class or neighboring branch,
and whether similarly named implementations became distractors. Then compare the
generated claims and missing-information statements against those exact excerpts.

A model's `complete` label is its own assessment. It can be wrong even when source
IDs are valid. A `partial` response can be useful when it accurately names a missing
piece or ambiguity. Missing deployment information remains a control: learned
similarity can retrieve related code but cannot create the absent fact.

The recorded source inspections are assistant judgments; independent human review
remains pending. Do not tune a threshold on these same questions and present the
result as a general improvement. Broader repositories, alternative models, repeated
generation, and an ordinary search/assistant comparison remain separate work.
