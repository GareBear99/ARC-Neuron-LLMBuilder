"""hello.py — the smallest possible governed interaction.

Usage:
    python3 examples/hello.py
    python3 examples/hello.py "Your custom prompt here"

What it does:
    1. Loads the current incumbent (`arc_governed_v6_conversation`).
    2. Runs your prompt through the canonical conversation pipeline
       (adapter → receipt → Omnibinary mirror → training-eligibility tag).
    3. Prints the response + the receipt ID so you can re-retrieve the
       exact event from the Omnibinary ledger later.

No training. No gate. Just one governed conversation turn.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.exemplar_adapter import ExemplarAdapter
from runtime.conversation_pipeline import ConversationPipeline


def main() -> None:
    prompt = (
        " ".join(sys.argv[1:])
        or "Critique a plan that ships without a rollback path."
    )

    incumbent = ROOT / "exports" / "candidates" / "arc_governed_v6_conversation" / "exemplar_train" / "exemplar_model.json"
    if not incumbent.exists():
        print(f"Incumbent artifact not found at {incumbent}")
        print("Run: python3 scripts/training/train_arc_native_candidate.py --candidate my_first --tier small --steps 300")
        sys.exit(1)

    adapter = ExemplarAdapter(artifact=str(incumbent), top_k=3)
    pipeline = ConversationPipeline(
        adapter,
        store_path=ROOT / "artifacts" / "omnibinary" / "arc_conversations.obin",
        conversation_id="hello",
    )

    print(f"\n→ {prompt}\n")
    record = pipeline.run_conversation(prompt)
    print(record.response_text)
    print()
    print(f"receipt_id:          {record.receipt_id}")
    print(f"turn_id:             {record.turn_id}")
    print(f"training_eligible:   {record.training_eligible}")
    print(f"training_score:      {record.training_score:.4f}")
    print(f"latency_ms:          {record.latency_ms}")


if __name__ == "__main__":
    main()
