# Threads Crawler

這個專案使用 [Scrapy](https://scrapy.org/) 搭配 [Playwright](https://playwright.dev/python/) 抓取 Meta Threads 與 Facebook 上的貼文，並提供自動發佈 Threads 貼文的腳本。

## 目錄結構

```
threads_scraper/
├── data/                 # 已抓取的 JSON 貼文資料
├── renew_cookies.py      # 透過 Selenium 更新登入 cookies
├── requirements.txt      # 依賴套件清單
├── scrapy.cfg            # Scrapy 設定檔
├── threads_scraper/      # Scrapy 專案原始碼
│   ├── spiders/          # Threads 與 Facebook 爬蟲
│   ├── generate_content.py   # 以 g4f 產生貼文內容
│   └── post_to_threads.py    # 使用 Playwright 發佈貼文
└── readme.txt            # 建立虛擬環境的簡短說明
```

## 安裝

1. 建立虛擬環境並安裝依賴：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install
```

2. (選用) 若需重新產生登入 cookies，可執行：

```bash
python renew_cookies.py
```

## 使用方式

### 抓取 Threads 貼文

```
scrapy crawl threads -a username="YOUR_INSTAGRAM" -a password="YOUR_PASSWORD" \
    -a scroll_limit=5 -a search_keyword="關鍵字"
```

- `scroll_limit` 控制向下捲動次數，影響抓取的貼文數量。
- `search_keyword` 可選，用來抓取搜尋結果。

結果會存成 `data/<帳號>_threads_posts.json` 或 `data/<關鍵字>_threads_posts_search.json`。

### 抓取 Facebook 貼文

```
scrapy crawl facebook -a username="YOUR_ACCOUNT" -a password="YOUR_PASSWORD" \
    -a scroll_limit=10 -a search_keyword="關鍵字"
```

儲存路徑同上，檔名以 `_facebook_posts.json` 結尾。

### 產生並發佈 Threads 貼文

執行以下指令會根據 `data/` 資料生成貼文內容，並登入 Threads 發佈：

```bash
python -m threads_scraper.post_to_threads
```

## 資料處理

`data/sort_posts.py` 提供排序工具，可將 `data/` 內的 JSON 檔依 `datetime` 由新到舊排序：

```bash
python data/sort_posts.py
```

## 授權

本專案未附授權條款，使用時請自行評估相關風險。

