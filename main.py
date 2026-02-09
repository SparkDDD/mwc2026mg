import os
import time
import random
import requests
from playwright.sync_api import sync_playwright

# ==========================================
# 1. 환경 변수 설정 (GitHub Secrets 및 Make 전달 데이터)
# ==========================================
EMAIL = os.getenv("MWC_EMAIL", "").strip()
PASSWORD = os.getenv("MWC_PASSWORD", "").strip()
MAKE_REPORT_URL = os.getenv("MAKE_REPORT_URL", "").strip()

# Make.com에서 전달받은 데이터
TARGET_IDS_RAW = os.getenv("TARGET_IDS", "")
CUSTOM_MESSAGE = os.getenv("CUSTOM_MSG", "Hello! Nice to meet you.")

def get_target_ids():
    """쉼표로 구분된 ID 문자열을 리스트로 변환"""
    if not TARGET_IDS_RAW:
        return []
    return [uid.strip() for uid in TARGET_IDS_RAW.split(",") if uid.strip()]

def report_status(uid, status, log=""):
    """발송 결과를 Make.com Webhook으로 전송하여 구글 시트 업데이트"""
    if not MAKE_REPORT_URL:
        print(f"[Skip Report] {uid}: Webhook URL이 설정되지 않음")
        return
    try:
        data = {
            "uuid": uid,
            "status": status,
            "log": log,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        requests.post(MAKE_REPORT_URL, json=data, timeout=10)
    except Exception as e:
        print(f"[Log Error] {uid}: 시트 업데이트 실패 ({e})")

def do_login(page):
    """MWC 사이트 로그인 로직"""
    print("[Login] MWC 로그인 시도 중...")
    page.goto("https://www.mwcbarcelona.com/mymwc", wait_until="domcontentloaded")
    
    # 쿠키 수락 버튼 처리
    try:
        page.locator("#onetrust-accept-btn-handler").click(timeout=5000)
    except:
        pass

    try:
        page.wait_for_selector("input[type='email']", timeout=20000)
        page.fill("input[type='email']", EMAIL)
        page.fill("input[type='password']", PASSWORD)
        page.click("button:has-text('Log in'), #login-button")
        page.wait_for_timeout(10000) # 로그인 후 로딩 대기
        print("[Login] 로그인 성공!")
        return True
    except Exception as e:
        print(f"[Login Error] 로그인 실패: {e}")
        return False

def main():
    targets = get_target_ids()
    print(f"[Info] 총 발송 대상 수: {len(targets)}명")
    print(f"[Info] 발송 메시지: {CUSTOM_MESSAGE}")

    if not targets:
        print("[Exit] 발송할 대상 ID가 없습니다. 종료합니다.")
        return

    if not EMAIL or not PASSWORD:
        print("[Exit] 계정 정보(Email/PW)가 설정되지 않았습니다.")
        return

    with sync_playwright() as p:
        # GitHub Actions 환경이므로 headless=True 필수
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        if do_login(page):
            for idx, uid in enumerate(targets):
                print(f"\n[{idx+1}/{len(targets)}] Target ID: {uid} 진행 중...")
                msg_url = f"https://www.mwcbarcelona.com/mymwc/messaging?conversation={uid}"
                
                try:
                    page.goto(msg_url, wait_until="domcontentloaded", timeout=60000)
                    input_sel = "input[placeholder='Type a message...']"
                    page.wait_for_selector(input_sel, timeout=20000)
                    
                    # 메시지 입력 및 전송
                    page.click(input_sel)
                    page.keyboard.type(CUSTOM_MESSAGE, delay=random.randint(50, 100))
                    page.keyboard.press("Enter")
                    
                    print(f"[Success] {uid} 전송 완료")
                    report_status(uid, "Success", "Sent")
                    
                    # 1,000건 발송을 위한 안전 대기 간격 (평균 25초)
                    wait_time = random.uniform(20, 35)
                    print(f"[Wait] 다음 발송까지 {wait_time:.1f}초 대기...")
                    time.sleep(wait_time)

                except Exception as e:
                    error_msg = str(e)[:50]
                    print(f"[Fail] {uid}: {error_msg}")
                    report_status(uid, "Fail", error_msg)
                    time.sleep(5) # 에러 시 잠깐 대기 후 다음 ID로 이동

        browser.close()

if __name__ == "__main__":
    main()
