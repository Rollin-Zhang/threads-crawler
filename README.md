# Threads 專用爬蟲與自動化

本專案專注於 Threads 平台的爬蟲、去重工具、發文自動化。Facebook 相關功能已移除，將在另一個 repo 開發。

## 目錄結構

```
Threads/
  ├── renew_cookies.py         # Threads cookies 自動更新
  ├── requirements.txt         # 依賴套件
  ├── scrapy.cfg               # Scrapy 設定
  ├── data/                    # 貼文資料與處理工具
  └── threads_scraper/
      ├── spiders/             # Threads 爬蟲主程式
      ├── post_to_threads.py   # Threads 自動發文工具
      ├── ...                  # 其他輔助模組
```

## 安裝步驟

1. 建立虛擬環境
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
2. 安裝依賴
   ```bash
   pip install -r requirements.txt
   ```
3. 安裝 Playwright 瀏覽器
   ```bash
   playwright install
   ```

## 設定環境變數

請複製 `.env.example` 為 `.env`，並填入 Threads 帳號密碼：

```
THREADS_USERNAME=your_threads_account
THREADS_PASSWORD=your_threads_password
```

## 執行流程

- 更新 Threads cookies：
  ```bash
  python renew_cookies.py
  ```
- 執行 Threads 爬蟲：
  ```bash
  cd Threads
  scrapy crawl threads_spider
  ```
- Threads 自動發文：
  ```bash
  python Threads/threads_scraper/post_to_threads.py
  ```

## 注意事項

- 請勿將 `.env`、cookies、資料輸出等敏感檔案提交至版本控制。
- Facebook 相關功能已移除，請至另一 repo 取得。

---
