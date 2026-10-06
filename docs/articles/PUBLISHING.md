# Publishing this series to the existing blog

This bundle is prepared for a Payload blog using a Posts collection. Confirm the
destination schema before importing. No live CMS records have been created.

The post collection uses `title`, `slug`, a Lexical `content` field, optional
`heroImage`, `categories`, `authors`, and `meta`. `series.json` supplies editorial
titles, slugs, descriptions and asset choices. Category, author, and uploaded-media
IDs must be resolved in the actual CMS.

For each article, upload its PNG assets with the supplied alt text, then create a
draft post. Convert Markdown headings, paragraphs, links and lists to native
Lexical nodes. Use the blog's Code block for code excerpts and MediaBlock for
screenshots and diagrams. Convert the Markdown editorial source to the Lexical
JSON structure expected by the collection before assigning its content field.

Diagrams are provided as SVG and PNG. Use the PNG variant if the media collection
does not permit SVG. Keep the SVG as the editable source. Set the post's meta title
and description from the manifest, choose its hero image, and connect the series
using related posts after draft IDs exist.

Preview each post at desktop and mobile widths before publication. Keep the
offline-demo labels and identify the fifth article's live captures as observations
from the Codex provider on authored fixtures. The second article's learned-retrieval
comparison uses actual backend runs and cites pinned public source. Keep other
chat providers, remote embeddings, and broader
repository quality separate from that evidence. No test totals,
pass-rate claims, or synthetic live-model screenshots belong in the public series.

The self-contained HTML preview in `docs/site` supports reading and layout review.
The CMS import still requires conversion to Payload's rich-text schema.
Publication and live CMS import follow review of the draft bundle.
The release order is GitLab verification, then GitHub publication, then the blog.
Use the same reviewed source revision for the repository links in the posts.
See [the release gate](../RELEASE.md).

## Editorial voice

Explain concepts through concrete decisions and examples from this project.
Define RAG, embeddings, structured output, and orchestration when they first matter
to the reader. Keep the distinction between observed behavior and future work
explicit, and state limitations directly.

Use plain verbs and specific causes and effects. Avoid promotional language,
stock transitions, and the rhetorical “X, not Y” or “not just X, but Y” pattern.
Remove an unnecessary contrast and explain what the component actually does.
Technical negation is appropriate when needed to describe behavior accurately.
Preserve actual screenshot labels and observed results. Keep test counts and
pass-rate claims out of the posts.
