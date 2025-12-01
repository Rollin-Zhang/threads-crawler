#!/usr/bin/env bash

# 運行建議：
# 語法檢查與賦權
# bash -n scripts/triage_data.sh && chmod +x scripts/triage_data.sh
# 直接跑（掃描 Threads/data）
# scripts/triage_data.sh
# 自訂資料夾 / 參數
# IN="Threads/data/吳石_threads_posts_search.json" CHUNK_SIZE=100 scripts/triage_data.sh

set -euo pipefail

# === Config (overridable via env) ===
BASE="${BASE:-${TRIAGE_API_BASE:-http://127.0.0.1:3000}}"
IN="${IN:-Threads/data/_sample_threads_posts.json}"
PLATFORM="${PLATFORM:-threads}"
SOURCE_TAG="${SOURCE_TAG:-threads:search}"
LANG_TAG="${LANG_TAG:-zh-Hant}"

CHUNK_SIZE="${CHUNK_SIZE:-200}"   # items per batch
MODE="${MODE:-sync}"              # sync/async
WAIT_MS="${WAIT_MS:-0}"           # used by batch mode
DEDUP="${DEDUP:-true}"
DEDUP_FIELD="${DEDUP_FIELD:-seed.value}"

ts() { date +%Y%m%dT%H%M%S; }

require() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: need $1"; exit 1; }; }
require jq
require curl

if [[ ! -f "$IN" ]]; then
  echo "ERROR: missing file: $IN"
  exit 1
fi

# Ensure JSON array
jq -e 'type=="array"' "$IN" >/dev/null || { echo "ERROR: $IN is not a JSON array"; exit 1; }

TOTAL="$(jq 'length' "$IN")"
echo "Submitting: file=$IN total=$TOTAL chunk=$CHUNK_SIZE base=$BASE"

# Batch name prefix from filename (spaces -> underscores)
BN="$(basename "$IN")"
BN_NOEXT="${BN%.*}"
BN_SAFE="${BN_NOEXT// /_}"
BATCH_PREFIX="${BN_SAFE}_$(ts)"

PAGE=0
OFFSET=0

while (( OFFSET < TOTAL )); do
  END=$(( OFFSET + CHUNK_SIZE ))
  echo "=== page=$PAGE range=[$OFFSET:$END) ==="

  # Build candidates payload
  PAYLOAD="$(jq -c --arg pl "$PLATFORM" \
                   --arg src "$SOURCE_TAG" \
                   --arg lang "$LANG_TAG" \
                   --arg mode "$MODE" \
                   --argjson wait "$WAIT_MS" \
    ".[$OFFSET:$END]
     | map({
         context_digest: {
           target_snippet: (.content // \"\"),
           is_truncated: false,
           original_len: ((.content // \"\") | length)
         },
         features: {
           author: (.author // \"\"),
           len: ((.content // \"\") | length),
           engagement: { likes: (.likes // 0), comments: (.comments // 0) },
           posted_at_iso: (.datetime // null),
           lang: \$lang
         },
         seed: { type: \"url\", value: (.post_link // .url // \"\") },
         platform: \$pl,
         source: \$src,
         account: { handle: (.author // \"\") }
       })
     | {candidates: ., mode:\$mode, wait_ms:\$wait}
    " "$IN")"

  # Empty batch guard
  if [[ "$(jq '.candidates|length' <<< "$PAYLOAD")" -eq 0 ]]; then
    echo "No more candidates."
    break
  fi

  BATCH_NAME="${BATCH_PREFIX}_p${PAGE}"

  # Submit
  RESP="$(curl -sS -X POST "$BASE/v1/triage/batch?batch=$BATCH_NAME&dedupe=$DEDUP&dedupe_field=$DEDUP_FIELD" \
            -H 'Content-Type: application/json' \
            --data-binary "$PAYLOAD")" || { echo "ERROR: API call failed"; exit 1; }

  # Basic check and summary
  if ! jq -e '.results' >/dev/null 2>&1 <<< "$RESP"; then
    echo "ERROR: unexpected response:"
    echo "$RESP" | head -c 800; echo
    exit 1
  fi

  echo "$RESP" \
    | jq -c '{batch:"'"$BATCH_NAME"'", count:(.results|length),
              states:(.results|group_by(.state)|map({state:.[0].state, n:length})) }'

  PAGE=$((PAGE+1))
  OFFSET=$END
done

echo "Done: $IN"