#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${CODEX_HOME:-$HOME/.codex}/skills"

mkdir -p "$TARGET"
cp -R "$ROOT/flight-price" "$TARGET/"

printf 'Installed flight-price skill to %s/flight-price\n' "$TARGET"
