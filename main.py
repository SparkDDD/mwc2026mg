import os
import time
import random
import json
import gspread
from playwright.sync_api import sync_playwright
from oauth2client.service_account import ServiceAccountCredentials

# 1. 환경 변수 로드 (GitHub Secrets)
EMAIL = os.getenv("MWC_EMAIL")
PASSWORD = os.getenv("MWC_PASSWORD")
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

def get_sheet():
    """구글 시트 API 연결 및 시트 오픈"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(CREDS_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

def main():
    sheet = get_sheet()
    # 전체 데이터를 가져와서 헤더(1행) 제외하고 분석
    records = sheet.get_all_records()
    
    # 발송 대상 필터링 (Status가 'Pending'이거나 비어있는 경우)
    targets = []
    for i, row in enumerate(records, start=2): # 2행부터 시작
        status = str(row.get('Status', '')).strip()
        if status == 'Pending' or status == '':
            targets.append({
                'row': i,
                'uuid': row.get('UUID'),
                'name': row.get('Name')
            })

    if not targets:
        print("[System] 발송 대상을 찾지 못했습니다. (Status='Pending' 없음)")
        return

    print(f"[System] 총 {len(targets)}명의 발송 대상을 찾았습니다.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()

        # [Login]
        print(f"[Login] 페이지 접속 중: {EMAIL}")
        page.goto("https://www.mwcbarcelona.com/mymwc", wait_until="networkidle")
        try:
            if page.locator("#onetrust-accept-btn-handler").is_visible():
                page.click("#onetrust-accept-btn-handler")
        except: pass

        page.fill("input[type='email']", EMAIL)
        page.fill("input[type='password']", PASSWORD)
        page.click("button:has-text('Log in')")
        time.sleep(5)
        print("[Login] 로그인 시도 완료")

        for item in targets:
            uid = item['uuid']
            row_idx = item['row']
            name = item['name']
            
            print(f"\n[Target] {name} ({uid}) 전송 중... (Sheet {row_idx}행)")
            
            try:
                # 메시지 전송 페이지 이동
                page.goto(f"https://www.mwcbarcelona.com/mymwc/messaging?conversation={uid}", wait_until="domcontentloaded")
                
                # 메시지 입력 및 전송 (메시지 내용은 시트에 고정된 값을 쓰거나 코드에 정의)
                input_sel = "input[placeholder='Type a message...']"
                page.wait_for_selector(input_sel, timeout=15000)
                
                msg = f"Hi {name}! Nice to meet you." # 메시지 커스텀 가능
                page.fill(input_sel, msg)
                page.keyboard.press("Enter")
                
                # 시트 업데이트 (C: Status, D: Timestamp, E: Log)
                now = time.strftime('%Y-%m-%d %H:%M:%S')
                sheet.update(range_name=f"C{row_idx}:E{row_idx}", values=[["Success", now, "Sent Successfully"]])
                
                print(f"[Success] {uid} 전송 및 시트 업데이트 완료")
                
            except Exception as e:
                error_msg = str(e)[:50]
                print(f"[Fail] {uid}: {error_msg}")
                sheet.update(range_name=f"C{row_idx}:E{row_idx}", values=[["Fail", time.strftime('%Y-%m-%d %H:%M:%S'), error_msg]])

            # 스팸 방지 랜덤 대기
            wait_time = round(random.uniform(20, 35), 1)
            print(f"[Wait] 다음 발송까지 대기 ({wait_time}초)...")
            time.sleep(wait_time)

        browser.close()

if __name__ == "__main__":
    main()
