import os
import json
import logging
import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

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

def login_to_threads(username, password):
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

    # 保存 cookies 到 threads_scraper 資料夾
    project_root = os.path.dirname(os.path.abspath(__file__))
    cookies_path = os.path.join(project_root, 'threads_scraper', 'cookies.json')

    cookies = driver.get_cookies()
    with open(cookies_path, "w") as file:
        json.dump(cookies, file)
    logging.info(f"Cookies 已保存至 {cookies_path}")
    random_sleep(3, 5)

if __name__ == "__main__":
    INSTAGRAM_USERNAME = "zhangjuntao7190"
    INSTAGRAM_PASSWORD = "rn666777000"
    
    login_to_threads(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
    
    driver.quit()