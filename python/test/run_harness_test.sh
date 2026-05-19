#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PYTHON_DIR="$(dirname "$SCRIPT_DIR")"
REPO_DIR="$(dirname "$PYTHON_DIR")"
VENV_PYTHON="${PYTHON_DIR}/venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
  printf 'Missing venv python: %s\n' "$VENV_PYTHON" >&2
  exit 1
fi

export LINEHASH_RUN_FUNCTIONAL="${LINEHASH_RUN_FUNCTIONAL:-1}"
export LINEHASH_TEST_ENV_FILE="${LINEHASH_TEST_ENV_FILE:-${REPO_DIR}/.env}"
export LINEHASH_TEST_MODEL="${LINEHASH_TEST_MODEL:-qwen3:0.6b}"
export LINEHASH_TEST_BASE_URL="${LINEHASH_TEST_BASE_URL:-http://127.0.0.1:11434/v1}"
export LINEHASH_TEST_API_KEY="${LINEHASH_TEST_API_KEY:-ollama}"
export LINEHASH_TEST_VERBOSE="${LINEHASH_TEST_VERBOSE:-1}"
export LINEHASH_TEST_SHOW_FULL_REASONING="${LINEHASH_TEST_SHOW_FULL_REASONING:-0}"
export AGNO_TELEMETRY="${AGNO_TELEMETRY:-false}"

cd "$PYTHON_DIR"

if [[ $# -ge 1 ]]; then
  export LINEHASH_TEST_VECTOR_NAME="$1"
fi

if [[ $# -ge 2 ]]; then
  export LINEHASH_TEST_VECTOR_FILE="$2"
fi

printf 'Running harness functional test\n'
printf '  env file: %s\n' "$LINEHASH_TEST_ENV_FILE"
printf '  model:    %s\n' "$LINEHASH_TEST_MODEL"
printf '  base url: %s\n' "$LINEHASH_TEST_BASE_URL"
printf '  verbose:  %s\n' "$LINEHASH_TEST_VERBOSE"
printf '  reasoning:%s\n' "$LINEHASH_TEST_SHOW_FULL_REASONING"
if [[ -n "${LINEHASH_TEST_VECTOR_NAME:-}" ]]; then
  printf '  vector:   %s\n' "$LINEHASH_TEST_VECTOR_NAME"
fi
if [[ -n "${LINEHASH_TEST_VECTOR_FILE:-}" ]]; then
  printf '  file:     %s\n' "$LINEHASH_TEST_VECTOR_FILE"
fi

exec "$VENV_PYTHON" -m unittest discover -v -s test -p 'test_harness_functional.py'
