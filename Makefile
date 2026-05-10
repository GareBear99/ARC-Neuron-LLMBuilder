.PHONY: validate test counts candidate-gate backend-check bundle model-card \
        promote full-loop pipeline bootstrap-keys bundle-candidate \
        native-tiny native-small verify-store production-verify

# ── validation ────────────────────────────────────────────────────────────────
validate:
	python3 cognition_lab.py validate

test:
	python3 -m pytest tests -q

counts:
	python3 cognition_lab.py count-data
	python3 cognition_lab.py count-benchmarks

# ── backend / gate ────────────────────────────────────────────────────────────
candidate-gate:
	python3 cognition_lab.py candidate-gate

backend-check:
	python3 cognition_lab.py backend-check

# ── model operations ──────────────────────────────────────────────────────────
bundle:
	python3 scripts/execution/generate_release_bundle.py

model-card:
	python3 scripts/execution/generate_model_card.py --model-name heuristic_minimal_doctrine --adapter heuristic

readiness:
	python scripts/execution/generate_readiness_report.py

smoke-local:
	python scripts/execution/smoke_local_candidate.py

# ── ARC-native training ───────────────────────────────────────────────────────
native-tiny:
	python3 scripts/training/train_arc_native_candidate.py \
	  --candidate arc_native_tiny --tier tiny --steps 200

native-small:
	python3 scripts/training/train_arc_native_candidate.py \
	  --candidate arc_native_small --tier small --steps 300

# ── canonical full loop ───────────────────────────────────────────────────────
# The complete governed cycle: seed terms → train → benchmark → score → gate → bundle → verify
full-loop:
	@echo "[arc] ═══════════════════════════════════════════"
	@echo "[arc]  ARC FULL GOVERNED LOOP"
	@echo "[arc] ═══════════════════════════════════════════"
	@echo "[arc] Step 1: Seed terminology"
	python3 runtime/terminology.py --correct "omnibinary" "indexed binary ledger supporting O(1) event lookup"
	python3 runtime/terminology.py --correct "floor model" "frozen baseline every candidate must beat"
	python3 runtime/terminology.py --dump
	@echo "[arc] Step 2: Train candidate"
	python3 scripts/training/train_arc_native_candidate.py \
	  --candidate arc_loop_candidate --tier small --steps 300
	@echo "[arc] Step 3: Benchmark"
	python3 scripts/execution/run_model_benchmarks.py \
	  --adapter exemplar \
	  --artifact exports/candidates/arc_loop_candidate/exemplar_train/exemplar_model.json \
	  --output results/arc_loop_candidate_model_outputs.jsonl
	@echo "[arc] Step 4: Score"
	python3 scripts/execution/score_benchmark_outputs.py \
	  --input results/arc_loop_candidate_model_outputs.jsonl \
	  --output results/arc_loop_candidate_scored_outputs.json
	@echo "[arc] Step 5: Gate v2"
	python3 scripts/execution/promote_candidate.py \
	  --scored results/arc_loop_candidate_scored_outputs.json \
	  --model-name arc_loop_candidate \
	  --candidate arc_loop_candidate
	@echo "[arc] Step 6: Update floor from new incumbent if promoted"
	python3 runtime/floor_model.py --set-floor --from-scoreboard --note "auto-set after full-loop"
	@echo "[arc] Step 7: Verify Omnibinary store"
	python3 -c "import sys; sys.path.insert(0,'.'); from pathlib import Path; from runtime.learning_spine import OmnibinaryStore; import json; print(json.dumps(OmnibinaryStore(Path('artifacts/omnibinary/arc_conversations.obin')).verify(), indent=2))"
	@echo "[arc] Loop complete. Check reports/promotion_decision.json"

# ── conversation pipeline ─────────────────────────────────────────────────────
pipeline:
	@echo "[arc] Running one conversation through the canonical pipeline..."
	python3 -c " \
import sys; sys.path.insert(0, '.'); \
from adapters.heuristic_adapter import HeuristicAdapter; \
from runtime.conversation_pipeline import ConversationPipeline; \
p = ConversationPipeline(HeuristicAdapter()); \
r = p.run_conversation('Plan the next step for the ARC system.'); \
import json; print(json.dumps({'ok': r.response_ok, 'eligible': r.training_eligible, 'score': r.training_score, 'chars': len(r.response_text)}, indent=2)); \
print(p.store_stats()) \
"

# ── security ops ──────────────────────────────────────────────────────────────
bootstrap-keys:
	python3 scripts/ops/bootstrap_keys.py

# ── archive ops ───────────────────────────────────────────────────────────────
bundle-candidate:
	@if [ -z "$(CANDIDATE)" ]; then echo "Usage: make bundle-candidate CANDIDATE=<name>"; exit 1; fi
	python3 scripts/ops/bundle_promoted_candidate.py --candidate $(CANDIDATE)

# ── omnibinary store health ───────────────────────────────────────────────────
verify-store:
	python3 -c " \
import sys; sys.path.insert(0, '.'); \
from pathlib import Path; \
from runtime.learning_spine import OmnibinaryStore; \
store = OmnibinaryStore(Path('artifacts/omnibinary/arc_conversations.obin')); \
import json; print(json.dumps(store.verify(), indent=2)) \
"

# ── training stubs (external base models) ────────────────────────────────────
prepare-corpus:
	python scripts/training/prepare_distillation_corpus.py

training-readiness:
	python scripts/execution/run_training_readiness_gate.py

train-candidate-stub:
	python scripts/training/train_lora_candidate.py --candidate qwen3_coder_480b_a35b_instruct

preference-candidate-stub:
	python scripts/training/train_preference_candidate.py --candidate qwen3_coder_480b_a35b_instruct

merge-candidate-stub:
	python scripts/training/merge_adapters_stub.py --candidate qwen3_coder_480b_a35b_instruct

export-gguf-candidate-stub:
	python scripts/training/export_gguf_candidate.py --candidate qwen3_coder_480b_a35b_instruct

distillation-counts:
	python3 scripts/training/report_distillation_counts.py

run-day0:
	bash scripts/operator/run_day0_candidate.sh

run-day1-stub:
	bash scripts/operator/run_day1_shaping_stub.sh

run-day2-stub:
	bash scripts/operator/run_day2_export_stub.sh


# ── production handoff verification ──────────────────────────────────────────
production-verify:
	python3 scripts/production_verify.py

seo-validate:
	python scripts/seo_validate.py
