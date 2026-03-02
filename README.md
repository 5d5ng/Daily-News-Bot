# Daily News Bot

매일 주요 뉴스 기사를 수집하고, LLM으로 요약/분류한 뒤 Google Sheets, Telegram, 이메일로 전달하는 자동화 스크립트입니다.

## 주요 기능

- RSS + 네이버 신문보기 기반 기사 수집
- 단일 배치 LLM 호출로 기사 요약/섹터 분류/중요도 산출
- Google Sheets `Daily_News` 시트 자동 적재
- Telegram 메시지 전송
- SMTP 이메일 전송
- GitHub Actions 기반 일일 스케줄 실행

## 수집 소스

- 글로벌 RSS: Reuters, BBC, AP, FT
- 국내 RSS: 연합뉴스, 한국경제, 매일경제
- 네이버 신문보기: 한국경제, 매일경제, 연합뉴스, 조선일보, 중앙일보, 동아일보, 한겨레

## 필수 환경변수

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5-mini

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

GOOGLE_SHEET_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=
```

## 선택 환경변수

```env
PROMPT_ONLY=0
LLM_PREVIEW_ONLY=0
DISPLAY_GROUP_BY_SECTOR=1
DISPLAY_GROUP_BY_OUTLET=1
USE_TITLE_SECTOR_HINT=1

EMAIL_ENABLED=0
EMAIL_SMTP_HOST=
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=
EMAIL_PASSWORD=
EMAIL_FROM=
EMAIL_TO=
EMAIL_RECIPIENTS_FILE=email_recipients.txt
```

## 실행 방법

```bash
pip install -r requirements.txt
python3 news.py
```

## 이메일 수신자 관리

- `email_recipients.txt`에 한 줄당 이메일 1개씩 입력
- 또는 `.env`의 `EMAIL_TO`에 콤마 구분으로 입력

## GitHub Actions

- 워크플로 파일: `.github/workflows/daily-news.yml`
- 기본 스케줄: 매일 오전 7시(KST)
- 실행 전 GitHub Actions Secrets 설정 필요
