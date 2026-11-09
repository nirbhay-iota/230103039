#!/usr/bin/env bash
set -euo pipefail

if kubectl -n data get secret seaweedfs-s3-config >/dev/null 2>&1; then
  echo "secrets already exist, leaving them unchanged"
  exit 0
fi

ACCESS_KEY="$(openssl rand -hex 8)"
SECRET_KEY="$(openssl rand -hex 24)"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
cat > "$tmp" <<JSON
{"identities":[{"name":"project","credentials":[{"accessKey":"${ACCESS_KEY}","secretKey":"${SECRET_KEY}"}],"actions":["Admin","Read","Write","List","Tagging"]}]}
JSON

kubectl -n data create secret generic seaweedfs-s3-config --from-file=s3.json="$tmp"
for ns in pipeline app; do
  kubectl -n "$ns" create secret generic s3-credentials \
    --from-literal=AWS_ACCESS_KEY_ID="$ACCESS_KEY" \
    --from-literal=AWS_SECRET_ACCESS_KEY="$SECRET_KEY"
done
echo "created S3 secrets in namespaces data, pipeline and app"
