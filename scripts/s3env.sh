#!/usr/bin/env bash
set -euo pipefail
ak="$(kubectl -n app get secret s3-credentials -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d)"
sk="$(kubectl -n app get secret s3-credentials -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d)"
echo "export AWS_ACCESS_KEY_ID='${ak}'"
echo "export AWS_SECRET_ACCESS_KEY='${sk}'"
echo "export S3_ENDPOINT='http://localhost:8333'"
