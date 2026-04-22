# ARC-Neuron LLMBuilder — production image
#
# Minimal Python 3.12 image with the full runtime and training
# dependencies pre-installed. Runtime secrets are generated at container
# start via scripts/ops/bootstrap_keys.py.
#
# Build:
#   docker build -t arc-neuron-llmbuilder:latest .
#
# Run the canonical 9-step proof workflow:
#   docker run --rm arc-neuron-llmbuilder:latest \
#     python3 scripts/ops/demo_proof_workflow.py
#
# Run the 87-test suite:
#   docker run --rm arc-neuron-llmbuilder:latest \
#     python3 -m pytest tests/ -q
#
# Interactive:
#   docker run --rm -it arc-neuron-llmbuilder:latest bash
FROM python:3.12-slim

LABEL org.opencontainers.image.title="ARC-Neuron LLMBuilder"
LABEL org.opencontainers.image.description="A governed local AI build-and-memory system with Gate v2, Arc-RAR, Omnibinary, canonical conversation pipeline, and conversation-driven model growth."
LABEL org.opencontainers.image.authors="Gary Doman"
LABEL org.opencontainers.image.source="https://github.com/GareBear99/ARC-Neuron-LLMBuilder"
LABEL org.opencontainers.image.documentation="https://github.com/GareBear99/ARC-Neuron-LLMBuilder#readme"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.version="1.0.0-governed"

WORKDIR /app

# System deps kept minimal; the repo itself is pure Python + torch CPU.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir "torch>=2.0" "numpy<2.0"

# Copy the repo.
COPY . .

# Generate runtime secrets on first boot. Safe to re-run.
RUN python3 scripts/ops/bootstrap_keys.py

# Sanity check — fail the build early if the tests don't pass.
RUN python3 -m pytest tests/ -q

# Default entrypoint drops you into a bash shell with PYTHONPATH set.
ENV PYTHONPATH=/app
CMD ["bash"]
