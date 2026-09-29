#!/usr/bin/env bash
set -euo pipefail

if (( $# > 1 )); then
    echo "Usage: bash scripts/download_verifier.sh [model_directory]" >&2
    exit 2
fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$ROOT/models/autoverifier}"
REVISION="2ad58735622f70bbe2f106049bcdf34f5bb93cfd"

if ! command -v hf >/dev/null 2>&1; then
    echo "Missing hf CLI. Install with: python -m pip install 'huggingface-hub>=1,<2'" >&2
    exit 1
fi

echo "Downloading the AutoVerifier checkpoint (approximately 68 GiB) to: $DEST"
hf download debouter/AdvancedMathBench-AutoVerifier \
    --repo-type model --revision "$REVISION" --local-dir "$DEST"
