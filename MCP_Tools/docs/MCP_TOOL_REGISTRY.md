# ARC-Neuron MCP Tool Registry

This registry summarizes MCP tools exposed by the ARC-Neuron LLMBuilder governed tool layer.

## Dataset

- `dataset.scan`
- `dataset.validate_jsonl`
- `dataset.normalize`
- `dataset.deduplicate`
- `dataset.quality_score`
- `dataset.license_check`
- `dataset.pii_scan`
- `dataset.split_train_eval`

## Repository

- `repo.read_tree`
- `repo.search`
- `repo.read_file`
- `repo.create_patch`
- `repo.apply_patch_sandbox`
- `repo.run_tests`
- `repo.generate_diff_receipt`
- `repo.commit_prepare`

## Evaluation

- `eval.run_benchmark`
- `eval.compare_candidates`
- `eval.score_regression`
- `eval.score_grounding`
- `eval.generate_report`

## Model

- `model.train_smoke`
- `model.train_candidate`
- `model.export_gguf`
- `model.write_manifest`
- `model.promote_candidate`
- `model.rollback`

## Memory / Archive

- `memory.write_receipt`
- `memory.search_receipts`
- `memory.link_artifact`
- `memory.export_audit_bundle`

## Business

- `business.ingest_docs`
- `business.extract_sop`
- `business.generate_ticket_response`
- `business.create_report`

## Artifact / Release

- `artifact.package_model`
- `artifact.verify_hashes`
- `artifact.release_notes`
