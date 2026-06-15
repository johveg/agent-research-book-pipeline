#!/usr/bin/env bash
set -euo pipefail

KEY_PATH="/root/.ssh/id_ed25519_github_hermione_hermes"
SSH_OPTS="-i ${KEY_PATH} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

usage() {
  cat <<'USAGE'
Usage: scripts/git_push_with_hermes_key.sh [--dry-run] [--check-key-only] [git-push-args...]

Uses the configured Hermione Hermes GitHub SSH identity without printing key material.
USAGE
}

DRY_RUN=0
CHECK_KEY_ONLY=0
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --check-key-only)
      CHECK_KEY_ONLY=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ ! -f "$KEY_PATH" ]]; then
  echo "ERROR: configured GitHub SSH key is missing at expected path" >&2
  exit 2
fi
if [[ ! -r "$KEY_PATH" ]]; then
  echo "ERROR: configured GitHub SSH key is not readable" >&2
  exit 2
fi

if [[ "$CHECK_KEY_ONLY" -eq 1 ]]; then
  echo "OK: configured GitHub SSH key exists and is readable"
  exit 0
fi

if [[ "${#ARGS[@]}" -eq 0 ]]; then
  ARGS=(push)
else
  ARGS=(push "${ARGS[@]}")
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf 'DRY_RUN: GIT_SSH_COMMAND=<redacted ssh command> git'
  printf ' %q' "${ARGS[@]}"
  printf '\n'
  exit 0
fi

export GIT_SSH_COMMAND="ssh ${SSH_OPTS}"
exec git "${ARGS[@]}"
