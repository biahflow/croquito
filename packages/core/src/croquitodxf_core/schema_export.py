"""Exporta o JSON Schema canônico consumido pelos demais runtimes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from croquitodxf_core.models import SCENE_SCHEMA_VERSION, SceneRevision


def schema_text() -> str:
    schema = SceneRevision.model_json_schema()
    schema["$id"] = f"https://schemas.croquitodxf.local/scene/{SCENE_SCHEMA_VERSION}.json"
    schema["title"] = "CroquiToDXF Scene Revision"
    return f"{json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True)}\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--check", type=Path)
    args = parser.parse_args()
    expected = schema_text()

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(expected, encoding="utf-8")
        return 0

    current = args.check.read_text(encoding="utf-8") if args.check.exists() else ""
    if current != expected:
        print(f"Contrato desatualizado: {args.check}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
