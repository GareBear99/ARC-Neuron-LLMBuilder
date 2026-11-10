// Unit tests for single-model routing (worker.js resolveModel +
// PING_MODELS allowlist) — pure logic, no network, no wrangler.
// Run: node models.test.mjs   (Node >= 18, no dependencies.)
// Gary's decision (2026-11-06): ONLY Llama 3.2 1B is on the
// allowlist and selectable. Neurons (10,000/day, Cloudflare free
// tier) are the only quota that matters for scaling, and 1B is the
// only model we can support at the user numbers we want within
// that budget. The other 33 models were removed from the
// allowlist and from the Lucid client's dropdown. The tests pin
// the routing contract — if the allowlist changes, update
// PING_MODELS in worker.js and the count below.

import assert from 'node:assert/strict';
import { PING_MODELS, resolveModel } from './worker.js';

const DEFAULT = '@cf/meta/llama-3.2-1b-instruct';
const ENV = { MODEL: DEFAULT };

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok - ${name}`);
}

// --- allowlist shape ---
check('allowlist has exactly 1 model — the default 1B, no duplicates', () => {
  assert.equal(PING_MODELS.length, 1);
  assert.equal(new Set(PING_MODELS).size, 1);
  for (const m of PING_MODELS) {
    assert.equal(typeof m, 'string');
    assert.ok(m.startsWith('@cf/'), m);
  }
  assert.ok(PING_MODELS.includes(DEFAULT));
});

check('allowlist excludes the removed models (70B, GPT-OSS, DeepSeek, Qwen, Gemma, Mistral, Kimi, Nemotron, Granite, Apertus, EuroLLM, GLM, PhoneLLM)', () => {
  for (const m of [
    '@cf/meta/llama-3.3-70b-instruct-fp8-fast',
    '@cf/meta/llama-4-scout-17b-16e-instruct',
    '@cf/meta/llama-3.2-11b-vision-instruct',
    '@cf/meta/llama-3.1-8b-instruct-fp8',
    '@cf/meta/llama-3.2-3b-instruct',
    '@cf/meta-llama/llama-2-7b-chat-hf-lora',
    '@cf/openai/gpt-oss-120b',
    '@cf/openai/gpt-oss-20b',
    '@cf/deepseek-ai/deepseek-r1-distill-qwen-32b',
    '@cf/deepseek-ai/deepseek-v4-flash-0731',
    '@cf/deepseek-ai/deepseek-v4-pro-0813',
    '@cf/deepseek-ai/deepseek-v4.1-flash-1017',
    '@cf/qwen/qwen2.5-coder-32b-instruct',
    '@cf/qwen/qwq-32b',
    '@cf/qwen/qwen3-30b-a3b-fp8',
    '@cf/qwen/qwen3.8-27b',
    '@cf/google/gemma-4-26b-a4b-it',
    '@cf/google/gemma-7b-it-lora',
    '@cf/google/gemma-2b-it-lora',
    '@cf/aisingapore/gemma-sea-lion-v4-27b-it',
    '@cf/mistral/mistral-7b-instruct-v0.2-lora',
    '@cf/mistralai/mistral-small-3.1-24b-instruct',
    '@cf/moonshotai/kimi-k2.7-code',
    '@cf/moonshotai/kimi-k2.6',
    '@cf/nvidia/nemotron-3-120b-a12b',
    '@cf/ibm-granite/granite-4.0-h-micro',
    '@cf/swiss-ai/apertus-v1.5-8b',
    '@cf/utter-project/eurollm-9b-it',
    '@cf/zai-org/glm-5.3-flash',
    '@cf/zai-org/glm-4.7-flash',
    '@cf/zai-org/glm-5.2',
    '@cf/zai-org/glm-5.3',
    '@cf/daily-co/phonellm-mini-alpha-2',
  ]) {
    assert.ok(!PING_MODELS.includes(m), m);
  }
});

check('allowlist excludes the non-chat models (Clef/Clairic decision + extraction, Llama Guard classifier)', () => {
  for (const m of [
    '@cf/cloudflare/clairic',
    '@cf/cloudflare/clef',
    '@cf/cloudflare/clef-flash',
    '@cf/cloudflare/clef-omni',
    '@cf/meta/llama-guard-3-8b',
  ]) {
    assert.ok(!PING_MODELS.includes(m), m);
  }
});

// --- resolveModel: allowlisted model is honoured ---
check('the allowlisted 1B model is served when requested', () => {
  assert.equal(resolveModel({ model: DEFAULT }, ENV), DEFAULT);
});

// --- resolveModel: fallback to the configured default ---
check('absent body.model falls back to env.MODEL', () => {
  assert.equal(resolveModel({}, ENV), DEFAULT);
  assert.equal(resolveModel({ messages: [] }, ENV), DEFAULT);
  assert.equal(resolveModel(null, ENV), DEFAULT);
  assert.equal(resolveModel(undefined, ENV), DEFAULT);
});

check('unknown body.model falls back to env.MODEL, never passed through', () => {
  assert.equal(resolveModel({ model: '@cf/meta/llama-9-999b-instruct' }, ENV), DEFAULT);
  assert.equal(resolveModel({ model: 'gpt-4' }, ENV), DEFAULT);
  assert.equal(resolveModel({ model: '' }, ENV), DEFAULT);
});

check('non-string body.model falls back to env.MODEL', () => {
  assert.equal(resolveModel({ model: 42 }, ENV), DEFAULT);
  assert.equal(resolveModel({ model: ['@cf/meta/llama-3.2-1b-instruct'] }, ENV), DEFAULT);
  assert.equal(resolveModel({ model: null }, ENV), DEFAULT);
});

check('near-miss strings fall back (exact match only — no trimming, no case folding)', () => {
  assert.equal(resolveModel({ model: '@cf/meta/llama-3.2-1b-instruct ' }, ENV), DEFAULT);
  assert.equal(resolveModel({ model: '@CF/META/LLAMA-3.2-1B-INSTRUCT' }, ENV), DEFAULT);
  assert.equal(resolveModel({ model: ' @cf/meta/llama-3.2-1b-instruct' }, ENV), DEFAULT);
});

check('removed models now fall back to the default', () => {
  assert.equal(resolveModel({ model: '@cf/meta/llama-3.3-70b-instruct-fp8-fast' }, ENV), DEFAULT);
  assert.equal(resolveModel({ model: '@cf/openai/gpt-oss-120b' }, ENV), DEFAULT);
  assert.equal(resolveModel({ model: '@cf/qwen/qwq-32b' }, ENV), DEFAULT);
  assert.equal(resolveModel({ model: '@cf/deepseek-ai/deepseek-r1-distill-qwen-32b' }, ENV), DEFAULT);
});

check('excluded non-chat models fall back to the default', () => {
  assert.equal(resolveModel({ model: '@cf/cloudflare/clef' }, ENV), DEFAULT);
  assert.equal(resolveModel({ model: '@cf/cloudflare/clairic' }, ENV), DEFAULT);
  assert.equal(resolveModel({ model: '@cf/meta/llama-guard-3-8b' }, ENV), DEFAULT);
});

check('no env.MODEL falls back to the built-in default', () => {
  assert.equal(resolveModel({}, {}), DEFAULT);
  assert.equal(resolveModel({ model: '@cf/meta/unknown' }, {}), DEFAULT);
  assert.equal(resolveModel({ model: '@cf/qwen/qwq-32b' }, {}), DEFAULT);
});

check('env.MODEL override is honoured as the fallback', () => {
  // A synthetic id (not a real model) proves the mechanism: the
  // fallback returns env.MODEL verbatim when it is set.
  const env = { MODEL: '@cf/test/override-model' };
  assert.equal(resolveModel({}, env), '@cf/test/override-model');
  assert.equal(resolveModel({ model: 'nope' }, env), '@cf/test/override-model');
});

console.log(`\n${passed} model routing tests passed, 0 failed.`);
