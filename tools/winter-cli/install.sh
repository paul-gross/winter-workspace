#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/bin/winter"
TARGET="$INSTALL_DIR/winter"

force=0
if [[ "${1:-}" == "--force" ]]; then
  force=1
fi

# Absence of the file, or absence of the marker line (a pre-versioning
# shim), both read as version 0.
shim_version() {
  grep -m1 '^WINTER_SHIM_VERSION=' "$1" 2>/dev/null | cut -d= -f2 || echo 0
}

source_version="$(shim_version "$SOURCE")"
installed_version=0
target_exists=0
if [[ -f "$TARGET" ]]; then
  target_exists=1
  installed_version="$(shim_version "$TARGET")"
fi

if [[ "$force" -eq 0 && "$target_exists" -eq 1 && "$installed_version" -ge "$source_version" ]]; then
  echo "Installed shim at $TARGET (v$installed_version) is already up to date with this source (v$source_version) — leaving in place."
  echo "Use --force to overwrite anyway."
  exit 0
fi

mkdir -p "$INSTALL_DIR"
cp "$SOURCE" "$TARGET"
chmod +x "$TARGET"

if [[ "$target_exists" -eq 1 ]]; then
  echo "Updated $TARGET: v$installed_version -> v$source_version"
else
  echo "Installed $TARGET (v$source_version)"
fi

if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
  echo "Warning: $INSTALL_DIR is not on your PATH. Add it with:"
  echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
else
  echo "Run 'winter' from any winter workspace."
fi
