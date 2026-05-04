import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
from PIL import Image
from datetime import datetime
import json
import os
import re
import io
import base64

# ==========================================
# 1. 사용자 계정 및 API 설정
# ==========================================
USER_REGISTRY = {
    "C12": {"pw": "241130", "db": "diet_db.json"},
}

MY_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=MY_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(db_path):
    try:
        # 시트에서 데이터 읽기 (ttl=0은 캐시 없이 실시간으로 가져온다는 뜻)
        df = conn.read(ttl="0s")
        return df.to_dict(orient="records")
    except:
        return []

def save_data(db_path, data_list):
    # 만약 데이터가 비어있다면 (리스트가 [] 인 경우)
    if not data_list:
        # 빈 데이터프레임을 만들되, 컬럼명(항목 이름)은 유지해주는 게 좋습니다.
        # 기존 시트의 헤더 컬럼 이름들을 적어주세요.
        df = pd.DataFrame(columns=["id", "date", "food", "grade", "full_text", "thumb"])
    else:
        # 데이터가 있으면 정상적으로 변환
        df = pd.DataFrame(data_list)
    
    # 구글 시트 업데이트
    conn.update(data=df)


def make_thumbnail(image):
    img = image.copy()
    img.thumbnail((200, 200))
    buffered = io.BytesIO()
    img.convert("RGB").save(buffered, format="JPEG", quality=60)
    return base64.b64encode(buffered.getvalue()).decode()


# ==========================================
# 2. 아이콘 및 6단계 색상 총평 로직
# ==========================================
def get_grade_detail(raw_grade):
    g = raw_grade.upper().strip()
    specs = {
        "S": {"icon": "💎", "bg": "#E1F5FE", "border": "#0288D1", "score": 5.0, "color": "#0288D1"},
        "A+": {"icon": "🔵", "bg": "#E3F2FD", "border": "#1565C0", "score": 4.5, "color": "#1565C0"},
        "A": {"icon": "🔵", "bg": "#E3F2FD", "border": "#1976D2", "score": 4.0, "color": "#1976D2"},
        "B+": {"icon": "🟢", "bg": "#E8F5E9", "border": "#2E7D32", "score": 3.5, "color": "#2E7D32"},
        "B": {"icon": "🟢", "bg": "#E8F5E9", "border": "#388E3C", "score": 3.0, "color": "#388E3C"},
        "C+": {"icon": "🟠", "bg": "#FFF3E0", "border": "#EF6C00", "score": 2.5, "color": "#EF6C00"},
        "C": {"icon": "🟠", "bg": "#FFF3E0", "border": "#FB8C00", "score": 2.0, "color": "#FB8C00"},
        "D+": {"icon": "🔴", "bg": "#FFEBEE", "border": "#C62828", "score": 1.5, "color": "#C62828"},
        "D": {"icon": "🔴", "bg": "#FFEBEE", "border": "#E53935", "score": 1.0, "color": "#E53935"},
        "F": {"icon": "⚫", "bg": "#F5F5F5", "border": "#212121", "score": 0.0, "color": "#212121"}
    }
    return specs.get(g, specs["C"])


def get_monthly_analysis(items):
    if not items: return None
    total_score = sum(get_grade_detail(item['grade'])['score'] for _, item in items)
    avg_score = round(total_score / len(items), 2)

    if avg_score >= 4.5:
        color, msg = "#0288D1", "💎 다이아몬드급 식단! 완벽한 자기관리입니다."
    elif avg_score >= 3.8:
        color, msg = "#1565C0", "🔵 우수한 식습관입니다. 아주 건강해요!"
    elif avg_score >= 3.3:
        color, msg = "#2E7D32", "🟢 건강 전선 이상 무! 초록빛 안정권입니다."
    elif avg_score >= 2.8:
        color, msg = "#FBC02D", "🟡 안정적이지만 조금 더 개선할 수 있어요."
    elif avg_score >= 1.8:
        color, msg = "#EF6C00", "🟠 주황색 경고등! 영양소 균형에 신경 써주세요."
    else:
        color, msg = "#C62828", "🔴 관리가 필요한 붉은색 구간입니다. 힘내세요!"

    return {"avg": avg_score, "color": color, "count": len(items), "msg": msg}


# ==========================================
# 3. 로그인 및 환경 설정
# ==========================================
st.set_page_config(page_title="다정한 영양 분석사", page_icon="🥗", layout="centered")

if 'auth' not in st.session_state:
    st.session_state['auth'] = None

if not st.session_state['auth']:
    st.title("🥗 C12의 식단 기록 사이트")
    with st.form("login_form"):
        login_id = st.text_input("아이디(ID)")
        login_pw = st.text_input("비밀번호(PW)", type="password")
        if st.form_submit_button("AI 분석하러 가기", use_container_width=True):
            if login_id in USER_REGISTRY and USER_REGISTRY[login_id]["pw"] == login_pw:
                st.session_state['auth'] = {"id": login_id, "db": USER_REGISTRY[login_id]["db"]}
                st.balloons()
                st.rerun()
            else:
                st.error("정보를 다시 확인해 주세요! 🧐")
    st.stop()

with st.sidebar:
    st.success(f"👤 **{st.session_state['auth']['id']}**님 접속 중")
    if st.button("로그아웃"):
        st.session_state['auth'] = None
        st.rerun()

CURRENT_DB = st.session_state['auth']['db']

# ==========================================
# 4. 분석 기능 (수정 사항 반영)
# ==========================================
st.title("🍱 오늘의 식단 기록하기")
img_file = st.file_uploader("", type=['png', 'jpg', 'jpeg'])

if img_file:
    raw_img = Image.open(img_file)
    st.image(raw_img, use_container_width=True)

    # [수정] 4명 이상 옵션에 코멘트 안내 문구 추가
    meal_info = st.radio("🍴 식사 인원을 선택해 주세요", ["1명", "2명", "3명", "4명 이상 (식사 코멘트 작성해주세요)"], horizontal=True)

    # [수정] 식사 코멘트 이름 유지 및 예시(Placeholder) 변경
    memo = st.text_input("📝 식사 코멘트", placeholder="예시: 5명이서 먹었어요 / 소중한 사람들과 따뜻하고 맛있는 한 끼였어요!")

    if st.button("분석 시작하기 ✨", use_container_width=True):
        try:
            with st.spinner("식단 분석 중..."):
                prompt = f"""너는 세상에서 가장 다정한 영양사야. 아래 1~5양식 무조건 지켜줘 '*' 출력 금지!! 이모티콘 1~2개씩 넣어줘, 건강에 나쁘면 냉철하게 점수 줘, 인원:{meal_info}, 코멘트:{memo}
                ###
                1. 메뉴 이름: (총 글자 20자로 제한해줘, 이모티콘 금지)
                
                2. 식단 점수: (점수는 S, A+, A, B+, B, C+, C, D+, D, F 중 무조건 선택 다른 점수 없음, 이모티콘 금지)
                
                3. 예상 칼로리: (1인당 예상 칼로리로 써줘) 
                
                4. 영양 성분 평가 및 조언: 
                
                5. 다정한 한마디: 
                ###"""
                response = model.generate_content([prompt, raw_img])
                result_text = response.text

                name_match = re.search(r"1\.\s*메뉴\s*이름\s*:(.*?)(?=2\.)", result_text, re.DOTALL)
                food_name = name_match.group(1).strip() if name_match else "오늘의 식단"
                grade_match = re.search(r"점수\s*:\s*([S|A-F][\+]?)", result_text)
                grade = grade_match.group(1).strip() if grade_match else "C"

                data = load_data(CURRENT_DB)
                data.append({
                    "id": datetime.now().timestamp(),
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "grade": grade,
                    "food": food_name[:30],
                    "full_text": result_text,
                    "thumb": make_thumbnail(raw_img)
                })
                save_data(CURRENT_DB, data)
                st.markdown(result_text)
        except Exception as e:
            st.error(f"오류가 발생했어요: {e}")

# ==========================================
# 5. 다이어리
# ==========================================
st.divider()
history = load_data(CURRENT_DB)
if history:
    monthly_data = {}
    for i, item in enumerate(history):
        month_key = datetime.strptime(item['date'], "%Y-%m-%d %H:%M").strftime("%Y년 %m월")
        if month_key not in monthly_data: monthly_data[month_key] = []
        monthly_data[month_key].append((i, item))

    for month in sorted(monthly_data.keys(), reverse=True):
        with st.expander(f"📅 {month} 총평 및 기록", expanded=False):
            analysis = get_monthly_analysis(monthly_data[month])
            #if analysis:
            #    st.markdown(f"""
            #    <div style="background-color:#F8FAFC; padding:20px; border-radius:15px; border-left: 10px solid {analysis['color']};">
            #        <h2 style="margin:5px 0; color:{analysis['color']};">평균 {analysis['avg']} <small>/ 5.0</small></h2>
            #        <p style="margin:5px 0; font-weight:bold; color:#1E293B;">{analysis['msg']}</p>
            #        <p style="margin:0; font-size:0.85em; color:#94A3B8;">총 {analysis['count']}회의 식사를 기록했습니다.</p>
            #    </div>
            #    """, unsafe_allow_html=True)
            #    st.write("")

            for i, item in sorted(monthly_data[month], key=lambda x: x[1]['date'], reverse=True):
                spec = get_grade_detail(item['grade'])
                with st.expander(f"{spec['icon']} {item['date']} | {item['food']} ({item['grade']})"):
                    if "thumb" in item:
                        st.markdown(
                            f'<img src="data:image/jpeg;base64,{item["thumb"]}" style="width: 100%; border-radius: 12px; margin-bottom:10px;">',
                            unsafe_allow_html=True)
                    st.markdown(f"""<div style="border-left: 5px solid {spec['border']}; background-color: {spec['bg']}; padding: 15px; color: #333;">
                                    {item['full_text'].replace(chr(10), '<br>')}</div>""", unsafe_allow_html=True)
                    if st.button("🗑️ 삭제", key=f"del_{i}"):
                        data = load_data(CURRENT_DB)
                        data.pop(i)
                        save_data(CURRENT_DB, data)
                        st.rerun()
