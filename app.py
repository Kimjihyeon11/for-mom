# -*- coding: utf-8 -*-
"""
♻️ 이거 어떻게 버려요? — 분리배출 판독기 (Streamlit · QR 접속형)

- QR 코드를 스캔하면 이 앱으로 접속합니다. (3번째 화면에서 QR 생성)
- 화면은 탭 3개뿐: ① 판독  ② 우리 동네  ③ QR
- 물건 데이터는 '예시'입니다. 공식 자료와 대조하지 않았으니
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

st.set_page_config(page_title="이거 어떻게 버려요?", page_icon="♻️", layout="centered")

KST = timezone(timedelta(hours=9))
WEEK = ["월", "화", "수", "목", "금", "토", "일"]
DATA_NOTE = "예시 데이터 (공식 자료 미검증)"

# ──────────────────────────────────────────────────────────────
# 1. 데이터 (나중에 공공 API로 바꿔 끼울 수 있도록 이 블록만 교체하면 됩니다)
# ──────────────────────────────────────────────────────────────
SIGNAL = {
    # 키: (이모지, 이름, 테두리·원 색, 원 안 글자색, 원 안 글자)
    "green": ("🟢", "그대로 재활용", "#2e9e4f", "#ffffff", "그대로"),
    "yellow": ("🟡", "손질 후 배출", "#f2b705", "#3b2f00", "손질"),
    "red": ("🔴", "재활용 불가", "#e5392d", "#ffffff", "불가"),
    "gray": ("⚪", "확실하지 않아요", "#9aa0a6", "#ffffff", "확인"),
}

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

QUICK_CHIPS = ["투명 페트병", "종이박스", "음료 캔", "치킨 뼈", "건전지", "우유팩", "소파", "남은 밥·반찬"]

# 동네 배출표 샘플 (kind 키: rec=재활용, gen=일반, food=음식물)
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


# ──────────────────────────────────────────────────────────────
# 2. 상태 초기화 (QR로 들어올 때 ?area=샘플 동네 A 처럼 동네를 미리 고를 수 있음)
# ──────────────────────────────────────────────────────────────
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


def set_query(value: str) -> None:
    st.session_state["query"] = value


if "init" not in st.session_state:
    wanted = st.query_params.get("area", "")
    first = wanted if wanted in AREAS else list(AREAS)[0]
    st.session_state["area"] = first
    apply_preset(first)
    st.session_state["query"] = ""
    st.session_state["recent"] = []
    st.session_state["memo"] = ""
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
        return "warn", "우리 동네 배출 요일이 아직 비어 있어요. '우리 동네' 탭에서 입력해 주세요."
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
# 4. 화면 조각
# ──────────────────────────────────────────────────────────────
def inject_css(big: bool) -> None:
    base = "html{font-size:19px !important;}" if big else ""
    st.markdown(
        f"""<style>
{base}
.block-container{{padding-top:1.4rem;max-width:640px;}}
.sig-card{{display:flex;align-items:center;gap:16px;padding:18px 20px;border:4px solid;border-radius:22px;background:#fff;margin:8px 0 12px 0;}}
.sig-dot{{min-width:88px;height:88px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1.15rem;}}
.sig-label{{font-size:.95rem;color:#555;font-weight:600;}}
.sig-head{{font-size:1.3rem;font-weight:800;line-height:1.35;color:#1f2937;}}
.badge{{display:inline-block;padding:4px 12px;margin:0 6px 6px 0;border-radius:999px;background:#eef2f7;color:#334155;font-size:.9rem;font-weight:600;}}
.drop{{padding:14px 18px;border-radius:18px;margin:10px 0;font-size:1.05rem;line-height:1.5;}}
.drop.ok{{background:#e8f7ee;border:2px solid #2e9e4f;}}
.drop.wait,.drop.next{{background:#fff7e0;border:2px solid #f2b705;}}
.drop.warn,.drop.info{{background:#f1f3f5;border:2px solid #9aa0a6;}}
.foot{{color:#6b7280;font-size:.82rem;line-height:1.5;margin-top:14px;}}
.step{{font-size:1.05rem;line-height:1.55;margin:2px 0;}}
</style>""",
        unsafe_allow_html=True,
    )


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
    st.markdown("**이렇게 버리세요**")
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


# ──────────────────────────────────────────────────────────────
# 5. 화면 (탭 3개)
# ──────────────────────────────────────────────────────────────
now = datetime.now(KST)

top_l, top_r = st.columns([3, 1])
with top_l:
    st.markdown("## ♻️ 이거 어떻게 버려요?")
    st.caption(f"지금 {now.month}월 {now.day}일({WEEK[now.weekday()]}) {now:%H:%M}")
with top_r:
    big = st.toggle("글자 크게", key="big")
inject_css(big)

tab_find, tab_area, tab_qr = st.tabs(["🔍 판독", "🏘️ 우리 동네", "📲 QR"])

# ── 화면 1: 판독 ────────────────────────────────────────────
with tab_find:
    st.text_input(
        "물건 이름", key="query", placeholder="예) 치킨 뼈, 페트병, 소파", label_visibility="collapsed"
    )
    query = st.session_state["query"].strip()

    if not query:
        st.markdown("**자주 찾는 물건**")
        cols = st.columns(4)
        for i, name in enumerate(QUICK_CHIPS):
            cols[i % 4].button(name, key=f"chip_{i}", on_click=set_query, args=(name,), use_container_width=True)
        if st.session_state["recent"]:
            st.markdown("**최근에 찾아본 것**")
            cols = st.columns(3)
            for i, name in enumerate(st.session_state["recent"]):
                cols[i % 3].button(f"🕘 {name}", key=f"recent_{i}", on_click=set_query, args=(name,), use_container_width=True)
        st.info("물건 이름을 치면 🟢🟡🔴 신호등으로 알려드려요.", icon="💡")
    else:
        results, mode = search(query)
        if not results:
            render_unknown(query)
        else:
            top = results[0]
            if mode == "fuzzy":
                st.caption(f"'{query}'와(과) 가장 비슷한 물건을 찾았어요. 혹시 이거 찾으셨나요?")
            recent = [r for r in st.session_state["recent"] if r != top["name"]]
            st.session_state["recent"] = ([top["name"]] + recent)[:6]
            render_result(top, now)
            if len(results) > 1:
                st.markdown("**비슷한 물건**")
                cols = st.columns(len(results) - 1)
                for col, it in zip(cols, results[1:]):
                    col.button(
                        f'{SIGNAL[it["color"]][0]} {it["name"]}', key=f'sim_{it["name"]}',
                        on_click=set_query, args=(it["name"],), use_container_width=True,
                    )
        st.button("← 처음으로", on_click=set_query, args=("",))
    footer()

# ── 화면 2: 우리 동네 ───────────────────────────────────────
with tab_area:
    st.markdown("### 우리 동네 배출 요일·시간·장소")
    st.selectbox("동네 고르기", [*AREAS, CUSTOM_AREA], key="area", on_change=on_area_change)
    st.caption("샘플 동네는 예시 값이에요. 우리 동네 실제 요일과 시간으로 고쳐 주세요.")
    for k in ("rec", "gen", "food"):
        with st.container(border=True):
            st.markdown(f"**{KIND_LABEL[k]}**")
            st.multiselect("배출 요일", WEEK, key=f"{k}_days")
            c1, c2 = st.columns(2)
            c1.time_input("시작", key=f"{k}_s", step=900)
            c2.time_input("종료", key=f"{k}_e", step=900)
            st.text_input("배출 장소", key=f"{k}_p", placeholder="예) 101동 앞 분리배출장")
            if st.session_state[f"{k}_e"] <= st.session_state[f"{k}_s"]:
                st.warning("종료 시간이 시작 시간보다 늦어야 해요. (자정을 넘기는 시간대는 아직 지원하지 않아요)")
    st.text_area("📝 동별 배출 장소 메모 (아파트용)", key="memo", placeholder="예) 102동은 지하 1층, 103동은 정문 옆", height=90)
    st.caption("입력한 내용은 이 접속(세션) 동안만 유지돼요. 새로고침하면 처음 값으로 돌아가요.")
    footer()

# ── 화면 3: QR ──────────────────────────────────────────────
with tab_qr:
    st.markdown("### 📲 QR로 앱 열기")
    st.write("가족이나 이웃이 QR을 스캔하면 이 앱이 바로 열려요. 냉장고나 분리배출함 옆에 붙여 두세요.")

    if "app_url" not in st.session_state:
        st.session_state["app_url"] = detect_app_url()
    st.text_input(
        "앱 주소", key="app_url", placeholder="https://내앱이름.streamlit.app",
        help="배포한 Streamlit 앱 주소를 넣으세요. 배포된 앱에서는 자동으로 채워져요.",
    )
    include_area = st.checkbox("선택한 샘플 동네도 함께 담기", value=False)

    base = st.session_state["app_url"].strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        st.warning("앱 주소를 https:// 로 시작하게 입력하면 QR이 만들어져요.")
    else:
        qr_url = base
        area = st.session_state["area"]
        if include_area and area in AREAS:
            qr_url = f"{base}/?{urlencode({'area': area})}"
        if base.startswith(("http://localhost", "http://127.0.0.1")):
            st.warning("지금 주소는 내 컴퓨터에서만 열려요. 배포한 주소로 바꾸면 다른 사람 폰에서도 열려요.")
        png = make_qr_png(qr_url)
        st.image(png, width=280, caption="📷 폰 카메라로 스캔하세요")
        st.code(qr_url, language=None)
        st.download_button("⬇️ QR 이미지 저장 (PNG)", data=png, file_name="how-to-dispose-qr.png", mime="image/png")

    with st.expander("GitHub + Streamlit Cloud로 배포하는 방법"):
        st.markdown(
            "1. GitHub 저장소를 만들고 `app.py`, `requirements.txt` 두 파일을 올려요.\n"
            "2. [share.streamlit.io](https://share.streamlit.io)에서 GitHub로 로그인하고 **Create app**을 눌러요.\n"
            "3. 저장소를 고르고 Main file path에 `app.py`를 입력한 뒤 Deploy 해요.\n"
            "4. 배포된 주소가 위 '앱 주소'에 자동으로 들어오면 QR을 저장해서 인쇄해요."
        )
    footer()
