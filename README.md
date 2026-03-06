# Daily News Bot

매일 주요 뉴스 기사를 수집하고, LLM으로 요약/분류한 뒤 Google Sheets, Telegram, 이메일로 전달하는 자동화 스크립트입니다.

## 주요 기능

- RSS + 네이버 신문보기 기반 기사 수집
- 분할 배치 LLM 호출로 기사 요약/섹터 분류/중요도 산출
- 구조화 점수(`market_impact`, `urgency`, `duration`, `confidence`) 기반 중요도 보정
- Google Sheets `Daily_News` 시트 자동 적재
- Telegram 메시지 전송
- SMTP 이메일 전송
- GitHub Actions 기반 일일 스케줄 실행

## 수집 소스

- 글로벌 RSS: Reuters, BBC, AP, FT
- 국내 RSS: 연합뉴스, 한국경제, 매일경제
- 네이버 신문보기: 한국경제, 매일경제, 조선일보, 동아일보, 한겨레

## 섹터 표시 순서

- 경제종합
- 부동산(한국 중심 + 글로벌)
- 주식(한국/글로벌)
- 국제(지정학/분쟁)
- 에너지/원자재
- 테크/AI
- 기후/재난
- 여행/항공/물류

## 필수 환경변수

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5-mini

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

GOOGLE_SHEET_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=
```

## GitHub Actions 필수 Secrets

- `OPENAI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`  
  GitHub에서는 파일 경로가 아니라 JSON 본문 전체를 넣어야 합니다.

## 선택 환경변수

```env
PROMPT_ONLY=0
LLM_PREVIEW_ONLY=0
DISPLAY_GROUP_BY_SECTOR=1
DISPLAY_GROUP_BY_OUTLET=0
USE_TITLE_SECTOR_HINT=1
RSS_MAX_PER_FEED=8
NAVER_MAX_PER_PAPER=15
LLM_BATCH_SIZE=25
ENABLE_TITLE_PREFILTER=1

EMAIL_ENABLED=0
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=
EMAIL_PASSWORD=
EMAIL_FROM=
EMAIL_TO=
EMAIL_RECIPIENTS_FILE=email_recipients.txt
```

## 환경변수 상세 설명

### 민감정보 (Secrets 권장)

- `OPENAI_API_KEY`: OpenAI API 인증 키
- `TELEGRAM_BOT_TOKEN`: BotFather 발급 봇 토큰
- `TELEGRAM_CHAT_ID`: 텔레그램 수신 채팅 ID (`getUpdates`의 `chat.id`)
- `GOOGLE_SHEET_ID`: Google Sheet 문서 ID
- `GOOGLE_SERVICE_ACCOUNT_JSON`:  
  로컬 실행은 JSON 파일 경로 가능,  
  GitHub Actions는 JSON 본문 전체를 Secret 값으로 입력해야 함
- `EMAIL_USERNAME`: SMTP 로그인 계정(보통 발신 이메일)
- `EMAIL_PASSWORD`: SMTP 로그인 비밀번호(Gmail은 앱 비밀번호 권장)
- `EMAIL_FROM`: 이메일 발신자 주소

### 일반 설정 (Variables 권장)

- `OPENAI_MODEL`: 사용할 모델 (`gpt-5-mini` 권장)
- `PROMPT_ONLY`: `1`이면 프롬프트 파일 생성 후 종료
- `LLM_PREVIEW_ONLY`: `1`이면 LLM 결과 파일 생성까지만 수행
- `DISPLAY_GROUP_BY_SECTOR`: `1`이면 섹터별 섹션 표시
- `DISPLAY_GROUP_BY_OUTLET`: `1`이면 신문사별 섹션도 추가 표시
- `USE_TITLE_SECTOR_HINT`: `1`이면 제목 키워드 기반 rough 섹터 힌트 사용
- `RSS_MAX_PER_FEED`: RSS 피드별 최대 수집 건수
- `NAVER_MAX_PER_PAPER`: 네이버 신문보기 신문사별 최대 수집 건수
- `LLM_BATCH_SIZE`: LLM 1회 호출당 기사 수
- `ENABLE_TITLE_PREFILTER`: `1`이면 저신호 제목 기사 일부를 사전 제외
- `EMAIL_ENABLED`: `1`이면 이메일 전송 활성화
- `EMAIL_SMTP_HOST`: SMTP 서버 주소 (Gmail: `smtp.gmail.com`)
- `EMAIL_SMTP_PORT`: SMTP 포트 (Gmail TLS: `587`)
- `EMAIL_RECIPIENTS_FILE`: 수신자 목록 파일 경로

## 실행 방법

```bash
pip install -r requirements.txt
python3 news.py
```

## 이메일 수신자 관리

- `email_recipients.txt`에 한 줄당 이메일 1개씩 입력
- 또는 `.env`의 `EMAIL_TO`에 콤마 구분으로 입력
- GitHub Actions에서는 `EMAIL_RECIPIENTS` Secret(여러 줄) 사용 가능

## GitHub Actions

- 워크플로 파일: `.github/workflows/daily-news.yml`
- 기본 스케줄: 매일 오전 7시(KST)
- 실행 전 GitHub Actions Secrets/Variables 설정 필요
