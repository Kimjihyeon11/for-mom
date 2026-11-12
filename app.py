# -*- coding: utf-8 -*-
"""
♻️ 분리배출 — 이거 어떻게 버려요? (Streamlit · QR 접속형)

화면은 딱 3개 (표지 포함):
  1) 표지      : 큰 글씨 '분리배출' — 글자를 누르면 다음 화면으로
  2) 판독      : 물건 이름 → 🟢🟡🔴⚪ 신호등 + "지금 내놔도 돼요?"
  3) 동네·QR   : 우리 동네 배출 일정 설정 + 앱 접속용 QR 만들기

※ 물건·동네 데이터는 '예시'입니다. 공식 자료와 대조하지 않았으니
   실제 서비스 전에 공공데이터 API 또는 지자체 자료로 교체·검수하세요.
"""
from __future__ import annotations

import difflib
import html
import os
from datetime import datetime, time as dtime, timedelta, timezone
from io import BytesIO
from urllib.parse import quote, urlencode

import qrcode
import streamlit as st
from qrcode.constants import ERROR_CORRECT_M

st.set_page_config(
    page_title="분리배출",
    page_icon="♻️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

KST = timezone(timedelta(hours=9))
WEEK = ["월", "화", "수", "목", "금", "토", "일"]
DATA_NOTE = "예시 데이터 (공식 자료 미검증)"

# ──────────────────────────────────────────────────────────────
# 1. 데이터 (나중에 공공 API로 바꿀 땐 이 블록만 교체하면 됩니다)
# ──────────────────────────────────────────────────────────────
SIGNAL = {
    # 키: (이모지, 이름, 테두리·원 색, 원 안 글자색, 원 안 글자)
    "green": ("🟢", "그대로 재활용", "#2e9e4f", "#ffffff", "그대로"),
    "yellow": ("🟡", "손질 후 배출", "#f2b705", "#3b2f00", "손질"),
    "red": ("🔴", "재활용 불가", "#e5392d", "#ffffff", "불가"),
    "gray": ("⚪", "확실하지 않아요", "#9aa0a6", "#ffffff", "확인"),
}
LEGEND = [
    ("green", "그대로 재활용"),
    ("yellow", "비우고 헹궈서 손질 후 배출"),
    ("red", "재활용 불가 · 종량제 봉투 / 신고"),
    ("gray", "잘 모르겠어요 · 동네 기준 확인"),
]

# kind: 재활용 / 일반 / 음식물 → 동네 배출 요일표 적용, 별도 / 대형 → 수거함·신고 안내
ITEMS = [
    {"name": "투명 페트병", "alias": ["페트병", "패트병", "생수병", "물병", "음료수병"], "color": "yellow", "kind": "재활용",
     "headline": "비우고 라벨 떼서 찌그러뜨려 내놓으세요",
     "steps": ["내용물을 비우고 한 번 헹궈요", "라벨(비닐)을 떼요", "찌그러뜨린 뒤 뚜껑을 닫아 내놓아요"], "badges": []},
    {"name": "종이박스", "alias": ["택배박스", "박스", "상자", "골판지"], "color": "yellow", "kind": "재활용",
     "headline": "테이프·송장 떼고 납작하게 펼쳐 내놓으세요",
     "steps": ["테이프와 송장 스티커를 떼요 (송장은 개인정보라 찢거나 가려서 버려요)", "납작하게 펼쳐요", "물에 젖지 않게 묶어서 내놓아요"], "badges": []},
    {"name": "음료 캔", "alias": ["캔", "캔음료", "깡통", "맥주캔", "콜라캔"], "color": "yellow", "kind": "재활용",
     "headline": "비우고 헹궈서 찌그러뜨려 내놓으세요",
     "steps": ["내용물을 비우고 헹궈요", "담배꽁초 같은 이물질은 넣지 않아요", "찌그러뜨려 캔류로 내놓아요"], "badges": []},
    {"name": "유리병", "alias": ["소주병", "맥주병", "병", "유리"], "color": "yellow", "kind": "재활용",
     "headline": "뚜껑 빼고 헹궈서 내놓으세요",
     "steps": ["내용물을 비우고 헹궈요", "뚜껑은 재질별로 따로 분리해요", "깨진 유리는 재활용이 아니에요. 신문지로 싸서 동네 기준대로 버려요 (지역마다 달라요)"], "badges": []},
    {"name": "국물 있는 배달 용기", "alias": ["배달용기", "배달 그릇", "일회용기", "포장용기", "짜장면 그릇"], "color": "yellow", "kind": "재활용",
     "headline": "국물 버리고 헹궈서 내놓으세요",
     "steps": ["음식물과 국물을 비워요", "물로 헹궈요", "기름때가 안 지워지면 종량제 봉투로 가요"], "badges": []},
    {"name": "치킨 뼈", "alias": ["닭뼈", "뼈다귀", "갈비뼈", "족발 뼈"], "color": "red", "kind": "일반",
     "headline": "음식물이 아니라 일반 쓰레기(종량제)예요",
     "steps": ["딱딱한 뼈는 음식물 쓰레기가 아니에요", "종량제 봉투에 넣어요", "소스가 묻은 포장재는 따로 분리해요"], "badges": []},
    {"name": "달걀 껍데기", "alias": ["계란껍질", "계란 껍데기", "달걀껍질"], "color": "red", "kind": "일반",
     "headline": "일반 쓰레기(종량제)로 버리세요",
     "steps": ["음식물이 아니라 일반 쓰레기예요", "종량제 봉투에 넣어요"], "badges": []},
    {"name": "건전지", "alias": ["배터리", "폐건전지", "AA건전지"], "color": "red", "kind": "별도",
     "headline": "일반 쓰레기에 넣지 말고 수거함에 넣으세요",
     "steps": ["아파트·주민센터의 건전지 수거함에 넣어요", "수거함이 없으면 주민센터에 문의해요"], "badges": ["🔌 별도 수거"]},
    {"name": "형광등", "alias": ["폐형광등", "형광램프", "형광등관"], "color": "red", "kind": "별도",
     "headline": "깨뜨리지 말고 전용 수거함에 넣으세요",
     "steps": ["깨지지 않게 조심해서 옮겨요", "전용 수거함에 넣어요", "깨졌다면 주민센터에 문의해요"], "badges": ["🔌 별도 수거"]},
    {"name": "영수증", "alias": ["감열지", "전표", "계산서"], "color": "red", "kind": "일반",
     "headline": "종이처럼 보여도 일반 쓰레기예요",
     "steps": ["코팅된 감열지라 종이류로 재활용이 안 돼요", "개인정보가 있으면 찢어서 버려요", "종량제 봉투에 넣어요"], "badges": []},
    {"name": "우유팩", "alias": ["종이팩", "두유팩", "주스팩"], "color": "yellow", "kind": "재활용",
     "headline": "헹궈서 펼쳐 종이팩으로 내놓으세요",
     "steps": ["내용물을 비우고 헹궈요", "펼쳐서 말려요", "일반 종이와 섞지 말고 종이팩으로 내놓아요"], "badges": []},
    {"name": "소파", "alias": ["쇼파", "쇼파베드", "대형가구", "장롱"], "color": "red", "kind": "대형",
     "headline": "대형폐기물이에요. 신고하고 스티커를 붙여 내놓으세요",
     "steps": ["구청·주민센터 또는 온라인으로 배출 신고를 해요", "수수료를 내고 스티커를 받아요", "신고한 날짜에 지정 장소에 내놓아요"], "badges": ["📄 신고·수수료"]},
    {"name": "신문지", "alias": ["신문", "종이신문", "전단지", "A4용지", "깨끗한 종이"], "color": "green", "kind": "재활용",
     "headline": "묶어서 그대로 내놓으세요",
     "steps": ["물기나 음식물이 묻은 것은 빼요", "끈으로 묶거나 상자에 담아 내놓아요"], "badges": []},
    {"name": "남은 밥·반찬", "alias": ["음식물쓰레기", "음식물", "잔반", "밥", "반찬", "남은 음식"], "color": "yellow", "kind": "음식물",
     "headline": "물기 빼서 음식물 전용 용기에 버리세요",
     "steps": ["물기를 꼭 짜요", "비닐·이쑤시개·뼈는 빼요", "음식물 전용 용기에 넣어요"], "badges": ["🍚 음식물"]},
    {"name": "칫솔", "alias": ["플라스틱칫솔", "치솔"], "color": "red", "kind": "일반",
     "headline": "플라스틱이어도 일반 쓰레기예요",
     "steps": ["여러 재질이 섞여 있어 재활용이 안 돼요", "종량제 봉투에 넣어요"], "badges": []},
]
ITEM_BY_NAME = {it["name"]: it for it in ITEMS}
QUICK_CHIPS = ["투명 페트병", "종이박스", "음료 캔", "치킨 뼈", "건전지", "우유팩", "소파", "남은 밥·반찬"]

# 동네 배출표 샘플 (rec=재활용, gen=일반, food=음식물)
AREAS = {
    "샘플 동네 A": {
        "rec": (["수", "일"], dtime(18, 0), dtime(22, 0), "단지 분리배출장"),
        "gen": (["월", "목"], dtime(18, 0), dtime(22, 0), "단지 종량제 배출장"),
        "food": (["월", "화", "수", "목", "금", "토", "일"], dtime(18, 0), dtime(23, 0), "음식물 수거함"),
    },
    "샘플 동네 B": {
        "rec": (["화", "금"], dtime(7, 0), dtime(21, 0), "집 앞 지정 장소"),
        "gen": (["월", "수", "금"], dtime(18, 0), dtime(23, 0), "집 앞 지정 장소"),
        "food": (["월", "화", "수", "목", "금"], dtime(18, 0), dtime(23, 0), "음식물 수거함"),
    },
}
CUSTOM_AREA = "직접 입력"
KIND_KEY = {"재활용": "rec", "일반": "gen", "음식물": "food"}
KIND_LABEL = {"rec": "♻️ 재활용", "gen": "🗑️ 일반(종량제)", "food": "🍚 음식물"}

PAGES = {"cover": "🏠 표지", "find": "🔍 판독", "area": "🏘️ 동네·QR"}  # 화면은 딱 3개


# ──────────────────────────────────────────────────────────────
# 2. 상태 관리
#    화면을 바꾸면 안 보이는 위젯의 값이 사라지므로, 매번 값을 다시 저장해 둡니다.
# ──────────────────────────────────────────────────────────────
PERSIST = ["query", "memo", "area", "big", "app_url", "include_area"] + [
    f"{k}_{s}" for k in ("rec", "gen", "food") for s in ("days", "s", "e", "p")
]
for _k in PERSIST:
    if _k in st.session_state:
        st.session_state[_k] = st.session_state[_k]


def apply_preset(name: str) -> None:
    preset = AREAS.get(name)
    if not preset:  # '직접 입력'이면 현재 값을 그대로 둠
        return
    for k, (days, start, end, place) in preset.items():
        st.session_state[f"{k}_days"] = list(days)
        st.session_state[f"{k}_s"] = start
        st.session_state[f"{k}_e"] = end
        st.session_state[f"{k}_p"] = place


def on_area_change() -> None:
    apply_preset(st.session_state["area"])


def go(page: str) -> None:
    st.session_state["page"] = page


def on_nav() -> None:
    label = st.session_state.get("nav")
    for page, text in PAGES.items():
        if text == label:
            st.session_state["page"] = page


def set_query(value: str) -> None:
    st.session_state["query"] = value


def make_pick(widget_key: str):
    """pills(알약 버튼)에서 고른 값을 검색어로 넣고, 선택 표시는 비웁니다."""
    def _cb() -> None:
        v = st.session_state.get(widget_key)
        if v:
            st.session_state["query"] = v
        st.session_state[widget_key] = None
    return _cb


if "init" not in st.session_state:
    wanted = st.query_params.get("area", "")  # QR에 ?area=샘플 동네 A 가 담겨 있으면 미리 선택
    first = wanted if wanted in AREAS else list(AREAS)[0]
    st.session_state["area"] = first
    apply_preset(first)
    st.session_state["query"] = ""
    st.session_state["recent"] = []
    st.session_state["memo"] = ""
    st.session_state["page"] = "cover"
    st.session_state["init"] = True


# ──────────────────────────────────────────────────────────────
# 3. 로직
# ──────────────────────────────────────────────────────────────
def norm(s: str) -> str:
    return "".join(s.lower().split())


def search(query: str):
    """(결과 목록, 방식) 반환. 방식: 'exact' | 'fuzzy' | 'none'"""
    nq = norm(query)
    if not nq:
        return [], "none"
    exact, partial = [], []
    for it in ITEMS:
        names = [norm(n) for n in [it["name"], *it["alias"]]]
        if nq in names:
            exact.append(it)
        elif any(nq in n or (len(n) >= 2 and n in nq) for n in names):
            partial.append(it)
    found = exact + [p for p in partial if p not in exact]
    if found:
        return found[:3], "exact"
    pool = {}
    for it in ITEMS:
        for n in [it["name"], *it["alias"]]:
            pool[norm(n)] = it
    close = difflib.get_close_matches(nq, list(pool), n=5, cutoff=0.6)
    out = []
    for c in close:
        if pool[c] not in out:
            out.append(pool[c])
    return (out[:3], "fuzzy") if out else ([], "none")


def get_sched(k: str) -> dict:
    ss = st.session_state
    return {"days": ss[f"{k}_days"], "start": ss[f"{k}_s"], "end": ss[f"{k}_e"], "place": ss[f"{k}_p"]}


def drop_status(k: str, now: datetime):
    """(상태, 안내문) 반환. 상태: ok | wait | next | warn"""
    s = get_sched(k)
    days = {WEEK.index(d) for d in s["days"]}
    if not days:
        return "warn", "우리 동네 배출 요일이 아직 비어 있어요. '동네·QR' 화면에서 입력해 주세요."
    place = s["place"] or "정해진 배출 장소"
    rng = f"{s['start']:%H:%M}~{s['end']:%H:%M}"
    today, t = now.weekday(), now.time()
    if today in days:
        if t < s["start"]:
            return "wait", f"오늘이 수거일이에요. {s['start']:%H:%M}부터 {place}에 내놓을 수 있어요."
        if t <= s["end"]:
            return "ok", f"지금 내놔도 돼요! {s['end']:%H:%M}까지 {place}에 내놓으세요."
    for add in range(1, 8):
        if (today + add) % 7 in days:
            d = now + timedelta(days=add)
            when = {1: "내일", 2: "모레"}.get(add, f"{add}일 뒤")
            head = "오늘 배출 시간은 지났어요." if today in days else "오늘은 수거일이 아니에요."
            return "next", f"{head} {when}({WEEK[d.weekday()]}, {d.month}월 {d.day}일) {rng}에 {place}에 내놓으세요."
    return "warn", "배출 요일을 확인할 수 없어요."


def sched_summary(k: str) -> str:
    s = get_sched(k)
    days = "·".join(d for d in WEEK if d in s["days"]) or "요일 미입력"
    return f"{KIND_LABEL[k]}  |  {days}  {s['start']:%H:%M}~{s['end']:%H:%M}"


def detect_app_url() -> str:
    url = os.environ.get("APP_URL", "")
    if not url:
        try:
            url = str(st.secrets.get("APP_URL", ""))
        except Exception:
            url = ""
    if not url:
        try:
            host = st.context.headers.get("Host", "")
            if host:
                scheme = "http" if host.startswith(("localhost", "127.0.0.1")) else "https"
                url = f"{scheme}://{host}"
        except Exception:
            url = ""
    return url


def make_qr_png(url: str) -> bytes:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=12, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#14532d", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────
# 4. 디자인 (CSS)
# ──────────────────────────────────────────────────────────────
def inject_css(big: bool, cover: bool) -> None:
    root = "22px" if big else "19px"  # 기본부터 큼직하게, '더 크게'를 켜면 한 단계 더
    bg = (
        "linear-gradient(180deg,#eaf7ee 0%,#f8fcf9 55%,#ffffff 100%)"
        if cover
        else "#f6fbf7"
    )
    st.markdown(
        f"""<style>
html{{font-size:{root} !important;}}
#MainMenu,footer,header[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"]{{display:none !important;}}
.stApp{{background:{bg} !important;color:#1f2937 !important;}}
.block-container{{max-width:620px;padding:1.2rem 1.1rem 3rem 1.1rem;}}
.stApp [data-testid="stMarkdownContainer"] p,.stApp [data-testid="stMarkdownContainer"] li,
.stApp [data-testid="stCaptionContainer"],.stApp label,.stApp h1,.stApp h2,.stApp h3{{color:#1f2937;}}

/* 일반 버튼 */
.stButton>button,.stDownloadButton>button,.stLinkButton>a{{border-radius:16px;border:2px solid #cfe3d6;background:#fff;padding:.6rem 1.1rem;}}
.stButton>button p,.stDownloadButton>button p,.stLinkButton>a p{{color:#1f2937;font-weight:700;font-size:1.05rem;}}

/* 검색창 */
.stTextInput input{{font-size:1.3rem !important;padding:.85rem 1rem !important;color:#111827 !important;background:#fff !important;}}
.stTextInput [data-baseweb="input"],.stTextInput [data-baseweb="base-input"]{{border-radius:18px !important;background:#fff !important;}}
.stTextInput [data-baseweb="input"]{{border:2px solid #cfe3d6 !important;}}

/* 화면 제목 */
.page-title{{font-size:1.9rem;font-weight:900;color:#14532d;letter-spacing:-.02em;margin:.9rem 0 .6rem 0;line-height:1.25;}}
.sec-title{{font-size:1.35rem;font-weight:800;color:#14532d;margin:.2rem 0 .5rem 0;}}

/* 신호등 결과 카드 */
.sig-card{{display:flex;align-items:center;gap:16px;padding:20px 20px;border:5px solid;border-radius:26px;background:#fff;margin:10px 0 12px 0;}}
.sig-dot{{min-width:92px;height:92px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:1.2rem;}}
.sig-label{{font-size:1rem;color:#555;font-weight:700;}}
.sig-head{{font-size:1.4rem;font-weight:900;line-height:1.35;color:#1f2937;}}
.badge{{display:inline-block;padding:5px 14px;margin:0 6px 8px 0;border-radius:999px;background:#e7efe9;color:#25402f;font-size:1rem;font-weight:700;}}
.steps-title{{font-size:1.15rem;font-weight:800;margin:.6rem 0 .2rem 0;color:#14532d;}}
.step{{font-size:1.2rem;line-height:1.6;margin:3px 0;color:#1f2937;}}
.drop{{padding:16px 20px;border-radius:20px;margin:12px 0;font-size:1.15rem;line-height:1.55;color:#1f2937;}}
.drop.ok{{background:#e5f6ec;border:3px solid #2e9e4f;}}
.drop.wait,.drop.next{{background:#fff6dc;border:3px solid #f2b705;}}
.drop.warn,.drop.info{{background:#f1f3f5;border:3px solid #9aa0a6;}}
.foot{{color:#6b7280;font-size:.9rem;line-height:1.55;margin-top:18px;}}

/* 신호등 설명(처음 화면) */
.legend{{background:#fff;border:2px solid #dcebe1;border-radius:22px;padding:8px 18px;margin-top:18px;}}
.lg{{display:flex;align-items:center;gap:14px;padding:11px 0;border-bottom:1px solid #eef3ef;font-size:1.15rem;font-weight:700;color:#1f2937;}}
.lg:last-child{{border-bottom:none;}}
.lgdot{{width:30px;height:30px;border-radius:50%;flex:none;}}

/* 표지 */
.cover-pre{{text-align:center;color:#2e9e4f;font-weight:800;font-size:1.3rem;margin-top:13vh;letter-spacing:.01em;}}
.st-key-start{{display:flex;justify-content:center;}}
.stApp .st-key-start button{{background:transparent !important;border:none !important;box-shadow:none !important;padding:.2rem .4rem !important;min-height:0 !important;width:auto !important;}}
.stApp .st-key-start button p{{font-size:min(19vw,112px) !important;font-weight:900 !important;color:#14532d !important;letter-spacing:-.04em !important;line-height:1.15 !important;white-space:nowrap !important;}}
.stApp .st-key-start button:hover p,.stApp .st-key-start button:active p,.stApp .st-key-start button:focus p{{color:#2e9e4f !important;}}
.stApp .st-key-start button:hover,.stApp .st-key-start button:active,.stApp .st-key-start button:focus{{background:transparent !important;border:none !important;box-shadow:none !important;}}
.cover-hint{{text-align:center;color:#4b5563;font-size:1.25rem;font-weight:700;margin-top:.2rem;animation:nudge 1.8s ease-in-out infinite;}}
@keyframes nudge{{0%,100%{{transform:translateY(0);}}50%{{transform:translateY(7px);}}}}
.cover-sub{{text-align:center;color:#374151;font-size:1.2rem;font-weight:600;margin-top:2rem;line-height:1.6;}}
.cover-dots{{display:flex;justify-content:center;gap:16px;margin-top:1.6rem;}}
.cover-dots span{{width:34px;height:34px;border-radius:50%;display:inline-block;}}
.st-key-cover_toggle{{margin-top:3rem;display:flex;justify-content:center;}}
</style>""",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────
# 5. 화면 조각
# ──────────────────────────────────────────────────────────────
def signal_card(sig: str, headline: str) -> None:
    emoji, label, color, fg, short = SIGNAL[sig]
    st.markdown(
        f'<div class="sig-card" style="border-color:{color}">'
        f'<div class="sig-dot" style="background:{color};color:{fg}">{short}</div>'
        f'<div><div class="sig-label">{emoji} {label}</div>'
        f'<div class="sig-head">{html.escape(headline)}</div></div></div>',
        unsafe_allow_html=True,
    )


def footer() -> None:
    st.markdown(
        f'<div class="foot">안내 기준일: {DATA_NOTE}<br>'
        "참고용입니다. 최종 기준은 관할 지자체에 확인하세요.</div>",
        unsafe_allow_html=True,
    )


def render_drop(item: dict, now: datetime) -> None:
    kind = item["kind"]
    if kind in KIND_KEY:
        k = KIND_KEY[kind]
        status, msg = drop_status(k, now)
        title = f"🕗 지금 내놔도 돼요? · {KIND_LABEL[k]}"
    elif kind == "별도":
        status, title = "info", "🕗 지금 내놔도 돼요?"
        msg = "배출 요일이 따로 없어요. 아파트·주민센터의 전용 수거함을 이용하세요."
    else:  # 대형
        status, title = "info", "🕗 지금 내놔도 돼요?"
        msg = "신고한 배출일에만 내놓을 수 있어요. 신고 없이 내놓으면 과태료 대상일 수 있어요."
    memo = st.session_state.get("memo", "").strip()
    memo_html = f"<br>📝 {html.escape(memo)}" if memo and kind in KIND_KEY else ""
    st.markdown(
        f'<div class="drop {status}"><b>{title}</b><br>{html.escape(msg)}{memo_html}</div>',
        unsafe_allow_html=True,
    )


def render_result(item: dict, now: datetime) -> None:
    signal_card(item["color"], f'{item["name"]}: {item["headline"]}')
    if item["badges"]:
        st.markdown("".join(f'<span class="badge">{b}</span>' for b in item["badges"]), unsafe_allow_html=True)
    st.markdown('<div class="steps-title">이렇게 버리세요</div>', unsafe_allow_html=True)
    for i, step in enumerate(item["steps"][:3], 1):
        st.markdown(f'<div class="step">{i}. {html.escape(step)}</div>', unsafe_allow_html=True)
    render_drop(item, now)


def render_unknown(query: str) -> None:
    signal_card("gray", "잘 모르겠어요. 동네 기준을 확인해 주세요")
    st.markdown(
        '<div class="drop info">관할 구청(청소 담당 부서)이나 동 주민센터에 문의하면 가장 정확해요.</div>',
        unsafe_allow_html=True,
    )
    st.link_button("🔎 인터넷에서 찾아보기", f"https://search.naver.com/search.naver?query={quote(query + ' 분리배출')}")


def render_legend() -> None:
    rows = "".join(
        f'<div class="lg"><span class="lgdot" style="background:{SIGNAL[k][2]}"></span>{html.escape(t)}</div>'
        for k, t in LEGEND
    )
    st.markdown(f'<div class="legend">{rows}</div>', unsafe_allow_html=True)


def render_nav(page: str) -> None:
    """상단 화면 이동 버튼 (3개)"""
    st.session_state["nav"] = PAGES[page]
    st.segmented_control(
        "화면 이동", list(PAGES.values()), key="nav", on_change=on_nav, label_visibility="collapsed"
    )


# ──────────────────────────────────────────────────────────────
# 6. 화면 3개
# ──────────────────────────────────────────────────────────────
def screen_cover() -> None:
    st.markdown('<div class="cover-pre">이거 어떻게 버려요?</div>', unsafe_allow_html=True)
    st.button("분리배출", key="start", on_click=go, args=("find",))  # 글자 자체가 버튼
    st.markdown(
        '<div class="cover-hint">👆 글자를 눌러 시작하세요</div>'
        '<div class="cover-sub">물건 이름만 치면<br>신호등 색으로 알려드려요</div>'
        '<div class="cover-dots">'
        '<span style="background:#2e9e4f"></span>'
        '<span style="background:#f2b705"></span>'
        '<span style="background:#e5392d"></span></div>',
        unsafe_allow_html=True,
    )
    with st.container(key="cover_toggle"):
        st.toggle("글자 더 크게", key="big")


def screen_find(now: datetime) -> None:
    render_nav("find")
    st.markdown('<div class="page-title">무엇을 버리시나요?</div>', unsafe_allow_html=True)
    st.text_input(
        "물건 이름", key="query", placeholder="예) 치킨 뼈, 페트병, 소파", label_visibility="collapsed"
    )
    query = st.session_state["query"].strip()

    if not query:
        st.markdown('<div class="sec-title" style="margin-top:1rem">자주 찾는 물건</div>', unsafe_allow_html=True)
        st.pills("자주 찾는 물건", QUICK_CHIPS, key="chip", on_change=make_pick("chip"), label_visibility="collapsed")
        if st.session_state["recent"]:
            st.markdown('<div class="sec-title" style="margin-top:.8rem">최근에 찾아본 것</div>', unsafe_allow_html=True)
            st.pills(
                "최근에 찾아본 것", st.session_state["recent"], key="recent_pick",
                on_change=make_pick("recent_pick"), label_visibility="collapsed",
            )
        render_legend()
    else:
        results, mode = search(query)
        if not results:
            render_unknown(query)
        else:
            top = results[0]
            if mode == "fuzzy":
                st.markdown(f'<div class="step">\'{html.escape(query)}\'와(과) 가장 비슷한 물건이에요. 혹시 이거 찾으셨나요?</div>', unsafe_allow_html=True)
            recent = [r for r in st.session_state["recent"] if r != top["name"]]
            st.session_state["recent"] = ([top["name"]] + recent)[:6]
            render_result(top, now)
            if len(results) > 1:
                st.markdown('<div class="sec-title" style="margin-top:.8rem">비슷한 물건</div>', unsafe_allow_html=True)
                st.pills(
                    "비슷한 물건", [it["name"] for it in results[1:]], key="sim_pick",
                    format_func=lambda n: f'{SIGNAL[ITEM_BY_NAME[n]["color"]][0]} {n}',
                    on_change=make_pick("sim_pick"), label_visibility="collapsed",
                )
        st.button("🔄 다른 물건 찾기", on_click=set_query, args=("",))
    footer()


def screen_area() -> None:
    render_nav("area")
    st.markdown('<div class="page-title">우리 동네 · QR</div>', unsafe_allow_html=True)

    # ── 우리 동네 ──
    with st.container(border=True):
        st.markdown('<div class="sec-title">🏘️ 우리 동네 배출 일정</div>', unsafe_allow_html=True)
        st.selectbox("동네 고르기", [*AREAS, CUSTOM_AREA], key="area", on_change=on_area_change)
        st.caption("샘플 동네는 예시 값이에요. 우리 동네 실제 요일과 시간으로 고쳐 주세요.")
        st.markdown(
            "".join(f'<div class="step">{html.escape(sched_summary(k))}</div>' for k in ("rec", "gen", "food")),
            unsafe_allow_html=True,
        )
        for k in ("rec", "gen", "food"):
            with st.expander(f"✏️ {KIND_LABEL[k]} 수정"):  # 라벨을 고정해야 수정 중에 접히지 않아요
                st.multiselect("배출 요일", WEEK, key=f"{k}_days")
                c1, c2 = st.columns(2)
                c1.time_input("시작", key=f"{k}_s", step=900)
                c2.time_input("종료", key=f"{k}_e", step=900)
                st.text_input("배출 장소", key=f"{k}_p", placeholder="예) 101동 앞 분리배출장")
                if st.session_state[f"{k}_e"] <= st.session_state[f"{k}_s"]:
                    st.warning("종료 시간이 시작 시간보다 늦어야 해요. (자정을 넘기는 시간대는 아직 지원하지 않아요)")
        st.text_area("📝 동별 배출 장소 메모 (아파트용)", key="memo", placeholder="예) 102동은 지하 1층, 103동은 정문 옆", height=90)
        st.caption("입력한 내용은 이 접속 동안만 유지돼요. 새로고침하면 처음 값으로 돌아가요.")

    # ── QR ──
    with st.container(border=True):
        st.markdown('<div class="sec-title">📲 QR로 앱 열기</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="step">가족이나 이웃이 QR을 스캔하면 이 앱이 바로 열려요. 냉장고나 분리배출함 옆에 붙여 두세요.</div>',
            unsafe_allow_html=True,
        )
        if "app_url" not in st.session_state:
            st.session_state["app_url"] = detect_app_url()
        st.text_input(
            "앱 주소", key="app_url", placeholder="https://내앱이름.streamlit.app",
            help="배포한 Streamlit 앱 주소를 넣으세요. 배포된 앱에서는 자동으로 채워져요.",
        )
        st.checkbox("선택한 샘플 동네도 함께 담기", key="include_area")

        base = st.session_state["app_url"].strip().rstrip("/")
        if not base.startswith(("http://", "https://")):
            st.warning("앱 주소를 https:// 로 시작하게 입력하면 QR이 만들어져요.")
        else:
            qr_url = base
            area = st.session_state["area"]
            if st.session_state.get("include_area") and area in AREAS:
                qr_url = f"{base}/?{urlencode({'area': area})}"
            if base.startswith(("http://localhost", "http://127.0.0.1")):
                st.warning("지금 주소는 내 컴퓨터에서만 열려요. 배포한 주소로 바꾸면 다른 사람 폰에서도 열려요.")
            png = make_qr_png(qr_url)
            st.image(png, width=300, caption="📷 폰 카메라로 스캔하세요")
            st.code(qr_url, language=None)
            st.download_button("⬇️ QR 이미지 저장 (PNG)", data=png, file_name="bunri-baechul-qr.png", mime="image/png")

        with st.expander("GitHub + Streamlit Cloud 배포 방법"):
            st.markdown(
                "1. GitHub 저장소를 만들고 `app.py`, `requirements.txt` 두 파일을 올려요.\n"
                "2. [share.streamlit.io](https://share.streamlit.io)에서 GitHub로 로그인하고 **Create app**을 눌러요.\n"
                "3. 저장소를 고르고 Main file path에 `app.py`를 입력한 뒤 Deploy 해요.\n"
                "4. 배포된 주소가 위 '앱 주소'에 자동으로 들어오면 QR을 저장해서 인쇄해요."
            )

    with st.container(key="size_toggle"):
        st.toggle("글자 더 크게", key="big")
    footer()


# ──────────────────────────────────────────────────────────────
# 7. 실행
# ──────────────────────────────────────────────────────────────
now = datetime.now(KST)
page = st.session_state["page"]
inject_css(bool(st.session_state.get("big", False)), page == "cover")

if page == "cover":
    screen_cover()
elif page == "find":
    screen_find(now)
else:
    screen_area()
