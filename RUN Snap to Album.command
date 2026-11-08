#!/bin/zsh
# Snap to Album — double-click to start.
# Opens Claude Code in this folder and asks it to create a photo album.
# Claude installs everything it needs on the first run (it asks you first).
cd "$(dirname "$0")" || exit 1
# Finder starts this without your shell setup — add the usual install locations of Claude Code
export PATH="$HOME/.local/bin:$HOME/.claude/local:$HOME/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v claude >/dev/null 2>&1; then
  echo "Claude Code is not installed yet."
  echo "Get it at https://claude.com/claude-code — or open this folder in the Claude desktop app"
  echo "and type: create a photo album"
  echo
  read -k1 "?Press any key to close."
  exit 1
fi
exec claude "create a photo album"
