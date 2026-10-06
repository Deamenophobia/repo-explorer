import json
from pathlib import Path


def publish_record(destination: Path, payload: dict) -> None:
    """Publish a JSON record after preparing its complete payload."""
    serialized = json.dumps(payload, sort_keys=True)
    pending = destination.with_suffix(".pending")
    pending.write_text(serialized, encoding="utf-8")
    pending.replace(destination)
