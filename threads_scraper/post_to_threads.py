import os
import asyncio
from playwright.async_api import async_playwright
import random
from .generate_content import generate_post  # 引入生成貼文內容的函數

async def login(page, username, password):
    """
    處理登入操作
    """
    await page.goto("https://www.threads.net/login/?hl=zh-tw", wait_until="networkidle")
    await asyncio.sleep(random.uniform(2, 5))  # 等待頁面穩定
    await page.fill('input[placeholder="用戶名稱、手機號碼或電子郵件地址"]', username)
    await asyncio.sleep(random.uniform(1, 3))
    await page.fill('input[placeholder="密碼"]', password)
    await asyncio.sleep(random.uniform(1, 3))
    await page.press('input[placeholder="密碼"]', 'Enter')
    await asyncio.sleep(random.uniform(5, 8))  # 隨機等待登入完成

async def post_content(page, content):
    """
    處理貼文發布操作
    """
    await page.goto("https://www.threads.net/?hl=zh-tw", wait_until="networkidle")
    await asyncio.sleep(random.uniform(3, 6))  # 等待頁面加載

    # 滾動到頁面底部，模擬用戶瀏覽內容
    for _ in range(random.randint(1, 3)):
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await asyncio.sleep(random.uniform(1, 2))

    # 點擊建立串文的框框
    await page.click('text=建立串文……', delay=random.uniform(100, 300))  # 模擬手動點擊的延遲
    await asyncio.sleep(random.uniform(2, 5))

    # 找到輸入框並輸入內容
    content_input = await page.query_selector('p.xdj266r.x11i5rnm.xat24cr.x1mh8g0r')
    if content_input:
        for char in content:
            # 隨機決定是否模擬打字錯誤和修正
            if random.random() < 0.1:
                await content_input.type(random.choice("abcdefghijklmnopqrstuvwxyz"))
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await content_input.press("Backspace")

            await content_input.type(char)
            await asyncio.sleep(random.uniform(0.05, 0.3))  # 模擬真實輸入
    else:
        print("無法找到輸入框")
        return

    # 模擬用戶等待並查看自己輸入的內容
    await asyncio.sleep(random.uniform(3, 6))

    # 找到懸浮視窗的上層容器
    modal_container = await page.query_selector('div.x6s0dn4.x9f619.x78zum5.x15zctf7.x18r3tyq.x1qughib.x1p5oq8j.xxbr6pl.xwxc41k.xbbxn1n')

    if modal_container:
        # 在這個容器中查找「發佈」按鈕
        publish_button = await modal_container.query_selector('div.xc26acl.x6s0dn4.x78zum5.xl56j7k.x6ikm8r.x10wlt62.x1swvt13.x1pi30zi.xlyipyv.xp07o12')
        
        if publish_button:
            # 模擬鼠標移動到按鈕上
            box = await publish_button.bounding_box()
            await page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, steps=random.randint(3, 10))
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await publish_button.click(delay=random.uniform(100, 300))  # 模擬手動點擊的延遲
            await asyncio.sleep(random.uniform(5, 10))  # 等待貼文發布
        else:
            print("未找到發佈按鈕")
    else:
        print("未找到懸浮視窗容器")

async def main(username, password):
    async with async_playwright() as p:
        # 模擬不同的用戶代理
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(user_agent=user_agent)
        page = await context.new_page()

        await login(page, username, password)

        # 生成貼文內容
        generated_content = generate_post()

        # 發布生成的貼文內容
        await post_content(page, generated_content)

        await browser.close()

if __name__ == "__main__":
    username = "rollin1005tw@gmail.com"
    password = "rn666777000"

    asyncio.run(main(username, password))