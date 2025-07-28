# scrapy crawl facebook
import os
import asyncio
import scrapy
from scrapy_playwright.page import PageMethod
import logging
import random
import urllib.parse
from .utils import save_posts_to_file, load_existing_posts, remove_duplicates
from .custom_settings import CUSTOM_SETTINGS_facebook

class FacebookSpider(scrapy.Spider):
    name = "facebook"
    start_urls = ['https://www.facebook.com/']

    custom_settings = CUSTOM_SETTINGS_facebook

    def __init__(self, username=None, password=None, scroll_limit=10, search_keyword=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.username = username
        self.password = password
        self.scroll_limit = scroll_limit
        self.search_keyword = search_keyword  # 用於搜尋的關鍵字
        self.target_accounts = ["TurnipMagazine"]  # 需要抓取的目標帳號或專頁

    def start_requests(self):
        project_root = os.path.dirname(os.path.abspath(__file__))
        cookies_path = os.path.join(project_root, 'facebook_cookies.json')

        headers = {
            "User-Agent": CUSTOM_SETTINGS_facebook["USER_AGENT"],
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

        if not os.path.exists(cookies_path):
            yield scrapy.Request(
                url="https://www.facebook.com/login",
                callback=self.login_and_save_cookies,
                headers=headers,
                cb_kwargs={'headers': headers},
                meta=dict(
                    playwright=True,
                    playwright_include_page=True,
                    playwright_page_methods=[
                        PageMethod("wait_for_selector", 'input[name="email"]')
                    ],
                )
            )
        else:
            FacebookSpider.login_completed = True  # 直接設置為已登錄
            yield from self.process_accounts_after_login(headers)

            # 檢查是否有設置搜尋關鍵字
            if self.search_keyword:
                yield from self.process_search_after_login(headers)

    async def login_and_save_cookies(self, response, headers):
        page = response.meta["playwright_page"]
        logging.info("輸入用戶名和密碼。")

        # 模擬滑鼠移動到輸入框並點擊
        email_input = await page.query_selector('input[name="email"]')
        await self.simulate_mouse_move_and_click(page, email_input)
        await self.type_text_with_delay(page, email_input, self.username)

        await asyncio.sleep(random.uniform(1, 3))  # 隨機延遲

        password_input = await page.query_selector('input[name="pass"]')
        await self.simulate_mouse_move_and_click(page, password_input)
        await self.type_text_with_delay(page, password_input, self.password)

        logging.info("提交登入表單。")
        # 模擬滑鼠移動到登入按鈕並點擊
        login_button = await page.query_selector('button[name="login"]')
        await self.simulate_mouse_move_and_click(page, login_button)

        await asyncio.sleep(random.uniform(5, 10))  # 等待登入完成

        # 設置為已完成登入
        FacebookSpider.login_completed = True

        # 處理登入後的帳號
        for request in self.process_accounts_after_login(headers):
            yield request

        # 檢查是否有設置搜尋關鍵字
        if self.search_keyword:
            for request in self.process_search_after_login(headers):
                yield request

    async def simulate_mouse_move_and_click(self, page, element):
        """
        模擬滑鼠移動到元素上並點擊
        """
        box = await element.bounding_box()
        if box:
            # 隨機移動滑鼠到元素不同的位置
            target_x = box['x'] + random.uniform(0.3, 0.7) * box['width']
            target_y = box['y'] + random.uniform(0.3, 0.7) * box['height']
            await page.mouse.move(target_x, target_y, steps=random.randint(10, 20))
            await asyncio.sleep(random.uniform(0.3, 0.7))  # 懸停
            await page.mouse.click(target_x, target_y, delay=random.uniform(200, 500))  # 點擊帶有延遲

    async def type_text_with_delay(self, page, element, text):
        """
        模擬逐字輸入文字並隨機延遲和模擬錯誤輸入
        """
        for char in text:
            await element.type(char)
            if random.random() < 0.00:  # 0.5% 的概率出現輸入錯誤
                await element.press("Backspace")
            await asyncio.sleep(random.uniform(0.05, 0.3))  # 模擬真實輸入

    async def parse_account_page(self, response):
        page = response.meta["playwright_page"]
        is_search = response.meta.get('is_search', False)
        await page.wait_for_timeout(random.uniform(2, 4) * 1000)  # 等待頁面載入

        posts = []
        scroll_count = 0
        last_height = await page.evaluate("document.body.scrollHeight")

        base_selector = "#mount_0_0_\\/W > div > div > div:nth-child(1) > div > div.x9f619.x1n2onr6.x1ja2u2z > div > div > div.x78zum5.xdt5ytf.x1t2pt76.x1n2onr6.x1ja2u2z.x10cihs4 > div.x78zum5.xdt5ytf.x1t2pt76 > div > div > div.x6s0dn4.x78zum5.xdt5ytf.x193iq5w > div.x9f619.x193iq5w.x1talbiv.x1sltb1f.x3fxtfs.x1swvt13.x1pi30zi.xw7yly9 > div > div.x9f619.x1n2onr6.x1ja2u2z.xeuugli.xs83m0k.xjl7jj.x1xmf6yo.x1emribx.x1e56ztr.x1i64zmx.x19h7ccj.xu9j1y6.x7ep2pv > div:nth-child(3) > div:nth-child({})"

        post_index = 1
        while scroll_count < self.scroll_limit:
            logging.info("抓取貼文元素。")
            
            while True:
                selector = base_selector.format(post_index)
                post_element = await page.query_selector(selector)
                if not post_element:
                    break  # 當無法再找到下一個貼文時，退出循環
                post_index += 1

                try:
                    logging.info(f"抓取第 {post_index} 個元素的內容。")

                    # 抓取貼文首段內容
                    content = ""
                    first_paragraph = await post_element.query_selector("span.x193iq5w.xeuugli.x13faqbe.x1vvkbs.xlh3980.xvmahel.x1n0sxbx.x1lliihq.x1s928wv.xhkezso.x1gmr53x.x1cpjm7i.x1fgarty.x1943h6x.x4zkp8e.x3x7a5m.x6prxxf.xvq8zen.xo1l8bm.xzsf02u.x1yc453h")
                    if first_paragraph:
                        content += await first_paragraph.inner_text() + " "

                        # 檢查是否有 "查看更多" 按鈕
                        more_button = await post_element.query_selector("div.x1i10hfl.xjbqb8w.x1ejq31n.xd10rxx.x1sy0etr.x17r0tee.x972fbf.xcfux6l.x1qhh985.xm0m39n.x9f619.x1ypdohk.xt0psk2.xe8uvvx.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x16tdsg8.x1hl2dhg.xggy1nq.x1a2a7pz.x1sur9pj.xkrqix3.xzsf02u.x1s688f[role='button']")
                        if more_button:
                            await more_button.click()
                            await asyncio.sleep(random.uniform(1, 3))  # 模擬用戶點擊 "查看更多" 按鈕後的等待

                        # 抓取展開後的文字內容
                        expanded_paragraphs = await post_element.query_selector_all("div.x11i5rnm.xat24cr.x1mh8g0r.x1vvkbs.xtlvy1s.x126k92a div[dir='auto']")
                        for paragraph in expanded_paragraphs:
                            content += await paragraph.inner_text() + " "

                    # 定位時間、作者與連結的元素
                    time_container = await post_element.query_selector("div.xu06os2.x1ok221b")
                    time_container_2 = await time_container.query_selector("span.x193iq5w.xeuugli.x13faqbe.x1vvkbs.xlh3980.xvmahel.x1n0sxbx.x1lliihq.x1s928wv.xhkezso.x1gmr53x.x1cpjm7i.x1fgarty.x1943h6x.x4zkp8e.x676frb.x1nxh6w3.x1sibtaa.xo1l8bm.xi81zsa.x1yc453h")
                    time_div = await time_container_2.query_selector("div.html-div.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x1q0g3np")
                    author_span = await time_div.query_selector("span.html-span.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x1hl2dhg.x16tdsg8.x1vvkbs")
                    author_link = await author_span.query_selector("a")
                    
                    author_name = await author_link.inner_text() if author_link else "Unknown"
                    post_link = await author_link.get_attribute('href') if author_link else "N/A"

                    # 抓取附件（圖片或影片）
                    attachment = None
                    image_elements = await post_element.query_selector_all('img')
                    if image_elements:
                        attachment = "pic: "
                        for img in image_elements:
                            img_url = await img.get_attribute('src')
                            attachment += img_url + " "

                    video_elements = await post_element.query_selector_all('video')
                    if video_elements:
                        if attachment:
                            attachment += ", "
                        attachment += "video: "
                        for video in video_elements:
                            video_url = await video.get_attribute('src')
                            attachment += video_url + " "

                    # 判斷是否要保存該貼文
                    if content.strip():  # 排除無內容的貼文
                        post_data = {
                            "datetime": await self.extract_post_time(page),
                            "author": author_name,
                            "post_link": post_link,
                            "content": content.strip(),
                            "attachment": attachment
                        }
                        posts.append(post_data)

                except Exception as e:
                    logging.error(f"抓取貼文數據出錯: {e}")

            logging.info("滾動頁面。")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await page.wait_for_timeout(3000)  # 等待滾動效果

            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                logging.info("到達頁面底部。")
                break
            last_height = new_height
            scroll_count += 1

        # 去重貼文
        unique_posts = remove_duplicates(posts)

        # 更新貼文庫並保存
        account_name = response.meta['account_name']
        filename = f"data/{account_name}_facebook_posts.json"
        if is_search:
            filename = filename.replace(".json", "_search.json")

        all_posts = load_existing_posts(filename)
        all_posts.extend(unique_posts)
        all_posts = remove_duplicates(all_posts)

        logging.info(f"已抓取 {len(unique_posts)} 篇有效貼文，保存至庫中")
        save_posts_to_file(all_posts, filename)

        await page.close()

    async def extract_post_time(self, page):
        """
        從 time_div 中抓取時間信息
        """
        # 操控滑鼠到該位置，觸發時間顯示
        await page.hover()
        await asyncio.sleep(random.uniform(1, 2))  # 模擬用戶的懸停操作

        time_element = await page.query_selector("#mount_0_0_H2 > div > div > div:nth-child(1) > div > div.x9f619.x1n2onr6.x1ja2u2z > div > div > div:nth-child(2) > div")
        if time_element:
            return await time_element.get_attribute('title')
        return "N/A"