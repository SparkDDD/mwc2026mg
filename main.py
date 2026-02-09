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
CUSTOM_MESSAGE = os.getenv("CUSTOM_MSG", "")

def report_status(uid, status, log=""):
    """결과를 다시 Make.com으로 보내 시트 업데이트"""
    if not MAKE_REPORT_URL: return
    try:
        requests.post(MAKE_REPORT_URL, json={
            "uuid": uid, "status": status, "log": log,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }, timeout=10)
    except: pass

def main():
    # ID 리스트 정리
    targets = [uid.strip() for uid in TARGET_IDS_RAW.split(",") if uid.strip()]

    with sync_playwright() as p:
        # 가벼운 크로미움 실행
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()

        # [Login] 단계
        print(f"[Login] 페이지 접속 중: {EMAIL}")
        page.goto("https://www.mwcbarcelona.com/mymwc", wait_until="networkidle")

        try:
            if page.locator("#onetrust-accept-btn-handler").is_visible():
                page.click("#onetrust-accept-btn-handler")
                print("[Login] 쿠키 승인 완료")
        except: pass

        page.fill("input[type='email']", EMAIL)
        page.fill("input[type='password']", PASSWORD)
        page.click("button:has-text('Log in')")
        
        # 로그인 안정화를 위한 대기
        time.sleep(5) 
        print("[Login] 로그인 시도 완료. 대시보드 로딩 대기...")

        # [Messaging] 단계
        print(f"\n[Messaging] 총 {len(targets)}명에게 전송 시작")

        for uid in targets:
            print(f"\n[Target] {uid} 이동 중...")
            page.goto(f"https://www.mwcbarcelona.com/mymwc/messaging?conversation={uid}", wait_until="domcontentloaded")
            
            try:
                # 입력창 대기 및 입력
                input_sel = "input[placeholder='Type a message...']"
                page.wait_for_selector(input_sel, timeout=15000)
                page.fill(input_sel, CUSTOM_MESSAGE)
                page.keyboard.press("Enter")
                
                print(f"[Success] {uid} 전송 완료")
                report_status(uid, "Success")
            except Exception as e:
                error_snippet = str(e)[:30]
                print(f"[Fail] {uid}: {error_snippet}")
                report_status(uid, "Fail", error_snippet)

            # 스팸 방지 랜덤 대기
            wait_time = round(random.uniform(20, 35), 1)
            print(f"[Wait] 스팸 차단 방지 대기 ({wait_time}초)...")
            time.sleep(wait_time)

        browser.close()

if __name__ == "__main__":
    main()
