#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   scripts/translation/run_benchmark.sh \
#     --reference /home/node/.openclaw/secrets/translation_eval/ibn_hisham/reference_en.txt \
#     --candidate firstlight-research/data/translated/ibn_hisham/al-sirah.en.lit.txt \
#     --out firstlight-research/data/translated/ibn_hisham/benchmark_report.json

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$ROOT_DIR/scripts/translation/benchmark_eval.py"

python3 "$PY" "$@"
