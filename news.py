import os
import json
import re
import smtplib
from html import unescape
import feedparser
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from email.message import EmailMessage

from google.oauth2 import service_account
from googleapiclient.discovery import build

from openai import OpenAI

load_dotenv()
KST = timezone(timedelta(hours=9))

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or "gpt-5"

TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
SA_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
PROMPT_ONLY = os.getenv("PROMPT_ONLY", "0") == "1"
LLM_PREVIEW_ONLY = os.getenv("LLM_PREVIEW_ONLY", "0") == "1"
DISPLAY_GROUP_BY_SECTOR = os.getenv("DISPLAY_GROUP_BY_SECTOR", "1") == "1"
DISPLAY_GROUP_BY_OUTLET = os.getenv("DISPLAY_GROUP_BY_OUTLET", "1") == "1"
USE_TITLE_SECTOR_HINT = os.getenv("USE_TITLE_SECTOR_HINT", "1") == "1"
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "0") == "1"
EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT") or "587")
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
EMAIL_RECIPIENTS_FILE = os.getenv("EMAIL_RECIPIENTS_FILE", "email_recipients.txt")
RSS_MAX_PER_FEED = int(os.getenv("RSS_MAX_PER_FEED") or "8")
NAVER_MAX_PER_PAPER = int(os.getenv("NAVER_MAX_PER_PAPER") or "15")
LLM_BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE") or "25")
ENABLE_TITLE_PREFILTER = os.getenv("ENABLE_TITLE_PREFILTER", "1") == "1"

SHEET_NAME = "Daily_News"
PREVIEW_TEXT_PATH = "latest_digest_preview.txt"
PREVIEW_JSON_PATH = "latest_digest_preview.json"
PROMPT_PREVIEW_PATH = "latest_llm_prompt_preview.txt"
TELEGRAM_MAX_LEN = 4000
MODEL_PRICING_PER_1M = {
    "gpt-5": {"input": 1.25, "cached_input": 0.125, "output": 10.0},
    "gpt-5-chat-latest": {"input": 1.25, "cached_input": 0.125, "output": 10.0},
    "gpt-5-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.0},
    "gpt-5.1-codex-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.0},
}
SHEET_COLUMNS = [
    "날짜(KST)",
    "섹터",
    "지역",
    "언론사",
    "제목",
    "3줄요약",
    "왜중요한가",
    "영향자산",
    "중요도(1~5)",
    "URL",
]
SECTORS = [
    "국제(지정학/분쟁)",
    "거시경제/금리",
    "에너지/원자재",
    "주식(한국/글로벌)",
    "부동산(한국 중심 + 글로벌)",
    "테크/AI",
    "기후/재난",
    "여행/항공/물류",
]
NAVER_NEWSPAPER_CODES = {
    "매일경제": "009",
    "한국경제": "015",
#  "연합뉴스": "001",
    "조선일보": "023",
 #   "중앙일보": "025",
    "동아일보": "020",
    "한겨레": "028",
}
NAVER_TARGET_PAPERS = [
    "한국경제",
    "매일경제",
#    "연합뉴스",
    "조선일보",
#   "중앙일보",
    "동아일보",
    "한겨레",
]
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}
NAVER_NEWSPAPER_LIST_URLS = [
    "https://media.naver.com/press/{paper_code}/newspaper?date={target_date}",
    "https://n.news.naver.com/mnews/newspaper/home?media={paper_code}&date={target_date}",
    "https://n.news.naver.com/article/newspaper/{paper_code}?date={target_date}",
]

# 1) RSS 소스(원하는 대로 추가/교체)
RSS_FEEDS = {
    # Global
    "Reuters World": "https://www.reuters.com/rssFeed/worldNews",
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "AP Top News": "https://apnews.com/hub/ap-top-news?output=rss",
    "FT World": "https://www.ft.com/world?format=rss",
    # Korea (예시)
    "연합뉴스": "https://www.yna.co.kr/rss/all",
    "한국경제": "https://www.hankyung.com/feed/all-news",
    "매일경제": "https://www.mk.co.kr/rss/30000001/",
}

SYSTEM_PROMPT = """너는 '한국인 천재투자자,신문편집장이자 유명한 애널리스트'이다.
입력 기사 목록을 보고, 각 기사마다
(1) 섹터 분류 (2) 3문장 요약 (3) 핵심포인트 생각해봐야할점 1~2문장
(4) 영향 가능 자산/섹터 키워드 (5) 중요도(1~5)를 산출한다.
입력에 rough_sector_hint가 있으면 참고하되, 기사 내용상 더 적절한 섹터가 있으면 무시하고 수정한다.

[문체 가이드]
- 독자는 주식/부동산에 관심이 높은 투자자, 애널리스트, 경제 구독자다.
- 모든 문장은 한국어로 작성한다.
- 표현은 간결하되, 시장 해석과 투자 판단에 도움이 되도록 쓴다.
- 지나치게 쉬운 설명, 어린이 대상 표현, 과도하게 감성적인 문장은 피한다.
- summary_3는 사실관계와 시장 포인트 중심으로 쓴다.
- why_it_matters는 자산가격, 업종, 정책, 금리, 수급 관점에서 왜 중요한지 설명한다.
- 근거 없는 투자 추천 문구는 쓰지 말고, 관찰 포인트와 파급효과 중심으로 정리한다.

[섹터 목록]
""" + "\n".join(f"- {sector}" for sector in SECTORS) + """

[중요도 스코어링]
5: 전쟁/대규모 제재/중앙은행 결정/유가 급등락/대형 금융 이벤트
4: 시장에 직접 영향 가능성 높은 정책/기업 이벤트
3: 주목할 만한 흐름/리포트
2: 참고 수준
1: 단신

입력에 포함된 각 기사의 index를 반드시 그대로 유지한다.
기사 수만큼 결과를 모두 반환하려고 하되 중요도 순으로 최대 100개까지만 반환한다.
각 신문사별 사설은 포함시킨다.

[출력 형식 - JSON만]
{
  "items": [
    {
      "index": 0,
      "sector": "...",
      "region": "KR|Global|Mixed",
      "summary_3": ["...", "...", "..."],
      "why_it_matters": "...",
      "impact_assets": ["...", "..."],
      "importance_1to5": 1
    }
  ]
}
"""

client = OpenAI(api_key=OPENAI_API_KEY)

SECTOR_HINT_RULES = [
    ("국제(지정학/분쟁)", ["전쟁", "휴전", "제재", "나토", "미사일", "관세", "정상회담", "중동", "우크라", "러시아", "중국", "대만"]),
    ("거시경제/금리", ["연준", "fed", "금리", "물가", "cpi", "ppi", "고용", "실업", "채권", "국채", "환율", "달러", "boj", "ecb"]),
    ("에너지/원자재", ["유가", "원유", "wti", "브렌트", "천연가스", "lng", "opec", "구리", "금값", "니켈", "리튬", "원자재"]),
    ("주식(한국/글로벌)", ["증시", "주가", "코스피", "코스닥", "s&p", "나스닥", "다우", "실적", "상장", "ipo", "자사주", "배당"]),
    ("부동산(한국 중심 + 글로벌)", ["부동산", "아파트", "재건축", "재개발", "전세", "월세", "청약", "분양", "주택", "집값"]),
    ("테크/AI", ["ai", "반도체", "엔비디아", "오픈ai", "챗gpt", "로봇", "클라우드", "데이터센터", "테크", "빅테크", "칩"]),
    ("기후/재난", ["폭우", "폭설", "산불", "태풍", "허리케인", "지진", "홍수", "폭염", "한파", "재난", "기후"]),
    ("여행/항공/물류", ["항공", "여행", "관광", "물류", "해운", "운임", "항만", "크루즈", "항공권", "택배"]),
]
EDITORIAL_KEYWORDS = ["사설", "칼럼", "기고", "오피니언", "editorial", "opinion"]

def fetch_rss_items(max_per_feed=8):
    items = []
    print(f"[1/4] RSS 수집 시작: {len(RSS_FEEDS)}개 피드, 피드당 최대 {max_per_feed}건")
    for outlet, url in RSS_FEEDS.items():
        print(f"  - 수집 중: {outlet}")
        feed = feedparser.parse(url)
        for e in feed.entries[:max_per_feed]:
            article_url = getattr(e, "link", "").strip()
            if not article_url:
                continue
            items.append({
                "outlet": outlet,
                "title": getattr(e, "title", "").strip(),
                "url": article_url,
                "published": getattr(e, "published", "") or getattr(e, "updated", ""),
                "summary": getattr(e, "summary", "") or "",
                "description": getattr(e, "description", "") or "",
                "source_type": "rss",
            })
    print(f"[1/4] RSS 수집 완료: 총 {len(items)}건")
    return items

def guess_sector_from_title(title):
    normalized = (title or "").lower()
    for sector, keywords in SECTOR_HINT_RULES:
        for keyword in keywords:
            if keyword.lower() in normalized:
                return sector
    return "미분류"

def strip_html_text(value):
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return " ".join(value.split())

def fetch_naver_newspaper_items(date_kst=None, max_per_paper=None):
    target_date = date_kst or datetime.now(KST).strftime("%Y%m%d")
    items = []
    print(
        f"[1/4] 네이버 신문보기 수집 시작: "
        f"{len(NAVER_TARGET_PAPERS)}개 신문, 날짜 {target_date}"
    )

    for paper_name in NAVER_TARGET_PAPERS:
        paper_code = NAVER_NEWSPAPER_CODES[paper_name]
        print(f"  - 수집 중: {paper_name} ({paper_code})")
        html_text = fetch_naver_newspaper_list_html(paper_code, target_date)
        if not html_text:
            continue

        links = extract_naver_newspaper_links(html_text, paper_code, target_date)
        if max_per_paper:
            links = links[:max_per_paper]

        print(f"    · 링크 확보: {len(links)}건")
        for link in links:
            items.append({
                "outlet": paper_name,
                "title": link["title"],
                "url": link["url"],
                "published": target_date,
                "summary": "",
                "description": "",
                "source_type": "naver_newspaper",
            })

    print(f"[1/4] 네이버 신문보기 수집 완료: 총 {len(items)}건")
    return items

def fetch_naver_newspaper_list_html(paper_code, target_date):
    for template in NAVER_NEWSPAPER_LIST_URLS:
        list_url = template.format(paper_code=paper_code, target_date=target_date)
        try:
            resp = requests.get(
                list_url,
                headers=REQUEST_HEADERS,
                timeout=20,
            )
            resp.raise_for_status()
            print(f"    · 목록 페이지 성공: {list_url}")
            return resp.text
        except requests.RequestException as e:
            print(f"    · 목록 페이지 실패: {list_url} | {e}")
    print("    · 사용 가능한 네이버 신문보기 목록 URL을 찾지 못함")
    return ""

def extract_naver_newspaper_links(html_text, paper_code, target_date):
    pattern = re.compile(
        rf'<a[^>]+href="(?P<href>[^"]*/article/newspaper/{paper_code}/\d+[^"]*)"[^>]*>'
        rf'(?P<label>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    results = []
    seen_urls = set()

    for match in pattern.finditer(html_text):
        href = unescape(match.group("href"))
        if href.startswith("/"):
            href = f"https://n.news.naver.com{href}"
        if not href.startswith("https://n.news.naver.com/"):
            continue
        if f"date={target_date}" not in href:
            separator = "&" if "?" in href else "?"
            href = f"{href}{separator}date={target_date}"
        if href in seen_urls:
            continue

        title = strip_html_text(match.group("label"))
        if not title or len(title) < 4:
            continue

        seen_urls.add(href)
        results.append({
            "title": title,
            "url": href,
        })

    return results

def merge_items(*groups):
    merged = []
    seen_urls = set()
    for group in groups:
        for item in group:
            article_url = item.get("url", "").strip()
            if not article_url or article_url in seen_urls:
                continue
            seen_urls.add(article_url)
            if USE_TITLE_SECTOR_HINT:
                item["rough_sector"] = guess_sector_from_title(item.get("title", ""))
            else:
                item["rough_sector"] = ""
            merged.append(item)
    return merged

def is_editorial_title(title):
    normalized = (title or "").lower()
    return any(keyword.lower() in normalized for keyword in EDITORIAL_KEYWORDS)

def prefilter_items(items):
    if not ENABLE_TITLE_PREFILTER:
        return items, []

    kept = []
    dropped = []
    for item in items:
        if item.get("source_type") != "naver_newspaper":
            kept.append(item)
            continue
        if item.get("rough_sector") and item["rough_sector"] != "미분류":
            kept.append(item)
            continue
        if is_editorial_title(item.get("title", "")):
            kept.append(item)
            continue
        dropped.append(item)

    print(
        f"[1/4] 제목 기반 1차 필터 적용: 유지 {len(kept)}건, 제외 {len(dropped)}건"
    )
    return kept, dropped

def safe_get_text_from_entry(entry):
    # RSS에 본문이 있는 경우도 있어서 우선 사용
    for key in ["summary", "description"]:
        if key in entry and entry[key]:
            return str(entry[key])
    return ""

def build_sheets_service():
    if os.path.exists(SA_JSON):
        creds = service_account.Credentials.from_service_account_file(
            SA_JSON,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
    else:
        creds = service_account.Credentials.from_service_account_info(
            json.loads(SA_JSON),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
    return build("sheets", "v4", credentials=creds)

def ensure_sheet_ready(svc):
    spreadsheet = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sheet_titles = {
        sheet.get("properties", {}).get("title", "")
        for sheet in spreadsheet.get("sheets", [])
    }
    if SHEET_NAME not in sheet_titles:
        svc.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": SHEET_NAME,
                            }
                        }
                    }
                ]
            },
        ).execute()

    header_range = f"{SHEET_NAME}!A1:J1"
    current = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=header_range,
    ).execute()
    values = current.get("values", [])
    if values and values[0] == SHEET_COLUMNS:
        return

    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=header_range,
        valueInputOption="RAW",
        body={"values": [SHEET_COLUMNS]},
    ).execute()

def build_llm_batch_input(items):
    lines = []
    for idx, item in enumerate(items):
        llm_index = item.get("llm_index", idx)
        content = safe_get_text_from_entry(item)
        content = " ".join(content.split())[:800]
        if not content:
            content = item["title"]
        lines.append(
            "\n".join(
                [
                    f"index: {llm_index}",
                    f"outlet: {item['outlet']}",
                    f"title: {item['title']}",
                    f"rough_sector_hint: {item.get('rough_sector', '')}",
                    f"url: {item['url']}",
                    f"content: {content}",
                ]
            )
        )
    return "\n\n".join(lines)

def write_prompt_preview(system_prompt, user_input, item_count):
    with open(PROMPT_PREVIEW_PATH, "w", encoding="utf-8") as f:
        f.write(f"[item_count]\n{item_count}\n\n")
        f.write("[system_prompt]\n")
        f.write(system_prompt.strip())
        f.write("\n\n[user_input]\n")
        f.write(user_input)

def merge_usage_infos(usages):
    merged = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "estimated_cost_usd": 0.0,
    }
    has_cost = False
    for usage in usages:
        merged["input_tokens"] += int(usage.get("input_tokens", 0) or 0)
        merged["output_tokens"] += int(usage.get("output_tokens", 0) or 0)
        merged["cached_input_tokens"] += int(usage.get("cached_input_tokens", 0) or 0)
        if usage.get("estimated_cost_usd") is not None:
            merged["estimated_cost_usd"] += float(usage["estimated_cost_usd"])
            has_cost = True
    if has_cost:
        merged["estimated_cost_usd"] = round(merged["estimated_cost_usd"], 6)
    else:
        merged["estimated_cost_usd"] = None
    return merged

def extract_response_usage(resp):
    usage = getattr(resp, "usage", None)
    if not usage:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "estimated_cost_usd": None,
        }

    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    input_details = getattr(usage, "input_tokens_details", None)
    cached_input_tokens = 0
    if input_details:
        cached_input_tokens = int(getattr(input_details, "cached_tokens", 0) or 0)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_input_tokens,
        "estimated_cost_usd": estimate_llm_cost_usd(
            OPENAI_MODEL,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
        ),
    }

def estimate_llm_cost_usd(model_name, input_tokens, output_tokens, cached_input_tokens=0):
    pricing = MODEL_PRICING_PER_1M.get(model_name)
    if not pricing:
        return None

    non_cached_input_tokens = max(input_tokens - cached_input_tokens, 0)
    input_cost = (non_cached_input_tokens / 1_000_000) * pricing["input"]
    cached_cost = (cached_input_tokens / 1_000_000) * pricing["cached_input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + cached_cost + output_cost, 6)

def llm_enrich_batch(items, user_input=None):
    user_input = user_input or build_llm_batch_input(items)
    print(f"[2/4] LLM 배치 분석 시작: {len(items)}건")
    resp = client.responses.create(
        model=OPENAI_MODEL,
        instructions=SYSTEM_PROMPT,
        input=user_input,
    )
    usage_info = extract_response_usage(resp)
    text = resp.output_text.strip()

    # 모델이 JSON 외 텍스트를 섞는 경우 대비: 앞뒤 잡음 제거 시도
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            data = json.loads(text[start:end+1])
        else:
            raise

    results = {}
    for item in data.get("items", []):
        try:
            idx = int(item["index"])
        except (KeyError, TypeError, ValueError):
            continue
        results[idx] = item
    print(f"[2/4] LLM 배치 분석 완료: {len(results)}건 반환")
    print(
        "[2/4] 토큰 사용량:"
        f" input={usage_info['input_tokens']},"
        f" output={usage_info['output_tokens']},"
        f" cached_input={usage_info['cached_input_tokens']}"
    )
    if usage_info["estimated_cost_usd"] is not None:
        print(
            f"[2/4] 예상 비용(USD): ${usage_info['estimated_cost_usd']:.6f} "
            f"| model={OPENAI_MODEL}"
        )
    else:
        print(f"[2/4] 예상 비용 계산 불가: 모델 요금표 미등록 ({OPENAI_MODEL})")
    return results, usage_info

def chunk_items(items, batch_size):
    if batch_size <= 0:
        return [items]
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]

def llm_enrich_in_batches(items):
    batches = chunk_items(items, LLM_BATCH_SIZE)
    all_results = {}
    usage_list = []
    print(
        f"[2/4] LLM 분할 실행: 총 {len(items)}건, "
        f"배치 {len(batches)}개, 배치당 최대 {LLM_BATCH_SIZE}건"
    )

    for batch_no, batch in enumerate(batches, start=1):
        print(f"[2/4] 배치 {batch_no}/{len(batches)} 시작")
        batch_results, usage_info = llm_enrich_batch(batch)
        all_results.update(batch_results)
        usage_list.append(usage_info)
        print(f"[2/4] 배치 {batch_no}/{len(batches)} 완료")

    merged_usage = merge_usage_infos(usage_list)
    print(
        "[2/4] 전체 토큰 사용량:"
        f" input={merged_usage['input_tokens']},"
        f" output={merged_usage['output_tokens']},"
        f" cached_input={merged_usage['cached_input_tokens']}"
    )
    if merged_usage["estimated_cost_usd"] is not None:
        print(
            f"[2/4] 전체 예상 비용(USD): ${merged_usage['estimated_cost_usd']:.6f} "
            f"| model={OPENAI_MODEL}"
        )
    return all_results, merged_usage

def sheets_append_rows(svc, rows):
    if not rows:
        return
    body = {"values": rows}
    svc.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()

def telegram_send(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    chunks = split_telegram_message(text, TELEGRAM_MAX_LEN)
    for idx, chunk in enumerate(chunks, start=1):
        payload = {
            "chat_id": TG_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        r = requests.post(url, json=payload, timeout=20)
        r.raise_for_status()
        print(f"  - Telegram 메시지 전송: {idx}/{len(chunks)}")

def send_email(subject, body):
    if not EMAIL_ENABLED:
        return
    recipients = get_email_recipients()
    if not all([EMAIL_SMTP_HOST, EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_FROM]) or not recipients:
        raise ValueError("이메일 전송 환경변수가 비어 있습니다.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.send_message(msg)

def get_email_recipients():
    recipients = []

    if EMAIL_RECIPIENTS_FILE and os.path.exists(EMAIL_RECIPIENTS_FILE):
        with open(EMAIL_RECIPIENTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                email = line.strip()
                if email and not email.startswith("#"):
                    recipients.append(email)

    if recipients:
        return recipients

    if EMAIL_TO:
        return [email.strip() for email in EMAIL_TO.split(",") if email.strip()]

    return []

def split_telegram_message(text, max_len):
    if len(text) <= max_len:
        return [text]

    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    chunks = []
    current_parts = []
    current_len = 0

    for block in blocks:
        block_chunks = split_large_block(block, max_len)
        for piece in block_chunks:
            separator_len = 2 if current_parts else 0
            proposed_len = current_len + separator_len + len(piece)
            if proposed_len <= max_len:
                current_parts.append(piece)
                current_len = proposed_len
                continue

            if current_parts:
                chunks.append("\n\n".join(current_parts))
            current_parts = [piece]
            current_len = len(piece)

    if current_parts:
        chunks.append("\n\n".join(current_parts))
    return chunks

def split_large_block(block, max_len):
    if len(block) <= max_len:
        return [block]

    lines = [line.rstrip() for line in block.splitlines()]
    pieces = []
    current_lines = []
    current_len = 0

    for line in lines:
        line_len = len(line)
        separator_len = 1 if current_lines else 0
        proposed_len = current_len + separator_len + line_len

        if proposed_len <= max_len:
            current_lines.append(line)
            current_len = proposed_len
            continue

        if current_lines:
            pieces.append("\n".join(current_lines))
            current_lines = []
            current_len = 0

        if line_len <= max_len:
            current_lines = [line]
            current_len = line_len
            continue

        # 단일 라인이 너무 길 때만 마지막 방어로 강제 분할
        start = 0
        while start < line_len:
            pieces.append(line[start:start + max_len])
            start += max_len

    if current_lines:
        pieces.append("\n".join(current_lines))

    return pieces

def write_preview_files(digest_text, enriched_list, usage_info=None, missing_items=None):
    with open(PREVIEW_TEXT_PATH, "w", encoding="utf-8") as f:
        f.write(digest_text)

    with open(PREVIEW_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at_kst": datetime.now(KST).isoformat(),
                "model": OPENAI_MODEL,
                "usage": usage_info or {},
                "count": len(enriched_list),
                "items": enriched_list,
                "missing_items": missing_items or [],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

def build_telegram_digest(enriched_list, top_n_per_sector=1, missing_items=None):
    # 중요도 내림차순
    enriched_list = sorted(enriched_list, key=lambda x: x["importance_1to5"], reverse=True)
    today = datetime.now(KST).strftime("%Y.%m.%d")
    lines = [f"🗞 {today} 데일리 브리핑", f"총 {len(enriched_list)}건", ""]

    if DISPLAY_GROUP_BY_SECTOR:
        lines.extend(build_grouped_section("섹터별 정리", enriched_list, key_name="sector"))

    if DISPLAY_GROUP_BY_OUTLET:
        if DISPLAY_GROUP_BY_SECTOR:
            lines.append("")
        lines.extend(build_grouped_section("신문사별 정리", enriched_list, key_name="outlet"))

    if not DISPLAY_GROUP_BY_SECTOR and not DISPLAY_GROUP_BY_OUTLET:
        lines.extend(build_flat_section(enriched_list))

    if missing_items:
        lines.append("")
        lines.append("========== 기타 기사 ==========")
        for idx, item in enumerate(missing_items, start=1):
            lines.append(f"{idx}. {item['title']} ({item['outlet']})")
            lines.append(f"· 링크: {item['url']}")
            lines.append("")
    return "\n".join(lines)

def build_grouped_section(section_title, enriched_list, key_name):
    header_line, group_prefix, divider = get_group_display_style(key_name, section_title)
    lines = [header_line]
    groups = {}
    for item in enriched_list:
        group_key = item.get(key_name) or "기타"
        groups.setdefault(group_key, []).append(item)

    for group_key in sorted(groups):
        lines.append(f"{group_prefix} {group_key} ({len(groups[group_key])}건)")
        lines.append(divider)
        lines.extend(build_flat_section(groups[group_key]))
    return lines

def get_group_display_style(key_name, section_title):
    if key_name == "outlet":
        return (
            f"========== {section_title} ==========",
            "▣",
            "=" * 24,
        )
    return (
        f"========== {section_title} ==========",
        "■",
        "-" * 24,
    )

def build_flat_section(items):
    lines = []
    for idx, item in enumerate(items, start=1):
        summaries = item.get("summary_3", ["", "", ""])
        summary_lines = [line for line in summaries[:3] if line]
        lines.append(
            f"{idx}. [{item['sector']}] {item['title']} ({item['outlet']}) "
            f"| 중요도 {item['importance_1to5']}/5"
        )
        for line in summary_lines:
            lines.append(f"· {line}")
        if item.get("why_it_matters"):
            lines.append(f"· 포인트: {item['why_it_matters']}")
        lines.append(f"· 링크: {item['url']}")
        lines.append("-" * 24)
        lines.append("")
    return lines

def main():
    rss_items = fetch_rss_items(max_per_feed=RSS_MAX_PER_FEED)
    naver_items = fetch_naver_newspaper_items(max_per_paper=NAVER_MAX_PER_PAPER)
    merged_items = merge_items(rss_items, naver_items)
    print(f"[1/4] 통합 수집 완료: 총 {len(merged_items)}건")
    items, dropped_items = prefilter_items(merged_items)
    if dropped_items:
        print(f"[1/4] 1차 필터 제외 기사: {len(dropped_items)}건")
    if not items:
        telegram_send("🗞 오늘 수집된 뉴스가 없습니다. RSS 소스를 확인해 주세요.")
        print("수집된 RSS 항목이 없습니다.")
        return

    for idx, item in enumerate(items):
        item["llm_index"] = idx

    prompt_input = build_llm_batch_input(items)
    write_prompt_preview(SYSTEM_PROMPT, prompt_input, len(items))
    print(f"[2/4] 프롬프트 미리보기 저장 완료: {PROMPT_PREVIEW_PATH}")
    if PROMPT_ONLY:
        print("PROMPT_ONLY=1 설정으로 LLM 호출 없이 종료합니다.")
        return

    enriched_all = []
    rows_to_append = []
    missing_items = []
    try:
        batch_meta, usage_info = llm_enrich_in_batches(items)
    except Exception as e:
        print("LLM batch enrich failed:", e)
        telegram_send("🗞 뉴스 분석 단계에서 오류가 발생했습니다. OpenAI 응답 형식 또는 API 상태를 확인해 주세요.")
        return

    print("[3/4] 시트용 데이터 정리 중")
    for idx, it in enumerate(items):
        meta = batch_meta.get(idx)
        if not meta:
            print(f"  - 스킵: LLM 결과 누락 | {it['title']}")
            missing_items.append({
                "outlet": it["outlet"],
                "title": it["title"],
                "url": it["url"],
            })
            continue
        now_kst = datetime.now(KST).strftime("%Y-%m-%d")
        rows_to_append.append([
            now_kst,
            meta.get("sector", ""),
            meta.get("region", ""),
            it["outlet"],
            it["title"],
            " / ".join(meta.get("summary_3", [])[:3]),
            meta.get("why_it_matters", ""),
            ", ".join(meta.get("impact_assets", [])[:8]),
            int(meta.get("importance_1to5", 2)),
            it["url"],
        ])

        enriched_all.append({
            "outlet": it["outlet"],
            "title": it["title"],
            "url": it["url"],
            "sector": meta.get("sector", ""),
            "summary_3": meta.get("summary_3", ["", "", ""]),
            "why_it_matters": meta.get("why_it_matters", ""),
            "importance_1to5": int(meta.get("importance_1to5", 2)),
        })

    if enriched_all or missing_items:
        digest = build_telegram_digest(
            enriched_all,
            top_n_per_sector=1,
            missing_items=missing_items,
        )
        write_preview_files(
            digest,
            enriched_all,
            usage_info=usage_info,
            missing_items=missing_items,
        )
        print(f"[4/4] 미리보기 파일 저장 완료: {PREVIEW_TEXT_PATH}, {PREVIEW_JSON_PATH}")

        if LLM_PREVIEW_ONLY:
            print("LLM_PREVIEW_ONLY=1 설정으로 시트 저장과 텔레그램 전송 없이 종료합니다.")
            return

        if rows_to_append:
            sheets_svc = build_sheets_service()
            print("[3/4] Google Sheets 준비 중")
            ensure_sheet_ready(sheets_svc)
            print(f"[3/4] Google Sheets 저장 시작: {len(rows_to_append)}행")
            sheets_append_rows(sheets_svc, rows_to_append)
            print("[3/4] Google Sheets 저장 완료")
        else:
            print("[3/4] Google Sheets 저장 건너뜀: 저장할 LLM 결과가 없음")

        print("[4/4] Telegram 전송 시작")
        telegram_send(digest)
        print("[4/4] Telegram 전송 완료")

        if EMAIL_ENABLED:
            print("[4/4] 이메일 전송 시작")
            send_email(
                subject=f"{datetime.now(KST).strftime('%Y-%m-%d')} 데일리 뉴스 브리핑",
                body=digest,
            )
            print("[4/4] 이메일 전송 완료")
        print("완료: 분할 LLM 호출 + 시트 저장 + 텔레그램 전송")
    else:
        telegram_send("🗞 수집된 뉴스가 없거나 처리에 실패했습니다. RSS, 인증 정보, 시트 권한을 확인해 주세요.")
        print("No news.")

if __name__ == "__main__":
    main()
