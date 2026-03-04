#!/usr/bin/env bash
# scripts/build_interlock.sh — Build Interlock Go Lambda binaries for arm64
set -euo pipefail

INTERLOCK_DIR="${INTERLOCK_DIR:-$HOME/code/interlock}"
BUILD_DIR="build/interlock"

mkdir -p "$BUILD_DIR"

for handler in stream-router orchestrator sla-monitor watchdog event-sink alert-dispatcher; do
    echo "Building $handler..."
    GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build \
        -C "$INTERLOCK_DIR" \
        -o "$PWD/$BUILD_DIR/bootstrap" \
        "./cmd/lambda/$handler"
    (cd "$BUILD_DIR" && zip -j "$handler.zip" bootstrap && rm bootstrap)
    echo "  -> $BUILD_DIR/$handler.zip"
done

echo "All Interlock binaries built."
