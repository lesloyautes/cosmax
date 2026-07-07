import base64
import html
import json
import re
from pathlib import Path

import pandas as pd
import streamlit as st

# ----------------------------------------------------------------------
# 기본 설정
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="규제나침반 | 중국 화장품 규제 1차 스크리닝",
    page_icon="🧭",
    layout="wide",
)

# Streamlit 기본 크롬(헤더/여백)을 숨겨서 목업 HTML이 페이지 전체를 차지하게 함
st.markdown(
    """
    <style>
    #MainMenu, header[data-testid="stHeader"], footer {visibility: hidden;}
    .block-container {padding: 0 !important; max-width: 100% !important;}
    iframe {display: block;}
    </style>
    """,
    unsafe_allow_html=True,
)

BASE_DIR = Path(__file__).parent
MOCKUP_PATH = BASE_DIR / "assets" / "규제나침반_최종.html"
BANNER_PATH = BASE_DIR / "assets" / "cream_banner.jpg"
SAMPLE_CSV = BASE_DIR / "sample_data.csv"

# ----------------------------------------------------------------------
# 규제 판정용 데이터 (지금까지 조사한 근거 반영) — 이 값들이 화면(JS)에 그대로 주입됨
# ----------------------------------------------------------------------

# 등록 취소/철회 이력이 있는 신원료 (재확인 시급 - RED)
CANCELLED_INGREDIENTS = {
    "니코틴아마이드모노뉴클레오타이드": "2024년 8월 NMPA 신원료 등록 취소 이력이 있는 성분이에요. 최신 등록 상태를 반드시 재확인하세요.",
    "nmn": "2024년 8월 NMPA 신원료 등록 취소 이력이 있는 성분이에요. 최신 등록 상태를 반드시 재확인하세요.",
    "바쿠치올": "과거 신원료 등록이 취소된 이력이 있는 성분이에요. '한 번 등록됐던 성분'이라는 이유로 안심하면 안 돼요.",
    "알파-글루칸폴리새커라이드": "2024년 8월 NMPA 신원료 등록이 취소된 성분이에요.",
    "엑토인": "과거 등록이 취소된 이력이 있는 신원료예요.",
    "에덱테인": "과거 등록이 취소된 이력이 있는 신원료예요.",
}

# 허가(注册) 대상 가능성이 높은 기능군 (RED) - 방부/자외선차단/착색/염모/미백
LICENSE_REQUIRED = {
    "알파-알부틴": "미백 기능 원료 → 신원료라면 허가(注册) 대상, 기존 원료라도 특수화장품 분류 가능성 확인 필요",
    "트라넥사믹애씨드": "미백 기능으로 흔히 사용 → 클레임에 미백이 포함되면 허가 대상 여부 확인 필요",
    "페녹시에탄올": "방부제 → 방부 관련 신원료라면 허가 대상, 전체 방부 시스템 검토 필요",
    "트라이클로산": "방부제(항균) → 국가별 함량 제한 이력이 있어 최신 기준 재확인 필요",
    "에칠헥실메톡시신나메이트": "자외선차단 성분 → 특수화장품(자외선차단) 등록 절차 대상",
    "징크옥사이드": "자외선차단 성분 → 특수화장품(자외선차단) 등록 절차 대상",
    "티타늄디옥사이드": "자외선차단/착색 겸용 가능 성분 → 사용 목적에 따라 등록 절차 확인 필요",
    "파라페닐렌다이아민": "염모 성분 → 허가 대상, 알레르기 경고 표시 의무 대상",
    "살리실릭애씨드": "BHA 계열 → 국가별 함량 상한이 있어 배합 농도 확인 필요",
}

# 배합량/처방 확인이 필요한 원료군 (AMBER)
WATCH_INGREDIENTS = {
    "다이소듐이디티에이": "안정화제 → 일부 국가에서 함량 제한 이력 있어 재확인 권장",
    "카프릴릭/카프릭트라이글리세라이드": "IECIC 목록상 세척/방치 제품별 최대 사용 농도가 명시된 원료",
    "카보머": "점증제 → 처방 내 타 성분과의 배합 비율 확인 권장",
    "폴리소르베이트60": "유화제 → 방부 시스템과 함께 검토 필요",
    "폴리부텐": "합성 폴리머 → 최근 사용 범위 검토 이력이 있어 최신 공고 확인 권장",
    "라우릴라이신": "계면활성/항균 보조 기능 → 방부 체계와 함께 확인 필요",
    "나이아신아마이드": "일반적으로 널리 쓰이나, 미백 클레임과 함께 쓰이면 허가 대상 가능성 있어 확인 권장",
    "콜라겐": "'*' 표기 총칭 원료 유형 → 구체 원료명 명시 + 제조사 설명서·구매 증빙 등 증명서류 준비 필요",
}

# 2026.1.1부터 생산·판매 전면 금지된 5대 특수용도 클레임 키워드
BANNED_CLAIM_KEYWORDS = ["육모", "탈모", "제모", "유방", "가슴", "체형관리", "탈취", "체취"]

# 광고 클레임 표현 관련 주의 키워드 (실제 처벌 사례 기반)
SENSITIVE_CLAIM_KEYWORDS = ["민감성 피부", "민감성", "저자극"]

CATEGORY_TYPE_BY_PRODUCT = {
    "화이트 글로우 브라이트닝 앰플": ("스킨케어 – 앰플/세럼", "특수"),
    "시카 수딩 리페어 크림": ("스킨케어 – 크림/로션", "일반"),
    "헤어그로우 부스팅 스칼프 토닉": ("헤어", "특수"),
    "데일리 선 프로텍트 에센스 SPF50+": ("자외선차단", "특수"),
    "글로우 핏 커버 쿠션 SPF35": ("메이크업", "특수"),
    "마일드 pH 밸런스 바디워시": ("기능성 전반", "일반"),
    "프레시 24H 롤온 데오드란트": ("기능성 전반", "특수"),
    "허니 글로우 립 슬리핑 밤": ("스킨케어 – 크림/로션", "일반"),
    "클리어 업 살리실릭 클렌징 폼": ("기능성 전반", "미정"),
    "퍼펙트 커버 그레이 헤어 컬러 크림": ("헤어", "특수"),
    "센서티브 배리어 리페어 앰플": ("스킨케어 – 앰플/세럼", "일반"),
}
HISTORY_DATE_LABELS = [
    "방금 추가", "1일 전", "3일 전", "5일 전", "1주 전", "9일 전",
    "11일 전", "2주 전", "16일 전", "19일 전", "24일 전",
]


def classify_ingredient(name: str):
    """원료 1개를 신호등(색상)과 사유로 분류 — 화면(JS)의 판정 로직과 동일한 규칙"""
    key = name.strip().lower().replace(" ", "")

    for watch_name, reason in CANCELLED_INGREDIENTS.items():
        if watch_name.replace(" ", "").lower() in key:
            return "red", reason

    for watch_name, reason in LICENSE_REQUIRED.items():
        if watch_name.replace(" ", "").lower() in key:
            return "red", reason

    for watch_name, reason in WATCH_INGREDIENTS.items():
        if watch_name.replace(" ", "").lower() in key:
            return "amber", reason

    return "green", None


def overall_signal(ingredients):
    signals = [classify_ingredient(ing)[0] for ing in ingredients]
    if "red" in signals:
        return "red"
    if "amber" in signals:
        return "amber"
    return "green"


# ----------------------------------------------------------------------
# Python 데이터 → 목업 JS로 주입할 값 생성
# ----------------------------------------------------------------------

def build_ingredient_db_js() -> str:
    db = {}
    for name, reason in CANCELLED_INGREDIENTS.items():
        db[name] = {
            "signal": "red",
            "reason": reason,
            "reg": "신원료 (등록 상태 재확인 필요)",
            "issue": "신원료 등록·철회 이력 — 최신 상태 확인 필수",
        }
    for name, reason in LICENSE_REQUIRED.items():
        db[name] = {
            "signal": "red",
            "reason": reason,
            "reg": "허가(注册) 대상 가능 원료",
            "issue": "허가 절차 소요기간 사전 확인",
        }
    for name, reason in WATCH_INGREDIENTS.items():
        db[name] = {
            "signal": "amber",
            "reason": reason,
            "reg": "배합량 확인 필요 원료",
            "issue": "처방 내 배합비율·근거자료 확인",
        }
    return json.dumps(db, ensure_ascii=False)


def build_history_cards_html() -> str:
    if not SAMPLE_CSV.exists():
        return ""
    df = pd.read_csv(SAMPLE_CSV)
    cards = []
    for idx, row in df.iterrows():
        ingredients = [i.strip() for i in str(row["원료리스트"]).split(",") if i.strip()]
        category, ptype = CATEGORY_TYPE_BY_PRODUCT.get(row["제품명"], ("기능성 전반", "미정"))
        dot_color = {"red": "var(--red)", "amber": "var(--amber)", "green": "var(--green)"}[
            overall_signal(ingredients)
        ]
        date_label = HISTORY_DATE_LABELS[idx % len(HISTORY_DATE_LABELS)]
        # data-* 속성에 담을 값은 HTML 이스케이프해서 넣는다 — onclick 속성 안에 원료 배열(JSON)을
        # 직접 넣으면 배열 안의 큰따옴표가 onclick="..." 속성값의 닫는 따옴표와 충돌해 깨진다.
        ingredients_attr = html.escape(json.dumps(ingredients, ensure_ascii=False), quote=True)
        claim_attr = html.escape(str(row["효능클레임"]), quote=True)
        category_attr = html.escape(category, quote=True)
        type_attr = html.escape(ptype, quote=True)
        cards.append(
            f"""    <button class="history-card" data-category="{category_attr}" data-type="{type_attr}" data-ingredients="{ingredients_attr}" data-claim="{claim_attr}" onclick="loadHistoryFromCard(this)">
      <div class="history-top">
        <span class="history-cat">{category}</span>
        <span class="history-date">{date_label}</span>
      </div>
      <div class="history-title"><span class="risk-dot" style="background:{dot_color}"></span>{row['제품명']}</div>
      <div class="history-tags">
        <span class="history-tag">{row['효능클레임']}</span>
        <span class="history-tag">원료 {len(ingredients)}종</span>
      </div>
    </button>"""
        )
    return "\n".join(cards)


def build_banner_data_uri() -> str:
    if not BANNER_PATH.exists():
        return ""
    encoded = base64.b64encode(BANNER_PATH.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


NEW_CLASSIFY_FN = """function classifyIngredient(name){
    const key = name.trim().toLowerCase().replace(/\\s+/g, '');
    for (const dbName in INGREDIENT_DB) {
      if (key.indexOf(dbName.toLowerCase().replace(/\\s+/g, '')) !== -1) {
        return Object.assign({}, INGREDIENT_DB[dbName]);
      }
    }
    if(name.indexOf('추출물') !== -1){
      const hasPart = EXTRACT_PART_KEYWORDS.some(function(k){ return name.indexOf(k) !== -1; });
      if(!hasPart){
        return {signal:'amber', reason:'추출 부위(꽃/잎/줄기 등)를 명시하지 않았어요. 규정상 구체 부위를 표기해야 원료 사용 근거가 명확해져요.', reg:'기사용원료 (표기 불완전 가능성)', issue:'부위 표기 후 재확인 권장'};
      }
    }
    return {signal:'green', reason:'기사용원료로 널리 사용되며 특별한 제한 이력이 확인되지 않았어요.', reg:'기사용원료', issue:'-'};
  }"""

def build_page_html() -> str:
    page = MOCKUP_PATH.read_text(encoding="utf-8")

    # 1) 원료 판정 DB를 Python 쪽 데이터로 교체
    page, n = re.subn(
        r"const INGREDIENT_DB = \{.*?\n  \};\n(?=  const EXTRACT_PART_KEYWORDS)",
        lambda m: f"const INGREDIENT_DB = {build_ingredient_db_js()};\n",
        page,
        flags=re.S,
    )
    assert n == 1, "INGREDIENT_DB 치환 실패 — 목업 파일 구조가 바뀌었는지 확인하세요."

    # 2) exact-match 대신 Python과 동일한 substring 매칭 규칙 사용
    page, n = re.subn(
        r"function classifyIngredient\(name\)\{.*?\n  \}\n(?=\n  const BANNED_2026_KEYWORDS)",
        lambda m: NEW_CLASSIFY_FN + "\n",
        page,
        flags=re.S,
    )
    assert n == 1, "classifyIngredient 치환 실패"

    # 3) 금지 클레임 키워드 + 민감/저자극 체크 상수 주입
    sensitive_check_json = json.dumps(
        {
            "tone": "warn",
            "icon": "⚠️",
            "title": "클레임 표현 주의 — 민감성/저자극",
            "body": (
                "'민감성 피부'·'저자극' 표현은 실제 처벌 사례(2025년 11월)에서 과학적 근거 없이 "
                "사용해 광고 규정 위반으로 지적된 이력이 있어요. 근거 자료 없이 사용하지 마세요."
            ),
        },
        ensure_ascii=False,
    )
    replacement = (
        f"const BANNED_2026_KEYWORDS = {json.dumps(BANNED_CLAIM_KEYWORDS, ensure_ascii=False)};\n"
        f"  const SENSITIVE_CLAIM_KEYWORDS = {json.dumps(SENSITIVE_CLAIM_KEYWORDS, ensure_ascii=False)};\n"
        f"  const SENSITIVE_CHECK_INFO = {sensitive_check_json};"
    )
    page, n = re.subn(r"const BANNED_2026_KEYWORDS = \[.*?\];", replacement, page)
    assert n == 1, "BANNED_2026_KEYWORDS 치환 실패"

    # 4) 민감/저자극 체크를 카테고리 유효성 체크 목록에 반영
    old_marker = "    const whiteningHit = WHITENING_KEYWORDS.some"
    assert page.count(old_marker) == 1, "whiteningHit 마커를 찾을 수 없음"
    page = page.replace(
        old_marker,
        "    const sensitiveHit = SENSITIVE_CLAIM_KEYWORDS.some(function(k){ return c.indexOf(k) !== -1; });\n"
        "    if(sensitiveHit){ checks.push(SENSITIVE_CHECK_INFO); }\n" + old_marker,
        1,
    )

    # 5) loadHistory()를 data-* 속성 기반으로 호출하는 브릿지 함수 추가
    #    (onclick 속성 안에 원료 JSON 배열을 직접 넣으면 큰따옴표가 onclick="..." 의
    #    닫는 따옴표와 충돌해서 속성이 깨지기 때문에, data-* + JSON.parse 방식으로 우회)
    old_loadhistory_tail = (
        "    setTimeout(()=>{status.classList.remove('show'); status.textContent='';}, 2500);\n"
        "  }\n\n"
        "  /* ---------- 1차 스크리닝 규칙 엔진 ---------- */"
    )
    assert page.count(old_loadhistory_tail) == 1, "loadHistory 함수 종료 마커를 찾을 수 없음"
    new_loadhistory_tail = (
        "    setTimeout(()=>{status.classList.remove('show'); status.textContent='';}, 2500);\n"
        "  }\n\n"
        "  function loadHistoryFromCard(btn){\n"
        "    const category = btn.dataset.category;\n"
        "    const type = btn.dataset.type;\n"
        "    const ingredients = JSON.parse(btn.dataset.ingredients);\n"
        "    const claim = btn.dataset.claim;\n"
        "    loadHistory(category, type, ingredients, claim);\n"
        "  }\n\n"
        "  /* ---------- 1차 스크리닝 규칙 엔진 ---------- */"
    )
    page = page.replace(old_loadhistory_tail, new_loadhistory_tail, 1)

    # 6) 최근 스크리닝 이력을 sample_data.csv 기반으로 교체
    page, n = re.subn(
        r'<div class="history-list">.*?</div>\n</section>',
        lambda m: f'<div class="history-list">\n{build_history_cards_html()}\n  </div>\n</section>',
        page,
        flags=re.S,
    )
    assert n == 1, "history-list 치환 실패"

    # 7) 배너 이미지를 base64 데이터 URI로 임베드 (iframe srcdoc 안에서는 상대경로 파일을 못 읽음)
    banner_uri = build_banner_data_uri()
    old_img = 'src="3153f43349e726dcbb1326232ad5b6cd.jpg"'
    if banner_uri and old_img in page:
        page = page.replace(old_img, f'src="{banner_uri}"', 1)

    return page


# ----------------------------------------------------------------------
# 렌더링 — 목업 HTML/CSS/JS를 그대로 페이지에 임베드
# st.iframe은 raw HTML 문자열을 받아 콘텐츠 높이에 맞춰 자동으로 iframe 크기를 조절해줌
# ----------------------------------------------------------------------
st.iframe(build_page_html(), height="content", width="stretch")
