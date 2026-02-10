import os
import time
import random
import json
import gspread
import sys
from playwright.sync_api import sync_playwright
from oauth2client.service_account import ServiceAccountCredentials

# 로그를 터미널과 파일에 동시에 기록하기 위한 설정
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
# Make.com에서 넘어온 \\n을 실제 줄바꿈 \n으로 변환
RAW_MESSAGE = os.getenv("CUSTOM_MSG", "").replace("\\n", "\n").strip()

def get_sheet():
    """구글 시트 API 인증 및 연결"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(CREDS_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

def main():
    print(f"\n=== 발송 세션 시작: {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    if not SHEET_ID or not CREDS_JSON:
        print("[Error] 구글 시트 환경 변수 설정이 누락되었습니다.")
        return

    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
    except Exception as e:
        print(f"[Error] 구글 시트 접근 실패: {e}")
        return
    
    # 발송 대상 필터링 (Status가 'Pending'이거나 비어있는 경우)
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
        print("[System] 'Pending' 상태의 발송 대상을 찾지 못했습니다.")
        return

    print(f"[System] 총 {len(targets)}명의 대상에게 전송을 시작합니다.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # [1] 로그인 단계
        print(f"[Login] MWC 로그인 시도 중: {EMAIL}")
        page.goto("https://www.mwcbarcelona.com/mymwc", wait_until="networkidle")
        
        try:
            if page.locator("#onetrust-accept-btn-handler").is_visible():
                page.click("#onetrust-accept-btn-handler", timeout=5000)
        except: pass

        page.fill("input[type='email']", EMAIL)
        page.fill("input[type='password']", PASSWORD)
        page.click("button:has-text('Log in')")
        
        time.sleep(7) # 로그인 후 대시보드 로딩 대기
        print("[Login] 로그인 시도 프로세스 완료")

        # [2] 메시지 전송 단계
        for item in targets:
            uid, row_idx, name = item['uuid'], item['row'], item['name']
            
            # 메시지 조합: Hi {Name}! + 본문
            if RAW_MESSAGE:
                final_msg = f"Hi {name}!\n\n{RAW_MESSAGE}"
            else:
                final_msg = f"Hi {name}!"
            
            print(f"\n[Target] {name} ({uid}) 작업 중 (시트 {row_idx}행)...")
            
            try:
                # 대화창 이동
                page.goto(f"https://www.mwcbarcelona.com/mymwc/messaging?conversation={uid}", wait_until="domcontentloaded")
                
                # 입력창 대기
                input_sel = "input[placeholder='Type a message...']"
                page.wait_for_selector(input_sel, timeout=20000)
                
                # JS를 이용한 안전한 텍스트 주입 (줄바꿈 보존)
                page.evaluate("""([selector, text]) => {
                    const input = document.querySelector(selector);
                    if (input) {
                        input.value = text;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""", [input_sel, final_msg])
                
                time.sleep(1)
                page.keyboard.press("Enter")
                
                # 구글 시트 성공 업데이트
                now = time.strftime('%Y-%m-%d %H:%M:%S')
                sheet.update(range_name=f"C{row_idx}:E{row_idx}", values=[["Success", now, "Sent Successfully"]])
                print(f"[Success] {name}에게 전송 완료")
                
            except Exception as e:
                error_snippet = str(e)[:50]
                print(f"[Fail] {name} 전송 실패: {error_snippet}")
                now = time.strftime('%Y-%m-%d %H:%M:%S')
                sheet.update(range_name=f"C{row_idx}:E{row_idx}", values=[["Fail", now, error_snippet]])

            # 스팸 방지 대기
            wait_time = round(random.uniform(20, 35), 1)
            print(f"[Wait] 다음 발송까지 {wait_time}초 대기...")
            time.sleep(wait_time)

        browser.close()
    
    print(f"\n=== 발송 세션 종료: {time.strftime('%Y-%m-%d %H:%M:%S')} ===")

if __name__ == "__main__":
    main()
