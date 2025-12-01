#!/usr/bin/env bash

# 運行建議：
# 語法檢查與賦權
# bash -n scripts/triage_all_data.sh && chmod +x scripts/triage_all_data.sh
# 直接跑（掃描 Threads/data）
# scripts/triage_all_data.sh
# 自訂資料夾 / 參數
# DATA_DIR="Threads/data" CHUNK_SIZE=100 BASE="http://127.0.0.1:3000" scripts/triage_all_data.sh

#!/usr/bin/env bash
set -euo pipefail

# ====== Directory to scan ======
DATA_DIR="${DATA_DIR:-Threads/data}"

# ====== Triage parameters (sent to API) ======
BASE="${BASE:-${TRIAGE_API_BASE:-http://127.0.0.1:3000}}"
PLATFORM="${PLATFORM:-threads}"
SOURCE_TAG="${SOURCE_TAG:-threads:search}"
LANG_TAG="${LANG_TAG:-zh-Hant}"
CHUNK_SIZE="${CHUNK_SIZE:-100}"
MODE="${MODE:-sync}"
WAIT_MS="${WAIT_MS:-0}"
DEDUP="${DEDUP:-true}"
DEDUP_FIELD="${DEDUP_FIELD:-seed.value}"

require() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: need $1"; exit 1; }; }
require jq
require curl

[[ -d "$DATA_DIR" ]] || { echo "ERROR: data dir not found: $DATA_DIR"; exit 1; }

# macOS Bash 3.2 相容：用 glob 取檔，不用 mapfile / GNU find
shopt -s nullglob
FILES=( "$DATA_DIR"/*.json )
shopt -u nullglob

if (( ${#FILES[@]} == 0 )); then
  echo "WARN: no .json files under: $DATA_DIR"
  exit 0
fi

ts() { date +%Y%m%dT%H%M%S; }
echo "Scanning: $DATA_DIR (files: ${#FILES[@]})"

for IN in "${FILES[@]}"; do
  echo
  echo "========== Processing file: $IN =========="

  # 確保是 JSON 陣列
  if ! jq -e 'type=="array"' "$IN" >/dev/null 2>&1; then
    echo "Skip: not a JSON array"
    continue
  fi

  TOTAL="$(jq 'length' "$IN")"
  if (( TOTAL == 0 )); then
    echo "Skip: empty array"
    continue
  fi

  echo "Total=$TOTAL  chunk=$CHUNK_SIZE  base=$BASE"

  BN="$(basename "$IN")"
  BATCH_PREFIX="${BN%.*}_$(ts)"

  PAGE=0
  OFFSET=0
  while (( OFFSET < TOTAL )); do
    END=$(( OFFSET + CHUNK_SIZE ))
    echo "-- page=$PAGE  range=[$OFFSET:$END)"

    PAYLOAD="$(
      jq -c \
        --arg pl "$PLATFORM" \
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
        " "$IN"
    )"

    # 空批就跳出
    if [[ "$(jq '.candidates | length' <<<"$PAYLOAD")" -eq 0 ]]; then
      echo "No more candidates in this file."
      break
    fi

    BATCH_NAME="${BATCH_PREFIX}_p${PAGE}"
    RESP="$(
      curl -sS -X POST "$BASE/v1/triage/batch?batch=$BATCH_NAME&dedupe=$DEDUP&dedupe_field=$DEDUP_FIELD" \
        -H 'Content-Type: application/json' \
        --data-binary "$PAYLOAD"
    )" || { echo "ERROR: API request failed"; exit 1; }

    if ! jq -e '.results' >/dev/null 2>&1 <<<"$RESP"; then
      echo "ERROR: unexpected response:"
      echo "$RESP" | head -c 800; echo
      exit 1
    fi

    jq -c '{batch:"'"$BATCH_NAME"'", count:(.results|length),
            states:(.results|group_by(.state)|map({state:.[0].state, n:length})) }' \
      <<<"$RESP"

    PAGE=$((PAGE + 1))
    OFFSET=$END
  done
done

echo
echo "All files processed."