#!/usr/bin/env bash
set -euo pipefail

if (( $# > 1 )); then
    echo "Usage: bash scripts/download_data.sh [download_root]" >&2
    exit 2
fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$ROOT}"
REVISION="80abe34097edf2531e3d5b07337c4cc0710bfb24"

if ! command -v hf >/dev/null 2>&1; then
    echo "Missing hf CLI. Install with: python -m pip install 'huggingface-hub>=1,<2'" >&2
    exit 1
fi
if command -v sha256sum >/dev/null 2>&1; then
    CHECKSUM=(sha256sum -c)
elif command -v shasum >/dev/null 2>&1; then
    CHECKSUM=(shasum -a 256 -c)
else
    echo "SHA256 verification requires sha256sum or shasum." >&2
    exit 1
fi

hf download debouter/AdvancedMathBench \
    data/proverbench/test.jsonl data/verifierbench/test.jsonl \
    --repo-type dataset --revision "$REVISION" --local-dir "$DEST"

(
    cd -- "$DEST"
    "${CHECKSUM[@]}" "$ROOT/data/SHA256SUMS"
)
