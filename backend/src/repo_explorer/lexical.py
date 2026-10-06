"""Lexical tokenization helpers; these do not parse code or resolve symbols."""

import re


def code_identifier_tokens(text: str) -> list[str]:
    """Share components and a compact spelling across snake, camel, and Pascal case."""
    tokens = []
    for word in re.findall(r"\b\w+\b", text):
        separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", word)
        separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", separated)
        parts = separated.replace("_", " ").lower().split()
        tokens.extend(part for part in parts if len(part) > 1)
        if len(parts) > 1:
            tokens.append("".join(parts))
    return tokens
