import streamlit as st
import pandas as pd
import re
from pathlib import Path

# ----------------------------------------------------------------------
# 기본 설정
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="규제나침반 | 중국 화장품 규제 1차 스크리닝",
    page_icon="🧭",
    layout="wide",
)

ASSETS_DIR = Path(__file__).parent / "assets"
SAMPLE_CSV = Path(__file__).parent / "sample_data.csv"

# ----------------------------------------------------------------------
# 브랜드 톤 CSS (네이비 + 골드)
# ----------------------------------------------------------------------
st.markdown(
    """
    <style>
    :root{
        --bg:#0E1A2B; --surface:#16263B; --surface-2:#1C3049;
        --ivory:#F3EFE4; --muted:#96A3B8;
        --gold:#E8C24A; --gold-bright:#FFDD6B;
        --green:#4C9A6A; --amber:#E0A83E; --red:#C1503F;
        --border: rgba(201,162,39,0.18);
    }
    .stApp{ background-color:#0E1A2B; color:#F3EFE4; }
    h1,h2,h3,h4 { color:#F3EFE4 !important; font-weight:700; }
    p, li, span, label { color:#F3EFE4; }
    .eyebrow{
        display:inline-block; font-size:12.5px; color:#FFDD6B;
        background:rgba(232,194,74,0.12); border:1px solid rgba(232,194,74,0.35);
        padding:4px 12px; border-radius:999px; margin-bottom:10px;
    }
    .card{
        background:#16263B; border:1px solid var(--border);
        border-radius:16px; padding:20px 22px; margin-bottom:16px;
    }
    .disclaimer{
        background:linear-gradient(0deg, rgba(224,168,62,0.08), rgba(224,168,62,0.08)), #16263B;
        border:1px solid rgba(224,168,62,0.35); border-radius:14px;
        padding:16px 18px; font-size:13.5px; color:#96A3B8;
    }
    .disclaimer strong{ color:#F3EFE4; }
    .badge{ display:inline-block; font-size:12.5px; font-weight:600;
        padding:5px 12px; border-radius:999px; margin-right:6px; margin-bottom:6px;}
    .badge.green{ background:rgba(76,154,106,0.16); color:#7FCB9C; border:1px solid rgba(76,154,106,0.4);}
    .badge.amber{ background:rgba(224,168,62,0.16); color:#FFDD6B; border:1px solid rgba(224,168,62,0.4);}
    .badge.red{ background:rgba(193,80,63,0.16); color:#E38676; border:1px solid rgba(193,80,63,0.4);}
    .ing-row{ padding:10px 0; border-bottom:1px solid var(--border); }
    .ing-row:last-child{ border-bottom:none; }
    .dot{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:8px; }
    .dot.green{ background:#4C9A6A; }
    .dot.amber{ background:#E0A83E; }
    .dot.red{ background:#C1503F; }
    div[data-testid="stMetricValue"] { color:#F3EFE4; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------
# 규제 판정용 데이터 (지금까지 조사한 근거 반영)
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
    "콜라겐": "‘*’ 표기 총칭 원료 유형 → 구체 원료명 명시 + 제조사 설명서·구매 증빙 등 증명서류 준비 필요",
}

# 2026.1.1부터 생산·판매 전면 금지된 5대 특수용도 클레임 키워드
BANNED_CLAIM_KEYWORDS = ["육모", "탈모", "제모", "유방", "가슴", "체형관리", "탈취", "체취"]

# 광고 클레임 표현 관련 주의 키워드 (실제 처벌 사례 기반)
SENSITIVE_CLAIM_KEYWORDS = ["민감성 피부", "민감성", "저자극"]

# "○○추출물" 형태에서 부위가 명시되지 않은 경우 감지용
PLANT_PART_KEYWORDS = ["꽃", "잎", "줄기", "뿌리", "열매", "씨", "껍질", "넝쿨", "전초"]


def classify_ingredient(name: str):
    """원료 1개를 신호등(색상)과 사유로 분류"""
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

    # "○○추출물" 표기인데 부위가 없는 경우
    if "추출물" in name and not any(part in name for part in PLANT_PART_KEYWORDS):
        return "amber", "‘○○추출물’ 형식은 원칙상 전초와 그 추출물을 의미해요. 사용 부위(꽃/잎/줄기 등)를 구체적으로 명시해야 해요."

    return "green", "기사용 원료 목록에 해당할 가능성이 높은 일반 성분이에요. 그래도 최신 목록 등재 여부는 확인해보세요."


def run_screening(category, product_type, ingredients_raw, target, claim):
    ingredients = [i.strip() for i in re.split(r"[,\n]", ingredients_raw) if i.strip()]

    results = []
    for ing in ingredients:
        color, reason = classify_ingredient(ing)
        results.append({"원료": ing, "신호": color, "사유": reason})

    counts = {"green": 0, "amber": 0, "red": 0}
    for r in results:
        counts[r["신호"]] += 1

    # 클레임 체크
    claim_flags = []
    for kw in BANNED_CLAIM_KEYWORDS:
        if kw in claim:
            claim_flags.append(
                ("red", f"'{kw}' 관련 클레임은 2026년 1월 1일부터 생산·수출·판매가 전면 제한된 5대 특수용도(육모·제모·유방미용·체형관리·탈취)에 해당할 수 있어요.")
            )
    for kw in SENSITIVE_CLAIM_KEYWORDS:
        if kw in claim:
            claim_flags.append(
                ("amber", f"'{kw}' 표현은 실제 처벌 사례(2025년 11월)에서 효능 클레임 위반으로 지적된 적이 있는 표현이에요. 과학적 근거 없이 사용하면 광고 규정 위반 소지가 있어요.")
            )

    return results, counts, claim_flags


# ----------------------------------------------------------------------
# 헤더
# ----------------------------------------------------------------------
col_logo, col_update = st.columns([3, 2])
with col_logo:
    st.markdown("### 🧭 규제나침반")
    st.caption("China Compliance Compass")
with col_update:
    st.markdown(
        "<div style='text-align:right; color:#96A3B8; font-size:13px; padding-top:10px;'>"
        "🕐 최근 업데이트: NMPA 공고 반영중</div>",
        unsafe_allow_html=True,
    )

# 배너 이미지
banner_path = ASSETS_DIR / "cream_banner.jpg"
if banner_path.exists():
    st.image(str(banner_path), use_container_width=True)
    st.markdown(
        "<p style='margin-top:-10px; color:#96A3B8; font-size:13px;'>"
        "매끄러운 텍스처 뒤에는, 확인해야 할 규제가 있습니다.</p>",
        unsafe_allow_html=True,
    )

st.markdown(
    "<span class='eyebrow'>중국 화장품 규제 · 1차 스크리닝</span>",
    unsafe_allow_html=True,
)
st.markdown("## 놓치기 쉬운 규제, 먼저 확인하고 진행하세요.")
st.write(
    "카테고리와 원료만 입력하면 원료 규제, 등록·신고 절차, 최신 이슈까지 확인이 필요한 항목을 정리해드려요."
)

st.markdown(
    """
    <div class="disclaimer">
    <strong>이 결과는 1차 스크리닝용입니다.</strong> 규정은 자주 바뀌고 신뢰할 수 있는 최신 확인이 중요해요.
    최종 등록·신고 전에는 반드시 NMPA 공식 채널 또는 사내 규제 전문 부서를 통해 확인하세요.
    </div>
    """,
    unsafe_allow_html=True,
)

st.write("")

# ----------------------------------------------------------------------
# 최근 스크리닝 이력 (샘플 CSV) - 클릭하면 입력값 자동 채움
# ----------------------------------------------------------------------
st.markdown("### 최근 스크리닝 이력")
st.caption("카드를 누르면 해당 조건을 아래 입력폼에 바로 불러와요.")

if "form_state" not in st.session_state:
    st.session_state.form_state = {
        "category": "스킨케어 – 앰플/세럼",
        "product_type": "미정 / 확인 필요",
        "ingredients": "",
        "target": "성인용",
        "claim": "",
    }

if SAMPLE_CSV.exists():
    history_df = pd.read_csv(SAMPLE_CSV)
    cols = st.columns(4)
    for idx, row in history_df.iterrows():
        with cols[idx % 4]:
            if st.button(f"📋 {row['제품명']}", key=f"hist_{idx}", use_container_width=True):
                st.session_state.form_state["ingredients"] = row["원료리스트"]
                st.session_state.form_state["claim"] = row["효능클레임"]
                st.rerun()
            st.caption(row["효능클레임"])

st.write("---")

# ----------------------------------------------------------------------
# 입력 폼
# ----------------------------------------------------------------------
st.markdown("### STEP 1. 상품 기획안 입력")
st.caption("카테고리와 원료만 입력해도 충분해요. 정보가 많을수록 체크리스트가 더 구체적으로 나와요.")

with st.container():
    c1, c2 = st.columns(2)
    with c1:
        category = st.selectbox(
            "제품 카테고리",
            ["스킨케어 – 앰플/세럼", "스킨케어 – 크림/로션", "메이크업", "헤어", "자외선차단", "기능성 전반"],
        )
        target = st.radio("타겟 사용자", ["성인용", "영유아용"], horizontal=True)
    with c2:
        product_type = st.radio(
            "제품 유형 (확실하지 않으면 미정 선택)",
            ["일반화장품", "특수화장품", "미정 / 확인 필요"],
            horizontal=True,
        )
        claim = st.text_input(
            "주요 효능 클레임 (선택)",
            value=st.session_state.form_state["claim"],
            placeholder="예: 미백, 진정, 안티에이징",
        )

    ingredients_raw = st.text_area(
        "핵심 원료 리스트 (쉼표로 구분)",
        value=st.session_state.form_state["ingredients"],
        placeholder="예: 나이아신아마이드, 알파-알부틴, 병풀추출물",
        height=100,
    )
    st.caption("전성분표를 그대로 붙여넣어도 인식돼요.")

    submitted = st.button("🔍 1차 스크리닝 시작", type="primary", use_container_width=False)

# ----------------------------------------------------------------------
# 결과 화면
# ----------------------------------------------------------------------
if submitted:
    if not ingredients_raw.strip():
        st.warning("원료를 최소 1개 이상 입력해주세요.")
    else:
        results, counts, claim_flags = run_screening(
            category, product_type, ingredients_raw, target, claim
        )

        st.write("---")
        st.markdown("## 스크리닝 결과")

        m1, m2, m3 = st.columns(3)
        m1.metric("🟢 안전 가능성 높음", f"{counts['green']}종")
        m2.metric("🟡 확인 필요", f"{counts['amber']}종")
        m3.metric("🔴 절차 확인 필수", f"{counts['red']}종")

        # 클레임 체크 결과
        st.markdown("### 클레임 / 카테고리 유효성")
        if not claim.strip():
            st.info("효능 클레임을 입력하지 않아 클레임 체크는 생략했어요.")
        elif not claim_flags:
            st.success(f"'{claim}' 클레임은 즉시 확인이 필요한 금지·주의 키워드에 해당하지 않아요.")
        else:
            for level, msg in claim_flags:
                if level == "red":
                    st.error(msg)
                else:
                    st.warning(msg)

        # 원료별 상세
        st.markdown("### 원료별 상세 분석")
        order = {"red": 0, "amber": 1, "green": 2}
        for r in sorted(results, key=lambda x: order[x["신호"]]):
            dot_class = r["신호"]
            st.markdown(
                f"""
                <div class="ing-row">
                    <span class="dot {dot_class}"></span><strong>{r['원료']}</strong><br>
                    <span style="color:#96A3B8; font-size:13.5px;">{r['사유']}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 체크리스트
        st.markdown("### 확인 필요 체크리스트")
        checklist_items = []
        for r in results:
            if r["신호"] in ("red", "amber"):
                checklist_items.append(f"{r['원료']} — {r['사유']}")
        if product_type == "미정 / 확인 필요":
            checklist_items.append("제품 유형(일반/특수화장품)을 먼저 확정하세요 — 절차 자체가 달라져요.")

        if checklist_items:
            for item in checklist_items:
                st.checkbox(item, key=f"chk_{item[:30]}")
        else:
            st.write("별도로 확인이 필요한 항목이 발견되지 않았어요. (그래도 최종 확인은 필수예요!)")

        st.markdown(
            """
            <div class="disclaimer" style="margin-top:20px;">
            <strong>다시 한 번 안내드려요.</strong> 이 결과는 키워드 기반 1차 스크리닝이며, 법률·규제 자문을 대체하지 않아요.
            최종 진행 전 NMPA 공식 채널 또는 규제 전문 부서 확인이 반드시 필요해요.
            </div>
            """,
            unsafe_allow_html=True,
        )

st.write("")
st.caption("규제나침반은 중국 화장품 규제 확인을 돕는 1차 스크리닝 참고 도구이며, 법률·규제 자문을 대체하지 않습니다.")
