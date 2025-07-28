# scrapy crawl threads -a username="zhangjt7190" -a password="rn666777000" -a search_keyword="柯文哲" -a group_number=0 
import os
import scrapy
from scrapy_playwright.page import PageMethod
import logging
import random
import urllib.parse
from .utils import save_posts_to_file, load_existing_posts, remove_duplicates
from .custom_settings import CUSTOM_SETTINGS_threads

class ThreadsSpider(scrapy.Spider):
    name = "threads"
    start_urls = ['https://www.threads.net/?hl=zh-tw']

    custom_settings = CUSTOM_SETTINGS_threads

    def __init__(self, username=None, password=None, scroll_limit=5, search_keyword=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.username = username
        self.password = password
        self.scroll_limit = scroll_limit
        self.search_keyword = search_keyword
        self.target_accounts = ["asyoucansee498", "wusuyao541", "hello_sunhan", "redlover770305"]
        
    def start_requests(self):
        project_root = os.path.dirname(os.path.abspath(__file__))
        cookies_path = os.path.join(project_root, 'cookies.json')

        headers = {
            "User-Agent": CUSTOM_SETTINGS_threads["USER_AGENT"],
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

        if not os.path.exists(cookies_path):
            yield scrapy.Request(
                url="https://www.threads.net/login/?hl=zh-tw",
                callback=self.login_and_save_cookies,
                headers=headers,
                cb_kwargs={'headers': headers},
                meta=dict(
                    playwright=True,
                    playwright_include_page=True,
                    playwright_page_methods=[
                        PageMethod("wait_for_selector", 'input[placeholder="用戶名稱、手機號碼或電子郵件地址"]')
                    ],
                )
            )
        else:
            ThreadsSpider.login_completed = True  # 直接設置為已登錄
            yield from self.process_accounts_after_login(headers)

            # 檢查是否有設置搜尋關鍵字
            if self.search_keyword:
                yield from self.process_search_after_login(headers)

    def process_accounts_after_login(self, headers):
        if ThreadsSpider.login_completed:
            for account in self.target_accounts:
                account_url = f"https://www.threads.net/@{account}?hl=zh-tw"
                yield scrapy.Request(
                    url=account_url,
                    callback=self.parse_account_page,
                    headers=headers,
                    meta=dict(
                        playwright=True,
                        playwright_include_page=True,
                        account_name=account,
                        is_search=False  # 標記這不是搜尋
                    )
                )

    def process_search_after_login(self, headers):
        # 如果有設定搜尋關鍵字，則執行搜尋操作
        if self.search_keyword:
            encoded_keyword = urllib.parse.quote(self.search_keyword)
            search_url = f"https://www.threads.net/search?q={encoded_keyword}&filter=recent"
            yield scrapy.Request(
                url=search_url,
                callback=self.parse_account_page,
                headers=headers,
                meta=dict(
                    playwright=True,
                    playwright_include_page=True,
                    account_name=self.search_keyword,
                    is_search=True  # 標記這是搜尋
                )
            )

    async def login_and_save_cookies(self, response, headers):
        page = response.meta["playwright_page"]
        logging.info("輸入用戶名和密碼。")

        await page.fill('input[placeholder="用戶名稱、手機號碼或電子郵件地址"]', self.username)
        await page.wait_for_timeout(random.uniform(1, 3) * 1000)
        await page.fill('input[placeholder="密碼"]', self.password)
        await page.wait_for_timeout(random.uniform(1, 3) * 1000)
        
        logging.info("提交登入表單。")
        await page.press('input[placeholder="密碼"]', 'Enter')
        await page.wait_for_timeout(random.uniform(8, 12) * 1000)

        ThreadsSpider.login_completed = True  # 登錄完成後設置為True

        for request in self.process_accounts_after_login(headers):
            yield request

        # 檢查是否有設置搜尋關鍵字
        if self.search_keyword:
            for request in self.process_search_after_login(headers):
                yield request

    async def parse_account_page(self, response):
        page = response.meta["playwright_page"]
        is_search = response.meta.get('is_search', False)  # 獲取是否為搜尋結果
        await page.wait_for_timeout(random.uniform(10, 12) * 1000)  # 等待頁面載入

        posts = []
        scroll_count = 0
        last_height = await page.evaluate("document.body.scrollHeight")

        while scroll_count < self.scroll_limit:
            logging.info("抓取貼文元素。")
            unfiltered_thread_elements = await page.query_selector_all("div.x78zum5.xdt5ytf")

            # 過濾僅包含這兩個類別的元素
            thread_elements = []
            for element in unfiltered_thread_elements:
                class_names = await element.get_attribute("class")
                class_list = class_names.split()
                # 如果該元素僅包含這兩個類別，將其加入列表
                if set(class_list) == {"x78zum5", "xdt5ytf"}:
                    thread_elements.append(element)
            logging.info(f"找到 {len(thread_elements)} 個元素。")

            for index, thread in enumerate(thread_elements):
                try:
                    logging.info(f"抓取第 {index + 1} 個元素的內容。")

                    # 發文時間
                    datetime_element = await thread.query_selector("time.x1rg5ohu.xnei2rj.x2b8uid.xuxw1ft")
                    datetime = await datetime_element.get_attribute('datetime') if datetime_element else "N/A"
                    logging.info(f"發文時間: {datetime}")

                    # 貼文連結與發文者
                    author = None
                    post_link_element = await thread.query_selector("a.x1i10hfl.xjbqb8w.x1ejq31n.xd10rxx.x1sy0etr.x17r0tee.x972fbf.xcfux6l.x1qhh985.xm0m39n.x9f619.x1ypdohk.xt0psk2.xe8uvvx.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x16tdsg8.x1hl2dhg.xggy1nq.x1a2a7pz.x1lku1pv.x12rw4y6.xrkepyr.x1citr7e.x37wo2f")
                    post_link = await post_link_element.get_attribute('href') if post_link_element else "N/A"
                    author = post_link.split("/")[1][1:]
                    if post_link != "N/A":
                        post_link = f"https://www.threads.net{post_link}"

                    logging.info(f"貼文連結: {post_link}")
                    
                    # 貼文內容
                    content = ""
                    content_elements = await thread.query_selector_all("div.x1a6qonq.x6ikm8r.x10wlt62.xj0a0fe.x126k92a.x6prxxf.x7r5mf7 > span")
                    for element in content_elements:
                        content += await element.inner_text() + " "

                    # 檢查引用貼文
                    quoted_post_element = await thread.query_selector('div.x6bh95i.x1re03b8.x1hvtcl2.x3ug3ww.x1lq5wgf.xgqcy7u.x30kzoy.x9jhf4c.x13fuv20.xu3j5b3.x1q0q8m5.x26u7qi.x178xt8z.xm81vs4.xso031l.xy80clv.xyamay9.x1l90r2v.x1b34her.x1vk9qys.x1ypdohk.x14vqqas')
                    if quoted_post_element:
                        quoted_info = "引用:\n"

                        # 提取引用的貼文時間
                        quoted_time_element = await quoted_post_element.query_selector("time.x1rg5ohu.xnei2rj.x2b8uid.xuxw1ft")
                        quoted_datetime = await quoted_time_element.get_attribute('datetime') if quoted_time_element else "N/A"
                        quoted_info += f"時間: {quoted_datetime}, "

                        # 提取引用的貼文連結
                        quoted_link_element = await quoted_post_element.query_selector("a.x1i10hfl.x1qjc9v5")
                        quoted_post_link = await quoted_link_element.get_attribute('href') if quoted_link_element else "N/A"
                        quoted_info += f"連結: https://www.threads.net{quoted_post_link}, "

                        # 提取引用的貼文內容
                        quoted_content_element = await quoted_post_element.query_selector("span.x1lliihq.x1plvlek.xryxfnj")
                        quoted_content = await quoted_content_element.inner_text() if quoted_content_element else "N/A"
                        quoted_info += f"內容: {quoted_content}, "

                        # 提取引用的附件資訊
                        quoted_attachment = ""
                        if await quoted_post_element.query_selector('img'):
                            quoted_attachment += "圖片, "
                        if await quoted_post_element.query_selector('video'):
                            quoted_attachment += "影片, "
                        quoted_info += f"附件: {quoted_attachment.strip(', ')}, "

                        # 將引用的內容加入主貼文
                        content += quoted_info

                    # 檢查附件
                    attachment = ""

                    # 檢查是否有圖片
                    if await thread.query_selector('picture.x87ps6o'):
                        attachment = "pic, "

                    # 檢查是否有影片
                    if await thread.query_selector('video.x1lliihq.x5yr21d.xh8yej3'):
                        attachment += "video, "

                    # 檢查是否有連結
                    link_element = await thread.query_selector('div.x1j9u4d2 a, a.x1i10hfl.xjbqb8w.x1ejq31n.xd10rxx.x1sy0etr.x17r0tee.x972fbf.xcfux6l.x1qhh985.xm0m39n.x9f619.x1ypdohk.xt0psk2.xe8uvvx.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x16tdsg8.x1hl2dhg.xggy1nq.x1a2a7pz.xzlwxrv.xklvfq0.x1citr7e.x1w4el19.xt0b8zv')
                    if link_element:
                        attachment += "site: "
                        link_url = await link_element.get_attribute('href')
                        attachment += link_url

                    # 判斷是否要保存該貼文
                    if content.strip():  # 排除無內容的貼文
                        post_data = {
                            "datetime": datetime,
                            "post_link": post_link,
                            "content": content.strip(),
                            "attachment": attachment
                        }
                        if is_search:
                            post_data["author"] = author  # 加上發文者資訊

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
        filename = f"data/{account_name}_threads_posts.json"
        if is_search:
            filename = filename.replace(".json", "_search.json")

        all_posts = load_existing_posts(filename)
        all_posts.extend(unique_posts)
        all_posts = remove_duplicates(all_posts)

        logging.info(f"已抓取 {len(unique_posts)} 篇有效貼文，保存至庫中")
        save_posts_to_file(all_posts, filename)

        await page.close()