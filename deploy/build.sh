#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"
LAMBDA_DIR="$DIST_DIR/lambda"
LAYER_DIR="$DIST_DIR/layer"

LAMBDAS=(
  stream-router
  evaluator
  orchestrator
  trigger
  run-checker
  watchdog
)

INTERLOCK_VERSION="${INTERLOCK_VERSION:-v0.1.0}"
INTERLOCK_MODULE="github.com/dwsmith1983/interlock"

echo "Fetching interlock@${INTERLOCK_VERSION} source..."
INTERLOCK_DIR="$(go env GOMODCACHE)/${INTERLOCK_MODULE}@${INTERLOCK_VERSION}"
if [ ! -d "$INTERLOCK_DIR" ]; then
  go install "${INTERLOCK_MODULE}/cmd/lambda/stream-router@${INTERLOCK_VERSION}" 2>/dev/null || true
fi
# Module cache is read-only; copy to a writable temp dir for build output
INTERLOCK_BUILD="$(mktemp -d)"
trap 'rm -rf "$INTERLOCK_BUILD"' EXIT
cp -r "$INTERLOCK_DIR" "$INTERLOCK_BUILD/interlock"
chmod -R u+w "$INTERLOCK_BUILD/interlock"

echo "Building interlock Lambda binaries..."
mkdir -p "$LAMBDA_DIR"

for name in "${LAMBDAS[@]}"; do
  echo "  Building $name..."
  (cd "$INTERLOCK_BUILD/interlock" && GOOS=linux GOARCH=arm64 CGO_ENABLED=0 \
    go build -tags lambda.norpc \
    -o "$LAMBDA_DIR/$name/bootstrap" \
    "./cmd/lambda/$name")
done

echo "All Lambda binaries built to $LAMBDA_DIR"

# Stage archetype layer (archetypes/ at root for /opt/archetypes)
echo "Staging archetype layer..."
mkdir -p "$LAYER_DIR/archetypes"
cp "$PROJECT_ROOT"/archetypes/*.yaml "$LAYER_DIR/archetypes/"
echo "Archetype layer staged to $LAYER_DIR"

# Stage Python shared layer (python/shared/ + pip deps for /opt/python)
PYTHON_LAYER_DIR="$DIST_DIR/python-layer"
echo "Staging Python shared layer..."
rm -rf "$PYTHON_LAYER_DIR"
mkdir -p "$PYTHON_LAYER_DIR/python/shared"
cp "$PROJECT_ROOT"/lambdas/shared/__init__.py "$PYTHON_LAYER_DIR/python/shared/"
cp "$PROJECT_ROOT"/lambdas/shared/helpers.py "$PYTHON_LAYER_DIR/python/shared/"
pip install --quiet --target "$PYTHON_LAYER_DIR/python" requests 2>&1 | tail -1
echo "Python shared layer staged to $PYTHON_LAYER_DIR"
