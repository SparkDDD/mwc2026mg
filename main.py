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

# 메이크(Make) 등 외부에서 들어온 메시지를 그대로 사용
RAW_MESSAGE = os.getenv("CUSTOM_MSG", "").strip()

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

    print(f"[System] 총 {len(targets)}명 발송 시작")

    with sync_playwright() as p:
        # 브라우저 실행 (서버 환경이므로 headless=True)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # 전체 타임아웃 60초로 상향
        page = context.new_page()
        page.set_default_timeout(60000)

        # 1. 로그인 페이지 접속 (기준 완화)
        print("[System] 로그인 페이지 접속 중...")
        page.goto("https://www.mwcbarcelona.com/mymwc", wait_until="domcontentloaded")
        
        # 2. 쿠키 배너 제거 (로그인 버튼을 가릴 수 있음)
        try:
            accept_btn = page.locator("#onetrust-accept-btn-handler")
            if accept_btn.is_visible(timeout=5000):
                accept_btn.click(force=True) # 강제 클릭 옵션 사용
                print("[System] 쿠키 배너 제거 완료")
                time.sleep(2)
        except:
            pass

        # 3. 로그인 정보 입력
        page.fill("input[type='email']", EMAIL)
        page.fill("input[type='password']", PASSWORD)
        
        # 4. 로그인 실행 (배너 간섭을 피하기 위해 Enter 키 입력)
        print("[System] 로그인 시도 중...")
        page.keyboard.press("Enter")
        
        # 로그인 후 페이지 전환을 위해 넉넉히 대기
        time.sleep(10)

        for item in targets:
            uid, row_idx, name = item['uuid'], item['row'], item['name']
            final_msg = f"Hi {name}! {RAW_MESSAGE}" if RAW_MESSAGE else f"Hi {name}! "
            
            print(f"\n[Target] {name} ({uid}) 작업 중...")
            
            try:
                # 메시지 대화창으로 이동
                page.goto(f"https://www.mwcbarcelona.com/mymwc/messaging?conversation={uid}", 
                          wait_until="domcontentloaded")
                
                # 입력창 대기 (최대 30초)
                input_sel = "input[placeholder='Type a message...']"
                page.wait_for_selector(input_sel, timeout=30000)
                
                # JavaScript를 통한 직접 값 주입 (안전성 확보)
                page.evaluate("""([selector, text]) => {
                    const input = document.querySelector(selector);
                    if (input) {
                        input.value = text;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""", [input_sel, final_msg])
                
                time.sleep(1.5)
                page.keyboard.press("Enter")
                
                # 결과 기록
                now = time.strftime('%Y-%m-%d %H:%M:%S')
                sheet.update(range_name=f"C{row_idx}:E{row_idx}", values=[["Success", now, "Sent Successfully"]])
                print(f"[Success] {name} 완료")
                
            except Exception as e:
                error_full = str(e)
                print(f"[Fail] {name}: {error_full[:100]}")
                sheet.update(range_name=f"C{row_idx}:E{row_idx}", values=[["Fail", time.strftime('%Y-%m-%d %H:%M:%S'), error_full[:50]]])

            # 스팸 방지 랜덤 대기
            wait_time = round(random.uniform(20, 35), 1)
            print(f"[Wait] {wait_time}초 대기...")
            time.sleep(wait_time)

        browser.close()

if __name__ == "__main__":
    main()
