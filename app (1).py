"""장보기 알림메모
실행: streamlit run app.py
GitHub 저장소에 app.py와 requirements.txt를 올린 뒤 Streamlit Community Cloud에서 배포.
배포된 https 주소를 QR 코드로 공유하면 됩니다. QR 이미지 자체는 접속 인증 수단이 아닙니다.
개인 기록은 서버가 아닌 접속한 브라우저의 localStorage에 저장됩니다.
"""
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="장보기 알림메모", page_icon="🛒", layout="centered", initial_sidebar_state="collapsed")
st.markdown("""<style>
[data-testid="stHeader"], [data-testid="stToolbar"], footer {display:none!important}
.stMainBlockContainer {padding:8px!important;max-width:600px!important}
[data-testid="stAppViewContainer"] {overflow:hidden!important}
iframe {height:calc(100dvh - 24px)!important;border:0!important}
</style>""", unsafe_allow_html=True)

HTML = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f7f4;color:#183c32;font:14px system-ui,-apple-system,'Apple SD Gothic Neo',sans-serif;height:100dvh;overflow:hidden}button,input,select{font:inherit}button,input,select{min-height:38px;border:1px solid #cbd7cf;border-radius:10px;padding:7px;background:white;color:#183c32;min-width:0}button{cursor:pointer;font-weight:650}button:active{transform:translateY(1px)}button:focus-visible,input:focus,select:focus{outline:2px solid #157452;outline-offset:1px}.primary{background:#146649;color:white;border-color:#146649}.muted{color:#52675f;font-size:12px}#app{height:100%;display:flex;flex-direction:column;gap:8px;padding:8px 7px max(8px,env(safe-area-inset-bottom));max-width:570px;margin:auto}header{display:flex;justify-content:space-between;align-items:center}h1{margin:0;font-size:21px;letter-spacing:-1px}header span{font-size:11px}.panel{background:white;border:1px solid #dce5de;border-radius:15px;padding:10px}.row{display:flex;gap:6px;align-items:center}.row>*{min-width:0}.grow{flex:1}#addForm{display:grid;grid-template-columns:1fr 1.6fr;gap:6px}#addForm .wide{grid-column:1/-1}label{display:flex;flex-direction:column;gap:3px;font-size:11px}#addForm button{align-self:end}.tabs{display:flex;gap:6px}.tabs button{flex:1}.tabs .on{background:#e0efe6;border-color:#146649}#list{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;display:flex;flex-direction:column;gap:7px;padding:1px 0}article{padding:9px;background:#fff;border:1px solid #dce5de;border-radius:12px;display:flex;gap:8px;align-items:center}article .title{font-size:14px;font-weight:700;overflow-wrap:anywhere}article .meta{font-size:11px;color:#53685e;margin-top:3px}article button{font-size:12px;min-height:34px;padding:6px 8px}.badge{font-size:11px;color:#146649}.empty{text-align:center;padding:24px 8px;color:#66796f}.total{display:flex;justify-content:space-between;align-items:center;background:#163f31;color:#fff;padding:12px;border-radius:14px}.total strong{font-size:24px}.total small{color:#d2e7dc}#status{font-size:11px;min-height:15px;color:#476257;overflow-wrap:anywhere}dialog{border:0;border-radius:16px;padding:16px;width:calc(100% - 24px);max-width:390px;max-height:90dvh;overflow:auto;box-shadow:0 15px 70px #1235}dialog::backdrop{background:#09251988}dialog h2{font-size:18px;margin:0 0 10px;overflow-wrap:anywhere}dialog label{font-size:13px;margin:9px 0}dialog p{font-size:13px;line-height:1.5}.danger{color:#a22e29}#hint{color:#94601b;font-size:12px;min-height:18px}.small{font-size:11px} @media(max-height:600px){#app{gap:4px;padding-top:3px}.panel{padding:6px}h1{font-size:18px}input,select,button{min-height:33px;padding:5px}.total{padding:7px}.total strong{font-size:21px}}
</style></head><body><main id="app">
<header><h1>🛒 장보기 알림메모</h1><span>가볍게 담고, 합계는 바로</span></header>
<section class="panel"><form id="addForm">
<label>카테고리<select id="category" aria-label="카테고리"><option>야채</option><option>과일</option><option>육류·생선</option><option>유제품·계란</option><option>쌀·곡물</option><option>가공·냉동</option><option>음료·간식</option><option>생활용품</option><option>기타</option></select></label>
<label>상세 상품명<input id="name" placeholder="예: 무농약 당근 500g" maxlength="80" required autocomplete="off"></label>
<label class="wide">중요도<select id="priority"><option value="1">1 · 꼭 필요</option><option value="2" selected>2 · 보통</option><option value="3">3 · 저렴하면</option></select></label>
<button class="primary wide" type="submit">＋ 장보기 메모 추가</button>
</form></section>
<nav class="tabs" aria-label="목록 필터"><button id="pendingTab" class="on">메모 0</button><button id="cartTab">카트 0</button></nav>
<div class="row"><span class="muted grow" id="caption">중요도 순 · 비싸면 보류하세요</span><button id="tools" class="small" type="button">관리</button></div>
<section id="list" aria-label="상품 목록"></section>
<section class="total" aria-live="polite"><div>현재 카트 총액<br><small id="count">0종 · 0개</small></div><strong id="total">0원</strong></section>
<div id="status" role="status" aria-live="polite">이 브라우저에 자동 저장 · 목록 안에서만 스크롤</div>
</main>
<dialog id="buyDialog"><form id="buyForm"><h2 id="buyName"></h2><div class="muted" id="buyInfo"></div><label>실제 구매 단가 (원)<input id="price" type="number" min="0" max="999999999" step="1" inputmode="numeric" required></label><label>수량 (개·팩·묶음 수)<input id="qty" type="number" min="1" max="99999" step="1" inputmode="numeric" value="1" required></label><div id="hint" aria-live="polite"></div><p>입력 금액은 <b>단가 × 수량</b>으로 합산합니다.<br>묶음 할인은 묶음 단가와 묶음 수를 입력하세요.</p><div class="row"><button type="button" id="cancelBuy">취소</button><button type="button" id="deferBuy">비싸서 보류</button><button type="submit" class="primary grow">카트에 담기</button></div></form></dialog>
<dialog id="manageDialog"><h2>기록 관리</h2><p>같은 기기·같은 브라우저에 자동 저장됩니다. 다른 사람과 실시간 공유되지 않으며, 시크릿 모드나 브라우저 데이터 삭제 시 기록이 사라질 수 있습니다.</p><div class="row"><button id="export">백업 저장</button><button id="import">백업 복원</button></div><p><button id="clear" class="danger">전체 기록 초기화</button></p><button id="closeManage" class="primary">닫기</button><input id="file" type="file" accept="application/json,.json" hidden></dialog>
<script>
'use strict';
const $=id=>document.getElementById(id), KEY='shopping-memo-v1';
const categories=Array.from($('category').options).map(o=>o.value);
let items=[],view='pending',active=null,storageOK=true;
const money=n=>n.toLocaleString('ko-KR')+'원';
const integer=(n,min,max)=>Number.isSafeInteger(n)&&n>=min&&n<=max;
function valid(x){return x && typeof x.id==='string'&&x.id.length<=100&&typeof x.name==='string'&&x.name.length>0&&x.name.length<=80&&categories.includes(x.category)&&[1,2,3].includes(x.priority)&&['pending','cart'].includes(x.state)&&typeof x.deferred==='boolean'&&(x.limit===null||integer(x.limit,0,999999999))&&(x.state!=='cart'||(integer(x.price,0,999999999)&&integer(x.qty,1,99999)));}
function validated(data){if(!Array.isArray(data)||data.length>2000||!data.every(valid)||new Set(data.map(x=>x.id)).size!==data.length)throw Error('형식');return data;}
try{items=validated(JSON.parse(localStorage.getItem(KEY)||'[]'));}catch(e){storageOK=false;$('status').textContent='저장 기록을 읽지 못했습니다. 관리에서 백업을 복원하세요.';}
function save(message){try{localStorage.setItem(KEY,JSON.stringify(items));storageOK=true;$('status').textContent=message+' · 이 브라우저에 저장됨';}catch(e){storageOK=false;$('status').textContent='저장 불가: 관리에서 백업을 저장하세요. 새로고침하면 사라질 수 있습니다.';}render();}
function button(text,action){const b=document.createElement('button');b.type='button';b.textContent=text;b.onclick=action;return b;}
function render(){
const cart=items.filter(x=>x.state==='cart'),pending=items.filter(x=>x.state==='pending');
$('total').textContent=money(cart.reduce((s,x)=>s+x.price*x.qty,0));$('count').textContent=cart.length+'종 · '+cart.reduce((s,x)=>s+x.qty,0)+'개';
$('pendingTab').textContent='메모 '+pending.length;$('cartTab').textContent='카트 '+cart.length;
$('pendingTab').classList.toggle('on',view==='pending');$('cartTab').classList.toggle('on',view==='cart');
$('caption').textContent=view==='pending'?'1 꼭 필요 · 2 보통 · 3 저렴하면':'실제 단가 × 수량 · 되돌리면 합계에서 제외';
const list=$('list');list.replaceChildren();
const visible=(view==='pending'?pending:cart).slice().sort((a,b)=>Number(a.deferred)-Number(b.deferred)||a.priority-b.priority);
if(!visible.length){const d=document.createElement('div');d.className='empty';d.textContent=view==='pending'?'상품명을 적고 메모를 추가해 주세요.':'담은 상품이 없습니다. 메모에서 담기를 눌러 주세요.';list.append(d);}
visible.forEach(x=>{const a=document.createElement('article'),text=document.createElement('div');text.className='grow';const title=document.createElement('div');title.className='title';title.textContent=x.name;const meta=document.createElement('div');meta.className='meta';meta.textContent=x.category+' · 중요도 '+x.priority+(x.deferred?' · 보류 중':'');text.append(title,meta);a.append(text);
if(x.state==='pending'){a.append(button(x.deferred?'다시 담기':'담기',()=>openBuy(x)),button(x.deferred?'보류 해제':'보류',()=>{x.deferred=!x.deferred;save('보류 상태 변경');}));a.append(button('삭제',()=>{if(confirm('이 메모를 삭제할까요?')){items=items.filter(i=>i.id!==x.id);save('메모 삭제');}}));}
else{const cost=document.createElement('div');cost.className='meta';cost.textContent=money(x.price)+' × '+x.qty+' = '+money(x.price*x.qty);text.append(cost);a.append(button('수정',()=>openBuy(x)),button('되돌리기',()=>{x.state='pending';x.deferred=false;delete x.price;delete x.qty;save('메모로 되돌림');}));}list.append(a);});}
$('addForm').onsubmit=e=>{e.preventDefault();const name=$('name').value.trim();if(!name)return; if(items.length>=2000){alert('기록은 최대 2,000개입니다. 기존 기록을 정리해 주세요.');return;}const limit=null;items.push({id:Date.now().toString(36)+'-'+Math.random().toString(36).slice(2),name,category:$('category').value,priority:Number($('priority').value),limit,state:'pending',deferred:false});$('name').value='';view='pending';save('메모 추가');$('name').blur();};
function openBuy(x){active=x.id;$('buyName').textContent=x.name;$('buyInfo').textContent='중요도 '+x.priority;$('price').value=x.state==='cart'?x.price:'';$('qty').value=x.state==='cart'?x.qty:1;$('deferBuy').hidden=x.state==='cart';hint();$('buyDialog').showModal();}
function hint(){const x=items.find(i=>i.id===active);if(!x)return;const price=Number($('price').value),qty=Number($('qty').value);$('hint').textContent=$('price').value===''?'':('예상 금액 '+money(price*qty));}
$('price').oninput=hint;$('qty').oninput=hint;
$('buyForm').onsubmit=e=>{e.preventDefault();const x=items.find(i=>i.id===active),price=Number($('price').value),qty=Number($('qty').value);if(!x||!integer(price,0,999999999)||!integer(qty,1,99999))return;Object.assign(x,{price,qty,state:'cart',deferred:false});$('buyDialog').close();save('카트 반영');};
$('deferBuy').onclick=()=>{const x=items.find(i=>i.id===active);if(x){x.deferred=true;save('비싸서 보류');}$('buyDialog').close();};$('cancelBuy').onclick=()=>$('buyDialog').close();
$('pendingTab').onclick=()=>{view='pending';render();};$('cartTab').onclick=()=>{view='cart';render();};
$('tools').onclick=()=>$('manageDialog').showModal();$('closeManage').onclick=()=>$('manageDialog').close();
$('clear').onclick=()=>{if(confirm('메모와 카트 기록을 모두 삭제할까요? 복구할 수 없습니다.')){items=[];save('전체 초기화');$('manageDialog').close();}};
$('export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(items,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='shopping-backup.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
$('import').onclick=()=>$('file').click();$('file').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{if(f.size>2000000)throw Error('파일 크기');const data=validated(JSON.parse(await f.text()));if(confirm('현재 기록을 백업 내용 '+data.length+'건으로 교체할까요?')){items=data;save('백업 복원');$('manageDialog').close();}}catch(err){alert('유효한 장보기 백업 파일이 아닙니다.');}e.target.value='';};
render();
</script></body></html>'''
components.html(HTML, height=700, scrolling=False)
