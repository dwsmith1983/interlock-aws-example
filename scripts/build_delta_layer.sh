#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="${PROJECT_ROOT}/build"

echo "Building Delta Lake Lambda layer for arm64..."
rm -rf "${BUILD_DIR}/delta-layer"
mkdir -p "${BUILD_DIR}/delta-layer"

# Install packages inside Docker (arm64 Linux binaries), output to mounted volume
docker run --rm --platform linux/arm64 \
  --entrypoint bash \
  -v "${BUILD_DIR}/delta-layer:/out" \
  public.ecr.aws/lambda/python:3.12-arm64 \
  -c 'pip install pyarrow deltalake -t /out/python'

# Zip on host (zip is available on macOS)
cd "${BUILD_DIR}/delta-layer"
zip -r9 "${BUILD_DIR}/delta-lake-layer.zip" python

rm -rf "${BUILD_DIR}/delta-layer"
echo "Built ${BUILD_DIR}/delta-lake-layer.zip"
