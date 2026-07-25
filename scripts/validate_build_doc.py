#!/usr/bin/env python3
"""Validate build_docs/build.yaml — the build progress & context file.

Checks structural integrity so the file cannot silently drift from reality:
  * every module carries the full attribute schema
  * status values are from the allowed vocabulary
  * every pipeline stage references a real module
  * every depends_on / impacts reference resolves
  * the dependency graph is acyclic

Usage:
    python scripts/validate_build_doc.py
    python scripts/validate_build_doc.py --summary
    python scripts/validate_build_doc.py --file path/to/build.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Literal

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

try:
    from pydantic import BaseModel, ValidationError
except ImportError:
    sys.exit("Pydantic is required: pip install pydantic")


Status = Literal["not_started", "in_progress", "completed", "blocked"]
Layer = Literal["frontend", "api", "core_pipeline", "data", "platform"]

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "build_docs" / "build.yaml"


class Port(BaseModel):
    """An input or output of a module."""

    name: str
    type: str
    source: str | None = None
    consumed_by: list[str] | None = None


class Module(BaseModel):
    id: str
    name: str
    layer: Layer
    status: Status
    purpose: str
    description: str
    depends_on: list[str]
    inputs: list[Port]
    outputs: list[Port]
    core_logic: list[str]
    spec_ref: str
    expected_outcome: str
    progress: str
    tests: list[str]
    notes: list[str]
    future_improvements: list[str]


class PipelineStage(BaseModel):
    stage: int
    module_id: str
    payload_in: str
    payload_out: str


class Artifact(BaseModel):
    id: str
    file: str
    status: Status
    what: str
    destination: str
    record_count: int | None = None
    consumed_by: list[str] | None = None


class OpenQuestion(BaseModel):
    id: str
    question: str
    impacts: list[str]
    status: Literal["open", "resolved", "deferred"]
    recommendation: str | None = None


class ChangelogEntry(BaseModel):
    date: Any
    summary: str
    modules_touched: list[str]


class BuildDoc(BaseModel):
    schema_version: int
    project: dict[str, Any]
    invariants: dict[str, Any]
    artifacts: list[Artifact]
    pipeline: list[PipelineStage]
    modules: list[Module]
    open_questions: list[OpenQuestion]
    changelog: list[ChangelogEntry]


def find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Return a dependency cycle as a path, or None if the graph is acyclic."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(graph, WHITE)

    def visit(node: str, path: list[str]) -> list[str] | None:
        colour[node] = GREY
        for dep in graph.get(node, []):
            if dep not in colour:
                continue
            if colour[dep] == GREY:
                return path + [node, dep]
            if colour[dep] == WHITE:
                found = visit(dep, path + [node])
                if found:
                    return found
        colour[node] = BLACK
        return None

    for node in graph:
        if colour[node] == WHITE:
            cycle = visit(node, [])
            if cycle:
                return cycle
    return None


def cross_check(doc: BuildDoc) -> list[str]:
    """Referential-integrity checks that Pydantic alone cannot express."""
    errors: list[str] = []
    module_ids = [m.id for m in doc.modules]
    known = set(module_ids)

    duplicates = {mid for mid in module_ids if module_ids.count(mid) > 1}
    for mid in sorted(duplicates):
        errors.append(f"modules: duplicate id '{mid}'")

    for stage in doc.pipeline:
        if stage.module_id not in known:
            errors.append(
                f"pipeline stage {stage.stage}: unknown module_id '{stage.module_id}'"
            )

    stage_numbers = [s.stage for s in doc.pipeline]
    if stage_numbers != sorted(stage_numbers):
        errors.append("pipeline: stages are not in ascending order")

    for module in doc.modules:
        for dep in module.depends_on:
            if dep not in known:
                errors.append(f"module '{module.id}': unknown depends_on '{dep}'")
        if module.id in module.depends_on:
            errors.append(f"module '{module.id}': depends on itself")

    for question in doc.open_questions:
        for target in question.impacts:
            if target not in known:
                errors.append(
                    f"open_question '{question.id}': unknown impacts target '{target}'"
                )

    for entry in doc.changelog:
        for target in entry.modules_touched:
            if target not in known:
                errors.append(
                    f"changelog {entry.date}: unknown modules_touched '{target}'"
                )

    graph = {m.id: m.depends_on for m in doc.modules}
    cycle = find_cycle(graph)
    if cycle:
        errors.append("modules: dependency cycle " + " -> ".join(cycle))

    return errors


def print_summary(doc: BuildDoc) -> None:
    counts: dict[str, int] = {
        "not_started": 0,
        "in_progress": 0,
        "completed": 0,
        "blocked": 0,
    }
    for module in doc.modules:
        counts[module.status] += 1

    total = len(doc.modules)
    done = counts["completed"]
    pct = (done / total * 100) if total else 0.0
    breakdown = ", ".join(f"{n} {s}" for s, n in counts.items() if n)
    open_count = sum(1 for q in doc.open_questions if q.status == "open")

    print(f"{doc.project['name']} — build {doc.project['build']}")
    print(f"  modules       : {total} ({breakdown})")
    print(f"  completion    : {done}/{total} ({pct:.0f}%)")
    print(f"  artifacts     : {len(doc.artifacts)} "
          f"({sum(1 for a in doc.artifacts if a.status == 'completed')} completed)")
    print(f"  pipeline      : {len(doc.pipeline)} stages")
    print(f"  open questions: {open_count}")

    active = [m for m in doc.modules if m.status in ("in_progress", "blocked")]
    if active:
        print("\n  Active:")
        for module in active:
            print(f"    [{module.status}] {module.id} — {module.name}")

    ready = [
        m
        for m in doc.modules
        if m.status == "not_started"
        and all(
            d.status == "completed"
            for d in doc.modules
            if d.id in m.depends_on
        )
    ]
    if ready:
        print("\n  Unblocked (dependencies satisfied):")
        for module in ready:
            deps = ", ".join(module.depends_on) or "none"
            print(f"    {module.id} (depends_on: {deps})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--summary", action="store_true",
                        help="print the progress dashboard")
    args = parser.parse_args()

    if not args.file.is_file():
        print(f"FAIL: {args.file} not found", file=sys.stderr)
        return 1

    try:
        raw = yaml.safe_load(args.file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"FAIL: {args.file} is not valid YAML\n{exc}", file=sys.stderr)
        return 1

    try:
        doc = BuildDoc.model_validate(raw)
    except ValidationError as exc:
        print(f"FAIL: {args.file} does not match the schema", file=sys.stderr)
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            print(f"  {loc}: {err['msg']}", file=sys.stderr)
        return 1

    errors = cross_check(doc)
    if errors:
        print(f"FAIL: {args.file} has {len(errors)} reference error(s)",
              file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    print(f"OK: {args.file.name} is valid "
          f"({len(doc.modules)} modules, {len(doc.pipeline)} pipeline stages)")
    if args.summary:
        print()
        print_summary(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
