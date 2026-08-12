import streamlit as st
import sqlite3
import time
from google import genai
from google.genai import types
from datetime import datetime
import plotly.graph_objects as go
from gtts import gTTS
import io
import re
import base64

# --- 1. SETUP & CONFIG ---
st.set_page_config(page_title="AI Thai Nutritionist Pro", page_icon="🥗", layout="wide")

# ⚠️ ใส่ API Key จาก Google AI Studio ของคุณที่นี่
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

MODEL_NAME = 'gemini-2.5-flash'

# --- Custom CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Kanit', sans-serif;
        background-color: #FAFAF8;
        color: #2D3748;
    }
    
    .stApp {
        background-color: #FAFAF8;
    }

    .header-card {
        background: linear-gradient(135deg, #4E6E58 0%, #3A5342 100%);
        color: white;
        padding: 20px 24px;
        border-radius: 20px;
        box-shadow: 0 8px 20px rgba(78, 110, 88, 0.15);
        margin-bottom: 20px;
    }
    .header-card h2 {
        color: white !important;
        font-weight: 600;
        margin: 0;
    }

    .stButton>button[kind="primary"] {
        background-color: #4E6E58 !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 10px 20px !important;
        font-weight: 500 !important;
        box-shadow: 0 4px 12px rgba(78, 110, 88, 0.2) !important;
        transition: all 0.2s ease !important;
    }
    .stButton>button[kind="primary"]:hover {
        background-color: #3A5342 !important;
        transform: translateY(-1px);
    }

    .stButton>button[kind="secondary"] {
        background-color: #FFFFFF !important;
        color: #4E6E58 !important;
        border: 1px solid #D1E0D5 !important;
        border-radius: 12px !important;
        font-weight: 500 !important;
    }
    
    .card-container {
        background-color: #FFFFFF;
        border-radius: 18px;
        padding: 20px;
        border: 1px solid #EAEFEA;
        box-shadow: 0 4px 15px rgba(0,0,0,0.02);
        margin-bottom: 15px;
    }

    .ai-summary-box {
        background-color: #FFFFFF;
        border-radius: 18px;
        padding: 24px;
        border: 1px solid #EAEFEA;
        border-left: 6px solid #4E6E58;
        box-shadow: 0 4px 15px rgba(0,0,0,0.03);
        margin-top: 15px;
        line-height: 1.6;
    }
    
    div[data-testid="stHorizontalBlock"] .stButton>button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)


# --- 2. DATABASE FUNCTIONS ---
def get_db_connection():
    conn = sqlite3.connect("health_app_v4.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                 (email TEXT PRIMARY KEY, nickname TEXT, gender TEXT, birth_year INTEGER, 
                  weight REAL, height REAL, bmi REAL, goals TEXT, diseases TEXT, allergies TEXT,
                  blood_sugar REAL, blood_pressure TEXT)''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS favorites 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_email TEXT, nickname TEXT, gender TEXT, birth_year INTEGER, 
                  weight REAL, height REAL, bmi REAL, goals TEXT, diseases TEXT, allergies TEXT, photo BLOB,
                  blood_sugar REAL, blood_pressure TEXT)''')
    
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'blood_sugar' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN blood_sugar REAL")
    if 'blood_pressure' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN blood_pressure TEXT")
        
    cursor.execute("PRAGMA table_info(favorites)")
    fav_columns = [column[1] for column in cursor.fetchall()]
    if 'blood_sugar' not in fav_columns:
        cursor.execute("ALTER TABLE favorites ADD COLUMN blood_sugar REAL")
    if 'blood_pressure' not in fav_columns:
        cursor.execute("ALTER TABLE favorites ADD COLUMN blood_pressure TEXT")
        
    conn.commit()
    conn.close()

init_db()

# --- Helper Functions: คำนวณ BMI & Plot Horizontal Status Bars ---
def calculate_bmi(weight, height):
    if height > 0 and weight > 0:
        height_m = height / 100
        bmi = weight / (height_m ** 2)
        if bmi < 18.5:
            status = "บาง (น้ำหนักน้อย)"
        elif 18.5 <= bmi < 23:
            status = "มาตรฐาน (ปกติ)"
        elif 23 <= bmi < 25:
            status = "ท้วม (เริ่มอ้วน)"
        elif 25 <= bmi < 30:
            status = "สูง (อ้วนระดับ 1)"
        else:
            status = "สูงเกินไป (อ้วนระดับ 2)"
        return round(bmi, 1), status
    return 0, "ไม่มีข้อมูล"

def render_bmi_bar(bmi_value):
    st.markdown(f"<div style='font-size: 0.95rem; font-weight: 600; color: #2D3748;'>⚖️ BMI: <span style='color:#E53E3E;'>{bmi_value}</span></div>", unsafe_allow_html=True)
    fig = go.Figure()

    fig.add_trace(go.Bar(y=['BMI'], x=[6.5], base=12, orientation='h', marker=dict(color='#54C5F8'), hoverinfo='none', showlegend=False))
    fig.add_trace(go.Bar(y=['BMI'], x=[4.5], base=18.5, orientation='h', marker=dict(color='#4CD964'), hoverinfo='none', showlegend=False))
    fig.add_trace(go.Bar(y=['BMI'], x=[2.0], base=23.0, orientation='h', marker=dict(color='#FF9500'), hoverinfo='none', showlegend=False))
    fig.add_trace(go.Bar(y=['BMI'], x=[7.0], base=25.0, orientation='h', marker=dict(color='#FF3B30'), hoverinfo='none', showlegend=False))

    display_bmi = max(12.2, min(bmi_value if bmi_value > 0 else 12.2, 31.8))

    fig.add_trace(go.Scatter(
        x=[display_bmi], y=['BMI'], mode='markers',
        marker=dict(color='#E53E3E', size=14, line=dict(color='white', width=2)),
        hoverinfo='text', hovertext=f"BMI: {bmi_value}",
        showlegend=False
    ))

    fig.update_layout(
        barmode='stack', height=45, margin=dict(l=0, r=0, t=10, b=10),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(range=[12, 32], tickvals=[18.5, 23.0, 25.0], ticktext=['18.5', '23.0', '25.0'], tickfont=dict(size=10, color='#718096'), showgrid=False, zeroline=False, fixedrange=True),
        yaxis=dict(visible=False, fixedrange=True)
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    st.markdown("""
    <div style="display: flex; justify-content: space-between; font-size: 0.72rem; color: #718096; margin-top: -15px;">
        <div><span style="color:#54C5F8;">●</span> บาง</div>
        <div><span style="color:#4CD964;">●</span> ปกติ</div>
        <div><span style="color:#FF9500;">●</span> ท้วม</div>
        <div><span style="color:#FF3B30;">●</span> สูงเกิน</div>
    </div>
    """, unsafe_allow_html=True)

def render_fbs_bar(fbs_value):
    status_text = "ปกติ" if fbs_value <= 100 else ("เริ่มสูง" if fbs_value <= 125 else "สูงมาก")
    st.markdown(f"<div style='font-size: 0.95rem; font-weight: 600; color: #2D3748;'>🩸 FBS: <span style='color:#E53E3E;'>{fbs_value} mg/dL</span> ({status_text})</div>", unsafe_allow_html=True)
    
    fig = go.Figure()
    fig.add_trace(go.Bar(y=['FBS'], x=[30], base=70, orientation='h', marker=dict(color='#4CD964'), hoverinfo='none', showlegend=False))
    fig.add_trace(go.Bar(y=['FBS'], x=[25], base=100, orientation='h', marker=dict(color='#FF9500'), hoverinfo='none', showlegend=False))
    fig.add_trace(go.Bar(y=['FBS'], x=[45], base=125, orientation='h', marker=dict(color='#FF3B30'), hoverinfo='none', showlegend=False))

    display_fbs = max(72, min(fbs_value if fbs_value > 0 else 72, 168))

    fig.add_trace(go.Scatter(
        x=[display_fbs], y=['FBS'], mode='markers',
        marker=dict(color='#E53E3E', size=14, line=dict(color='white', width=2)),
        hoverinfo='text', hovertext=f"FBS: {fbs_value} mg/dL",
        showlegend=False
    ))

    fig.update_layout(
        barmode='stack', height=45, margin=dict(l=0, r=0, t=10, b=10),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(range=[70, 170], tickvals=[100, 125], ticktext=['100', '125'], tickfont=dict(size=10, color='#718096'), showgrid=False, zeroline=False, fixedrange=True),
        yaxis=dict(visible=False, fixedrange=True)
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    st.markdown("""
    <div style="display: flex; justify-content: space-between; font-size: 0.72rem; color: #718096; margin-top: -15px;">
        <div><span style="color:#4CD964;">●</span> ปกติ (≤100)</div>
        <div><span style="color:#FF9500;">●</span> เสี่ยง (101-125)</div>
        <div><span style="color:#FF3B30;">●</span> สูง (≥126)</div>
    </div>
    """, unsafe_allow_html=True)

def render_bp_bar(bp_string):
    sys_val = 120
    if bp_string and "/" in bp_string:
        try:
            sys_val = float(bp_string.split("/")[0])
        except:
            sys_val = 120
            
    status_text = "ปกติ" if sys_val < 120 else ("เริ่มสูง" if sys_val <= 139 else "สูง")
    st.markdown(f"<div style='font-size: 0.95rem; font-weight: 600; color: #2D3748;'>🩺 BP: <span style='color:#E53E3E;'>{bp_string if bp_string else '120/80'} mmHg</span> ({status_text})</div>", unsafe_allow_html=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(y=['BP'], x=[30], base=90, orientation='h', marker=dict(color='#4CD964'), hoverinfo='none', showlegend=False))
    fig.add_trace(go.Bar(y=['BP'], x=[19], base=120, orientation='h', marker=dict(color='#FF9500'), hoverinfo='none', showlegend=False))
    fig.add_trace(go.Bar(y=['BP'], x=[41], base=139, orientation='h', marker=dict(color='#FF3B30'), hoverinfo='none', showlegend=False))

    display_sys = max(92, min(sys_val, 178))

    fig.add_trace(go.Scatter(
        x=[display_sys], y=['BP'], mode='markers',
        marker=dict(color='#E53E3E', size=14, line=dict(color='white', width=2)),
        hoverinfo='text', hovertext=f"Systolic: {sys_val} mmHg",
        showlegend=False
    ))

    fig.update_layout(
        barmode='stack', height=45, margin=dict(l=0, r=0, t=10, b=10),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(range=[90, 180], tickvals=[120, 139], ticktext=['120', '140'], tickfont=dict(size=10, color='#718096'), showgrid=False, zeroline=False, fixedrange=True),
        yaxis=dict(visible=False, fixedrange=True)
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    st.markdown("""
    <div style="display: flex; justify-content: space-between; font-size: 0.72rem; color: #718096; margin-top: -15px;">
        <div><span style="color:#4CD964;">●</span> ปกติ (<120)</div>
        <div><span style="color:#FF9500;">●</span> เสี่ยง (120-139)</div>
        <div><span style="color:#FF3B30;">●</span> สูง (≥140)</div>
    </div>
    """, unsafe_allow_html=True)

# --- Text To Speech Helper (ปรับปรุงเป็น Base64 HTML5 Audio แก้ปัญหา Error สดๆ) ---
def play_audio_from_text(text):
    try:
        # ทำความสะอาดข้อความ ตัด Tag สัญลักษณ์ตาราง และ Markdown ออกทั้งหมด
        clean_text = re.sub(r'<[^>]*>', '', text)
        clean_text = re.sub(r'[|:─\-\*#_`~]', ' ', clean_text)
        clean_text = ' '.join(clean_text.split())
        
        # จำกัดความยาวไม่เกิน 1500 ตัวอักษร เพื่อให้ gTTS แปลงได้เร็ว ไม่ Timeout
        if len(clean_text) > 1500:
            clean_text = clean_text[:1500]
            
        tts = gTTS(text=clean_text, lang='th')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        
        # แปลงเป็น Base64 เพื่อเล่นผ่าน HTML5 Audio Player โดยตรง
        b64_audio = base64.b64encode(fp.read()).decode('utf-8')
        md_audio = f"""
            <audio controls autoplay style="width: 100%; border-radius: 10px; margin-top: 10px;">
                <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
                เบราว์เซอร์ของคุณไม่รองรับการเล่นเสียง
            </audio>
        """
        st.markdown(md_audio, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"❌ ไม่สามารถสร้างเสียงพูดได้: {e}")

# --- 3. AI LOGIC ---
def ask_ai_nutritionist(profile):
    current_year = datetime.now().year
    age = current_year - profile['birth_year']
    
    user_w = profile['weight'] if profile['weight'] is not None else 60.0
    user_h = profile['height'] if profile['height'] is not None else 165.0
    bmi_val, bmi_status = calculate_bmi(user_w, user_h)
    
    bs_str = f"{profile['blood_sugar']} mg/dL" if profile.get('blood_sugar') and profile['blood_sugar'] > 0 else "ไม่ได้ระบุ"
    bp_str = profile.get('blood_pressure') if profile.get('blood_pressure') and str(profile['blood_pressure']).strip() != "" else "ไม่ได้ระบุ"
    
    prompt = f"""
    คุณคือนักโภชนาการและผู้เชี่ยวชาญด้านสุขภาพระดับมืออาชีพ ตอบคำแนะนำอย่างเป็นกันเอง อ่านง่าย สบายตา จัดรูปแบบ Markdown สวยงาม
    
    [ข้อมูลผู้ใช้งาน]
    - ชื่อ: {profile['nickname']}
    - เพศ: {profile['gender']}, อายุ: {age} ปี
    - BMI: {bmi_val} ({bmi_status})
    - เป้าหมายสุขภาพ: {profile['goals']}
    - โรคประจำตัว: {profile['diseases'] if profile['diseases'] else 'ไม่มี'}
    - อาหารที่แพ้: {profile['allergies'] if profile['allergies'] else 'ไม่มี'}
    - ผลตรวจน้ำตาล (FBS): {bs_str}
    - ความดันโลหิต: {bp_str}
    
    [โครงสร้างคำตอบที่ต้องการ]:
    
    ### 🟢 1. สรุปภาวะสุขภาพ & คำแนะนำโภชนาการภาพรวม
    (ประเมินภาพรวมสุขภาพจาก BMI, น้ำตาล, ความดัน สั้นๆ 2-3 บรรทัด)

    ### 🍽️ 2. เมนูอาหารไทยแนะนำประจำวัน & สรุปพลังงาน
    จัดทำสรุปมื้ออาหารและแคลอรีให้อยู่ใน **รูปแบบตาราง Markdown** ดังนี้:

    | มื้ออาหาร | เมนูแนะนำ | พลังงาน (kcal) | เหตุผลโภชนาการ |
    | :--- | :--- | :--- | :--- |
    | 🌅 มื้อเช้า | [ชื่อเมนู] | [XXX] | [เหตุผลสั้นๆ] |
    | ☀️ มื้อกลางวัน | [ชื่อเมนู] | [XXX] | [เหตุผลสั้นๆ] |
    | 🌙 มื้อเย็น | [ชื่อเมนู] | [XXX] | [เหตุผลสั้นๆ] |
    | 📊 **รวมพลังงานทั้งหมด** | **เป้าหมายสำหรับวันนี้** | **[XXXX] kcal** | **เหมาะสมกับเป้าหมาย** |

    ### 🚫 3. อาหารและวัตถุดิบที่ควรหลีกเลี่ยง / ลด ละ เลิก
    (ระบุเป็นข้อๆ วิเคราะห์จาก BMI, โรคประจำตัว, แพ้อาหาร และผลเลือด)
    - [ชื่ออาหาร/ประเภทอาหาร]: เหตุผลที่ควรหลีกเลี่ยง

    ### 💡 4. คำแนะนำการดูแลตัวเอง & ไลฟ์สไตล์ (Actionable Advice)
    - **การออกกำลังกาย**: (การออกกำลังกายที่เหมาะสมกับ BMI และสุขภาพ)
    - **การดื่มน้ำ & การนอน**: (เป้าหมายปริมาณน้ำดื่ม และเวลาพักผ่อน)
    - **ข้อควรระวังพิเศษ**: (ถ้ามี)
    
    *หมายเหตุ: ห้ามเสนอเมนูที่มีส่วนผสมของสิ่งที่ผู้ใช้แพ้เด็ดขาด*
    """
    
    models_to_try = [MODEL_NAME, 'gemini-2.5-pro', 'gemini-1.5-flash']
    
    for model_variant in models_to_try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_variant,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.7)
                )
                return response.text
            except Exception as e:
                if "503" in str(e):
                    time.sleep(2)
                    continue
                elif "404" in str(e):
                    break
                else:
                    return f"❌ เกิดข้อผิดพลาด: {str(e)}"
                    
    return "❌ ไม่สามารถเชื่อมต่อกับ AI ได้ในขณะนี้"

# --- 4. UI COMPONENTS ---
def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="text-align: center; padding: 40px 20px;">
            <div style="font-size: 50px;">🥗</div>
            <h2 style="color: #4E6E58; font-weight: 600;">AI Thai Nutritionist</h2>
            <p style="color: #718096; font-size: 0.9rem;">โภชนาการอาหารไทยส่วนบุคคล เข้าถึงง่าย</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.container():
            st.markdown('<div class="card-container">', unsafe_allow_html=True)
            email = st.text_input("อีเมลของคุณ (Gmail)", placeholder="yourname@gmail.com")
            st.write(" ")
            if st.button("เข้าสู่ระบบ / สมัครสมาชิก ➔", type="primary", use_container_width=True):
                if "@" in email:
                    st.session_state.user_email = email.strip()
                    st.session_state.active_tab = "my_meal"
                    st.rerun()
                else:
                    st.error("⚠️ กรุณากรอกอีเมลให้ถูกต้อง")
            st.markdown('</div>', unsafe_allow_html=True)

def profile_form(existing_data=None):
    is_edit = existing_data is not None
    
    st.markdown(f"""
    <div class="header-card">
        <h2>{"✏️ แก้ไขโปรไฟล์สุขภาพ" if is_edit else "📝 ลงทะเบียนโปรไฟล์สุขภาพ"}</h2>
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("user_profile_form"):
        col1, col2 = st.columns(2)
        with col1:
            nickname = st.text_input("ชื่อเล่น", value=existing_data['nickname'] if is_edit else "", placeholder="เช่น น็อต")
            gender = st.selectbox("เพศ", ["ชาย", "หญิง", "อื่นๆ"], index=["ชาย", "หญิง", "อื่นๆ"].index(existing_data['gender']) if is_edit else 0)
            default_year = (existing_data['birth_year'] + 543) if is_edit else 2545
            birth_year = st.number_input("ปีเกิด (พ.ศ.)", min_value=2450, max_value=datetime.now().year + 543, value=default_year)

        with col2:
            w_val = existing_data['weight'] if is_edit else 60.0
            h_val = existing_data['height'] if is_edit else 165.0
            weight = st.number_input("น้ำหนัก (กก.)", min_value=1.0, max_value=300.0, value=w_val, step=0.1)
            height = st.number_input("ส่วนสูง (ซม.)", min_value=50.0, max_value=250.0, value=h_val, step=0.1)

        all_goals = ["ลดน้ำหนัก", "ลดไขมัน", "เพิ่มกล้ามเนื้อ", "สร้างความแข็งแรง", "ดูแลสุขภาพองค์รวม"]
        
        default_goals = []
        if is_edit and existing_data['goals']:
            raw_goals = [g.strip() for g in existing_data['goals'].split(",")]
            default_goals = [g for g in raw_goals if g in all_goals]
            
        goals = st.multiselect("เป้าหมายสุขภาพ", all_goals, default=default_goals)
        
        diseases = st.text_input("โรคประจำตัว (เว้นว่างได้)", value=existing_data['diseases'] if is_edit else "")
        allergies = st.text_input("อาหารที่แพ้ (เว้นว่างได้)", value=existing_data['allergies'] if is_edit else "")
        
        st.markdown("#### 🩺 ผลตรวจสุขภาพ (Optional)")
        bs_val = float(existing_data['blood_sugar']) if (is_edit and 'blood_sugar' in existing_data.keys() and existing_data['blood_sugar']) else 0.0
        bp_val = existing_data['blood_pressure'] if (is_edit and 'blood_pressure' in existing_data.keys() and existing_data['blood_pressure']) else ""
        
        col_bs, col_bp = st.columns(2)
        with col_bs:
            blood_sugar = st.number_input("ระดับน้ำตาล FBS (mg/dL)", min_value=0.0, max_value=500.0, value=bs_val, step=1.0)
        with col_bp:
            blood_pressure = st.text_input("ความดันโลหิต (mmHg)", value=bp_val, placeholder="เช่น 120/80")

        col_sub1, col_sub2 = st.columns([1, 1])
        with col_sub1:
            submit = st.form_submit_button("💾 บันทึกข้อมูล", type="primary", use_container_width=True)
        with col_sub2:
            if is_edit:
                cancel = st.form_submit_button("❌ ยกเลิก", type="secondary", use_container_width=True)
                if cancel:
                    del st.session_state.edit_my_profile
                    st.rerun()

        if submit:
            if not nickname:
                st.error("กรุณากรอกชื่อเล่น")
            elif not goals:
                st.error("กรุณาเลือกเป้าหมายอย่างน้อย 1 ข้อ")
            else:
                bmi_calc, _ = calculate_bmi(weight, height)
                goals_str = ", ".join(goals)
                conn = get_db_connection()
                conn.execute('''INSERT OR REPLACE INTO users 
                             (email, nickname, gender, birth_year, weight, height, bmi, goals, diseases, allergies, blood_sugar, blood_pressure) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                             (st.session_state.user_email, nickname, gender, birth_year - 543, weight, height, bmi_calc, goals_str, diseases, allergies, blood_sugar, blood_pressure))
                conn.commit()
                conn.close()
                st.success("🎉 บันทึกข้อมูลสำเร็จ!")
                if is_edit:
                    del st.session_state.edit_my_profile
                st.rerun()

# --- 5. MAIN APPLICATION ---
if 'user_email' not in st.session_state:
    login_page()
else:
    if 'active_tab' not in st.session_state:
        st.session_state.active_tab = "my_meal"

    if 'edit_my_profile' in st.session_state:
        conn = get_db_connection()
        user_data = conn.execute("SELECT * FROM users WHERE email = ?", (st.session_state.user_email,)).fetchone()
        conn.close()
        profile_form(user_data)
    else:
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (st.session_state.user_email,)).fetchone()
        conn.close()

        if not user:
            profile_form()
        else:
            # --- TOP HEADER ---
            st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <div>
                    <h3 style="margin: 0; color: #4E6E58;">สวัสดี, คุณ {user['nickname']} 👋</h3>
                    <p style="margin: 0; font-size: 0.85rem; color: #718096;">{st.session_state.user_email}</p>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # --- TABS NAVIGATION ---
            tab_col1, tab_col2, tab_col3, tab_col4 = st.columns(4)
            with tab_col1:
                btn_type = "primary" if st.session_state.active_tab == "my_meal" else "secondary"
                if st.button("🍴 มื้ออาหารของฉัน", type=btn_type, use_container_width=True):
                    st.session_state.active_tab = "my_meal"
                    st.rerun()
            with tab_col2:
                btn_type = "primary" if st.session_state.active_tab == "temp_friend" else "secondary"
                if st.button("🤝 คำนวณให้เพื่อน", type=btn_type, use_container_width=True):
                    st.session_state.active_tab = "temp_friend"
                    st.rerun()
            with tab_col3:
                btn_type = "primary" if st.session_state.active_tab == "favorites" else "secondary"
                if st.button("⭐️ คนโปรด (สูงสุด 5)", type=btn_type, use_container_width=True):
                    st.session_state.active_tab = "favorites"
                    st.rerun()
            with tab_col4:
                if st.button("🚪 ออกจากระบบ", type="secondary", use_container_width=True):
                    del st.session_state.user_email
                    st.rerun()

            st.write(" ")

            # ================= TAB 1: มื้ออาหารของฉัน =================
            if st.session_state.active_tab == "my_meal":
                user_w = user['weight'] if user['weight'] is not None else 60.0
                user_h = user['height'] if user['height'] is not None else 165.0
                bmi_val, bmi_status = calculate_bmi(user_w, user_h)
                bs_val = float(user['blood_sugar']) if ('blood_sugar' in user.keys() and user['blood_sugar']) else 0.0
                bp_val = user['blood_pressure'] if ('blood_pressure' in user.keys() and user['blood_pressure'] and str(user['blood_pressure']).strip() != "") else "120/80"
                
                st.markdown('<div class="card-container">', unsafe_allow_html=True)
                st.markdown("##### 📊 ภาพรวมสุขภาพ (Health Metrics Visualized)")
                
                v_col1, v_col2, v_col3 = st.columns(3)
                
                with v_col1:
                    render_bmi_bar(bmi_val)

                with v_col2:
                    render_fbs_bar(bs_val)

                with v_col3:
                    render_bp_bar(bp_val)

                st.markdown('</div>', unsafe_allow_html=True)

                col_det, col_btn = st.columns([3, 1])
                with col_det:
                    st.caption(f"🎯 **เป้าหมาย:** {user['goals']} | ⚠️ **โรคประจำตัว:** {user['diseases'] if user['diseases'] else 'ไม่มี'} | ❌ **แพ้:** {user['allergies'] if user['allergies'] else 'ไม่มี'}")
                with col_btn:
                    if st.button("✏️ แก้ไขโปรไฟล์", type="secondary", use_container_width=True):
                        st.session_state.edit_my_profile = True
                        st.rerun()

                st.write("---")
                
                if st.button("🎲 สุ่มคำแนะนำโภชนาการและแผนดูแลสุขภาพประจำวัน", type="primary", use_container_width=True):
                    with st.spinner("🤖 AI กำลังวิเคราะห์และจัดทำคำแนะนำโภชนาการฉบับสมบูรณ์..."):
                        result = ask_ai_nutritionist(dict(user))
                        st.session_state.last_ai_result = result
                
                if 'last_ai_result' in st.session_state:
                    st.markdown(f"""
                    <div class="ai-summary-box">
                        {st.session_state.last_ai_result}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.write(" ")
                    if st.button("🔊 ฟังเสียงคำแนะนำจาก AI", type="secondary", key="btn_play_mymeal"):
                        with st.spinner("🔊 กำลังแปลงข้อความเป็นเสียงพูด..."):
                            play_audio_from_text(st.session_state.last_ai_result)

            # ================= TAB 2: คำนวณให้เพื่อน (ชั่วคราว) =================
            elif st.session_state.active_tab == "temp_friend":
                st.markdown("##### 🤝 คำนวณโภชนาการให้เพื่อน (รายครั้ง)")
                with st.form("temp_friend_form"):
                    f_name = st.text_input("ชื่อเพื่อน", placeholder="เช่น เอ็กซ์")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        f_gender = st.selectbox("เพศ", ["ชาย", "หญิง", "อื่นๆ"])
                    with col2:
                        f_year = st.number_input("ปีเกิด พ.ศ.", 2450, datetime.now().year + 543, 2545)
                    with col3:
                        f_w = st.number_input("น้ำหนัก (กก.)", min_value=1.0, max_value=300.0, value=65.0)
                    
                    f_h = st.number_input("ส่วนสูง (ซม.)", min_value=50.0, max_value=250.0, value=170.0)
                    all_goals = ["ลดน้ำหนัก", "ลดไขมัน", "เพิ่มกล้ามเนื้อ", "สร้างความแข็งแรง", "ดูแลสุขภาพองค์รวม"]
                    f_goals = st.multiselect("เป้าหมายสุขภาพ", all_goals)
                    
                    f_dis = st.text_input("โรคประจำตัว (ถ้ามี)")
                    f_alg = st.text_input("อาหารที่แพ้ (ถ้ามี)")
                    
                    col_f_bs, col_f_bp = st.columns(2)
                    with col_f_bs:
                        f_bs = st.number_input("ระดับน้ำตาล FBS (mg/dL)", min_value=0.0, max_value=500.0, value=0.0)
                    with col_f_bp:
                        f_bp = st.text_input("ความดันโลหิต (mmHg)", placeholder="เช่น 120/80")

                    submit_temp = st.form_submit_button("⚡ ประมวลผลคำแนะนำโภชนาการ", type="primary")
                    
                if submit_temp:
                    if not f_name or not f_goals:
                        st.error("กรุณากรอกชื่อและเลือกเป้าหมายสุขภาพอย่างน้อย 1 ข้อ")
                    else:
                        temp_profile = {
                            "nickname": f_name, "gender": f_gender, "birth_year": f_year - 543,
                            "weight": f_w, "height": f_h, "goals": ", ".join(f_goals),
                            "diseases": f_dis, "allergies": f_alg,
                            "blood_sugar": f_bs, "blood_pressure": f_bp
                        }
                        with st.spinner(f"กำลังสรุปคำแนะนำสุขภาพให้ คุณ {f_name}..."):
                            res = ask_ai_nutritionist(temp_profile)
                            st.session_state.friend_ai_result = res

                if 'friend_ai_result' in st.session_state and st.session_state.active_tab == "temp_friend":
                    st.markdown(f"""
                    <div class="ai-summary-box">
                        {st.session_state.friend_ai_result}
                    </div>
                    """, unsafe_allow_html=True)
                    st.write(" ")
                    if st.button("🔊 ฟังเสียงคำแนะนำจาก AI", type="secondary", key="btn_play_friend"):
                        with st.spinner("🔊 กำลังแปลงข้อความเป็นเสียงพูด..."):
                            play_audio_from_text(st.session_state.friend_ai_result)

            # ================= TAB 3: จัดการคนโปรด (สูงสุด 5) =================
            elif st.session_state.active_tab == "favorites":
                st.markdown("##### ⭐️ คนโปรดในครอบครัว (บันทึกได้สูงสุด 5 คน)")
                conn = get_db_connection()
                favs = conn.execute("SELECT * FROM favorites WHERE owner_email = ?", (st.session_state.user_email,)).fetchall()
                
                if 'edit_fav_id' in st.session_state:
                    fav_id = st.session_state.edit_fav_id
                    f_data = conn.execute("SELECT * FROM favorites WHERE id = ?", (fav_id,)).fetchone()
                    
                    st.subheader(f"✏️ แก้ไขข้อมูล: {f_data['nickname']}")
                    with st.form("edit_fav_form"):
                        en = st.text_input("ชื่อเล่น", value=f_data['nickname'])
                        eg = st.selectbox("เพศ", ["ชาย", "หญิง", "อื่นๆ"], index=["ชาย", "หญิง", "อื่นๆ"].index(f_data['gender']))
                        ey = st.number_input("ปีเกิด พ.ศ.", 2450, datetime.now().year + 543, value=f_data['birth_year']+543)
                        ew = st.number_input("น้ำหนัก (กก.)", value=f_data['weight'])
                        eh = st.number_input("ส่วนสูง (ซม.)", value=f_data['height'])
                        
                        all_goals = ["ลดน้ำหนัก", "ลดไขมัน", "เพิ่มกล้ามเนื้อ", "สร้างความแข็งแรง", "ดูแลสุขภาพองค์รวม"]
                        
                        curr_goals = []
                        if f_data['goals']:
                            raw_fgoals = [g.strip() for g in f_data['goals'].split(",")]
                            curr_goals = [g for g in raw_fgoals if g in all_goals]
                            
                        egoals = st.multiselect("เป้าหมายสุขภาพ", all_goals, default=curr_goals)
                        
                        ed = st.text_input("โรคประจำตัว", value=f_data['diseases'])
                        ea = st.text_input("อาหารที่แพ้", value=f_data['allergies'])
                        
                        ebs_val = float(f_data['blood_sugar']) if ('blood_sugar' in f_data.keys() and f_data['blood_sugar']) else 0.0
                        ebp_val = f_data['blood_pressure'] if ('blood_pressure' in f_data.keys() and f_data['blood_pressure']) else ""
                        ebs = st.number_input("ระดับน้ำตาล (mg/dL)", min_value=0.0, max_value=500.0, value=ebs_val)
                        ebp = st.text_input("ความดันโลหิต (mmHg)", value=ebp_val)
                        eimg = st.file_uploader("รูปภาพใหม่", type=['jpg', 'jpeg', 'png'])
                        
                        col_fsub1, col_fsub2 = st.columns([1, 1])
                        with col_fsub1:
                            sub_fav = st.form_submit_button("💾 อัปเดต", type="primary", use_container_width=True)
                        with col_fsub2:
                            can_fav = st.form_submit_button("❌ ยกเลิก", type="secondary", use_container_width=True)
                            if can_fav:
                                del st.session_state.edit_fav_id
                                conn.close()
                                st.rerun()

                        if sub_fav:
                            ebmi, _ = calculate_bmi(ew, eh)
                            egoals_str = ", ".join(egoals)
                            if eimg:
                                img_byte = eimg.read()
                                conn.execute('''UPDATE favorites SET nickname=?, gender=?, birth_year=?, weight=?, height=?, bmi=?, goals=?, diseases=?, allergies=?, blood_sugar=?, blood_pressure=?, photo=? WHERE id=?''',
                                             (en, eg, ey-543, ew, eh, ebmi, egoals_str, ed, ea, ebs, ebp, img_byte, fav_id))
                            else:
                                conn.execute('''UPDATE favorites SET nickname=?, gender=?, birth_year=?, weight=?, height=?, bmi=?, goals=?, diseases=?, allergies=?, blood_sugar=?, blood_pressure=? WHERE id=?''',
                                             (en, eg, ey-543, ew, eh, ebmi, egoals_str, ed, ea, ebs, ebp, fav_id))
                            conn.commit()
                            conn.close()
                            del st.session_state.edit_fav_id
                            st.rerun()

                else:
                    if favs:
                        cols = st.columns(len(favs) if len(favs) <= 3 else 3)
                        for idx, f in enumerate(favs):
                            with cols[idx % 3]:
                                f_w = f['weight'] if f['weight'] is not None else 60.0
                                f_h = f['height'] if f['height'] is not None else 165.0
                                fbmi, fstatus = calculate_bmi(f_w, f_h)

                                st.markdown('<div class="card-container">', unsafe_allow_html=True)
                                if f['photo']:
                                    st.image(f['photo'], use_column_width=True)
                                else:
                                    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
                                
                                st.markdown(f"**คุณ {f['nickname']}** (BMI: {fbmi})")
                                st.caption(f"📌 {fstatus}")
                                st.caption(f"🎯 {f['goals']} | ⚠️ {f['diseases'] if f['diseases'] else 'ไม่มี'}")
                                
                                if st.button("🎲 คำนวณโภชนาการ", key=f"ai_{f['id']}", type="primary", use_container_width=True):
                                    with st.spinner("AI กำลังวิเคราะห์..."):
                                        res = ask_ai_nutritionist(dict(f))
                                        st.session_state[f"fav_ai_{f['id']}"] = res
                                
                                if f"fav_ai_{f['id']}" in st.session_state:
                                    st.markdown(f"<div class='ai-summary-box'>{st.session_state[f'fav_ai_{f['id']}']}</div>", unsafe_allow_html=True)
                                    if st.button("🔊 ฟังเสียงคำแนะนำ", key=f"tts_fav_{f['id']}", type="secondary", use_container_width=True):
                                        play_audio_from_text(st.session_state[f"fav_ai_{f['id']}"])

                                c_btn1, c_btn2 = st.columns(2)
                                with c_btn1:
                                    if st.button("✏️ แก้ไข", key=f"editbtn_{f['id']}", use_container_width=True):
                                        st.session_state.edit_fav_id = f['id']
                                        conn.close()
                                        st.rerun()
                                with c_btn2:
                                    if st.button("🗑️ ลบ", key=f"del_{f['id']}", type="secondary", use_container_width=True):
                                        conn.execute("DELETE FROM favorites WHERE id = ?", (f['id'],))
                                        conn.commit()
                                        conn.close()
                                        st.rerun()
                                st.markdown('</div>', unsafe_allow_html=True)
                    else:
                        st.info("ยังไม่มีข้อมูลคนโปรด กดเพิ่มด้านล่างได้เลยครับ")

                    if len(favs) < 5:
                        with st.expander("➕ เพิ่มคนโปรดคนใหม่"):
                            with st.form("add_new_favorite"):
                                n = st.text_input("ชื่อเล่น", placeholder="เช่น คุณแม่")
                                g = st.selectbox("เพศ", ["ชาย", "หญิง", "อื่นๆ"], key="fav_g")
                                y = st.number_input("ปีเกิด พ.ศ.", 2450, datetime.now().year + 543, 2520, key="fav_y")
                                w = st.number_input("น้ำหนัก (กก.)", min_value=1.0, max_value=300.0, value=60.0, key="fav_w")
                                h = st.number_input("ส่วนสูง (ซม.)", min_value=50.0, max_value=250.0, value=165.0, key="fav_h")
                                
                                all_goals = ["ลดน้ำหนัก", "ลดไขมัน", "เพิ่มกล้ามเนื้อ", "สร้างความแข็งแรง", "ดูแลสุขภาพองค์รวม"]
                                f_goals_new = st.multiselect("เป้าหมายสุขภาพ", all_goals, key="fav_goals")
                                d = st.text_input("โรคประจำตัว", placeholder="ถ้าไม่มีเว้นว่าง")
                                a = st.text_input("อาหารที่แพ้", placeholder="ถ้าไม่มีเว้นว่าง")
                                
                                bs_new = st.number_input("ระดับน้ำตาล FBS (mg/dL)", min_value=0.0, max_value=500.0, value=0.0, key="fav_bs")
                                bp_new = st.text_input("ความดันโลหิต (mmHg)", placeholder="เช่น 120/80", key="fav_bp")
                                img_file = st.file_uploader("รูปภาพ", type=['jpg', 'jpeg', 'png'])
                                
                                if st.form_submit_button("💾 บันทึกคนโปรด", type="primary"):
                                    if not n or not f_goals_new:
                                        st.error("กรุณากรอกชื่อและเป้าหมายสุขภาพ")
                                    else:
                                        img_byte = img_file.read() if img_file else None
                                        fbmi_calc, _ = calculate_bmi(w, h)
                                        goals_str = ", ".join(f_goals_new)
                                        conn.execute('''INSERT INTO favorites 
                                                     (owner_email, nickname, gender, birth_year, weight, height, bmi, goals, diseases, allergies, blood_sugar, blood_pressure, photo) 
                                                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                                                     (st.session_state.user_email, n, g, y - 543, w, h, fbmi_calc, goals_str, d, a, bs_new, bp_new, img_byte))
                                        conn.commit()
                                        conn.close()
                                        st.rerun()
                    if conn:
                        conn.close()
