# Threads_Bot：A 握手（Triage）設計最終版

> 目標：把 `Threads/data` 的爬取輸出轉為 CandidateLite[]，以本機 REST 打到 PO_Bot `/v1/triage/batch`，只送審/收結果，不做 LLM、不做回覆（B 段）。

## 1. 邊界與契約
- 輸入：CandidateLite[]
- 輸出：TriageResult（APPROVE/HOLD/SKIP + priority + reason…），含 PENDING 收割
- 冪等與持久化：`Threads/provider/store/{candidates_sent.jsonl,pending.jsonl,triage_results.jsonl,dead_letter/}`

## 2. 固定資料路徑與設定
- 來源資料夾：`Threads/data`
- 實體路徑：`/Users/wangshihya/Meta_scrapy_playwright/Threads/data`
- PO_Bot REST：`http://127.0.0.1:3000/v1`
- 本機儲存：`Threads/provider/store/`

`config/triage_client.yaml`
```yaml
source:
  data_dir: "Threads/data"
  timezone: "Asia/Taipei"
account:
  handle: "<你的 Threads 帳號>"
batch:
  mode: "sync"
  wait_ms: 1200
  max_size: 50
  flush_seconds: 5
http:
  base_url: "http://127.0.0.1:3000/v1"
  timeout_seconds: 8
  max_retries: 4
  retry_backoff_seconds: 2
security:
  auth_token_env: "POBOT_TOKEN"
persist:
  dir: "Threads/provider/store"
gate0:
  enabled: true
  min_len: 10
  max_recency_minutes: 1440
  dedup:
    enabled: true
    simhash_threshold: 0.92
  keywords_any: []  # 命中可放寬長度
```

`.env.example`
```
POBOT_TOKEN=local-dev
```

## 3. 目錄與檔案職責
```
Threads/provider/
  adapters/
    ingest.py        # 讀 Threads/data 的 JSON/JSONL → StandardRecord[]（保留 source_file,line_no）
    normalize.py     # URL canonical、lang 標記（預設 zh-Hant）
  triage/
    gate0.py         # min_len / max_recency / dedup(simhash) / keywords_any；拒件寫 audit
    builder.py       # StandardRecord → CandidateLite；account.handle；schema 檢驗；dead_letter/
    batcher.py       # 依 max_size/flush_seconds 聚批；X-Correlation-Id；批前 append sent.jsonl
    client.py        # POST /v1/triage/batch；429 Retry-After；5xx/網錯退避；Idempotency-Key
    fetcher.py       # 分批（≤50 ids）GET /v1/triage/results；DONE → results，移除 pending
    persist.py       # sent/pending/results/dead_letter 讀寫與索引；冪等
    schemas/
      candidate_lite.json
      triage_batch_resp.json
  api/
    app.py           # 展示與 dry-run：/status /triage/preview /sent /pending /results
  cli/
    threads_tool.py  # triage-preview / triage-submit / triage-poll / triage-replay（預設直呼內部庫）
```

## 4. URL canonical 規則（影響 candidate_id，兩端一致，"不可變更"）
- host 小寫
- 移除結尾斜線（/）
- 移除追蹤參數（utm_*/ref/* 等，白名單保留必要參數）
- 解碼常見轉義（%xx、+ 空白）
- 去除 fragment（#...）與無意義片段

## 5. candidate_id 公式（不可變更）
```
CAND_ + sha1(
  canonical_url +
  sha1(content)[:16] +
  floor_to_minute(datetime_iso)
)
```

## 6. 分步驟與驗收
1) 配置
- YES：source.data_dir=Threads/data、account.handle、source.timezone=Asia/Taipei
- YES：.env 有 POBOT_TOKEN；http 超時/重試/退避配置

2) Ingest
- 讀 `Threads/data/**/*.(json|jsonl)` → StandardRecord[]；保留 source_file,line_no
- 驗收：`triage-preview` 能列出前 N 筆

3) Gate-0（可關）
- min_len / max_recency / dedup(simhash) / keywords_any
- 驗收：短文被 SKIPPED(policy:min_len)，結果可見

4) Builder
- StandardRecord → CandidateLite；account.handle；timezone 計 recency_minutes；schema 驗證
- 不符落 `dead_letter/`

5) Batcher
- 依 max_size/flush_seconds 聚批；X-Correlation-Id；Idempotency-Key=sha1(sorted(candidate_ids))
- 送前 append `candidates_sent.jsonl`

6) Client
- POST `/v1/triage/batch?mode=sync|async&wait_ms=`
- Headers：Authorization, Content-Type, X-Correlation-Id, Idempotency-Key
- 429：尊重 Retry-After；5xx/網錯：指數退避；所有重試保冪等
- 回應驗證：triage_batch_resp；DONE→results；PENDING→pending
- errors[]：逐筆落 `dead_letter/`，並在 `triage_results.jsonl` 記 decision="ERROR" 與 code/message

7) Fetcher
- 從 pending 讀取 ids，分批（≤50）查 `/v1/triage/results?ids=...`
- DONE → results；並自 pending 移除；429 尊重 Retry-After
- 驗收：重跑至 pending 清空

8) Persist
- candidate_id 索引；中斷恢復；重送不重複

9) 本機 REST（展示與 dry-run）
- /status（含 dead_letter 計數、最近 correlation_id）
- /triage/preview?limit=K、/triage/sent?limit=K、/triage/pending?limit=K、/triage/results?limit=K

10) CLI（預設直呼內部庫）
- triage-preview / triage-submit / triage-poll / triage-replay
- 驗收：`Threads/provider/store/` 檔案對應增長

## 7. Schema 對齊
- `schemas/*.json` 直接複製 PO_Bot 契約
- 啟動時比對版本（不同則 log warn）

## 8. 補充
- 時區與 recency：爬蟲 datetime 視為 ISO8601 並含 Z 或偏移；若無偏移視作本地時間（config.source.timezone）
- 安全：只打 127.0.0.1；token 讀環境變數；避免把 token 落檔
- 失敗樣本：一律丟 `dead_letter/`，便於回放與除錯
