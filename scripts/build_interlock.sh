#!/usr/bin/env bash
# scripts/build_interlock.sh — Build Interlock Go Lambda binaries for arm64
set -euo pipefail

INTERLOCK_DIR="${INTERLOCK_DIR:-$HOME/code/interlock}"
BUILD_DIR="build/interlock"

mkdir -p "$BUILD_DIR"

for handler in stream-router orchestrator sla-monitor watchdog; do
    echo "Building $handler..."
    cd "$INTERLOCK_DIR"
    GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -o bootstrap "./cmd/lambda/$handler"
    cd -
    cp "$INTERLOCK_DIR/bootstrap" "$BUILD_DIR/"
    (cd "$BUILD_DIR" && zip -j "$handler.zip" bootstrap && rm bootstrap)
    echo "  -> $BUILD_DIR/$handler.zip"
done

echo "All Interlock binaries built."
