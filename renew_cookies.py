import os
import json
import logging
import time
import random
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

# 初始化日誌設置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 初始化WebDriver
def init_driver():
    service = ChromeService(executable_path=ChromeDriverManager().install())
    options = Options()
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--incognito")  # 使用無痕模式
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    return webdriver.Chrome(service=service, options=options)

driver = init_driver()

def random_sleep(min_seconds=1, max_seconds=3):
    time.sleep(random.uniform(min_seconds, max_seconds))

def login_to_threads(username, password, cookies_path, storage_state_path):
    logging.info("導航至Threads登入頁面。")
    driver.get("https://www.threads.net/login/?hl=zh-tw")
    random_sleep(2, 4)
    
    logging.info("輸入用戶名和密碼。")
    
    # 使用 placeholder 屬性來選擇 "用戶名稱" 和 "密碼" 的輸入框
    username_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="用戶名稱、手機號碼或電子郵件地址"]')
    password_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="密碼"]')
    
    username_input.send_keys(username)
    random_sleep()
    password_input.send_keys(password)
    random_sleep()
    
    logging.info("提交登入表單。")
    password_input.send_keys(Keys.RETURN)
    random_sleep(7, 10)

    # 進入首頁等待一段時間，確保 cookies 寫入
    try:
        driver.get("https://www.threads.net/?hl=zh-tw")
        random_sleep(5, 8)
    except Exception:
        pass

    # 保存 cookies 到指定路徑
    cookies = driver.get_cookies() or []
    os.makedirs(os.path.dirname(cookies_path), exist_ok=True)
    if not cookies:
        logging.warning("目前取得的 cookies 為空，將寫入空陣列以避免 null。")
    with open(cookies_path, "w", encoding="utf-8") as file:
        json.dump(list(cookies), file, ensure_ascii=False)
    logging.info(f"Cookies 已保存至 {cookies_path}")
    random_sleep(3, 5)

    # 嘗試轉為 storage_state
    try:
        from tools.cookies_to_storage_state import to_storage_state
        to_storage_state(cookies_path, storage_state_path)
        logging.info(f"storage_state 已生成：{storage_state_path}")
    except Exception as e:
        logging.warning(f"轉 storage_state 失敗：{e}（可手動執行：python tools/cookies_to_storage_state.py）")

if __name__ == "__main__":
    INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME") or os.getenv("THREADS_USERNAME")
    INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD") or os.getenv("THREADS_PASSWORD")

    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        logging.error("請在 .env 設定 INSTAGRAM_USERNAME 與 INSTAGRAM_PASSWORD（或沿用 THREADS_USERNAME/THREADS_PASSWORD）！")
        driver.quit()
        raise SystemExit(1)

    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    COOKIES_PATH = os.path.join(PROJECT_ROOT, 'Threads', 'threads_scraper', 'cookies.json')
    STORAGE_STATE_PATH = os.path.join(PROJECT_ROOT, 'Threads', 'threads_scraper', 'storage_state.json')

    login_to_threads(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, COOKIES_PATH, STORAGE_STATE_PATH)
    driver.quit()