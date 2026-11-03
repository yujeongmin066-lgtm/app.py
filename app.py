import csv
import io
import json
import uuid
from datetime import datetime

import qrcode
import streamlit as st

st.set_page_config(page_title="장보기 알림메모", page_icon="🛒", layout="centered")

CATEGORIES = ["야채", "과일", "육류·달걀", "생선·해산물", "유제품", "쌀·곡류", "가공식품", "생활용품", "기타"]
PRIORITIES = {1: "🔴 1 · 꼭 사야 해요", 2: "🟡 2 · 필요해요", 3: "🟢 3 · 여유가 있으면"}

st.markdown("""<style>
.block-container {max-width:720px;padding-top:1.4rem;padding-bottom:3rem;}
.stButton button,.stFormSubmitButton button,.stDownloadButton button {min-height:48px;border-radius:13px;}
[data-testid="stMetric"] {background:#eff8f2;padding:14px;border-radius:14px;}
input {font-size:16px!important;}
</style>""", unsafe_allow_html=True)

if "shopping_items" not in st.session_state:
    st.session_state.shopping_items = []
if "budget" not in st.session_state:
    st.session_state.budget = 0
if "pending_budget" in st.session_state:
    st.session_state.budget = st.session_state.pop("pending_budget")


def items():
    return st.session_state.shopping_items


def money(value):
    return f"{value:,}원"


def total_price():
    return sum(x["unit_price"] * x["quantity"] for x in items() if x["in_cart"])


def rerun():
    st.rerun()


def export_data():
    return json.dumps({"version": 1, "budget": st.session_state.budget,
                       "items": items()}, ensure_ascii=False, indent=2)


def validate_backup(data):
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("지원하지 않는 백업 형식입니다.")
    source = data.get("items")
    if not isinstance(source, list) or len(source) > 5000:
        raise ValueError("목록 형식이 잘못되었거나 5,000개를 초과합니다.")
    cleaned = []
    for x in source:
        if not isinstance(x, dict):
            raise ValueError("항목 형식이 올바르지 않습니다.")
        name = x.get("name")
        category = x.get("category")
        priority = x.get("priority")
        price = x.get("unit_price")
        quantity = x.get("quantity")
        note = x.get("note", "")
        in_cart = x.get("in_cart")
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise ValueError("상품 이름을 확인해 주세요.")
        if category not in CATEGORIES or type(priority) is not int or priority not in PRIORITIES:
            raise ValueError("카테고리 또는 중요도가 올바르지 않습니다.")
        if type(price) is not int or not 0 <= price <= 100_000_000:
            raise ValueError("개당 가격이 올바르지 않습니다.")
        if type(quantity) is not int or not 1 <= quantity <= 9999:
            raise ValueError("수량이 올바르지 않습니다.")
        if type(in_cart) is not bool or not isinstance(note, str) or len(note) > 200:
            raise ValueError("메모 또는 카트 정보가 올바르지 않습니다.")
        cleaned.append({"id": uuid.uuid4().hex, "name": name.strip(), "category": category,
                        "priority": priority, "unit_price": price, "quantity": quantity,
                        "note": note, "in_cart": in_cart})
    budget = data.get("budget", 0)
    if type(budget) is not int or not 0 <= budget <= 1_000_000_000:
        raise ValueError("예산이 올바르지 않습니다.")
    return cleaned, budget


@st.dialog("🛒 카트에 담기 · 가격/수량 수정")
def cart_dialog(item_id):
    item = next((x for x in items() if x["id"] == item_id), None)
    if item is None:
        st.warning("해당 항목을 찾을 수 없습니다.")
        return
    st.subheader(item["name"])
    st.caption("개당 실제 구매 가격과 수량을 입력하세요. 금액은 원 단위입니다.")
    with st.form("cart_entry"):
        price = st.number_input("개당 가격(원)", min_value=0, max_value=100_000_000,
                                value=item["unit_price"], step=100)
        quantity = st.number_input("수량(개/팩)", min_value=1, max_value=9999,
                                   value=item["quantity"], step=1)
        st.caption("저장하면 개당 가격 × 수량으로 카트 합계에 반영됩니다. 무료 상품은 0원으로 입력하세요.")
        if st.form_submit_button("가격·수량 저장하고 담기", use_container_width=True):
            item.update(unit_price=int(price), quantity=int(quantity), in_cart=True)
            rerun()


st.title("🛒 장보기 알림메모")
st.caption("꼭 필요한 것부터 챙기고, 카트 금액은 바로 확인하세요.")

pending = [x for x in items() if not x["in_cart"]]
cart = [x for x in items() if x["in_cart"]]
important = sum(x["priority"] == 1 for x in pending)
a, b = st.columns(2)
a.metric("현재 카트 합계", money(total_price()))
b.metric("꼭 사야 할 물건", f"{important}개")
if st.session_state.budget:
    remaining = st.session_state.budget - total_price()
    if remaining < 0:
        st.error(f"예산보다 {money(-remaining)} 초과했어요.")
    else:
        st.caption(f"남은 예산 {money(remaining)} / 전체 예산 {money(st.session_state.budget)}")

shopping_tab, cart_tab, settings_tab = st.tabs(["📝 살 물건", "🛒 카트", "⚙️ 저장·QR"])

with shopping_tab:
    with st.expander("＋ 살 물건 추가", expanded=not bool(items())):
        with st.form("add_item", clear_on_submit=True):
            name = st.text_input("상품 이름", max_chars=80, placeholder="예: 당근, 사과, 우유")
            category = st.selectbox("카테고리", CATEGORIES)
            priority = st.radio("중요도 (1이 가장 중요)", [1, 2, 3], format_func=lambda x: PRIORITIES[x], horizontal=True)
            planned_quantity = st.number_input("예정 수량", min_value=1, max_value=9999, value=1, step=1)
            note = st.text_input("메모 (선택)", max_chars=200, placeholder="예: 작은 팩, 알레르기 성분 확인")
            if st.form_submit_button("목록에 추가", use_container_width=True):
                if not name.strip():
                    st.error("상품 이름을 입력해 주세요.")
                elif len(items()) >= 5000:
                    st.error("최대 5,000개까지 저장할 수 있습니다.")
                else:
                    items().append({"id": uuid.uuid4().hex, "name": name.strip(), "category": category,
                                    "priority": priority, "quantity": int(planned_quantity),
                                    "unit_price": 0, "note": note.strip(), "in_cart": False})
                    rerun()
    selected_category = st.selectbox("카테고리 보기", ["전체"] + CATEGORIES)
    only_important = st.toggle("🔴 중요도 1만 보기", value=False)
    search = st.text_input("물건 찾기", placeholder="이름이나 메모 검색")
    visible = sorted([x for x in pending
                      if (selected_category == "전체" or x["category"] == selected_category)
                      and (not only_important or x["priority"] == 1)
                      and (not search or search.casefold() in (x["name"] + " " + x["note"]).casefold())],
                     key=lambda x: x["priority"])
    st.caption(f"남은 물건 {len(pending)}개 · 표시 {len(visible)}개 · 중요도 순")
    if not visible:
        st.info("표시할 물건이 없어요. 물건을 추가하거나 필터를 바꿔 주세요.")
    # Large lists are paged so phones need not render thousands of controls at once.
    page_count = max(1, (len(visible) + 19) // 20)
    page = st.selectbox("목록 페이지 (20개씩)", range(1, page_count + 1)) if page_count > 1 else 1
    for item in visible[(page - 1) * 20:page * 20]:
        with st.container(border=True):
            st.markdown(f"**{PRIORITIES[item['priority']]}**")
            st.write(item["name"])
            st.caption(f"{item['category']} · 예정 {item['quantity']}개/팩")
            if item["note"]:
                st.write(item["note"])
            if st.button("🛒 가격·수량 입력하고 담기", key=f"put_{item['id']}", use_container_width=True):
                cart_dialog(item["id"])
            with st.expander("중요도 수정 / 항목 삭제"):
                new_priority = st.selectbox("중요도", [1, 2, 3], index=item["priority"] - 1,
                                           format_func=lambda x: PRIORITIES[x], key=f"priority_{item['id']}")
                if new_priority != item["priority"]:
                    item["priority"] = new_priority
                    rerun()
                if st.button("목록에서 삭제", key=f"delete_{item['id']}"):
                    st.session_state.shopping_items = [x for x in items() if x["id"] != item["id"]]
                    rerun()

with cart_tab:
    st.subheader(f"카트에 담은 물건 {len(cart)}종")
    st.caption("담은 물건은 살 물건 목록에서 빠지지만 구매 기록과 합계에는 남습니다.")
    st.metric("총 예상 결제금액", money(total_price()))
    if not cart:
        st.info("아직 카트에 담은 물건이 없어요.")
    for item in cart:
        with st.container(border=True):
            st.write(item["name"])
            st.caption(f"{item['category']} · {money(item['unit_price'])} × {item['quantity']}개/팩")
            st.markdown(f"**소계 {money(item['unit_price'] * item['quantity'])}**")
            if st.button("가격·수량 수정", key=f"edit_{item['id']}", use_container_width=True):
                cart_dialog(item["id"])
            if st.button("↩ 카트에서 빼고 살 목록으로", key=f"undo_{item['id']}", use_container_width=True):
                item["in_cart"] = False
                rerun()
    if cart:
        out = io.StringIO(newline="")
        writer = csv.writer(out)
        writer.writerow(["상품", "카테고리", "중요도", "개당가격(원)", "수량", "소계(원)"])
        for item in cart:
            # Prevent spreadsheet formula execution in user-provided names.
            safe_name = "'" + item["name"] if item["name"].startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else item["name"]
            writer.writerow([safe_name, item["category"], item["priority"], item["unit_price"],
                             item["quantity"], item["unit_price"] * item["quantity"]])
        writer.writerow(["합계", "", "", "", "", total_price()])
        st.download_button("📥 구매 내역 CSV 다운로드", out.getvalue().encode("utf-8-sig"),
                           "shopping_receipt.csv", "text/csv", use_container_width=True)

with settings_tab:
    st.subheader("예산 설정")
    st.number_input("전체 예산(원) · 0이면 사용 안 함", min_value=0, max_value=1_000_000_000,
                    step=1000, key="budget")
    st.subheader("메모 백업·복원")
    st.warning("목록은 현재 접속 세션에 보관됩니다. 새로고침·접속 종료·서버 재시작 시 사라질 수 있으니 백업 파일을 내려받으세요. QR은 앱 주소만 공유하며 개인 목록을 전달하지 않습니다.")
    st.download_button("💾 전체 메모 백업 다운로드", export_data().encode("utf-8"),
                       f"shopping_backup_{datetime.now():%Y%m%d_%H%M}.json", "application/json",
                       use_container_width=True)
    uploaded = st.file_uploader("백업 JSON 불러오기 (기존 목록을 대체)", type=["json"])
    overwrite = st.checkbox("복원하면 현재 목록과 예산이 대체되는 것을 확인했습니다.")
    if st.button("백업 복원", disabled=uploaded is None or not overwrite, use_container_width=True):
        try:
            if uploaded.size > 5_000_000:
                raise ValueError("백업 파일은 5MB 이하여야 합니다.")
            restored, budget = validate_backup(json.loads(uploaded.getvalue().decode("utf-8-sig")))
            st.session_state.shopping_items = restored
            st.session_state.pending_budget = budget
            rerun()
        except (ValueError, UnicodeError, TypeError, KeyError) as exc:
            st.error(f"복원하지 못했습니다: {exc}")
    st.subheader("📱 QR로 앱 열기")
    st.caption("배포 후 브라우저 주소창의 https://…streamlit.app 주소를 붙여 넣으세요. 스마트폰 기본 카메라로 QR을 스캔하면 앱이 열립니다.")
    app_url = st.text_input("배포된 앱 주소", placeholder="https://your-shopping-app.streamlit.app")
    if app_url:
        from urllib.parse import urlparse
        parsed = urlparse(app_url.strip())
        if parsed.scheme == "https" and parsed.hostname and len(app_url) <= 2000:
            buffer = io.BytesIO()
            qrcode.make(app_url.strip()).save(buffer, format="PNG")
            st.image(buffer.getvalue(), width=230)
            st.download_button("QR 이미지 다운로드", buffer.getvalue(), "shopping_app_qr.png", "image/png")
        else:
            st.info("올바른 https:// 앱 주소를 입력해 주세요.")
    with st.expander("GitHub → Streamlit 배포 안내"):
        st.markdown("""1. GitHub 저장소를 만들고 **app.py**와 **requirements.txt**를 같은 최상위 폴더에 올립니다.
2. Streamlit Community Cloud에 GitHub 계정으로 로그인합니다.
3. 새 앱 만들기에서 저장소와 브랜치를 선택하고 실행 파일 경로에 **app.py**를 지정합니다.
4. 배포가 끝나면 발급된 HTTPS 주소를 위에 입력해 QR을 만듭니다.
5. QR을 스마트폰 카메라로 스캔합니다. 앱 설치 없이 브라우저에서 사용할 수 있습니다.

로컬 실행: `pip install -r requirements.txt` 다음 `streamlit run app.py`

**주의:** GitHub는 코드를 보관하고 실제 앱 실행은 Streamlit이 담당합니다. GitHub Pages에서는 Python 앱을 직접 실행할 수 없습니다. 이 앱은 로그인·기기 간 동기화·백그라운드 푸시 알림을 제공하지 않습니다. 중요 물건은 앱을 열었을 때 강조됩니다. 여러 접속자의 목록은 세션별로 분리됩니다.""")
    with st.expander("전체 초기화"):
        confirm_reset = st.checkbox("백업을 확인했으며 모든 항목을 삭제합니다.")
        if st.button("전체 목록·예산 초기화", disabled=not confirm_reset, use_container_width=True):
            st.session_state.shopping_items = []
            st.session_state.pending_budget = 0
            rerun()
