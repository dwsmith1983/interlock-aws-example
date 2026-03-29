#!/usr/bin/env bash
# chaos/scripts/build.sh — Build chaos controller Go Lambda binary for arm64
set -euo pipefail

CHAOS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="${CHAOS_DIR}/../build/chaos"

mkdir -p "$BUILD_DIR"

echo "Building chaos-controller..."
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build \
    -C "$CHAOS_DIR" \
    -o "$BUILD_DIR/bootstrap" \
    "./cmd/controller"
(cd "$BUILD_DIR" && zip -j "chaos-controller.zip" bootstrap && rm bootstrap)
echo "  -> $BUILD_DIR/chaos-controller.zip"

echo "Chaos controller binary built."
