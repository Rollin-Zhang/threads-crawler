# Threads 專用爬蟲與自動化工具

本專案專注於 **Threads 平台** 的 **資料蒐集、搜尋、去重合併、與自動發文**。
設計目標是讓研究者、開發者或 AI Agent 能快速部署並直接使用。

⚠️ **聲明**：本專案僅供研究與教學使用。請遵守 Threads 平台之服務條款與當地法律，避免觸犯反爬蟲或自動化限制。

---

## 📌 專案定位

本 repo 僅支援 Threads 平台，包含以下功能模組：

- **貼文爬取**（Scrapy + Playwright）
- **搜尋/去重/合併**（Python 工具）
- **自動發文**（Playwright 腳本，具備完整安全防護與人性化設計）
- **Cookies 自動更新**（Selenium）

> Facebook 相關功能已完全移除，若需 Facebook 請至另一個專案。

---

## 📂 目錄結構

```
Meta_scrapy_playwright/
├── README.md                  # 說明文件
├── .gitignore                 # 忽略 venv、log、cookies、輸出等
├── .env.example               # 環境變數範例（帳號密碼）
├── scrapy.cfg
├── requirements.txt           # 安裝依賴
├── renew_cookies.py           # Cookies 更新工具（Selenium）
└── Threads/
    ├── scrapy.cfg
    ├── requirements.txt
    ├── scrapy_log.txt         # 可有可無（執行日誌）
    ├── output.json            # 可有可無（範例輸出）
    └── threads_scraper/
        ├── generate_content.py  # 從歷史資料生成發文候選內容
        ├── post_to_threads.py   # 自動發文
        ├── items.py             # Scrapy Item（目前空白，預留）
        ├── middlewares.py       # Scrapy Middleware（預留）
        ├── pipelines.py         # Scrapy Pipeline（預留）
        ├── settings.py          # Scrapy 全域設定
        └── spiders/
            ├── threads_spider.py    # Threads 爬蟲主程式
            ├── custom_settings.py   # Playwright/Scrapy 客製化設定
            └── utils.py             # JSON 合併、去重工具
```

---

## ⚙️ 安裝與環境設定

1. **建立虛擬環境**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. **安裝依賴**
   ```bash
   pip install -r requirements.txt
   playwright install
   ```
3. **設定帳號密碼**
   ```bash
   cp .env.example .env
   # 編輯 .env
   THREADS_USERNAME=your_threads_account
   THREADS_PASSWORD=your_threads_password
   ```
> 建議以 .env 或環境變數傳遞帳號密碼，避免寫死在程式裡。

---

## 🚀 核心功能與使用方式

### 1. 爬取 Threads 貼文

- 主要程式：`Threads/threads_scraper/spiders/threads_spider.py`
- 執行方式（已生成 storage_state.json 時可省略帳密）：
   ```bash
   cd Threads
   scrapy crawl threads -O output.json
   ```
  無 storage_state 時，仍可傳入帳密：
   ```bash
   cd Threads
   scrapy crawl threads -a username="$INSTAGRAM_USERNAME" -a password="$INSTAGRAM_PASSWORD" -O output.json
   ```
- 參數：
   - `username` / `password`：登入帳號密碼（可用環境變數）
   - `scroll_limit`：最大滾動次數，預設 5
   - `search_keyword`：若提供則進入搜尋模式
   - `-O output.json`：輸出檔案（支援 JSON、CSV）
- 流程：
   1. 嘗試讀取 cookies.json（若不存在 → 自動登入並更新）
   2. 以 Playwright 啟動瀏覽器，模擬人類操作（登入/滾動/點擊）
   3. 擷取指定帳號或搜尋頁的貼文內容
   4. 解析：作者、時間、內文、互動數、附件（圖/影片/連結）、回覆/轉發
   5. 儲存至 output.json，並執行去重合併

### 2. Cookies / storage_state 自動更新

- 主要程式：`renew_cookies.py`
- 執行方式：
   ```bash
   python renew_cookies.py
   ```
- 設定：
   - 使用 .env（`INSTAGRAM_USERNAME`、`INSTAGRAM_PASSWORD`、`HEADLESS`）或沿用舊變數 `THREADS_USERNAME`/`THREADS_PASSWORD`
- 流程：
   1. Selenium 啟動瀏覽器 → 模擬登入

   ---

   ## 🔗 A 握手（Triage）API 與資料契約

   此區描述「Provider（本專案）」如何與「PO Bot」對接。你可以用 CLI 主動推送，或啟動本機 API 做預覽/拉取。

   ### 架構概覽
   - Provider 產生 CandidateLite（淨化後的候選），並以批次送到 PO Bot。
   - 本機也提供 Flask API 方便預覽（/status, /triage/*）。
   - 內容長文只提供「前 N 字」（預設 500，可在 config 調整）；同時附上原文長度與是否截斷。

   ### 設定重點（config/triage_client.yaml）
   - `source.timezone`: 時區（用於「現在」時間計算）
   - `context.snippet_max_chars`: 片段最大字數（預設 500），影響 `context_digest.target_snippet`
   - `items_gate.record_policy: payload_only`（推薦）：只淨化送審 payload，不動內部紀錄與 candidate_id 計算
   - Items Gate 防呆：
      - `content` 一律不可 strip/skip（強制 keep + warning）
      - `datetime` 一律強制 keep（避免破壞時間語意與 recency）
   - `batch.mode`: `async|sync`、`wait_ms`、`max_size`、`flush_seconds`

   ### 本機 API（Flask）
   啟動 API（預設 127.0.0.1:8081）：

   ```bash
   python -m Threads.provider.api.app
   ```

   可用端點：

   - GET `/status`
      - 回傳目前已送批次（sent）、待判（pending）、結果（results）、死信（dead_letter）數量
      - 彙總 items_gate 統計（被移除欄位計數、跳過筆數、warnings）

   - GET `/triage/preview?limit=K`（view=record，預設）
      - 顯示原始 StandardRecord（未經 Gate）

   - GET `/triage/preview?limit=K&view=candidate`
      - 顯示送審前的 CandidateLite（已依 N 截斷、已套 Items Gate，且會過濾被 skip 的項目）

   - GET `/triage/sent`、`/triage/pending`、`/triage/results`
      - 觀察最近一次的送出、待判、與判決結果分片

   ### CLI（Provider 側）
   - 預覽（原始）
      ```bash
      python -m Threads.provider.cli.threads_tool triage-preview --limit 3
      ```

   - 預覽（已淨化 CandidateLite，本地顯示 _items_gate 報告）
      ```bash
      python -m Threads.provider.cli.threads_tool triage-preview --limit 3 --sanitized --include-report
      ```

   - 送審（主動推送到 PO Bot）
      ```bash
      python -m Threads.provider.cli.threads_tool triage-submit --data-dir Threads/data --mode async
      ```

   - Poll 決策結果（僅 async 有意義）
      ```bash
      python -m Threads.provider.cli.threads_tool triage-poll --interval 2 --max-iter 5
      ```

   資料持久化位置：`Threads/provider/store`（sent.jsonl、pending.jsonl、results.jsonl、dead_letter/）。

   ### Provider → PO Bot 批次 API（資料契約）
   Provider 端會呼叫 PO Bot：

   - 方法與路徑：`POST {base_url}/v1/triage/batch?mode=sync|async&wait_ms=1200`
   - HTTP 標頭：
      - `Content-Type: application/json`
      - `Authorization: Bearer <token>`（可選）
      - `X-Correlation-Id: <uuid4>`（追蹤用）
      - `Idempotency-Key: <sha1(sorted(candidate_ids))>`（冪等去重）
   - Request Body：
      ```json
      {
         "candidates": [
            {
               "platform": "threads",
               "account": { "handle": "<your_threads_account>" },
               "seed": { "type": "url", "value": "https://www.threads.net/@user/post/POSTID" },
               "features": {
                  "lang": "zh-Hant",
                  "len": 123,
                  "engagement": { "likes": 10, "comments": 2 },
                  "recency_minutes": 456,
                  "posted_at_iso": "2025-09-30T19:03:43Z"
               },
               "context_digest": {
                  "target_snippet": "前 N 字…",
                  "original_len": 987,
                  "is_truncated": true
               },
               "submitted_at": "2025-10-14T02:43:47+08:00",
               "candidate_id": "CAND_..."
            }
         ]
      }
      ```

   備註：
   - 完整 content 不會上傳，只提供 `context_digest.target_snippet`（長文截斷、短文等於全文）
   - `posted_at_iso` 為原貼文時間（UTC、結尾 Z），`recency_minutes` 依此對應現在時間計算
   - Items Gate 會在 Provider 端先行處理：
      - `content` 永不剝除（不可 strip/skip）
      - `datetime` 永遠保留（不可 strip/skip）
      - `post_link` 如被設為 strip，只影響 payload 的 `seed`；不影響 `candidate_id` 計算

   PO Bot 回應格式（擇一支援）：
   - 新：`{ "results": Result[] }`
   - 舊：`{ "done":[], "skipped":[], "errors":[], "pending":[] }`

   429/5xx：Provider 已包含退避重試與 Retry-After 處理。

   ### 驗收步驟（範例）
   1) 啟動本機 API：
       ```bash
       python -m Threads.provider.api.app
       ```
   2) 預覽原始與候選：
       ```bash
       curl -s "http://127.0.0.1:8081/triage/preview?limit=3" | jq .
       curl -s "http://127.0.0.1:8081/triage/preview?limit=3&view=candidate" | jq .
       ```
   3) 檢查片段長度與欄位：
       - `context_digest.target_snippet` 長度 ≤ `context.snippet_max_chars`
       - `context_digest.original_len` ≥ `target_snippet` 長度
       - `context_digest.is_truncated` 合理
       - `features.posted_at_iso` 為 UTC（Z 結尾）
   4) 送審與 /status 檢查：
       ```bash
       python -m Threads.provider.cli.threads_tool triage-submit --data-dir Threads/data --mode async
       curl -s "http://127.0.0.1:8081/status" | jq .
       ```

   ### 其他整合模式（擴充選項）
   - Pull（PO Bot 主動拉）：在 Provider 端新增 `/triage/export`（支援游標/ack）供 PO Bot 週期拉取。
   - 檔案匯出：Provider 匯出 `candidates_sanitized.jsonl`（建議命名含批次/日期），PO Bot 讀檔消費。
   - 佇列/流：Kafka/RabbitMQ/PubSub；Provider 發佈、PO Bot 訂閱。

   > 預設推薦 Push（REST）模式，改動最少也最直覺；若你要我加入「匯出檔案」或「拉取 API」功能，告訴我偏好我可直接補上指令與端點。
   2. 擷取 cookies → 儲存至 `Threads/threads_scraper/cookies.json`
   3. 自動轉檔 → 產生 `Threads/threads_scraper/storage_state.json`
   4. 後續 Playwright（爬蟲與自動發文）可直接載入 storage_state，不需每次登入

> 單獨轉檔（若需要）：
> ```bash
> python tools/cookies_to_storage_state.py --in Threads/threads_scraper/cookies.json --out Threads/threads_scraper/storage_state.json
> ```

### 3. 資料處理（搜尋、去重、合併）

- 主要程式：`Threads/threads_scraper/spiders/utils.py`
- 範例使用：
   ```python
   from threads_scraper.spiders import utils
   posts = utils.load_existing_posts("output.json")
   cleaned = utils.remove_duplicates(posts)
   utils.save_posts_to_file(cleaned, "clean_output.json")
   ```
- 或執行範例腳本：
   ```bash
   python Threads/data/sort_posts.py
   ```

### 4. 自動發文（使用 storage_state 與自我修復）

- 主要程式：`Threads/threads_scraper/post_to_threads.py`
- 執行方式（建議以模組呼叫，確保 import 路徑正確）：
   ```bash
   python -m Threads.threads_scraper.post_to_threads
   ```
- 流程：
   1. 優先載入 `storage_state.json` 建立 context
   2. 快速檢測 `is_logged_in()`；若失效 → 自動進登入流程（使用 .env 帳密）
   3. 登入成功後立即 `save_storage_state()`，形成閉環
   4. 生成/發文 → 支援批次與狀態回報

Scrapy 端的預設 context 也會讀取 `storage_state.json`：
`Threads/threads_scraper/spiders/custom_settings.py` 內設定了 `PLAYWRIGHT_CONTEXTS.default`。

---

## 🚀 進階發文管道（Posting Pipeline）

本專案提供全面的 Threads 自動發文系統，具備**雙模式架構**、**四種運行模式**、**多層安全防護**與**完整人性化設計**。

### 🏗️ 系統架構概覽

#### **雙模式架構**
- **模式一（Mode 1）**：全新發文流程
- **模式二（Mode 2）**：指定串文回覆，最大化重用模式一邏輯

#### **四種運行模式**
- **`check`**：基礎設定檢查，無實際操作
- **`rehearsal`**：完整流程演練，所有步驟但不實際提交
- **`dress`**：正式彩排，具備雙層防護（DOM 去功能化 + 網路攔截）
- **`live`**：實際發文執行

#### **安全防護系統**
- **雙道風險閘門**：pre-composer 與 pre-submit 階段風險評估
- **三級風險分類**：R0（安全）、R1（輕微）、R2（中等）、R3（高風險需人工）
- **冷卻機制**：R3 風險觸發後強制冷卻時間
- **速率限制**：智慧頻率控制與間隔管理

#### **人性化設計**
- **初始空閒**：隨機等待模擬真實使用者行為
- **智慧滾動**：可設定上下文滾動範圍與節奏
- **逐字輸入**：可調式打字速度（200-900ms/字符）
- **微滑鼠動作**：自然滑鼠移動軌跡

---

### 📋 模式一：全新發文（post_new）

#### **基本使用**

```bash
# 安全演練（推薦首次使用）
python -m Threads.threads_scraper.posting.post_new \
   --run-mode rehearsal \
   --no-headless \
   --verbose

# 正式彩排（含雙層防護驗證）
python -m Threads.threads_scraper.posting.post_new \
   --run-mode dress \
   --no-headless \
   --verbose

# 實際發文
python -m Threads.threads_scraper.posting.post_new \
   --run-mode live \
   --output Threads/output_live.json
```

#### **完整參數控制**

```bash
# 高安全性配置（推薦生產環境）
python -m Threads.threads_scraper.posting.post_new \
   --run-mode live \
   --text-file /path/to/your/content.txt \
   --no-headless \
   --verbose \
   \
   --humanize-session on \
   --initial-idle 3-8 \
   --humanize-pre 25-40 \
   --humanize-post 20-35 \
   --per-char-ms 400-800 \
   \
   --risk-mode stop \
   --risk-ceiling R2 \
   --enforce-cooldown-on-r3 1 \
   --cooldown-on-r3-s 3600 \
   \
   --enable-scroll 1 \
   --enable-composer 1 \
   --enable-typing 1 \
   \
   --output Threads/output_production.json
```

#### **核心參數說明**

| 參數類別 | 參數名稱 | 說明 | 範例值 |
|---------|----------|------|--------|
| **運行控制** | `--run-mode` | 執行模式 | `check\|rehearsal\|dress\|live` |
| | `--text-file` | 內容文件路徑 | `config/my_content.txt` |
| | `--no-headless` | 顯示瀏覽器視窗 | （無需參數值） |
| | `--verbose` | 詳細日誌輸出 | （無需參數值） |
| **人性化** | `--humanize-session` | 啟用會話人性化 | `on\|off` |
| | `--initial-idle` | 初始等待時間（秒） | `2-8` |
| | `--humanize-pre` | 操作前滾動範圍 | `15-35` |
| | `--humanize-post` | 操作後滾動範圍 | `10-25` |
| | `--per-char-ms` | 打字速度（毫秒/字符） | `300-700` |
| **風險控制** | `--risk-mode` | 風險處理模式 | `stop\|warn\|continue` |
| | `--risk-ceiling` | 風險等級上限 | `R0\|R1\|R2\|R3` |
| | `--enforce-cooldown-on-r3` | 強制 R3 冷卻 | `0\|1` |
| | `--cooldown-on-r3-s` | R3 冷卻時間（秒） | `3600` |

#### **執行時間估算**

以 400 字符內容為例：
- **Rehearsal/Dress**：30-60 秒（無實際提交）
- **Live 模式**：
  - 無人性化：60-90 秒
  - 中等人性化（400ms/字符）：3-4 分鐘
  - 高人性化（800ms/字符）：6-7 分鐘

---

### 💬 模式二：串文回覆（post_reply）

完全重用模式一的所有安全與人性化機制，針對指定串文進行回覆。

#### **基本使用**

```bash
# 回覆演練
python -m Threads.threads_scraper.posting.post_reply \
   --permalink "https://www.threads.net/@user/post/POST_ID" \
   --run-mode rehearsal \
   --no-headless \
   --verbose

# 實際回覆
python -m Threads.threads_scraper.posting.post_reply \
   --permalink "https://www.threads.net/@user/post/POST_ID" \
   --run-mode live \
   --text-file config/reply_content.txt \
   --output Threads/output_reply.json
```

#### **回覆模式特殊行為**
- **Thread 頁面**：不執行 pre-scroll（避免影響現有內容位置）
- **快速退出**：rehearsal/dress 模式在 composer 開啟後立即退出
- **Post-scroll**：僅在成功開啟 composer 後執行
- **選擇器增強**：回覆按鈕與發文按鈕選擇器自動合併提升穩定性

#### **完整參數範例**

```bash
python -m Threads.threads_scraper.posting.post_reply \
   --permalink "https://www.threads.net/@target_user/post/ABC123" \
   --text-file Threads/threads_scraper/posting/config/reply_post_content.txt \
   --run-mode live \
   --no-headless \
   --verbose \
   \
   --humanize-session on \
   --initial-idle 2-5 \
   --humanize-pre 20-30 \
   --humanize-post 15-25 \
   --per-char-ms 350-650 \
   \
   --risk-mode stop \
   --risk-ceiling R2 \
   --enforce-cooldown-on-r3 1 \
   --cooldown-on-r3-s 3600 \
   \
   --pre-scroll 1 \
   --output Threads/output_reply_live.json
```

---

### 🛡️ 安全防護詳解

#### **雙道風險閘門**

1. **Pre-Composer 閘門**：開啟編輯器前風險評估
   - 檢查登入狀態
   - 驗證速率限制
   - 評估頁面異常狀況

2. **Pre-Submit 閘門**：提交前最終檢查
   - 內容驗證與比對
   - 最終風險等級確認
   - 冷卻狀態檢查

#### **風險等級分類**

| 等級 | 描述 | 建議處理 |
|------|------|----------|
| **R0** | 完全安全 | 可繼續執行 |
| **R1** | 輕微風險（minor warnings） | 記錄但可繼續 |
| **R2** | 中等風險（rate limits, soft blocks） | 建議暫停或降頻 |
| **R3** | 高風險（challenges, captcha） | **必須停止，人工處理** |

#### **Dress 模式雙層防護**

1. **DOM 去功能化**：移除提交按鈕點擊功能
2. **網路攔截**：阻止實際 POST 請求發送
3. **安全驗證**：確保無實際內容發布

---

### 📊 標準 JSON 輸出格式

每次執行都會產生標準化的 JSON 輸出，包含完整的執行資訊、風險評估與稽核追蹤。

```json
{
  "ok": true,
  "run_mode": "live",
  "execution_time_s": 45.2,
  "content_summary": {
    "expected_chars": 156,
    "actual_chars": 156,
    "source_file": "config/new_post_content.txt"
  },
  "text_check": {
    "match": true,
    "expected_len": 156,
    "actual_len": 156,
    "verification_method": "paragraph_extraction"
  },
  "risk_summary": {
    "level": "R0",
    "triggers": [],
    "pre_composer_risk": "R0",
    "pre_submit_risk": "R0"
  },
  "rate_limit": {
    "check": "allowed",
    "next_try_eta": null,
    "r3_cooldown_remaining_s": 0
  },
  "composer_close": {
    "composer_closed": true,
    "close_method": "escape_key"
  },
  "humanization": {
    "initial_idle_s": 3.2,
    "pre_scroll_px": 28,
    "post_scroll_px": 22,
    "typing_duration_s": 41.8,
    "total_humanization_s": 45.0
  },
  "artifacts": {
    "screenshot_path": "Threads/artifacts/screenshot_20250101_123456.png",
    "trace_path": "Threads/artifacts/trace_20250101_123456.zip"
  },
  "timestamp": "2025-01-01T12:34:56.789Z"
}
```

---

### 🔧 架構優化成果

#### **CLI 基礎設施重構**
- **程式碼減少**：從 ~400 行重複程式碼縮減至 ~135 行，減幅 66%
- **維護性提升**：共用 40+ 個 CLI 參數定義，單點維護
- **向後相容**：保持完整的 CLI 介面相容性

#### **共用組件**（`cli_shared.py`）
- `add_common_args()`：標準化參數定義
- `build_runtime_overrides()`：設定覆寫邏輯統一
- `resolve_content_file()`：內容檔案解析
- `output_result()`：結果輸出標準化
- `run_with_error_handling()`：錯誤處理統一

#### **日誌優化**
- **噪聲過濾**：自動過濾 CDN、媒體檔案、GraphQL 的無關錯誤
- **重要資訊保留**：保持核心業務邏輯的完整錯誤資訊
- **用戶體驗**：減少無意義輸出，提升可讀性

## 📄 輸出資料格式

### 爬蟲輸出範例

```json
{
  "author": "account_name",
  "post_link": "https://www.threads.net/@user/post/123",
  "datetime": "2025-08-31T12:34:56.000Z",
  "content": "這是內文…",
  "likes": 15300,
  "comments": 233,
  "attachment": "video: https://...",
  "response_to": "被回覆帳號",
  "repost_author": "原作者",
  "repost_content": "原文內容"
}
```

### 發文管道輸出範例

發文管道的標準 JSON 輸出已在上方「標準 JSON 輸出格式」章節詳細說明，包含執行狀態、風險評估、人性化統計、稽核追蹤等完整資訊。

---

## ⚠️ 注意事項

- 合規使用：僅供研究教學，請勿用於商業或違法用途。
- 敏感檔案：cookies、.env、輸出資料已在 .gitignore 忽略，請勿提交。
- 穩定性：Threads DOM 可能更新，若爬蟲失敗，需更新 threads_spider.py 或 custom_settings.py 的選擇器。
- Playwright 問題：若啟動失敗，請重新執行 playwright install。

---

## 🛠️ 常見問題 (FAQ)

**Q: 登入時顯示帳號/密碼錯誤？**
→ 請確認 .env 內的帳密是否正確，或 Threads 是否有額外驗證（如 2FA）。

**Q: 爬蟲啟動後沒有抓到資料？**
→ 檢查是否已設定 target_accounts 或 search_keyword。
→ 確認 scroll_limit 不為 0。

**Q: 輸出檔案格式不符？**
→ 使用 Scrapy 的 -O filename.json 指定輸出；Scrapy 支援 JSON、CSV。

**Q: 自動發文失敗？**
→ 確認 cookies 有效，或帳號是否被平台風控。
→ 嘗試降低發文頻率。

---

## 📌 後續發展 (Roadmap)

### 🎯 短期規劃
- **多帳號支援增強**：整合檔案或環境變數的帳號清單管理
- **排程系統**：CLI 參數化的內容排程與自動發文
- **選擇器韌性提升**：加入 m.threads.net fallback 機制
- **非 headless 穩定性**：改善視覺模式下的 composer 開啟/關閉機制

### 🚀 中期目標
- **資料庫整合**：PostgreSQL / MongoDB 支援
- **API 介面**：REST API 包裝現有功能
- **監控面板**：發文狀態、風險監控、執行統計的 Web Dashboard
- **內容管理**：多樣化內容來源（API、資料庫、範本系統）

### 💡 長期願景
- **AI 輔助**：智慧內容生成與風險預測
- **跨平台擴展**：類似架構適配其他社交平台
- **合規工具包**：進階的平台政策遵循檢查
- **企業級功能**：團隊協作、審核流程、批量管理

---

## 🤝 貢獻指南

歡迎貢獻！請在 PR 前：

1. **遵循現有架構**：特別是發文管道的雙模式設計與安全機制
2. **保持向後相容**：CLI 介面與 JSON 輸出格式
3. **完善測試**：所有四種運行模式都應通過測試
4. **文件更新**：同步更新 README.md 與程式碼註解

如有建議或問題，歡迎開 issue 討論，或提交 PR 貢獻。