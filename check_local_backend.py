from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.model_factory import create_adapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--adapter', default='heuristic')
    parser.add_argument('--endpoint', default=None)
    parser.add_argument('--model', default=None)
    parser.add_argument('--artifact', default=None)
    parser.add_argument('--command-template', default=None)
    parser.add_argument('--timeout-seconds', type=float, default=None)
    parser.add_argument('--first-output-timeout-seconds', type=float, default=None)
    parser.add_argument('--idle-timeout-seconds', type=float, default=None)
    parser.add_argument('--max-output-bytes', type=int, default=None)
    # native_llamafile adapter args
    parser.add_argument('--llamafile-path', default=None, help='Path to assembled llamafile binary')
    parser.add_argument('--llamafile-model', default=None, help='Path to GGUF model file')
    parser.add_argument('--loading-timeout', type=float, default=None, help='Silence budget (s) before first token during model load')
    parser.add_argument('--inactivity-timeout', type=float, default=None, help='Silence budget (s) between tokens during generation')
    parser.add_argument('--max-tokens', type=int, default=None, help='Max tokens to generate (-n flag)')
    parser.add_argument('--temperature', type=float, default=None, help='Sampling temperature')
    parser.add_argument('--require-live-backend', action='store_true')
    parser.add_argument('--smoke-prompt', default='Reply with the single word READY.')
    args = parser.parse_args()

    build_kwargs = {}
    if args.endpoint:
        build_kwargs['endpoint'] = args.endpoint
    if args.model:
        build_kwargs['model'] = args.model
    if args.artifact:
        build_kwargs['artifact'] = args.artifact
    if args.command_template:
        build_kwargs['command_template'] = args.command_template
    if args.timeout_seconds is not None:
        build_kwargs['timeout_seconds'] = args.timeout_seconds
    if args.first_output_timeout_seconds is not None:
        build_kwargs['first_output_timeout_seconds'] = args.first_output_timeout_seconds
    if args.idle_timeout_seconds is not None:
        build_kwargs['idle_timeout_seconds'] = args.idle_timeout_seconds
    if args.max_output_bytes is not None:
        build_kwargs['max_output_bytes'] = args.max_output_bytes
    # native_llamafile kwargs
    if args.llamafile_path is not None:
        build_kwargs['llamafile_path'] = args.llamafile_path
    if args.llamafile_model is not None:
        build_kwargs['model_path'] = args.llamafile_model
    if args.loading_timeout is not None:
        build_kwargs['loading_timeout_s'] = args.loading_timeout
    if args.inactivity_timeout is not None:
        build_kwargs['inactivity_timeout_s'] = args.inactivity_timeout
    if args.max_tokens is not None:
        build_kwargs['max_tokens'] = args.max_tokens
    if args.temperature is not None:
        build_kwargs['temperature'] = args.temperature

    adapter = create_adapter(args.adapter, **build_kwargs)
    health = adapter.healthcheck()
    smoke = None
    ok = bool(health.get('ok'))
    if ok:
        if hasattr(adapter, 'smokecheck'):
            smoke = adapter.smokecheck(prompt=args.smoke_prompt)
        else:
            response = adapter.generate(args.smoke_prompt, system_prompt='You are a backend smokecheck agent.')
            smoke = {'ok': response.ok and bool(response.text.strip()), 'text': response.text[:120], 'error': response.error, 'latency_ms': response.latency_ms, 'finish_reason': response.finish_reason}
        ok = ok and bool(smoke.get('ok'))

    if args.require_live_backend and getattr(adapter, 'promotable', True) is False:
        ok = False
        if smoke is None:
            smoke = {}
        smoke['error'] = 'Synthetic baseline adapter does not satisfy require-live-backend.'

    payload = {
        'ok': ok,
        'adapter': args.adapter,
        'identity': adapter.backend_identity(),
        'health': health,
        'smoke': smoke,
        'require_live_backend': args.require_live_backend,
    }
    print(json.dumps(payload, indent=2))
    if not ok:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
