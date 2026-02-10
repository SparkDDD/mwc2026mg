import os
import time
import random
import json
import gspread
import sys
from playwright.sync_api import sync_playwright
from oauth2client.service_account import ServiceAccountCredentials

# 로그를 터미널과 파일에 동시에 기록
class Logger(object):
    def __init__(self):
        self.terminal = sys.stdout
        self.log = open("execution_log.txt", "a", encoding="utf-8")
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
    def flush(self):
        pass

sys.stdout = Logger()

# 환경 변수 로드
EMAIL = os.getenv("MWC_EMAIL")
PASSWORD = os.getenv("MWC_PASSWORD")
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
# 줄바꿈 처리 없이 메시지 그대로 가져옴
RAW_MESSAGE = os.getenv("CUSTOM_MSG", "").strip()

def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(CREDS_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

def main():
    print(f"\n=== 세션 시작: {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    sheet = get_sheet()
    records = sheet.get_all_records()
    
    targets = []
    for i, row in enumerate(records, start=2):
        status = str(row.get('Status', '')).strip()
        if status.lower() == 'pending' or status == '':
            targets.append({'row': i, 'uuid': row.get('UUID'), 'name': row.get('Name')})

    if not targets:
        print("[System] 'Pending' 대상이 없습니다.")
        return

    print(f"[System] 총 {len(targets)}명 발송을 시작합니다.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0...")
        page = context.new_page()

# [수정] 로그인 전 배너 처리 강화
        page.goto("https://www.mwcbarcelona.com/mymwc", wait_until="networkidle")
        time.sleep(3) # 배너가 뜰 시간을 조금 더 줌

        try:
            # 쿠키 승인 버튼 대기 및 클릭 (id가 onetrust-accept-btn-handler인 경우가 많음)
            accept_btn = page.locator("#onetrust-accept-btn-handler")
            if accept_btn.is_visible():
                accept_btn.click()
                print("[Login] 쿠키 승인 완료")
                time.sleep(3)
        except:
            print("[Login] 쿠키 배너가 없거나 이미 닫혀있음")

        # 이메일/비번 입력
        page.fill("input[type='email']", EMAIL)
        page.fill("input[type='password']", PASSWORD)
        
        # [중요] force=True를 추가하여 레이어가 가리고 있어도 강제로 클릭 시도
        page.click("button:has-text('Log in')", force=True)
        print("[Login] 로그인 버튼 클릭 완료")
        
        time.sleep(7) # 로그인 후 전환 대기

        for item in targets:
            uid, row_idx, name = item['uuid'], item['row'], item['name']
            # 이름만 붙인 심플한 메시지 조합
            final_msg = f"Hello {name}! {RAW_MESSAGE}" if RAW_MESSAGE else f"Hello {name}!"
            
            print(f"\n[Target] {name} 작업 중...")
            
            try:
                page.goto(f"https://www.mwcbarcelona.com/mymwc/messaging?conversation={uid}", wait_until="domcontentloaded")
                input_sel = "input[placeholder='Type a message...']"
                page.wait_for_selector(input_sel, timeout=15000)
                
                # 가장 표준적인 입력 방식
                page.fill(input_sel, final_msg)
                page.keyboard.press("Enter")
                
                # 시트 업데이트
                now = time.strftime('%Y-%m-%d %H:%M:%S')
                sheet.update(range_name=f"C{row_idx}:E{row_idx}", values=[["Success", now, "Sent"]])
                print(f"[Success] {name} 완료")
                
            except Exception as e:
                print(f"[Fail] {name}: {str(e)[:30]}")
                sheet.update(range_name=f"C{row_idx}:E{row_idx}", values=[["Fail", time.strftime('%Y-%m-%d %H:%M:%S'), str(e)[:30]]])

            time.sleep(random.uniform(20, 35))

        browser.close()
    print(f"\n=== 세션 종료: {time.strftime('%Y-%m-%d %H:%M:%S')} ===")

if __name__ == "__main__":
    main()
