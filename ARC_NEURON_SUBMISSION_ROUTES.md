# ARC-Neuron Submission Routes

## Current submission status

### Submitted PRs

| # | Target list | Class / category | Placement used | PR |
|---:|---|---|---|---|
| 1 | Awesome Production Machine Learning | Production ML / MLOps / model lifecycle | Model, Data & Experiment Management near ZenML | https://github.com/EthicalML/awesome-production-machine-learning/pull/770 |
| 2 | Awesome MLOps | MLOps / model lifecycle | Model Lifecycle near MLflow | https://github.com/kelvins/awesome-mlops/pull/199 |
| 3 | Awesome LLMOps | LLMOps / model lifecycle / evaluation | LLMOps lifecycle area near MLflow / Polyaxon / Seldon-Core | https://github.com/InftyAI/Awesome-LLMOps/pull/429 |
| 4 | Awesome Local LLM | Local LLM tools / evaluation / training | Local LLM tools section; testing/evaluation or training/fine-tuning fit | https://github.com/rafska/awesome-local-llm/pull/72 |
| 5 | Awesome Local AI | Local AI tools / local-first control | Tools section near Local AI Planning Tool | https://github.com/msb-msb/awesome-local-ai/pull/6 |

---

## Core project links

- **Main repo:** https://github.com/GareBear99/ARC-Neuron-LLMBuilder
- **Protected v1.0.0 release baseline:** https://github.com/GareBear99/arc-neuron-llmbuilder-v1.0.0

---

## Standard submission entry

```md
- [ARC-Neuron LLMBuilder](https://github.com/GareBear99/ARC-Neuron-LLMBuilder) - Local-first AI model lifecycle framework for deterministic small-model promotion, benchmark receipts, candidate/incumbent comparison, archive-ready lineage, and governed AI improvement.
```

## Star-badge entry style

```md
* [ARC-Neuron LLMBuilder](https://github.com/GareBear99/ARC-Neuron-LLMBuilder) ![](https://img.shields.io/github/stars/GareBear99/ARC-Neuron-LLMBuilder.svg?cacheSeconds=86400) - Local-first AI model lifecycle framework for deterministic small-model promotion, benchmark receipts, candidate/incumbent comparison, archive-ready lineage, and governed AI improvement.
```

## Awesome-LLMOps badge style

```md
* **[ARC-Neuron LLMBuilder](https://github.com/GareBear99/ARC-Neuron-LLMBuilder)**: Local-first AI model lifecycle framework for deterministic small-model promotion, benchmark receipts, candidate/incumbent comparison, archive-ready lineage, and governed AI improvement. ![Stars](https://img.shields.io/github/stars/GareBear99/ARC-Neuron-LLMBuilder.svg?style=flat&color=green) ![Contributors](https://img.shields.io/github/contributors/GareBear99/ARC-Neuron-LLMBuilder?color=green) ![LastCommit](https://img.shields.io/github/last-commit/GareBear99/ARC-Neuron-LLMBuilder?color=green)
```

---

# Remaining submission routes

## Highest priority remaining

### 6. Awesome Open MLOps

- **Repo:** https://github.com/fuzzylabs/awesome-open-mlops
- **Local folder:** `~/GITHUB_WORK/arc-neuron-submissions/targets/awesome-open-mlops`
- **Best class:** Open MLOps / model registry / metadata / lifecycle
- **Placement angle:** model lifecycle, metadata, registry-adjacent, reproducible promotion
- **Suggested section:** model registry, experiment tracking, metadata, lifecycle, or similar
- **Status:** prepared locally, not submitted yet
- **Next command:**

```bash
cd ~/GITHUB_WORK/arc-neuron-submissions/targets/awesome-open-mlops
grep -nEi "model|registry|metadata|lifecycle|mlops|experiment|governance|version|tracking|tools" README.md | head -120
```

### 7. Awesome Trustworthy Deep Learning

- **Repo:** https://github.com/MinghuiChen43/awesome-trustworthy-deep-learning
- **Local folder:** `~/GITHUB_WORK/arc-neuron-submissions/targets/awesome-trustworthy-deep-learning`
- **Best class:** trustworthy AI / provenance / evidence-first governance
- **Placement angle:** deterministic receipts, model regression prevention, failure preservation, benchmark-gated promotion
- **Suggested section:** robustness, reliability, safety, model governance, trustworthy ML tools, or related tooling section
- **Status:** prepared locally, not submitted yet
- **Next command:**

```bash
cd ~/GITHUB_WORK/arc-neuron-submissions/targets/awesome-trustworthy-deep-learning
grep -nEi "tool|trust|robust|safety|security|governance|provenance|evaluation|benchmark|reproducible|reliability|validation" README.md | head -160
```

### 8. Awesome Data Management

- **Repo:** https://github.com/awesome-mlops/awesome-data-management
- **Local folder:** `~/GITHUB_WORK/arc-neuron-submissions/targets/awesome-data-management`
- **Best class:** dataset lineage / data governance / truth-pack ingestion
- **Placement angle:** dataset lineage and model lifecycle receipts
- **Suggested section:** data versioning, metadata, lineage, governance, dataset tracking
- **Status:** prepared locally, not submitted yet
- **Next command:**

```bash
cd ~/GITHUB_WORK/arc-neuron-submissions/targets/awesome-data-management
grep -nEi "data|metadata|lineage|version|governance|catalog|provenance|tracking|mlops|model" README.md | head -120
```

## Secondary priority

### 9. Awesome Machine Learning

- **Repo:** https://github.com/josephmisiti/awesome-machine-learning
- **Local folder:** `~/GITHUB_WORK/arc-neuron-submissions/targets/awesome-machine-learning`
- **Best class:** general ML tooling / Python / model lifecycle
- **Placement angle:** AI model lifecycle framework for local reproducible model promotion
- **Suggested section:** Python machine learning, MLOps, model management, experiment tracking, or tools
- **Status:** prepared locally, not submitted yet
- **Next command:**

```bash
cd ~/GITHUB_WORK/arc-neuron-submissions/targets/awesome-machine-learning
grep -nEi "python|model|mlops|lifecycle|experiment|tracking|management|tools|version|benchmark" README.md | head -160
```

### 10. Awesome Python Machine Learning

- **Repo:** https://github.com/sorend/awesome-python-machine-learning
- **Local folder:** `~/GITHUB_WORK/arc-neuron-submissions/targets/awesome-python-machine-learning`
- **Best class:** Python ML tools
- **Placement angle:** Python-based local AI lifecycle governance
- **Suggested section:** model lifecycle, ML tools, experiment tracking, or Python AI tooling
- **Status:** prepared locally, not submitted yet
- **Next command:**

```bash
cd ~/GITHUB_WORK/arc-neuron-submissions/targets/awesome-python-machine-learning
grep -nEi "python|model|machine learning|tools|experiment|tracking|lifecycle|version|mlops" README.md | head -120
```

---

# Additional future routes

These were not included in the first 10 cloned targets, but they are worth submitting after the highest-fit routes are handled.

## Local / LLM ecosystem lists

### Awesome AI

- **Repo:** https://github.com/openbestof/awesome-ai
- **Class:** open-source AI tools
- **Placement angle:** governed local AI lifecycle framework
- **Strength:** medium
- **Submit after:** open MLOps and local lists

### Awesome LLM

- **Repo:** https://github.com/hannibal046/awesome-llm
- **Class:** LLM tools and resources
- **Placement angle:** LLM lifecycle governance, benchmark receipts, local model improvement
- **Strength:** medium
- **Submit after:** adding GOVERNANCE.md / ANCF.md improves acceptance odds

### Awesome Efficient LLM

- **Repo:** https://github.com/horseee/Awesome-Efficient-LLM
- **Class:** efficient LLM / small model lifecycle
- **Placement angle:** higher usefulness per parameter through governed small-model promotion
- **Strength:** medium now, high after real trainer wiring and benchmark receipts

## Agent / app lists

These are weaker fits right now. Submit later when ARC-Neuron has runnable apps, demos, or agent-facing workflows.

### Awesome LLM Agents

- **Repo:** https://github.com/kaushikb11/awesome-llm-agents
- **Class:** agents
- **Placement angle:** governed agent/model lifecycle only after agent workflow exists
- **Strength:** low-to-medium right now

### Awesome LLM Apps

- **Repo:** https://github.com/Shubhamsaboo/awesome-llm-apps
- **Class:** runnable LLM apps
- **Placement angle:** only after demo app or local lifecycle UI is available
- **Strength:** low right now

---

# Recommended submission order from here

```text
6. awesome-open-mlops
7. awesome-trustworthy-deep-learning
8. awesome-data-management
9. awesome-machine-learning
10. awesome-python-machine-learning
11. awesome-ai
12. awesome-llm
13. Awesome-Efficient-LLM
14. agent/app lists only after runnable demos
```

---

# Best class positioning by list type

| Class | Best wording | Current fit |
|---|---|---|
| Production ML | Local-first model lifecycle framework | Strong |
| MLOps | Deterministic small-model promotion and receipts | Strong |
| LLMOps | LLM lifecycle governance and benchmark receipts | Strong |
| Local LLM | Local model improvement governance | Strong |
| Local AI | Privacy/local-first lifecycle control | Strong |
| Open MLOps | Metadata, model lineage, model registry-adjacent lifecycle | Strong |
| Trustworthy AI | Evidence-first promotion and anti-regression governance | Strong |
| Data management | Dataset lineage and truth-pack governance | Medium-strong |
| General ML | AI lifecycle tooling | Medium |
| Python ML | Python local AI governance framework | Medium |
| Efficient LLM | Small-model governance and usefulness-per-parameter | Medium now, stronger after trainer wiring |
| Agents | Agent lifecycle support | Weak until demo exists |
| Apps | Runnable demo app | Weak until app exists |

---

# PR tracking checklist

| Target | PR link | Status |
|---|---|---|
| Awesome Production Machine Learning | https://github.com/EthicalML/awesome-production-machine-learning/pull/770 | Submitted |
| Awesome MLOps | https://github.com/kelvins/awesome-mlops/pull/199 | Submitted |
| Awesome LLMOps | https://github.com/InftyAI/Awesome-LLMOps/pull/429 | Submitted |
| Awesome Local LLM | https://github.com/rafska/awesome-local-llm/pull/72 | Submitted |
| Awesome Local AI | https://github.com/msb-msb/awesome-local-ai/pull/6 | Submitted |
| Awesome Open MLOps | TBD | Not submitted |
| Awesome Trustworthy Deep Learning | TBD | Not submitted |
| Awesome Data Management | TBD | Not submitted |
| Awesome Machine Learning | TBD | Not submitted |
| Awesome Python Machine Learning | TBD | Not submitted |
| Awesome AI | TBD | Future |
| Awesome LLM | TBD | Future |
| Awesome Efficient LLM | TBD | Future |
| Awesome LLM Agents | TBD | Future / wait |
| Awesome LLM Apps | TBD | Future / wait |
