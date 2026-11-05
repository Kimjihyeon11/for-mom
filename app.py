# -*- coding: utf-8 -*-
"""근무·당직 스케줄 관리 (Streamlit, 단일 화면 / 모바일 컴팩트)
- 데이터는 사용자 브라우저 localStorage 에만 저장 (외부 서버/DB 전송 없음)
- QR 은 앱 접속 URL 을 인코딩
"""
import calendar
import io
import json
from datetime import date, timedelta

import holidays
import pandas as pd
import qrcode
import streamlit as st
from streamlit_js_eval import streamlit_js_eval

st.set_page_config(page_title="당직 스케줄", page_icon="📅", layout="centered",
                   initial_sidebar_state="collapsed")

LS_KEY = "duty_app_v1"
COLORS = {"당직": "#ef4444", "휴가": "#22c55e", "출장": "#3b82f6",
          "교육": "#a855f7", "휴무": "#9ca3af"}
EVENT_TYPES = ["휴가", "출장", "교육"]
SLOT_MODES = {"단독": ["당직"], "주간·야간": ["주간", "야간"], "정·부": ["정", "부"]}
NIGHT_SLOTS = {"당직", "야간", "부"}  # 다음 날 휴무 대상
WD = ["일", "월", "화", "수", "목", "금", "토"]

DEFAULT = {
    "people": [], "events": [], "sched": {},
    "cfg": {"mode": "주간·야간", "max_month": 4, "min_gap": 1, "no_consec": True,
            "rest_after": True, "balance": True, "url": ""},
}

# ---------- 스타일 (한 화면에 들어오도록 컴팩트) ----------
st.markdown("""
<style>
.block-container{padding:.5rem .5rem .3rem !important;max-width:640px}
header[data-testid="stHeader"]{display:none}
div[data-testid="stVerticalBlock"]{gap:.35rem}
div[data-testid="stHorizontalBlock"]{flex-wrap:nowrap !important;gap:.3rem}
div[data-testid="column"],div[data-testid="stColumn"]{min-width:0 !important}
h1,h2,h3{padding:0 !important;margin:0 !important}
.stButton button,.stDownloadButton button,div[data-testid="stPopover"] button{
  padding:.15rem .3rem;min-height:1.9rem;font-size:.78rem;width:100%}
label,.stSelectbox,.stNumberInput{font-size:.75rem !important}
.cal{width:100%;border-collapse:collapse;table-layout:fixed;font-size:10px}
.cal th{background:#f3f4f6;padding:1px;font-size:10px}
.cal td{border:1px solid #e5e7eb;vertical-align:top;height:3.6rem;padding:1px;overflow:hidden}
.cal .d{font-weight:700;font-size:10px}
.cal .sun,.cal .hol{color:#dc2626}.cal .sat{color:#2563eb}
.cal .hn{font-size:8px;color:#dc2626;font-weight:400}
.cal .bg-off{background:#fef2f2}
.chip{display:block;color:#fff;border-radius:2px;margin-top:1px;padding:0 2px;
  font-size:8.5px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lg{font-size:10px;margin:0}.lg span{margin-right:6px}
</style>""", unsafe_allow_html=True)

# ---------- 브라우저 저장소 (localStorage) ----------
if "S" not in st.session_state:
    st.session_state.S = json.loads(json.dumps(DEFAULT))
    st.session_state.loaded = False
    st.session_state.last_saved = None
    st.session_state.save_n = 0

raw = streamlit_js_eval(js_expressions=f"localStorage.getItem('{LS_KEY}') || '{{}}'",
                        key="ls_get")
if raw is not None and not st.session_state.loaded:
    try:
        data = json.loads(raw)
        for k in ("people", "events", "sched"):
            if k in data:
                st.session_state.S[k] = data[k]
        st.session_state.S["cfg"].update(data.get("cfg", {}))
    except Exception:
        pass
    st.session_state.loaded = True
    st.session_state.last_saved = json.dumps(st.session_state.S, sort_keys=True)
    st.rerun()

S = st.session_state.S
cfg = S["cfg"]


def d2s(d):
    return d.isoformat()


def s2d(s):
    return date.fromisoformat(s)


# ---------- 공휴일 ----------
@st.cache_data
def kr_holidays(year):
    return dict(holidays.KR(years=[year - 1, year, year + 1], language="ko"))


def is_off(d):
    return d.weekday() >= 5 or d in kr_holidays(d.year)


# ---------- 일정/휴무 계산 ----------
def events_on(d):
    out = []
    for e in S["events"]:
        try:
            if s2d(e["s"]) <= d <= s2d(e["e"]):
                out.append(e)
        except Exception:
            pass
    return out


def rest_map(sched):
    """야간 당직 다음 날 자동 휴무: {date: set(names)}"""
    r = {}
    for ds, slots in sched.items():
        for slot, name in slots.items():
            if name and slot in NIGHT_SLOTS:
                r.setdefault(s2d(ds) + timedelta(days=1), set()).add(name)
    return r


# ---------- 당직표 자동 생성 ----------
def generate(year, month):
    people = S["people"]
    slots = SLOT_MODES[cfg["mode"]]
    n = len(people)
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    # 해당 월 기존 배정 삭제, 이전 기록은 유지
    S["sched"] = {k: v for k, v in S["sched"].items()
                  if not (first <= s2d(k) <= last)}
    last_duty, month_cnt, heavy_cnt = {}, {p: 0 for p in people}, {p: 0 for p in people}
    for ds in sorted(S["sched"]):
        for nm in S["sched"][ds].values():
            if nm:
                last_duty[nm] = s2d(ds)
    rests = rest_map(S["sched"]) if cfg["rest_after"] else {}
    gap = max(cfg["min_gap"], 1 if cfg["no_consec"] else 0)
    ptr, unfilled = 0, 0
    d = first
    while d <= last:
        used = set()
        for slot in slots:
            cands = []
            for i, p in enumerate(people):
                if p in used or month_cnt[p] >= cfg["max_month"]:
                    continue
                if any(e["p"] == p for e in events_on(d)):      # 휴가·출장·교육
                    continue
                if cfg["rest_after"] and p in rests.get(d, set()):
                    continue
                if p in last_duty and (d - last_duty[p]).days <= gap:
                    continue
                cands.append(((heavy_cnt[p] if cfg["balance"] and is_off(d) else 0),
                              month_cnt[p], (i - ptr) % n, i, p))
            if not cands:
                S["sched"].setdefault(d2s(d), {})[slot] = ""
                unfilled += 1
                continue
            _, _, _, i, p = min(cands)
            S["sched"].setdefault(d2s(d), {})[slot] = p
            used.add(p)
            month_cnt[p] += 1
            heavy_cnt[p] += 1 if is_off(d) else 0
            last_duty[p] = d
            ptr = (i + 1) % n
            if cfg["rest_after"] and slot in NIGHT_SLOTS:
                rests.setdefault(d + timedelta(days=1), set()).add(p)
        d += timedelta(days=1)
    return unfilled, month_cnt, heavy_cnt


# ---------- 달력 HTML ----------
def calendar_html(year, month):
    hol = kr_holidays(year)
    rests = rest_map(S["sched"])
    rows = ["<table class='cal'><tr>" + "".join(
        f"<th class='{'sun' if i == 0 else 'sat' if i == 6 else ''}'>{w}</th>"
        for i, w in enumerate(WD)) + "</tr>"]
    for week in calendar.Calendar(firstweekday=6).monthdayscalendar(year, month):
        tr = "<tr>"
        for i, dn in enumerate(week):
            if dn == 0:
                tr += "<td></td>"
                continue
            d = date(year, month, dn)
            cls = "hol" if d in hol else "sun" if i == 0 else "sat" if i == 6 else ""
            hn = f"<span class='hn'> {hol[d][:5]}</span>" if d in hol else ""
            bg = "bg-off" if is_off(d) else ""
            chips = ""
            for slot, nm in S["sched"].get(d2s(d), {}).items():
                lab = (slot[0] + " " if len(SLOT_MODES[cfg["mode"]]) > 1 else "")
                txt = f"{lab}{nm}" if nm else f"{lab}⚠미배정"
                chips += f"<span class='chip' style='background:{COLORS['당직'] if nm else '#f59e0b'}'>{txt}</span>"
            for e in events_on(d):
                chips += f"<span class='chip' style='background:{COLORS[e['t']]}'>{e['t'][0]} {e['p']}</span>"
            for nm in sorted(rests.get(d, [])):
                chips += f"<span class='chip' style='background:{COLORS['휴무']}'>휴 {nm}</span>"
            tr += f"<td class='{bg}'><div class='d {cls}'>{dn}{hn}</div>{chips}</td>"
        rows.append(tr + "</tr>")
    rows.append("</table>")
    return "".join(rows)


def month_rows(year, month):
    rests = rest_map(S["sched"])
    hol = kr_holidays(year)
    out = []
    for dn in range(1, calendar.monthrange(year, month)[1] + 1):
        d = date(year, month, dn)
        base = [d2s(d), WD[(d.weekday() + 1) % 7], hol.get(d, "주말" if d.weekday() >= 5 else "")]
        for slot, nm in S["sched"].get(d2s(d), {}).items():
            out.append(base + [f"당직({slot})", nm])
        for e in events_on(d):
            out.append(base + [e["t"], e["p"]])
        for nm in sorted(rests.get(d, [])):
            out.append(base + ["휴무(당직다음날)", nm])
    return pd.DataFrame(out, columns=["날짜", "요일", "공휴일/주말", "구분", "이름"])


# ================== UI ==================
today = date.today()
c1, c2, c3, c4 = st.columns([1.1, 1, 1, 1.3])
c1.markdown("##### 📅 당직표")
year = c2.selectbox("연", range(today.year - 2, today.year + 3), index=2,
                    label_visibility="collapsed")
month = c3.selectbox("월", range(1, 13), index=today.month - 1,
                     format_func=lambda m: f"{m}월", label_visibility="collapsed")
with c4.popover("📱 QR"):
    cfg["url"] = st.text_input("앱 접속 URL", cfg["url"],
                               placeholder="https://xxx.streamlit.app")
    if cfg["url"]:
        buf = io.BytesIO()
        qrcode.make(cfg["url"]).save(buf, format="PNG")
        st.image(buf.getvalue(), width=200, caption="스캔하면 앱으로 접속")
    else:
        st.caption("배포 후 받은 앱 주소를 입력하면 QR이 생성됩니다.")

st.markdown(calendar_html(year, month), unsafe_allow_html=True)
st.markdown("<p class='lg'>" + "".join(
    f"<span><b style='color:{c}'>■</b>{k}</span>" for k, c in COLORS.items()) +
    "<span><b style='color:#f59e0b'>■</b>미배정</span></p>", unsafe_allow_html=True)

b1, b2, b3, b4 = st.columns(4)

# 1) 인원·규칙
with b1.popover("👥 규칙"):
    txt = st.text_area("인원 (한 줄에 한 명, 순번 순서)", "\n".join(S["people"]), height=110)
    S["people"] = [x.strip() for x in txt.splitlines() if x.strip()]
    cfg["mode"] = st.selectbox("당직 구분", list(SLOT_MODES), list(SLOT_MODES).index(cfg["mode"]))
    a, b = st.columns(2)
    cfg["max_month"] = a.number_input("월 최대 횟수", 1, 31, int(cfg["max_month"]))
    cfg["min_gap"] = b.number_input("최소 간격(일)", 0, 14, int(cfg["min_gap"]),
                                    help="당직과 당직 사이에 비울 날 수")
    cfg["no_consec"] = st.checkbox("연속 당직 금지", cfg["no_consec"])
    cfg["rest_after"] = st.checkbox("야간 당직 다음 날 자동 휴무", cfg["rest_after"])
    cfg["balance"] = st.checkbox("주말·공휴일 당직 균등 배분", cfg["balance"])

# 2) 휴가·출장·교육 입력
with b2.popover("🗓️ 일정"):
    df = pd.DataFrame([{"이름": e["p"], "구분": e["t"], "시작": s2d(e["s"]), "종료": s2d(e["e"])}
                       for e in S["events"]],
                      columns=["이름", "구분", "시작", "종료"])
    ed = st.data_editor(
        df, num_rows="dynamic", hide_index=True, use_container_width=True, key="ev_editor",
        column_config={
            "이름": st.column_config.SelectboxColumn(options=S["people"] or [""]),
            "구분": st.column_config.SelectboxColumn(options=EVENT_TYPES),
            "시작": st.column_config.DateColumn(format="MM-DD"),
            "종료": st.column_config.DateColumn(format="MM-DD")})
    ev = []
    for _, r in ed.iterrows():
        if pd.notna(r["이름"]) and r["이름"] and pd.notna(r["구분"]) \
                and pd.notna(r["시작"]) and pd.notna(r["종료"]):
            ev.append({"p": r["이름"], "t": r["구분"],
                       "s": d2s(pd.to_datetime(r["시작"]).date()),
                       "e": d2s(pd.to_datetime(r["종료"]).date())})
    S["events"] = ev

# 3) 자동 생성
if b3.button("⚙️ 자동생성", type="primary"):
    if not S["people"]:
        st.toast("먼저 👥 규칙에서 인원을 입력하세요", icon="⚠️")
    else:
        miss, mc, hc = generate(year, month)
        st.toast(f"생성 완료 · 미배정 {miss}칸 | " +
                 ", ".join(f"{p} {mc[p]}회(휴일 {hc[p]})" for p in S["people"]), icon="✅")
        st.rerun()

# 4) 내보내기
with b4.popover("💾 저장"):
    mdf = month_rows(year, month)
    st.download_button("엑셀(CSV) 다운로드", mdf.to_csv(index=False).encode("utf-8-sig"),
                       f"duty_{year}-{month:02d}.csv", "text/csv")
    html = ("<html><head><meta charset='utf-8'><title>당직표</title><style>"
            "body{font-family:sans-serif}.cal{width:100%;border-collapse:collapse;table-layout:fixed;font-size:12px}"
            ".cal td,.cal th{border:1px solid #999;height:80px;vertical-align:top}.cal th{height:auto;background:#eee}"
            ".chip{display:block;color:#000;border:1px solid #666;margin:1px;padding:0 2px}.sun,.hol{color:red}.sat{color:blue}"
            "</style></head><body><h2>" + str(year) + "년 " + str(month) + "월 당직표</h2>"
            + calendar_html(year, month)
            + "<script>window.onload=()=>window.print()</script></body></html>")
    st.download_button("인쇄용 화면(HTML)", html.encode("utf-8"),
                       f"duty_{year}-{month:02d}.html", "text/html")
    if st.button("이 달 배정 초기화"):
        S["sched"] = {k: v for k, v in S["sched"].items()
                      if not (s2d(k).year == year and s2d(k).month == month)}
        st.rerun()

# ---------- 변경 시 브라우저에 저장 (서버 DB/외부 전송 없음) ----------
if st.session_state.loaded:
    cur = json.dumps(S, sort_keys=True)
    if cur != st.session_state.last_saved:
        st.session_state.last_saved = cur
        st.session_state.save_n += 1
        payload = json.dumps(json.dumps(S, ensure_ascii=False))
        streamlit_js_eval(js_expressions=f"localStorage.setItem('{LS_KEY}', {payload})",
                          key=f"ls_set_{st.session_state.save_n}")
