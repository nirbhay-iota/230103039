#!/usr/bin/env bash
set -euo pipefail
SOURCE="${1:?release|baseline}"
TAG="${2:-model-v1}"
mkdir -p ci
if [ "$SOURCE" = "release" ]; then
  gh release download "$TAG" --dir ci --pattern '*.tar.gz' --pattern '*.sha256' --clobber
  (cd ci && sha256sum -c "${TAG}.sha256")
  mkdir -p ci/model && tar -xzf "ci/${TAG}.tar.gz" -C ci/model
  MODEL=ci/model
else
  MODEL=EleutherAI/pythia-70m
fi
python training/evaluate.py --model "$MODEL" --input data/validation.jsonl --output ci/predictions.jsonl
python tools/score.py ci/predictions.jsonl data/validation.jsonl --out ci/report.json
