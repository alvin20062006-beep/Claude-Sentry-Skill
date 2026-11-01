#!/usr/bin/env bash
# Probe real interpreters instead of assuming Windows' python3 alias is usable.
root="$(cd -- "$(dirname -- "$0")" && pwd)"
if [[ "${OS:-}" == "Windows_NT" ]]; then
  if command -v py >/dev/null 2>&1 && py -3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' </dev/null >/dev/null 2>&1; then
    exec py -3 -X utf8 -B "$root/transparency.py" "$@"
  fi
  candidates=(python python3)
else
  candidates=(python3 python)
fi
for candidate in "${candidates[@]}"; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' </dev/null >/dev/null 2>&1; then
    exec "$candidate" -X utf8 -B "$root/transparency.py" "$@"
  fi
done
printf '%s\n' '{"terminalSequence":"\u001b]9;Claude Sentry Skill: Python 3.9+ unavailable; detection did not run.\u0007"}'
exit 0
