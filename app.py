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

# 원료별 실제 기사·자료 링크 — 검증 가능한 출처만 등록 (조사로 확인 못한 원료는 비워둠)
NMN_REFS = [
    {
        "title": "제11款！又一家企业的NMN完成化妆品新原料备案 — 中贸合规中心",
        "url": "https://www.zmuni.com/zh-hans/news/di-11-kuan-you-yi-jia-qi-ye-de-nmn-wan-cheng-hua-zhuang-pin/",
        "meta": "NMN 신원료 등록 현황을 추적한 중국 업계 자료예요. 여러 기업이 NMN을 신원료로 등록해 온 정황을 확인할 수 있어요.",
    },
    {
        "title": "邦泰生物领跑美妆新阶段：完成2024年NMN化妆品新原料备案 — 中华网",
        "url": "https://m.tech.china.com/tech/article/20240929/092024_1583451.html",
        "meta": "2024.09 한 기업의 NMN 신원료 등록 소식이에요. 등록번호 형식 등을 확인하는 참고자료로 쓸 수 있어요.",
    },
]
INGREDIENT_REFERENCE_LINKS = {
    "니코틴아마이드모노뉴클레오타이드": NMN_REFS,
    "nmn": NMN_REFS,
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

# 주제별 참고 자료 (전부 NMPA 공식 페이지) — 제품에 해당하는 주제만 골라서 보여줌
TOPIC_REFERENCES = {
    "whitening": {
        "title": "미백(美白) 화장품과 미백제 안내 (NMPA 공식)",
        "url": "https://www.nmpa.gov.cn/directory/web/nmpa/xxgk/kpzhsh/kpzhshhzhp/20211216170816138.html",
        "meta": "미백 기능성 화장품이 왜 특수화장품(注册) 등록 대상인지, 미백제의 정의와 관리 방식을 설명하는 NMPA 공식 자료예요.",
    },
    "sunscreen": {
        "title": "자외선차단(防晒) 화장품의 자외선차단제 종류 (NMPA 공식)",
        "url": "https://www.nmpa.gov.cn/directory/web/nmpa/xxgk/kpzhsh/kpzhshhzhp/20171025103001747.html",
        "meta": "자외선차단 화장품에 사용 가능한 무기·유기 자외선차단제 종류를 설명하는 NMPA 공식 자료예요.",
    },
    "hairdye": {
        "title": "화장품 법규 문건 모음 (NMPA 공식)",
        "url": "https://www.nmpa.gov.cn/hzhp/hzhpfgwj/index.html",
        "meta": "염모제 등 배합 제한이 있는 원료의 기술 기준을 확인할 수 있는 NMPA 공식 법규 문건 모음이에요.",
    },
    "new_ingredient": {
        "title": "화장품 신원료 등록·신고 관리 정책 Q&A (NMPA 공식)",
        "url": "https://www.nmpa.gov.cn/xxgk/zhcjd/zhcjdhzhp/20211111150042125.html",
        "meta": "신원료 등록이 어떤 경우 취소·철회되는지 등 신원료 관리 정책을 문답 형식으로 설명하는 NMPA 공식 자료예요.",
    },
    "banned_5_categories": {
        "title": "구 특수용도화장품(육모·제모·미유·건미·제취) 과도기 관리 공고 (NMPA 공식, 2021년 제150호)",
        "url": "https://www.nmpa.gov.cn/xxgk/ggtg/hzhpggtg/jmhzhptg/20211217140727142.html",
        "meta": "육모·제모·미유(유방)·건미(체형)·제취 5개 품목의 과도기가 2025년 12월 31일로 끝나 2026년부터 생산·수입·판매가 금지된다는 근거가 되는 NMPA 공식 공고예요.",
    },
}
TOPIC_REFERENCE_ORDER = ["whitening", "sunscreen", "hairdye", "new_ingredient", "banned_5_categories"]

# 원료별 주제 태깅 — 어떤 참고 자료를 보여줄지 판단하는 근거
# 나이아신아마이드처럼 여러 용도로 두루 쓰이는 원료는 제외 — 미백 클레임이 없는데도
# 자꾸 "미백" 참고자료가 붙어서 오히려 정확도가 떨어짐
INGREDIENT_TOPICS = {
    "알파-알부틴": "whitening",
    "트라넥사믹애씨드": "whitening",
    "에칠헥실메톡시신나메이트": "sunscreen",
    "징크옥사이드": "sunscreen",
    "티타늄디옥사이드": "sunscreen",
    "파라페닐렌다이아민": "hairdye",
}

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
        entry = {
            "signal": "red",
            "reason": reason,
            "reg": "신원료 (등록 상태 재확인 필요)",
            "issue": "신원료 등록·철회 이력 — 최신 상태 확인 필수",
            "topic": "new_ingredient",
        }
        if name in INGREDIENT_REFERENCE_LINKS:
            entry["refs"] = INGREDIENT_REFERENCE_LINKS[name]
        db[name] = entry
    for name, reason in LICENSE_REQUIRED.items():
        entry = {
            "signal": "red",
            "reason": reason,
            "reg": "허가(注册) 대상 가능 원료",
            "issue": "허가 절차 소요기간 사전 확인",
        }
        if name in INGREDIENT_TOPICS:
            entry["topic"] = INGREDIENT_TOPICS[name]
        db[name] = entry
    for name, reason in WATCH_INGREDIENTS.items():
        entry = {
            "signal": "amber",
            "reason": reason,
            "reg": "배합량 확인 필요 원료",
            "issue": "처방 내 배합비율·근거자료 확인",
        }
        if name in INGREDIENT_TOPICS:
            entry["topic"] = INGREDIENT_TOPICS[name]
        db[name] = entry
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

    # 8) 참고 자료(Section 4)를 제품의 원료·클레임·카테고리에 맞춰 동적으로 고르도록 교체
    old_build_references = (
        "  function buildReferences(){\n"
        "    return [\n"
        "      {title:'NMPA 공고·통지 (공식)', url:'https://www.nmpa.gov.cn/xxgk/ggtg/index.html', meta:'최신 공고·통지 원문을 실시간으로 확인할 수 있는 NMPA 공식 채널이에요.'},\n"
        "      {title:'NMPA 화장품 감독관리 공고 (공식)', url:'https://www.nmpa.gov.cn/hzhp/hzhpjmtg/index.html', meta:'등록·신고, 원료 관리 관련 공식 공고 게시 페이지예요.'},\n"
        "      {title:'실시간 웹서치 연동 안내', url:'', meta:'실제 서비스에서는 이 자리에 원료·카테고리별 최신 뉴스/공고 검색 결과가 자동으로 표시될 예정이에요. (이 데모는 정적 화면이라 고정 링크만 제공해요)'}\n"
        "    ];\n"
        "  }"
    )
    assert old_build_references in page, "buildReferences 함수를 찾을 수 없음 — 목업 파일 구조가 바뀌었는지 확인하세요."
    new_build_references = (
        f"const TOPIC_REFERENCES = {json.dumps(TOPIC_REFERENCES, ensure_ascii=False)};\n"
        f"  const TOPIC_REFERENCE_ORDER = {json.dumps(TOPIC_REFERENCE_ORDER, ensure_ascii=False)};\n"
        "  function buildReferences(claim, category, classified){\n"
        "    const refs = [\n"
        "      {title:'NMPA 공고·통지 (공식)', url:'https://www.nmpa.gov.cn/xxgk/ggtg/index.html', meta:'최신 공고·통지 원문을 실시간으로 확인할 수 있는 NMPA 공식 채널이에요.'},\n"
        "      {title:'NMPA 화장품 감독관리 공고 (공식)', url:'https://www.nmpa.gov.cn/hzhp/hzhpjmtg/index.html', meta:'등록·신고, 원료 관리 관련 공식 공고 게시 페이지예요.'}\n"
        "    ];\n"
        "    const topics = new Set();\n"
        "    (classified||[]).forEach(function(c){ if(c.topic) topics.add(c.topic); });\n"
        "    const cLower = (claim||'').toLowerCase();\n"
        "    if(BANNED_2026_KEYWORDS.some(function(k){ return cLower.indexOf(k) !== -1; })) topics.add('banned_5_categories');\n"
        "    if(WHITENING_KEYWORDS.some(function(k){ return cLower.indexOf(k) !== -1; })) topics.add('whitening');\n"
        "    if(SUNSCREEN_KEYWORDS.some(function(k){ return cLower.indexOf(k) !== -1; }) || category === '자외선차단') topics.add('sunscreen');\n"
        "    if(HAIRDYE_KEYWORDS.some(function(k){ return cLower.indexOf(k) !== -1; })) topics.add('hairdye');\n"
        "    TOPIC_REFERENCE_ORDER.forEach(function(key){\n"
        "      if(topics.has(key) && TOPIC_REFERENCES[key]) refs.push(TOPIC_REFERENCES[key]);\n"
        "    });\n"
        "    const seenUrls = new Set(refs.map(function(r){ return r.url; }));\n"
        "    (classified||[]).forEach(function(c){\n"
        "      (c.refs||[]).forEach(function(r){\n"
        "        if(!seenUrls.has(r.url)){ seenUrls.add(r.url); refs.push(r); }\n"
        "      });\n"
        "    });\n"
        "    refs.push({title:'실시간 웹서치 연동 안내', url:'', meta:'실제 서비스에서는 이 자리에 원료·카테고리별 최신 뉴스/공고 검색 결과가 자동으로 표시될 예정이에요. (이 데모는 제품 특성에 맞는 공식 자료를 우선 매칭하고, 실시간 검색은 다음 단계에서 추가돼요)'});\n"
        "    return refs;\n"
        "  }"
    )
    page = page.replace(old_build_references, new_build_references, 1)

    old_refs_call = "const refs = buildReferences().map(function(r){"
    assert page.count(old_refs_call) == 1, "buildReferences 호출부를 찾을 수 없음"
    page = page.replace(
        old_refs_call,
        "const refs = buildReferences(claim, category, classified).map(function(r){",
        1,
    )

    return page


# ----------------------------------------------------------------------
# 렌더링 — 목업 HTML/CSS/JS를 그대로 페이지에 임베드
# st.iframe은 raw HTML 문자열을 받아 콘텐츠 높이에 맞춰 자동으로 iframe 크기를 조절해줌
# ----------------------------------------------------------------------
st.iframe(build_page_html(), height="content", width="stretch")
