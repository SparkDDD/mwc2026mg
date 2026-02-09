import os
import time
import random
import json
import gspread
from playwright.sync_api import sync_playwright
from oauth2client.service_account import ServiceAccountCredentials

# 1. 환경 변수 로드
EMAIL = os.getenv("MWC_EMAIL")
PASSWORD = os.getenv("MWC_PASSWORD")
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

# [중요] Make.com에서 보낸 \\n 텍스트를 실제 줄바꿈 \n으로 복구
RAW_MESSAGE = os.getenv("CUSTOM_MSG", "").replace("\\n", "\n").strip()

def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(CREDS_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

def main():
    if not SHEET_ID or not CREDS_JSON:
        print("[Error] 구글 시트 설정이 누락되었습니다.")
        return

    sheet = get_sheet()
    records = sheet.get_all_records()
    
    targets = []
    for i, row in enumerate(records, start=2):
        status = str(row.get('Status', '')).strip()
        if status.lower() == 'pending' or status == '':
            targets.append({
                'row': i,
                'uuid': row.get('UUID'),
                'name': row.get('Name')
            })

    if not targets:
        print("[System] 'Pending' 상태의 대상을 찾지 못했습니다.")
        return

    print(f"[System] 총 {len(targets)}명 발송 시작 (메시지 길이: {len(RAW_MESSAGE)}자)")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()

        # 로그인
        page.goto("https://www.mwcbarcelona.com/mymwc", wait_until="networkidle")
        try:
            if page.locator("#onetrust-accept-btn-handler").is_visible():
                page.click("#onetrust-accept-btn-handler", timeout=5000)
        except: pass

        page.fill("input[type='email']", EMAIL)
        page.fill("input[type='password']", PASSWORD)
        page.click("button:has-text('Log in')")
        time.sleep(7)

        for item in targets:
            uid, row_idx, name = item['uuid'], item['row'], item['name']
            final_msg = f"Hi {name}!\n\n{RAW_MESSAGE}" if RAW_MESSAGE else f"Hi {name}!"
            
            print(f"\n[Target] {name} ({uid}) 작업 중...")
            
            try:
                page.goto(f"https://www.mwcbarcelona.com/mymwc/messaging?conversation={uid}", wait_until="domcontentloaded")
                
                # 입력창 대기
                input_sel = "input[placeholder='Type a message...']"
                page.wait_for_selector(input_sel, timeout=20000)
                
                # [핵심] 일반 fill 대신 자바스크립트로 값을 직접 주입하여 줄바꿈 보존
                page.evaluate(f"""(selector, text) => {{
                    const input = document.querySelector(selector);
                    input.value = text;
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}""", input_sel, final_msg)
                
                time.sleep(1) # 입력 안정화
                page.keyboard.press("Enter")
                
                # 결과 기록
                now = time.strftime('%Y-%m-%d %H:%M:%S')
                sheet.update(range_name=f"C{row_idx}:E{row_idx}", values=[["Success", now, "Sent Successfully"]])
                print(f"[Success] {name} 완료")
                
            except Exception as e:
                error_msg = str(e)[:50]
                print(f"[Fail] {name}: {error_msg}")
                sheet.update(range_name=f"C{row_idx}:E{row_idx}", values=[["Fail", time.strftime('%Y-%m-%d %H:%M:%S'), error_msg]])

            # 스팸 방지 대기
            wait_time = round(random.uniform(20, 35), 1)
            print(f"[Wait] {wait_time}초 대기...")
            time.sleep(wait_time)

        browser.close()

if __name__ == "__main__":
    main()
