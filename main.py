import os
import time
import random
import requests
from playwright.sync_api import sync_playwright

# 환경 변수 설정
EMAIL = os.getenv("MWC_EMAIL", "").strip()
PASSWORD = os.getenv("MWC_PASSWORD", "").strip()
MAKE_REPORT_URL = os.getenv("MAKE_REPORT_URL", "").strip()
TARGET_IDS_RAW = os.getenv("TARGET_IDS", "")
CUSTOM_MESSAGE = os.getenv("CUSTOM_MSG", "Hello!")

# 스크린샷 저장 폴더 생성
SCREENSHOT_DIR = "screenshots"
if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

def report_status(uid, status, log=""):
    if not MAKE_REPORT_URL: return
    try:
        requests.post(MAKE_REPORT_URL, json={
            "uuid": uid, "status": status, "log": log,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }, timeout=10)
    except: pass

def take_ss(page, name):
    """스크린샷 촬영 및 저장"""
    path = f"{SCREENSHOT_DIR}/{name}.png"
    page.screenshot(path=path)
    return path

def main():
    targets = [uid.strip() for uid in TARGET_IDS_RAW.split(",") if uid.strip()]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0...")
        page = context.new_page()

        # [Login] 단계
        print(f"[Login] 페이지 접속 중: {EMAIL}")
        page.goto("https://www.mwcbarcelona.com/mymwc", wait_until="networkidle")
        take_ss(page, "01_initial_page")

        try:
            if page.locator("#onetrust-accept-btn-handler").is_visible():
                page.click("#onetrust-accept-btn-handler")
                print("[Login] 쿠키 승인 완료")
                take_ss(page, "02_cookie_accepted")
        except: pass

        page.fill("input[type='email']", EMAIL)
        page.fill("input[type='password']", PASSWORD)
        page.click("button:has-text('Log in')")
        
        # 로그인 후 로딩 대기
        time.sleep(5) 
        print("[Login] 로그인 시도 완료. 대시보드 로딩 대기...")
        take_ss(page, "03_after_login_attempt")

        # [Messaging] 단계
        print(f"\n[Messaging] 총 {len(targets)}명에게 전송 시작")

        for uid in targets:
            print(f"\n[Target] {uid} 이동 중...")
            page.goto(f"https://www.mwcbarcelona.com/mymwc/messaging?conversation={uid}")
            time.sleep(3)
            take_ss(page, f"04_page_{uid}")

            try:
                input_sel = "input[placeholder='Type a message...']"
                page.wait_for_selector(input_sel, timeout=10000)
                page.fill(input_sel, CUSTOM_MESSAGE)
                page.keyboard.press("Enter")
                
                print(f"[Success] {uid} 전송 완료")
                report_status(uid, "Success")
                take_ss(page, f"05_sent_{uid}")
            except Exception as e:
                print(f"[Fail] {uid}: {str(e)[:50]}")
                report_status(uid, "Fail", str(e)[:50])

            wait_time = round(random.uniform(20, 30), 1)
            print(f"[Wait] 스팸 차단 방지 대기 ({wait_time}초)...")
            time.sleep(wait_time)

        browser.close()

if __name__ == "__main__":
    main()
