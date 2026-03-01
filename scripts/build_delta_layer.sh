#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="${PROJECT_ROOT}/build"

echo "Building Delta Lake Lambda layer for arm64..."
rm -rf "${BUILD_DIR}/delta-layer"
mkdir -p "${BUILD_DIR}/delta-layer"

docker run --rm --platform linux/arm64 \
  -v "${BUILD_DIR}/delta-layer:/out" \
  public.ecr.aws/lambda/python:3.12-arm64 \
  bash -c 'pip install pyarrow deltalake -t /out/python && cd /out && zip -r9 delta-lake-layer.zip python'

mv "${BUILD_DIR}/delta-layer/delta-lake-layer.zip" "${BUILD_DIR}/delta-lake-layer.zip"
rm -rf "${BUILD_DIR}/delta-layer"

echo "Built ${BUILD_DIR}/delta-lake-layer.zip"
