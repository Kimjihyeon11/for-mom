# -*- coding: utf-8 -*-
"""
♻️ 분리배출 — 이거 어떻게 버려요? (Streamlit · QR 접속형)

화면은 딱 3개 (표지 포함):
  1) 표지      : 큰 글씨 '분리배출' — 글자를 누르면 다음 화면으로
  2) 판독      : 물건 이름 → 🟢🟡🔴⚪ 신호등 + "지금 내놔도 돼요?"
  3) 동네·QR   : 우리 동네 배출 일정 설정 + 앱 접속용 QR 만들기

※ 물건 데이터는 서울시 표준 기준 등 공개 자료를 정리한 것이고 지역마다 다를 수 있어요.
   동네 배출 요일 샘플은 예시입니다. 실제 서비스 전에 공공데이터 API로 교체·검수하세요.
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
DATA_NOTE = "서울시 표준 배출 기준(2025-08-06 수정)·환경부 요령 등 공개 자료 정리 · 지역마다 다를 수 있어요"

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
def _i(name, alias, color, kind, headline, steps, badges=(), drop=None):
    return {"name": name, "alias": [x.strip() for x in alias.split(",") if x.strip()], "color": color, "kind": kind,
            "headline": headline, "steps": list(steps), "badges": list(badges), "drop": drop}


# 근거: 서울시 표준 배출 기준(2025-08-06 수정)·환경부 분리수거 요령·정책브리핑·부산 북구/광진구 품목 안내.
# 지자체마다 다를 수 있어요. 헷갈리는 품목 위주로 구성했어요.
ITEMS = [
    # ── 철·금속 ──
    _i("프라이팬·냄비", "프라이팬,후라이팬,냄비,팬,솥,주전자,철제냄비,스텐냄비", "yellow", "재활용", "씻어서 고철류로 내놓으세요",
       ["음식물과 기름때를 씻어요", "손잡이처럼 분리되는 다른 소재는 따로 빼요", "유리 뚜껑은 고철이 아니라 종량제(또는 불연성 봉투)예요"], ["🔩 고철류"]),
    _i("스테인리스 텀블러", "텀블러,보온병,스텐컵,스텐텀블러,수저,숟가락,젓가락(금속)", "yellow", "재활용", "비우고 씻어서 고철류로 내놓으세요",
       ["깨끗이 씻어요", "플라스틱 뚜껑·실리콘처럼 다른 소재는 분리해요", "분리가 안 되면 종량제로 가요"], ["🔩 고철류"]),
    _i("공구(드라이버·망치)", "공구,드라이버,망치,펜치,렌치,스패너,쇠", "yellow", "재활용", "씻어서 고철류로 내놓으세요",
       ["이물질을 씻어요", "고철류로 내놓아요"], ["🔩 고철류"]),
    _i("못·나사·철사", "못,나사,철사,녹슨 철,고철,쇠붙이,볼트,너트", "gray", "확인", "지역마다 달라요. 고철 또는 특수마대예요",
       ["고철로 받는 지역이 있고(부산 북구 안내)", "녹슨 못·철사는 특수마대로 보는 지역도 있어요(광진구 안내)", "다치지 않게 감싸서 내놓고, 동네 기준을 확인하세요"], [],
       "우리 동네가 고철로 받는지 구청에 먼저 확인하세요."),
    _i("알루미늄 호일", "호일,은박지,알루미늄호일,은박", "red", "일반", "캔이 아니에요. 종량제로 버리세요",
       ["알루미늄이지만 캔류가 아니에요", "음식물이 묻은 채로 종량제 봉투에 넣어요"]),
    _i("음료 캔", "캔,캔음료,깡통,맥주캔,콜라캔,통조림,참치캔", "yellow", "재활용", "비우고 헹궈서 찌그러뜨려 내놓으세요",
       ["내용물을 비우고 헹궈요", "담배꽁초 같은 이물질은 넣지 않아요", "플라스틱 뚜껑은 빼요"]),
    _i("부탄가스·스프레이", "부탄가스,스프레이,살충제,에어졸,가스통,가스용기", "yellow", "재활용", "가스를 완전히 빼고 캔류로 내놓으세요",
       ["바람이 잘 통하는 곳에서 노즐을 눌러 내용물을 완전히 빼요", "내용물을 뺀 뒤 캔류로 내놓아요"], ["⚠️ 폭발 주의"]),
    _i("페인트·락카통", "페인트,락카,래커,페인트통,락카스프레이", "red", "불연성", "내용물이 남았으면 특수규격마대예요",
       ["내용물이 남은 락카·페인트통은 폭발·화재 위험이 있어요", "특수규격마대 등 지자체 기준으로 배출해요"], ["⚠️ 폭발 주의"]),
    # ── 유리·도자기 ──
    _i("유리병", "소주병,맥주병,병,유리,음료수병,와인병,잼병", "yellow", "재활용", "비우고 헹궈서 내놓으세요",
       ["내용물을 비우고 헹궈요", "담배꽁초 같은 이물질은 넣지 않아요", "소주·맥주병은 보증금 환급이 되니 소매점에 반납하세요"]),
    _i("깨진 유리", "깨진유리,유리조각,깨진 컵,깨진 병,유리파편", "red", "일반", "신문지로 싸서 버리세요 (많으면 특수마대)",
       ["다치지 않게 신문지 등으로 단단히 싸요", "소량은 종량제 봉투에 넣어요", "많은 양은 특수규격마대를 써요"]),
    _i("도자기·그릇", "도자기,사기그릇,그릇,접시,머그컵,컵,찻잔,사기,깨진 그릇,화분", "red", "불연성", "특수규격마대 또는 대형폐기물이에요",
       ["도자기·사기류는 유리병 재활용이 안 돼요", "깨진 조각은 싸서 특수규격마대에 넣어요", "큰 것은 대형폐기물 기준을 확인해요"]),
    _i("내열유리·크리스탈", "내열유리,내열 유리,크리스탈,유리컵,판유리,유리판,유리뚜껑,전구,백열전구", "red", "불연성", "일반 유리병이 아니에요. 특수마대예요",
       ["내열·크리스탈·코팅 유리, 판유리, 조명용 유리는 병 재활용이 안 돼요", "특수규격마대 또는 대형폐기물로 내놓아요", "백열전구는 불연성 폐기물로 보는 지역이 있어요"]),
    _i("거울", "거울,깨진 거울,손거울,전신거울", "red", "불연성", "특수규격마대로 버리세요",
       ["깨진 거울은 싸서 특수규격마대에 넣어요", "큰 거울은 대형폐기물 기준을 확인해요"]),
    # ── 옷·천 ──
    _i("깨끗한 헌옷·신발", "옷,헌옷,의류,청바지,티셔츠,외투,패딩,신발,운동화,헌신발,목도리,가방,모자", "yellow", "별도", "의류 수거함에 젖지 않게 넣으세요",
       ["깨끗하고 마른 상태로 담아요", "묶거나 봉투에 담아 의류 수거함에 넣어요", "젖었거나 심하게 더러우면 종량제예요"], ["👕 의류 수거함"],
       "동네 폐의류 수거함 위치는 구청·주민센터에 확인하세요."),
    _i("못 입는 옷·헌가방·베개", "헌가방,낡은 옷,베개,걸레,양말,속옷,젖은 옷,더러운 옷", "red", "일반", "재활용이 안 되는 옷은 종량제예요",
       ["심하게 낡거나 더러워 재활용이 안 되는 옷·신발·가방은 종량제예요", "베개도 종량제예요"]),
    _i("솜이불·쿠션", "솜이불,이불,쿠션,인형,토퍼,담요,침구", "red", "대형", "솜이불·쿠션은 대형폐기물이에요",
       ["솜이 든 이불·쿠션은 대형폐기물 신고 대상이에요", "구청·주민센터나 온라인으로 신고하고 수수료 스티커를 붙여요", "방석처럼 작은 것은 종량제인 지역도 있어요"], ["📄 신고·수수료"]),
    # ── 종이 ──
    _i("택배상자(골판지)", "택배박스,종이박스,박스,상자,골판지,택배상자", "yellow", "재활용", "테이프 떼고 납작하게 펴서 내놓으세요",
       ["테이프·철핀을 떼요", "납작하게 접어요", "송장은 개인정보라 떼거나 가려서 버려요", "안쪽에 비닐·알루미늄이 붙은 보냉 상자는 종량제예요"]),
    _i("보냉 택배상자", "보냉박스,아이스박스,보냉상자,신선식품 박스,보냉팩", "red", "일반", "안쪽에 비닐·알루미늄이 있으면 종량제예요",
       ["종이와 분리되지 않는 보냉 상자는 종량제예요", "스티로폼 상자가 깨끗하면 스티로폼으로 내놓아요"]),
    _i("종이컵", "종이컵,일회용컵,커피컵,컵", "yellow", "재활용", "비우고 헹궈서 눌러 내놓으세요",
       ["내용물을 비우고 헹궈요", "눌러서 봉투에 모으거나 묶어요", "양면이 코팅된 종이컵은 종량제예요"]),
    _i("영수증·택배 전표", "영수증,감열지,전표,택배전표,송장,계산서,택배 송장", "red", "일반", "종이처럼 보여도 종량제예요",
       ["코팅된 감열지라 종이류 재활용이 안 돼요", "개인정보가 있으면 찢어서 버려요"]),
    _i("사진·종이호일·휴지", "사진,사진용지,종이호일,기름종이,휴지,화장지,사용한 휴지,색지,키친타월,물티슈", "red", "일반", "종이 같아도 종량제예요",
       ["사진용지·종이호일·색지·사용한 휴지는 재활용이 안 돼요", "종량제 봉투에 넣어요"]),
    _i("우유팩", "종이팩,두유팩,주스팩,소주팩,멸균팩", "yellow", "재활용", "헹궈서 말려 종이팩으로 내놓으세요",
       ["내용물을 비우고 헹궈요", "빨대·비닐 같은 다른 재질은 떼요", "종이팩 수거함에 넣어요(없으면 묶어서 종이류로)"]),
    _i("신문지·책·전단지", "신문지,신문,종이신문,전단지,책,노트,공책,A4용지,잡지", "green", "재활용", "물에 젖지 않게 묶어서 내놓으세요",
       ["비닐 코팅·스프링·비닐 포장은 떼요", "젖지 않게 펴서 묶거나 상자에 담아요"]),
    # ── 플라스틱·비닐·스티로폼 ──
    _i("투명 페트병", "페트병,패트병,생수병,물병,음료수병,pet", "yellow", "재활용", "비우고 라벨 떼서 찌그러뜨려 내놓으세요",
       ["내용물을 비우고 헹궈요", "라벨을 떼요", "찌그러뜨린 뒤 뚜껑을 닫아 내놓아요"]),
    _i("플라스틱 용기", "플라스틱,배달용기,배달 그릇,일회용기,포장용기,요거트병,샴푸통,세제통,화장품 용기,펌프", "yellow", "재활용", "비우고 헹궈서 라벨 떼고 내놓으세요",
       ["내용물을 비우고 헹궈요", "라벨 같은 다른 재질은 떼요", "펌핑용기의 철제 스프링 펌프는 빼요", "치약처럼 헹굴 수 없는 용기는 비워서 내놓아요"]),
    _i("칫솔·옷걸이·CD", "칫솔,치솔,옷걸이,플라스틱 옷걸이,CD,DVD,파일철,알약 포장,문구,볼펜", "red", "일반", "플라스틱이어도 종량제예요",
       ["칫솔·혼합재질 옷걸이·CD/DVD·파일철·알약 포장재는 재활용이 안 돼요", "종량제 봉투에 넣어요"]),
    _i("장난감", "장난감,완구,레고,블록,인형,미니카", "red", "일반", "혼합 재질 장난감은 종량제예요",
       ["플라스틱 외 다른 재질이 붙은 완구는 종량제예요", "건전지가 들어 있으면 일체로 초소형 전자제품 배출함에 넣어요"], [],
       "배터리 내장 장난감은 초소형 전자제품 배출함을 이용하세요."),
    _i("과자봉지·비닐", "비닐,과자봉지,비닐봉지,커피봉지,양파망,뽁뽁이,완충재,택배봉투,비닐팩", "yellow", "재활용", "털어서 투명 봉투에 모아 비닐로 내놓으세요",
       ["이물질은 털어내고 헹궈요(조금 묻어도 괜찮아요)", "플라스틱과 섞지 말고 투명 봉투에 모아 내놓아요", "택배봉투는 송장이 안 떼어져도 돼요"]),
    _i("랩·고무장갑", "랩,랩필름,고무장갑,고무호스,호스,식탁보,현수막,노끈,끈,마스크,라이터", "red", "일반", "비닐 같아도 종량제예요",
       ["랩·식탁보·고무장갑·고무호스·현수막·노끈은 비닐 재활용이 안 돼요", "마스크도 종량제예요", "라이터는 내용물을 비운 뒤 종량제예요"]),
    _i("스티로폼 상자", "스티로폼,스티로폼 상자,완충재,생선상자,과일상자", "yellow", "재활용", "깨끗한 것만 라벨 떼고 내놓으세요",
       ["이물질을 씻고 라벨·테이프를 떼요", "전자제품 완충재는 가능하면 구입처에 돌려줘요", "음식물이 묻었거나 다른 재질이 붙은 것은 종량제예요"]),
    _i("스티로폼 접시·과일망", "스티로폼 접시,정육 트레이,과일망,과일 그물,스티로폼 포장,일회용 트레이", "red", "일반", "음식물 묻은 스티로폼·과일망은 종량제예요",
       ["음식물이 묻었거나 이물질을 못 떼면 종량제예요", "과일 포장 그물망(과일망)도 종량제예요", "건축용 단열 스티로폼은 대형폐기물이에요"]),
    # ── 전지·전자·약 ──
    _i("건전지", "배터리,폐건전지,AA건전지,알카라인,리튬전지,단추전지,전지", "red", "별도", "일반쓰레기에 넣지 말고 전지 수거함에 넣으세요",
       ["아파트·주민센터의 건전지 수거함에 넣어요", "수거함이 없으면 주민센터에 문의해요"], ["🔌 별도 수거"],
       "배출 요일이 없어요. 건전지 수거함이나 정해진 전지류 배출일을 이용하세요."),
    _i("보조배터리", "보조배터리,충전식배터리,2차전지,충전지,폐배터리,리튬이온", "red", "별도", "캔류에 섞지 말고 전지류로 내놓으세요",
       ["금속이어도 캔류에 섞지 않아요", "전지류 수거함으로 배출해요", "부풀거나 불이 날 수 있으니 따로 조심해서 보관해요"], ["🔌 별도 수거", "⚠️ 화재 주의"],
       "전지류 수거함을 이용하세요. 부풀었다면 주민센터에 먼저 문의하세요."),
    _i("형광등", "폐형광등,형광램프,형광등관,LED조명,LED,조명,전등", "red", "별도", "깨뜨리지 말고 형광등 수거함에 넣으세요",
       ["깨지지 않게 조심해서 옮겨요", "형광등 전용 수거함에 넣어요", "깨진 형광등·LED조명은 소량 종량제, 많으면 특수마대예요"], ["🔌 별도 수거"],
       "형광등 수거함 위치는 주민센터나 아파트 관리실에 확인하세요."),
    _i("소형가전", "소형가전,헤어드라이어,드라이기,다리미,노트북,믹서기,청소기,선풍기,밥솥,전기밥솥,에어프라이어,프린터,키보드,휴대폰,핸드폰,마우스", "red", "별도", "소형가전은 가전 수거로 내놓으세요",
       ["일반쓰레기에 넣지 않아요", "동주민센터 방문 배출이 가능한 지역이 있어요", "5개 이상 모으면 무상 방문수거 서비스(1599-0903)를 쓸 수 있어요"], ["🔌 폐가전"],
       "동주민센터 수거함이나 무상 방문수거 서비스를 이용하세요."),
    _i("냉장고·세탁기·TV", "냉장고,세탁기,에어컨,TV,텔레비전,대형가전,김치냉장고,전자레인지", "red", "대형", "대형 가전은 무상 방문수거를 예약하세요",
       ["폐가전 무상 방문수거(1599-0903)를 예약해요", "에어컨·벽걸이 TV 같은 설치 제품은 철거 후 수거해요"], ["🔌 폐가전"]),
    _i("폐의약품", "약,알약,물약,폐의약품,감기약,연고,유통기한 지난 약,시럽", "red", "별도", "약국·보건소 수거함에 넣으세요",
       ["싱크대나 변기에 버리지 않아요", "약국·보건소·주민센터의 폐의약품 수거함에 넣어요", "알약 포장재(PTP)는 종량제예요"], ["💊 전용 수거함"],
       "가까운 약국이나 보건소 수거함을 이용하세요."),
    # ── 대형·기타 ──
    _i("우산", "우산,장우산,양산,접이식우산", "red", "대형", "서울 기준 대형폐기물이에요. 지역을 확인하세요",
       ["서울시 표준은 대형폐기물이에요", "구마다 우산을 분해해 고철·종량제로 나누게 하는 곳도 있어요", "동네 기준을 확인하세요"], ["📄 신고·수수료"]),
    _i("소파·가구", "소파,쇼파,쇼파베드,가구,장롱,책상,의자,침대,매트리스,서랍장,식탁,대형가구", "red", "대형", "대형폐기물이에요. 신고하고 스티커를 붙이세요",
       ["구청·주민센터 또는 온라인으로 배출 신고를 해요", "수수료를 내고 스티커를 받아요", "신고한 날짜에 지정 장소에 내놓아요"], ["📄 신고·수수료"]),
    _i("유모차·캐리어·낚싯대", "유모차,보행기,캐리어,여행가방,트렁크,골프가방,낚싯대,아기욕조", "red", "대형", "큰 플라스틱 제품은 대형폐기물이에요",
       ["유모차·보행기·여행용 트렁크·골프가방·낚싯대는 대형폐기물이에요", "신고 후 스티커를 붙여 내놓아요"], ["📄 신고·수수료"]),
    _i("장판·돗자리·텐트", "장판,돗자리,천막,텐트,러그,카펫,매트,요가매트", "red", "대형", "대형폐기물이에요",
       ["장판·돗자리·천막은 대형폐기물이에요", "신고 후 스티커를 붙여 내놓아요"], ["📄 신고·수수료"]),
    _i("고양이 모래·흙", "고양이모래,고양이 배변,배변모래,흙,화분 흙,모래", "red", "불연성", "특수규격마대로 버리세요(광진구 안내)",
       ["흙·고양이 배변 모래는 특수마대로 안내하는 구가 있어요", "종량제로 받는 지역도 있으니 동네 기준을 확인하세요"]),
    _i("면도칼·가위", "면도칼,면도기,칼날,커터칼,칼", "red", "일반", "다치지 않게 감싸서 종량제로 버리세요",
       ["날이 보이지 않게 두껍게 감싸요", "종량제 봉투에 넣고 겉에 표시해요"]),
    # ── 음식물 ──
    _i("과일·채소 껍질", "바나나껍질,과일껍질,채소,상한음식,남은 음식,잔반,밥,반찬,국,음식물쓰레기,음식물,남은 밥,커피찌꺼기", "yellow", "음식물", "물기 빼서 음식물 전용 용기에 버리세요",
       ["물기를 꼭 짜요", "비닐·이쑤시개·뼈는 빼요", "음식물 전용 용기에 넣어요"], ["🍚 음식물"]),
    _i("뼈다귀(닭·생선·고기)", "치킨뼈,닭뼈,뼈다귀,갈비뼈,생선뼈,족발뼈,뼈,치킨 뼈,돼지뼈", "red", "일반", "음식물이 아니라 종량제예요",
       ["딱딱한 뼈는 음식물 쓰레기가 아니에요", "종량제 봉투에 넣어요"]),
    _i("껍데기·씨앗", "달걀껍질,계란껍질,달걀 껍데기,조개껍데기,어패류,굴껍데기,복숭아씨,호두,밤껍질,과일씨,양파껍질,파뿌리,뿌리,티백,복어내장,옥수수껍질", "red", "일반", "음식물 같아도 종량제예요",
       ["달걀·메추리알 껍질, 조개 등 어패류 껍데기는 종량제예요", "복숭아·호두 같은 딱딱한 껍데기와 씨, 양파 껍질, 채소 뿌리도 종량제예요", "티백, 복어 내장도 종량제예요"]),
    # ── 추가: 생활 속 헷갈리는 것들 ──
    _i("가발·걸레·골프공", "가발,걸레,골프공,야구공,공,마우스패드,양초,초,촛농,수세미,스펀지", "red", "일반", "재활용이 안 돼요. 종량제로 버리세요",
       ["가발·걸레·골프공·야구공·마우스패드·양초는 종량제예요(부산 북구 안내)", "종량제 봉투에 넣어요"]),
    _i("방석", "방석,의자 방석,좌식 방석", "red", "일반", "방석은 종량제예요(지역에 따라 대형)",
       ["부산 북구 안내는 종량제예요", "솜이 많은 큰 쿠션류는 대형폐기물인 곳도 있어요", "동네 기준을 확인하세요"]),
    _i("랩·휴지 심", "랩심,랩 심,랩의 심,호일심,키친타월심", "green", "재활용", "속 심지는 종이류로 내놓으세요",
       ["랩 자체는 종량제지만 안의 종이 심은 종이류예요", "납작하게 펴서 종이류에 넣어요"]),
    _i("볼풀공", "볼풀공,볼풀,플라스틱 공", "yellow", "재활용", "플라스틱으로 내놓으세요(부산 북구 안내)",
       ["깨끗이 털어서 플라스틱류로 내놓아요", "동네 기준을 확인하세요"]),
    _i("실리콘·머리빗·욕실화", "실리콘,실리콘 주걱,주걱,머리빗,빗,욕실화,욕실 슬리퍼,욕실신발,고무밴드", "red", "일반", "재활용이 안 돼요. 종량제예요",
       ["실리콘 주방도구·머리빗·욕실 신발은 종량제예요(광진구 안내)", "종량제 봉투에 넣어요"]),
    _i("남은 화장품 용기", "화장품,화장품 용기 남은 것,크림통,립스틱,파운데이션,매니큐어", "red", "일반", "내용물이 남아 분리 어려우면 종량제예요",
       ["내용물이 남아 있고 분리가 어려우면 종량제예요(광진구 안내)", "내용물을 비워 씻을 수 있으면 플라스틱·유리로 내놓아요"]),
    _i("파쇄지", "파쇄지,세단기,세단 종이,갈아버린 종이,종이 파쇄", "red", "일반", "잘게 파쇄한 종이는 종량제예요",
       ["파쇄지는 종이류 재활용이 안 돼요(광진구 안내)", "종량제 봉투에 넣어요"]),
    _i("벽돌·타일·깨진 화분", "벽돌,타일,깨진 화분,시멘트,콘크리트,석고,돌", "red", "불연성", "특수규격마대로 버리세요",
       ["벽돌·타일·깨진 화분은 불연성이라 특수마대예요(광진구 안내)", "많으면 공사 폐기물 기준을 구청에 확인해요"]),
    _i("단열재·소량 목재", "단열재,목재,나무,나무 조각,합판,각목,벽지,벽지 조각,장판 조각", "red", "불연성", "소량은 특수규격마대예요",
       ["단열재·소량의 목재·벽지·장판 조각은 특수마대예요(광진구 안내)", "건축용 단열 스티로폼과 많은 양은 대형폐기물이에요"]),
    _i("멀티탭·콘센트", "멀티탭,콘센트,전선,연장선,전기선", "red", "불연성", "소량은 특수규격마대예요(광진구 안내)",
       ["멀티탭은 소량이면 특수마대예요", "동네 기준을 확인하세요"]),
    _i("가죽 제품", "가죽,가죽 지갑,가죽신발,가죽 소파,인조가죽,레자", "red", "불연성", "가죽은 특수규격마대예요(광진구 안내)",
       ["가죽 제품은 특수마대로 안내하는 구가 있어요", "큰 가죽 가구는 대형폐기물 기준을 확인해요"]),
    _i("공기청정기 필터", "공기청정기 필터,필터,헤파필터,정수기 필터,에어컨 필터", "red", "불연성", "특수규격마대예요(광진구 안내)",
       ["공기청정기 필터는 특수마대로 안내하는 구가 있어요", "동네 기준을 확인하세요"]),
    _i("욕실의자·폼롤러", "욕실의자,폼롤러,플라스틱 의자,큰 플라스틱,어린이 의자,빨래건조대", "red", "대형", "부피 큰 플라스틱은 대형폐기물이에요",
       ["아기욕조·욕실의자·폼롤러처럼 부피 큰 플라스틱은 대형폐기물이에요(광진구 안내)", "신고 후 스티커를 붙여 내놓아요"], ["📄 신고·수수료"]),
    _i("먹다 남은 생선·상한 음식", "먹다남은 생선,상한음식,상한 음식,썩은 음식,유통기한 지난 음식,생선살,김치", "yellow", "음식물", "물기 빼서 음식물로 버리세요",
       ["살코기·상한 음식은 음식물이에요(부산 북구 안내)", "생선 뼈는 종량제예요"], ["🍚 음식물"]),
]
ITEM_BY_NAME = {it["name"]: it for it in ITEMS}
QUICK_CHIPS = ["프라이팬·냄비", "영수증·택배 전표", "깨끗한 헌옷·신발", "우산", "깨진 유리", "종이컵", "보조배터리", "칫솔·옷걸이·CD", "껍데기·씨앗", "스티로폼 접시·과일망", "폐의약품", "소형가전"]

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
KIND_PLAIN = {"rec": "재활용", "gen": "일반쓰레기", "food": "음식물"}
KIND_LABEL = {"rec": "♻️ 재활용", "gen": "🗑️ 일반(종량제)", "food": "🍚 음식물"}

PAGES = {"cover": "🏠 표지", "area": "🏘️ 우리 동네 배출일정", "find": "🔍 물건 검색"}  # 화면은 딱 3개


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
        return "warn", "우리 동네 배출 요일이 아직 비어 있어요. '우리 동네 배출일정' 화면에서 입력해 주세요."
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
    root = "19px"
    zoom = "1.35" if big else "1"  # '글자 더 크게'를 켜면 화면 전체가 1.35배로 커져요
    title_fs = "min(16.9vw,115px)" if big else "min(19vw,112px)"
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
.block-container{{max-width:620px;padding:1.2rem 1.1rem 3rem 1.1rem;zoom:{zoom};}}
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
.cover-pre{{text-align:center;color:#2e9e4f;font-weight:800;font-size:1.3rem;margin-top:20vh;letter-spacing:.01em;}}
.st-key-start,.st-key-start [data-testid="stButton"],.st-key-start [data-testid="stElementContainer"]{{display:flex;justify-content:center;align-items:center;width:100%;text-align:center;}}
.stApp .st-key-start button{{background:transparent !important;border:none !important;box-shadow:none !important;padding:.2rem .4rem !important;min-height:0 !important;width:auto !important;}}
.stApp .st-key-start button p{{font-size:{title_fs} !important;font-weight:900 !important;color:#14532d !important;letter-spacing:-.04em !important;line-height:1.15 !important;white-space:nowrap !important;}}
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


DEFAULT_DROP = {
    "대형": "신고한 배출일에만 내놓을 수 있어요. 신고 없이 내놓으면 과태료 대상일 수 있어요.",
    "불연성": "특수규격마대(불연성 봉투)에 담아 내놓아요. 이름과 판매처는 지역마다 달라요.",
    "별도": "배출 요일이 따로 없어요. 전용 수거함을 이용하세요.",
    "확인": "구청 청소 담당 부서나 주민센터에 확인하세요.",
}


def render_drop(item: dict, now: datetime) -> None:
    kind = item["kind"]
    if kind in KIND_KEY:
        k = KIND_KEY[kind]
        status, msg = drop_status(k, now)
        title = f"🕗 지금 내놔도 돼요? · {KIND_LABEL[k]}"
    else:
        status, title = "info", "🕗 지금 내놔도 돼요?"
        msg = item.get("drop") or DEFAULT_DROP.get(kind, "동네 기준을 확인하세요.")
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
    st.button("분리배출", key="start", on_click=go, args=("area",))  # 글자 자체가 버튼
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
    st.markdown('<div class="page-title">우리 동네 배출 일정</div>', unsafe_allow_html=True)
    st.button("🔍 이거 어떻게 버려요? 물건 검색하기", key="to_find", on_click=go, args=("find",), use_container_width=True)

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
            with st.expander(f"📅 {KIND_PLAIN[k]} 날짜 선택하기"):  # 라벨을 고정해야 수정 중에 접히지 않아요
                st.multiselect("날짜(요일) 선택하기", WEEK, key=f"{k}_days")
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
