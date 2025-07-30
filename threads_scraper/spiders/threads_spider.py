# scrapy crawl threads -a username="xxx" -a password="xxx" -a scroll_limit=10 -a search_keyword="柯文哲" -a group_number=0

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

    custom_settings = {
        **CUSTOM_SETTINGS_threads,
    }

    def __init__(self, username=None, password=None,
                 scroll_limit=5, search_keyword=None,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.username = username
        self.password = password
        try:
            self.scroll_limit = int(scroll_limit)
        except (TypeError, ValueError):
            self.scroll_limit = 5
        self.search_keyword = search_keyword
        self.target_accounts = []

    # ------------------------------------------------------------------ #
    # 登入 / Cookie / 目標網址產生
    # ------------------------------------------------------------------ #
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
                        PageMethod(
                            "wait_for_selector",
                            'input[placeholder="用戶名稱、手機號碼或電子郵件地址"]'
                        )
                    ],
                ),
            )
        else:
            ThreadsSpider.login_completed = True
            yield from self.process_accounts_after_login(headers)
            if self.search_keyword:
                yield from self.process_search_after_login(headers)

    def process_accounts_after_login(self, headers):
        if ThreadsSpider.login_completed:
            for acc in self.target_accounts:
                yield scrapy.Request(
                    url=f"https://www.threads.net/@{acc}?hl=zh-tw",
                    callback=self.parse_account_page,
                    headers=headers,
                    meta={
                        "playwright": True,
                        "playwright_include_page": True,
                        "account_name": acc,
                        "is_search": False,
                    },
                )

    def process_search_after_login(self, headers):
        if self.search_keyword:
            kw = urllib.parse.quote(self.search_keyword)
            url = f"https://www.threads.net/search?q={kw}&filter=recent"
            yield scrapy.Request(
                url,
                callback=self.parse_account_page,
                headers=headers,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "account_name": self.search_keyword,
                    "is_search": True,
                },
            )

    async def login_and_save_cookies(self, response, headers):
        page = response.meta["playwright_page"]
        logging.info("輸入用戶名和密碼。")
        await page.fill(
            'input[placeholder="用戶名稱、手機號碼或電子郵件地址"]',
            self.username
        )
        await page.wait_for_timeout(random.uniform(1, 3) * 1000)
        await page.fill('input[placeholder="密碼"]', self.password)
        await page.wait_for_timeout(random.uniform(1, 3) * 1000)
        logging.info("提交登入表單。")
        await page.press('input[placeholder="密碼"]', 'Enter')
        await page.wait_for_timeout(random.uniform(8, 12) * 1000)

        ThreadsSpider.login_completed = True
        for r in self.process_accounts_after_login(headers):
            yield r
        if self.search_keyword:
            for r in self.process_search_after_login(headers):
                yield r

    # ------------------------------------------------------------------ #
    # **修改點 1**：以「恰好只有 x78zum5 xdt5ytf」的大外框為單位擷取
    # **修改點 2**：平面 schema，新增 response_to 欄位 (方案 B)
    # **修改點 3**：Attachment for pic, link, video（先檢測影片）
    # **修改點 4**：清洗並解析讚/留言數字
    # **修改點 5**：轉發（repost）抽取，並為原帖 B 加上 attachment
    # ------------------------------------------------------------------ #
    async def parse_account_page(self, response):
        page = response.meta["playwright_page"]
        is_search = bool(response.meta.get("is_search", False))
        account_name = response.meta["account_name"]

        try:
            await page.wait_for_selector('div.x78zum5.xdt5ytf', timeout=10_000)
        except:
            self.logger.warning("10 秒內未找到任何串文大外框。")

        posts, seen = [], set()
        last_height = await page.evaluate("document.body.scrollHeight")
        scroll_cnt = 0

        def parse_count(text: str) -> int:
            s = text.replace(',', '').replace('\n', '').strip()
            if not s:
                return 0
            if '萬' in s:
                try:
                    num = float(s.replace('萬', '').strip())
                except:
                    return 0
                return int(num * 10000)
            digits = ''.join(ch for ch in s if ch.isdigit())
            return int(digits) if digits else 0

        async def handle_attachment(container, data):
            # 1. 先檢測影片
            vid = await container.query_selector('video.x1lliihq.x5yr21d.xh8yej3')
            if vid:
                vsrc = (await vid.get_attribute("src")) or ""
                data["attachment"] = f"video, src={vsrc.strip()}"
                return
            # 2. 再檢測圖片
            pic = await container.query_selector('picture.x87ps6o img')
            if pic:
                alt = (await pic.get_attribute("alt")) or ""
                src = (await pic.get_attribute("srcset")) or (await pic.get_attribute("src") or "")
                data["attachment"] = f"pic, alt={alt.strip()}, src={src.strip()}"
                return
            # 3. 最後檢測一般連結
            linkdiv = await container.query_selector('div.x1e56ztr.xw7yly9.x1j9u4d2 a')
            if linkdiv:
                alt = (await linkdiv.get_attribute("alt")) or ""
                href = (await linkdiv.get_attribute("href")) or ""
                data["attachment"] = f"link, alt={alt.strip()}, href={href.strip()}"

        async def parse_single(el):
            # --- 基本貼文 link & datetime ---
            anchor = await el.query_selector(
                'a[role="link"][href*="/post/"]:not([href$="/media"])'
            )
            if not anchor:
                return [], None
            rel = await anchor.get_attribute("href")
            if not rel or "/post/" not in rel:
                return [], None
            link = f"https://www.threads.net{rel}"
            t_el = await anchor.query_selector("time")
            dt = await t_el.get_attribute("datetime") if t_el else "N/A"

            # --- 檢測「正在回覆@username」 ---
            response_to = await el.evaluate(
                "node => {"
                "  const s = [...node.querySelectorAll('span')].find(x=>x.innerText.includes('正在回覆@'));"
                "  return s ? s.innerText.split('@')[1].trim() : null;"
                "}"
            )

            # --- 正文 ---
            texts = await el.evaluate(
                "node=>[...node.querySelectorAll('div[dir=\"auto\"] span'),"
                "...node.querySelectorAll('div.x1a6qonq span span')]"
                ".map(s=>s.innerText.trim())"
            )
            content = " ".join([t for t in texts if t])

            # --- 讚/留言 數字清洗 ---
            stats = await el.query_selector_all('span.x1o0tod.x10l6tqk.x13vifvy')
            raw_likes = await stats[0].inner_text() if len(stats) >= 1 else ""
            raw_comments = await stats[1].inner_text() if len(stats) >= 2 else ""
            likes = parse_count(raw_likes)
            comments = parse_count(raw_comments)

            # --- 初始資料物件 A ---
            main_data = {
                "datetime": dt,
                "post_link": link,
                "content": content,
                "likes": likes,
                "comments": comments,
                "attachment": "",
                "response_to": response_to,
            }
            if is_search:
                main_data["author"] = rel.split("/")[1][1:]

            # --- 處理主帖的 attachment（會先檢影片）---
            await handle_attachment(el, main_data)

            # --- 檢測並抽取「轉發」(repost) ---
            repost_box = await el.query_selector(
                'div.x6bh95i.x1gzj6u4.x1hvtcl2.x1e1ff7m.xgrrwr1.x7o7tq0.'
                'x1rs6hn2.xvb4t3y.x13fuv20.x18b5jzi.x1q0q8m5.x1t7ytsu.'
                'x178xt8z.x1lun4ml.xso031l.xpilrb4.x101abm8.x1s73dr8.'
                'xyamay9.x1l90r2v.xoytce5.x180ibxj'
            )
            posts_out = []
            if repost_box:
                # 原帖 B 的作者
                orig_author_el = await repost_box.query_selector(
                    'span.x1lliihq.x193iq5w.x6ikm8r.x10wlt62.xlyipyv.xuxw1ft'
                )
                orig_author = await orig_author_el.inner_text() if orig_author_el else None
                # 原帖 B 的 link & datetime
                orig_link_el = await repost_box.query_selector(
                    'div.x78zum5.x1c4vz4f.x2lah0s a'
                )
                orig_link = await orig_link_el.get_attribute("href") if orig_link_el else None
                if orig_link and orig_link.startswith("/"):
                    orig_link = f"https://www.threads.net{orig_link}"
                orig_time_el = await repost_box.query_selector(
                    'div.x78zum5.x1c4vz4f.x2lah0s time'
                )
                orig_dt = await orig_time_el.get_attribute("datetime") if orig_time_el else "N/A"
                # 原帖 B 的內容
                orig_content = await repost_box.evaluate(
                    "node=>node.querySelector('div.x1gslohp span')?.innerText.trim() || ''"
                )

                # --- 組原帖 B 的資料，並處理 attachment ---
                orig_data = {
                    "datetime": orig_dt,
                    "post_link": orig_link,
                    "content": orig_content,
                    "likes": 0,
                    "comments": 0,
                    "attachment": "",
                    "response_to": None,
                    "author": orig_author,
                }
                await handle_attachment(repost_box, orig_data)

                # 主帖 A 標記為轉發
                main_data["response_to"] = orig_link
                main_data["attachment"] = f"repost, link={orig_link}"
                posts_out.append(orig_data)

            # 最後把主帖 A 加入
            posts_out.append(main_data)
            return posts_out, link

        # ---------- 主迴圈：滾動抓取 ----------
        while scroll_cnt < self.scroll_limit:
            boxes = []
            for b in await page.query_selector_all('div.x78zum5.xdt5ytf'):
                cls = (await b.get_attribute("class") or "").split()
                if set(cls) == {"x78zum5", "xdt5ytf"}:
                    boxes.append(b)

            for bx in boxes:
                try:
                    items = await bx.query_selector_all('div.x1a2a7pz.x1n2onr6')
                    if not items:
                        continue
                    # 解析主貼文 + 可能的轉發原帖
                    batch, mlink = await parse_single(items[0])
                    for entry in batch:
                        if entry["post_link"] and entry["post_link"] not in seen:
                            seen.add(entry["post_link"])
                            posts.append(entry)
                    # 解析回覆貼文
                    for sub in items[1:]:
                        reply_batch, rlink = await parse_single(sub)
                        for rep in reply_batch:
                            if rep and rlink not in seen:
                                seen.add(rlink)
                                posts.append(rep)
                except Exception as e:
                    self.logger.error(f"解析外框失敗: {e}")

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(4000)
            new_h = await page.evaluate("document.body.scrollHeight")
            if new_h == last_height:
                self.logger.info("已到頁面底部")
                break
            last_height, scroll_cnt = new_h, scroll_cnt + 1

        unique = remove_duplicates(posts)
        self.logger.info(f"本輪共擷取 {len(unique)} 則貼文")

        fname = f"data/{account_name}_threads_posts"
        if is_search:
            fname += "_search"
        fname += ".json"

        existing = load_existing_posts(fname)
        existing.extend(unique)
        save_posts_to_file(remove_duplicates(existing), fname)

        await page.close()