import os
import time
import random
import json
import gspread
from playwright.sync_api import sync_playwright
from oauth2client.service_account import ServiceAccountCredentials

# 1. 환경 변수 로드 (GitHub Secrets & Payload)
EMAIL = os.getenv("MWC_EMAIL")
PASSWORD = os.getenv("MWC_PASSWORD")
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
# Softr에서 넘어온 메시지 (양끝 공백 제거)
RAW_MESSAGE = os.getenv("CUSTOM_MSG", "").strip()

def get_sheet():
    """구글 시트 API 연결"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(CREDS_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    # 첫 번째 워크시트 오픈
    return client.open_by_key(SHEET_ID).sheet1

def main():
    if not SHEET_ID or not CREDS_JSON:
        print("[Error] 구글 시트 설정(ID 또는 JSON)이 누락되었습니다.")
        return

    sheet = get_sheet()
    records = sheet.get_all_records()
    
    # 발송 대상 필터링 (Status 컬럼 기준)
    targets = []
    for i, row in enumerate(records, start=2): # 헤더 제외 2행부터 시작
        status = str(row.get('Status', '')).strip()
        if status.lower() == 'pending' or status == '':
            targets.append({
                'row': i,
                'uuid': row.get('UUID'),
                'name': row.get('Name')
            })

    if not targets:
        print("[System] 'Pending' 상태의 발송 대상을 찾지 못했습니다.")
        return

    print(f"[System] 총 {len(targets)}명의 전송 작업을 시작합니다.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # [Login] 단계
        print(f"[Login] 접속 중: {EMAIL}")
        page.goto("https://www.mwcbarcelona.com/mymwc", wait_until="networkidle")
        
        try:
            # 쿠키 승인 창이 뜨면 클릭
            if page.locator("#onetrust-accept-btn-handler").is_visible():
                page.click("#onetrust-accept-btn-handler", timeout=5000)
                print("[Login] 쿠키 승인 완료")
        except: pass

        page.fill("input[type='email']", EMAIL)
        page.fill("input[type='password']", PASSWORD)
        page.click("button:has-text('Log in')")
        
        # 로그인 안정화 대기
        time.sleep(7)
        print("[Login] 로그인 시도 완료. 발송을 시작합니다.")

        for item in targets:
            uid = item['uuid']
            row_idx = item['row']
            name = item['name']
            
            # 메시지 조합 (Hi Name! + 커스텀 메시지)
            if RAW_MESSAGE:
                final_msg = f"Hi {name}! {RAW_MESSAGE}"
            else:
                final_msg = f"Hi {name}!"
            
            print(f"\n[Target] {name} ({uid}) 이동 중...")
            
            try:
                # 메시지 전송 페이지 진입
                page.goto(f"https://www.mwcbarcelona.com/mymwc/messaging?conversation={uid}", wait_until="domcontentloaded")
                
                # 입력창 대기
                input_sel = "input[placeholder='Type a message...']"
                page.wait_for_selector(input_sel, timeout=20000)
                
                # 메시지 입력 및 전송
                page.fill(input_sel, final_msg)
                page.keyboard.press("Enter")
                
                # 구글 시트 업데이트 (C: Status, D: Timestamp, E: Log)
                now = time.strftime('%Y-%m-%d %H:%M:%S')
                sheet.update(range_name=f"C{row_idx}:E{row_idx}", values=[["Success", now, "Sent Successfully"]])
                print(f"[Success] {name} 전송 및 시트 업데이트 완료")
                
            except Exception as e:
                error_msg = str(e)[:50]
                print(f"[Fail] {name}: {error_msg}")
                sheet.update(range_name=f"C{row_idx}:E{row_idx}", values=[["Fail", time.strftime('%Y-%m-%d %H:%M:%S'), error_msg]])

            # 스팸 방지 랜덤 대기 (20~35초)
            wait_time = round(random.uniform(20, 35), 1)
            print(f"[Wait] 다음 발송까지 {wait_time}초 대기...")
            time.sleep(wait_time)

        browser.close()

if __name__ == "__main__":
    main()
