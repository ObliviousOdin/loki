"""Fail closed if an inherited job can execute inside the Loki repository."""
from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_GUARD = "github.repository == 'NousResearch/hermes-agent'"
LOKI_GUARD = "github.repository == 'ObliviousOdin/loki'"


def main() -> None:
    count = 0
    for path in sorted((ROOT / ".github/workflows").glob("*.y*ml")):
        data = YAML(typ="safe").load(path.read_text(encoding="utf-8-sig"))
        expected = LOKI_GUARD if path.name.startswith("loki-") else UPSTREAM_GUARD
        for name, job in data["jobs"].items():
            condition = str(job.get("if", "")).strip().removeprefix("${{").removesuffix("}}").strip()
            if expected not in condition:
                raise SystemExit(f"Missing repository ownership guard: {path.name}:{name}")
            if not path.name.startswith("loki-") and not condition.startswith(expected):
                raise SystemExit(f"Upstream ownership must be the outer AND guard: {path.name}:{name}")
            count += 1
    print(f"Verified repository ownership guards for {count} jobs")


if __name__ == "__main__":
    main()
