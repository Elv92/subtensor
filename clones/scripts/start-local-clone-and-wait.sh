#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

log_file="clone-node.log"
sealing="250"
use_node_default_sealing=false
min_blocks="20"
ready_attempts="450"
advance_timeout_seconds="60"

usage() {
  cat >&2 <<'EOF'
Usage: start-local-clone-and-wait.sh [options]

Options:
  --log-file PATH             Node log destination (default: clone-node.log)
  --sealing MODE              Value passed to node --sealing (default: 250)
  --node-default-sealing      Do not pass a --sealing option to the node
  --min-blocks COUNT          Required block advancement after readiness (default: 20)
  --ready-attempts COUNT      Two-second health-check attempts (default: 450)
  --advance-timeout SECONDS   Block-advancement deadline (default: 60)
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --log-file) [[ $# -ge 2 ]] || usage; log_file="$2"; shift 2 ;;
    --sealing) [[ $# -ge 2 ]] || usage; sealing="$2"; shift 2 ;;
    --node-default-sealing) use_node_default_sealing=true; shift ;;
    --min-blocks) [[ $# -ge 2 ]] || usage; min_blocks="$2"; shift 2 ;;
    --ready-attempts) [[ $# -ge 2 ]] || usage; ready_attempts="$2"; shift 2 ;;
    --advance-timeout) [[ $# -ge 2 ]] || usage; advance_timeout_seconds="$2"; shift 2 ;;
    *) usage ;;
  esac
done

[[ -n "$log_file" && -n "$sealing" ]] || usage
for value in "$min_blocks" "$ready_attempts" "$advance_timeout_seconds"; do
  [[ "$value" =~ ^[0-9]+$ ]] || usage
done
(( ready_attempts > 0 )) || usage

cd "$REPO_ROOT"
if [[ "$use_node_default_sealing" == true ]]; then
  nohup ./clones/scripts/start-local-clone.sh > "$log_file" 2>&1 &
else
  nohup ./clones/scripts/start-local-clone.sh --sealing "$sealing" > "$log_file" 2>&1 &
fi
node_pid=$!

cleanup_on_failure() {
  local status=$?
  (( status != 0 )) || return
  echo "Clone node startup failed; last log lines:"
  tail -n 200 "$log_file" 2>/dev/null || true
  "$SCRIPT_DIR/stop-local-clone.sh" || true
}
trap cleanup_on_failure EXIT

rpc() {
  local method="$1"
  curl -fsS -H "Content-Type: application/json" \
    -d "{\"id\":1,\"jsonrpc\":\"2.0\",\"method\":\"$method\",\"params\":[]}" \
    http://127.0.0.1:9944
}

ready=false
for ((attempt = 1; attempt <= ready_attempts; attempt++)); do
  if rpc system_health > /dev/null; then
    ready=true
    break
  fi
  kill -0 "$node_pid" 2>/dev/null || break
  sleep 2
done
[[ "$ready" == true ]] || exit 1

if (( min_blocks == 0 )); then
  echo "Clone node is healthy."
  trap - EXIT
  exit 0
fi

height() {
  local hex
  hex=$(rpc chain_getHeader | jq -er '.result.number')
  echo $((16#${hex#0x}))
}

first=$(height)
deadline=$(($(date +%s) + advance_timeout_seconds))
while (( $(date +%s) < deadline )); do
  current=$(height)
  if (( current >= first + min_blocks )); then
    echo "Clone advanced from block $first to $current."
    trap - EXIT
    exit 0
  fi
  sleep 1
done

exit 1
