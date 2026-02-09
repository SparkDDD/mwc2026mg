import os
import time
import random
import requests
from playwright.sync_api import sync_playwright

# --- 설정 (GitHub Secrets에 등록 필수) ---
EMAIL = os.getenv("MWC_EMAIL")
PASSWORD = os.getenv("MWC_PASSWORD")
MY_MESSAGE = os.getenv("MWC_CUSTOM_MSG", "Hello This is a sample message")
MAKE_REPORT_URL = os.getenv("MAKE_REPORT_URL") # 시트 업데이트용 Webhook

# 발송 대상을 인자로 받거나 외부 파일에서 읽어옵니다.
def get_target_ids():
    if os.path.exists("targets.txt"):
        with open("targets.txt", "r") as f:
            return [line.strip() for line in f if line.strip()]
    return []

def report_status(uid, status, log=""):
    """Make.com을 통해 구글 시트 상태 업데이트"""
    if not MAKE_REPORT_URL: return
    try:
        requests.post(MAKE_REPORT_URL, json={
            "uuid": uid,
            "status": status,
            "log": log,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        })
    except: pass

def do_login(page):
    page.goto("https://www.mwcbarcelona.com/mymwc", wait_until="domcontentloaded")
    try:
        page.locator("#onetrust-accept-btn-handler").click(timeout=5000)
        page.wait_for_timeout(2000)
    except: pass
    
    page.fill("input[type='email']", EMAIL)
    page.fill("input[type='password']", PASSWORD)
    page.click("button:has-text('Log in'), #login-button")
    page.wait_for_timeout(10000)

def main():
    targets = get_target_ids()
    if not targets: return

    with sync_playwright() as p:
        # GitHub 환경은 GUI가 없으므로 headless=True 필수
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36")
        page = context.new_page()

        do_login(page)

        for uid in targets:
            url = f"https://www.mwcbarcelona.com/mymwc/messaging?conversation={uid}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                input_sel = "input[placeholder='Type a message...']"
                page.wait_for_selector(input_sel, timeout=20000)
                
                page.click(input_sel)
                page.keyboard.type(MY_MESSAGE, delay=random.randint(50, 100))
                page.keyboard.press("Enter")
                
                print(f"[Success] {uid}")
                report_status(uid, "Success") # Make.com 호출
                
                # 안전한 간격 (1,000건 발송 시 최소 20초 이상 권장)
                time.sleep(random.uniform(20, 35))
            except Exception as e:
                print(f"[Fail] {uid}: {e}")
                report_status(uid, "Fail", str(e)[:50])

        browser.close()

if __name__ == "__main__":
    main()
