# Threads Crawler

這個專案使用 [Scrapy](https://scrapy.org/) 搭配 [Playwright](https://playwright.dev/python/) 抓取 Meta Threads 與 Facebook 上的貼文，並提供自動發佈 Threads 貼文的腳本。

## 環境需求

- Python 3.11 以上版本
- Google Chrome/Chromium（Playwright 會自動下載對應瀏覽器）
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)（供 `pytesseract` 使用）
- 建議使用虛擬環境以避免與系統套件衝突

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

1. 建立並啟用虛擬環境：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r threads_scraper/requirements.txt
# 安裝瀏覽器 (首次執行 Playwright 時需執行一次)
playwright install
```

2. 安裝 Tesseract（供 `pytesseract` 使用）：

```bash
sudo apt-get install tesseract-ocr   # 或依系統安裝方式
```
3. (選用) 若需重新產生登入 cookies，可執行：

```bash
python renew_cookies.py
```

## 使用方式

### 抓取 Threads 貼文

```
scrapy crawl threads -a username="YOUR_INSTAGRAM" -a password="YOUR_PASSWORD" \
    -a scroll_limit=5 -a search_keyword="關鍵字"
```

#### 參數說明

- `username`、`password`：Threads 登入帳密
- `scroll_limit`：向下捲動次數，影響抓取的貼文數量，預設為 5
- `search_keyword`：搜尋關鍵字（可省略）

結果會存成 `data/<帳號>_threads_posts.json` 或 `data/<關鍵字>_threads_posts_search.json`。

### 抓取 Facebook 貼文

```
scrapy crawl facebook -a username="YOUR_ACCOUNT" -a password="YOUR_PASSWORD" \
    -a scroll_limit=10 -a search_keyword="關鍵字"
```

#### 參數說明

- `username`、`password`：Facebook 登入帳密
- `scroll_limit`：向下捲動次數，預設為 10
- `search_keyword`：搜尋關鍵字（可省略）

結果儲存於 `data/`，檔名以 `_facebook_posts.json` 結尾。

### 產生並發佈 Threads 貼文

執行以下指令會根據 `data/` 資料生成貼文內容，並登入 Threads 發佈：

```bash
python -m threads_scraper.post_to_threads
```

預設帳號密碼寫在 `threads_scraper/post_to_threads.py` 末端，可依需求修改。

## 資料處理

`data/sort_posts.py` 提供排序工具，可將 `data/` 內的 JSON 檔依 `datetime` 由新到舊排序：

```bash
python data/sort_posts.py
```

