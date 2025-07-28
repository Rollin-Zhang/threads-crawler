CUSTOM_SETTINGS_threads = {
    "PLAYWRIGHT_BROWSER_TYPE": "chromium",
    "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": False},
    "DOWNLOAD_HANDLERS": {
        "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    },
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "LOG_LEVEL": "INFO",
    "LOG_FILE": "scrapy_log.txt",
}

CUSTOM_SETTINGS_facebook = {
    "PLAYWRIGHT_BROWSER_TYPE": "chromium",
    "PLAYWRIGHT_LAUNCH_OPTIONS": {
        "headless": False,
        "executable_path": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "args": [
            "--disable-blink-features=AutomationControlled",  # 禁用自動化控制標誌
            "--disable-web-security",  # 禁用網頁安全性，避免跨域問題
            "--disable-features=IsolateOrigins,site-per-process",  # 禁用站點隔離
            "--enable-features=NetworkService,NetworkServiceInProcess",  # 啟用網路服務
            "--no-sandbox",
            "--disable-setuid-sandbox",
            # "--start-maximized",  # 啟動時最大化窗口
        ],
    },
    "DOWNLOAD_HANDLERS": {
        "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    },
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "LOG_LEVEL": "INFO",
    "LOG_FILE": "facebook_scrapy_log.txt",
    "COOKIES_ENABLED": True,  # 啟用 cookies
    "RANDOMIZE_DOWNLOAD_DELAY": True,  # 隨機延遲
    "DOWNLOAD_DELAY": 2,  # 每個請求之間的延遲時間
    "AUTOTHROTTLE_ENABLED": True,  # 啟用自動限速
    "AUTOTHROTTLE_START_DELAY": 1,  # 開始延遲
    "AUTOTHROTTLE_MAX_DELAY": 10,  # 最大延遲
    "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,  # 目標並發數量
    "AUTOTHROTTLE_DEBUG": False,  # 禁用自動限速的調試日誌
}