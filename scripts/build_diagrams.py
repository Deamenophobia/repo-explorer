"""Generate focused, editable SVG figures without a network rendering service."""

from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1] / "docs/articles/assets"
ROOT.mkdir(parents=True, exist_ok=True)


def figure(name, title, subtitle, boxes, arrows, height=410):
    body = []
    for x1, y1, x2, y2 in arrows:
        body.append(
            f'<path d="M{x1} {y1} L{x2} {y2}" stroke="#91a281" '
            'stroke-width="2" marker-end="url(#arrow)" fill="none"/>'
        )
    for x, y, width, label, detail in boxes:
        body.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="76" rx="12" '
            'fill="#edf2e4" stroke="#cddbbd"/>'
        )
        body.append(
            f'<text x="{x + width / 2}" y="{y + 31}" text-anchor="middle" '
            f'font-size="17" fill="#294631">{escape(label)}</text>'
        )
        body.append(
            f'<text x="{x + width / 2}" y="{y + 54}" text-anchor="middle" '
            f'font-size="12" fill="#778968">{escape(detail)}</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="{height}"
viewBox="0 0 1000 {height}"
role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title><desc id="desc">{escape(subtitle)}</desc>
<defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
<path d="M0 0L7 3.5L0 7" fill="#91a281"/></marker></defs>
<rect width="1000" height="{height}" rx="18" fill="#f8faf4"/>
<g font-family="Segoe UI, Arial, sans-serif">
<text x="40" y="43" font-size="11" letter-spacing="2" fill="#849774">
REPO EXPLORER / ENGINEERING NOTES</text>
<text x="40" y="80" font-size="25" fill="#243e2e">{escape(title)}</text>
<text x="40" y="106" font-size="13" fill="#7b8b70">{escape(subtitle)}</text>
{"".join(body)}</g></svg>'''
    (ROOT / f"{name}.svg").write_text(svg, encoding="utf-8", newline="\n")


figure(
    "architecture",
    "One workflow owner, clear application boundaries",
    "Arrows show application dependencies; checkpoint storage sits behind the workflow.",
    [
        (40, 150, 180, "React workbench", "Questions + evidence"),
        (280, 150, 180, "FastAPI + service", "Typed HTTP boundary"),
        (520, 150, 180, "LangGraph", "Transitions + review"),
        (770, 140, 190, "KnowledgeIndex", "LangChain retrieval"),
        (770, 250, 190, "AnswerGenerator", "Demo or chat model"),
        (520, 290, 180, "SQLite", "Saved checkpoints"),
    ],
    [
        (220, 188, 280, 188),
        (460, 188, 520, 188),
        (700, 177, 770, 177),
        (700, 206, 770, 280),
        (610, 226, 610, 290),
    ],
    height=400,
)

figure(
    "retrieval",
    "Keep a path from every passage back to its source",
    "Default: lexical TF-IDF vectors. Optional live adapter: learned semantic embeddings.",
    [
        (35, 160, 190, "Curated files", "Path + content revision"),
        (280, 160, 190, "Split passages", "Preserve line ranges"),
        (525, 160, 190, "Vector index", "LangChain store"),
        (770, 160, 195, "Ranked evidence", "Question similarity"),
    ],
    [(225, 198, 280, 198), (470, 198, 525, 198), (715, 198, 770, 198)],
    height=290,
)

figure(
    "workflow",
    "A question can finish; a review waits for a decision",
    "No evidence abstains. Invalid references or insufficient evidence stop at validation.",
    [
        (35, 150, 170, "Retrieve", "Find source passages"),
        (285, 150, 170, "Compose", "Build the draft"),
        (535, 150, 170, "Validate", "References + answerability"),
        (790, 150, 170, "Finish", "Question intent"),
        (35, 295, 170, "Abstain", "No source evidence"),
        (790, 295, 170, "Human review", "Pause → decision"),
    ],
    [
        (205, 188, 285, 188),
        (455, 188, 535, 188),
        (705, 188, 790, 188),
        (120, 226, 120, 295),
        (705, 221, 790, 311),
    ],
    height=410,
)

figure(
    "context-expansion",
    "Expand a matched passage within explicit limits",
    "Optional LangGraph node. Snapshot text only; one pass; no semantic sufficiency claim.",
    [
        (35, 150, 185, "Retrieved seed", "Original rank + revision"),
        (280, 150, 185, "Nearby lines", "Configured window"),
        (525, 150, 185, "Growth budget", "Keep seed if too large"),
        (770, 150, 195, "Compose", "Evidence + saved trace"),
    ],
    [(220, 188, 280, 188), (465, 188, 525, 188), (710, 188, 770, 188)],
    height=280,
)
