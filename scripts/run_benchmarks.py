from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def load_tasks(folder: Path) -> int:
    total = 0
    for file in sorted(folder.rglob("*.jsonl")):
        with file.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    json.loads(line)
                    total += 1
    return total


def main() -> None:
    bench_root = ROOT / "benchmarks"
    summary: dict[str, int] = {}

    # Count root-level benchmark shards as well as capability folders.
    # Earlier versions only counted child directories, which hid root JSONL
    # lanes such as memory-continuity tasks from this public inventory while
    # scripts/validate_repo.py correctly counted them.
    root_total = load_tasks(bench_root)
    nested_total = 0
    for child in sorted(bench_root.iterdir()):
        if child.is_dir():
            count = load_tasks(child)
            summary[child.name] = count
            nested_total += count

    root_shard_count = root_total - nested_total
    if root_shard_count:
        summary["_root_jsonl_shards"] = root_shard_count

    print(json.dumps({"benchmark_task_counts": summary, "benchmark_total_tasks": root_total}, indent=2))


if __name__ == "__main__":
    main()
