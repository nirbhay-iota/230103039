#!/usr/bin/env bash
set -euo pipefail
RUN="${1:?usage: restore-model.sh RUN}"
REPO="${REPO:-$(git config --get remote.origin.url | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')}"
PY="${PY:-.venv/bin/python}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
base="https://github.com/${REPO}/releases/download/model-${RUN}"
curl -fsSL -o "$work/model-${RUN}.tar.gz" "$base/model-${RUN}.tar.gz"
curl -fsSL -o "$work/model-${RUN}.sha256" "$base/model-${RUN}.sha256"
(cd "$work" && shasum -a 256 -c "model-${RUN}.sha256")
mkdir -p "$work/model"
tar -xzf "$work/model-${RUN}.tar.gz" -C "$work/model"
cp "$work/model-${RUN}.sha256" "$work/model/model.sha256"
scripts/pf.sh start
eval "$(scripts/s3env.sh)"
"$PY" scripts/s3_tool.py put-dir "$work/model" models "${RUN}"
echo "restored model ${RUN} from release model-${RUN} into s3://models/${RUN}/"
