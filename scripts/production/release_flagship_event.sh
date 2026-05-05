#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ROOT_DIR}/configs/production/real_gguf_build.env"

[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 2; }
# shellcheck source=/dev/null
source "$ENV_FILE"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVENT_DIR="$ROOT_DIR/reports/upstream_events/${FLAGSHIP_MODEL_NAME}_${FLAGSHIP_VERSION}_$STAMP"
mkdir -p "$EVENT_DIR"

started="$EVENT_DIR/release_started.json"
python3 "$ROOT_DIR/scripts/production/write_upstream_event_manifest.py" \
  --event-type release \
  --flagship-model-name "$FLAGSHIP_MODEL_NAME" \
  --flagship-version "$FLAGSHIP_VERSION" \
  --model-family "$MODEL_FAMILY" \
  --status started \
  --inputs-json "{\"env_file\": \"$ENV_FILE\"}" \
  --outputs-json "{\"event_dir\": \"$EVENT_DIR\"}" \
  --notes-json '["starting release preflight"]' \
  --release-candidate \
  --output "$started" >/dev/null

"$ROOT_DIR/scripts/production/validate_real_gguf_build.sh" "$ENV_FILE"
"$ROOT_DIR/scripts/production/build_real_gguf_handoff.sh"

LATEST_MANIFEST="$(ls -1t "$ROOT_DIR"/reports/real_gguf_build/*/real_gguf_manifest.json | head -n 1)"
[[ -f "$LATEST_MANIFEST" ]] || { echo "Could not locate real_gguf_manifest.json" >&2; exit 9; }

REG_ARGS=()
if [[ -n "${COGNITION_LLAMAFILE_FILE:-}" && -f "${COGNITION_LLAMAFILE_FILE:-}" ]]; then
  REG_ARGS=(--llamafile "$COGNITION_LLAMAFILE_FILE")
else
  REG_ARGS=(--gguf "$COGNITION_QUANTIZED_MODEL_FILE" --binary "$COGNITION_RUNTIME_BINARY")
fi

"$ROOT_DIR/scripts/operator/register_real_gguf_artifact.sh" "${REG_ARGS[@]}"
"$ROOT_DIR/scripts/operator/validate_flagship_runtime.sh"

python3 "$ROOT_DIR/scripts/production/write_upstream_event_manifest.py" \
  --event-type release \
  --flagship-model-name "$FLAGSHIP_MODEL_NAME" \
  --flagship-version "$FLAGSHIP_VERSION" \
  --model-family "$MODEL_FAMILY" \
  --status passed \
  --inputs-json "{\"env_file\": \"$ENV_FILE\", \"artifact_manifest\": \"$LATEST_MANIFEST\"}" \
  --outputs-json "{\"runtime_env\": \"$ROOT_DIR/.env.direct-runtime\", \"event_dir\": \"$EVENT_DIR\"}" \
  --notes-json '["release preflight passed", "artifact registered", "runtime validated"]' \
  --release-candidate \
  --output "$EVENT_DIR/release_passed.json" >/dev/null

printf 'Flagship release validation complete. Event dir: %s\n' "$EVENT_DIR"
