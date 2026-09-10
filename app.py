import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import time
from google import genai
from google.genai import types
from datetime import datetime, date, timedelta
import plotly.graph_objects as go
import plotly.express as px
from gTTS import gTTS
import io
import re
import base64
import calendar

# --- 1. SETUP & CONFIG ---
MODEL_NAME = 'gemini-2.5-flash'
FALLBACK_MODEL = 'gemini-1.5-flash'

st.set_page_config(page_title="ไทยกินดี AI Plus", page_icon="🥗", layout="wide")

# ดึงค่าจาก Streamlit Secrets
DATABASE_URL = st.secrets.get("DATABASE_URL", "")
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")

# ตั้งค่า Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# --- Custom CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Kanit', sans-serif;
        background-color: #F4F7F6;
        color: #2D3748;
    }
    
    .stApp {
        background-color: #F4F7F6;
    }

    .top-navbar {
        background: linear-gradient(135deg, #00A86B 0%, #00875A 100%);
        color: white;
        padding: 16px 24px;
        border-radius: 0px 0px 20px 20px;
        box-shadow: 0 4px 15px rgba(0, 168, 107, 0.2);
        margin: -60px -40px 25px -40px;
    }
    .top-navbar h2 {
        color: white !important;
        font-weight: 600;
        font-size: 1.5rem;
        margin: 0;
    }

    .health-card {
        background-color: #FFFFFF;
        border-radius: 20px;
        padding: 20px 24px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.04);
        border: 1px solid #E2E8F0;
        margin-bottom: 20px;
    }

    .streak-card {
        background: linear-gradient(135deg, #FF9500 0%, #FF5E00 100%);
        color: white;
        padding: 12px 18px;
        border-radius: 16px;
        text-align: center;
        font-weight: 600;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(255, 94, 0, 0.25);
    }

    .badge-card {
        background-color: #FFFFFF;
        border-radius: 14px;
        padding: 12px;
        text-align: center;
        border: 1px solid #E2E8F0;
        margin-bottom: 10px;
    }

    .stButton>button[kind="primary"] {
        background-color: #00A86B !important;
        color: white !important;
        border: none !important;
        border-radius: 14px !important;
        padding: 10px 20px !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        box-shadow: 0 4px 12px rgba(0, 168, 107, 0.25) !important;
        transition: all 0.2s ease !important;
        width: 100%;
    }
    .stButton>button[kind="primary"]:hover {
        background-color: #00875A !important;
        transform: translateY(-1px);
    }

    .stButton>button[kind="secondary"] {
        background-color: #E8F5E9 !important;
        color: #00A86B !important;
        border: 1px solid #C8E6C9 !important;
        border-radius: 14px !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        transition: all 0.2s ease !important;
        width: 100%;
    }
    .stButton>button[kind="secondary"]:hover {
        background-color: #C8E6C9 !important;
    }

    div[data-testid="stExpander"] {
        background-color: #FFFFFF;
        border-radius: 16px;
        border: 1px solid #E2E8F0;
        margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.02);
    }

    div[data-testid="stHorizontalBlock"] .stButton>button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)


# --- 2. DATABASE FUNCTIONS ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

@st.cache_resource
def setup_database_schema():
    if not DATABASE_URL:
        return
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''CREATE TABLE IF NOT EXISTS users 
                     (email TEXT PRIMARY KEY, 
                      nickname TEXT, 
                      gender TEXT, 
                      birth_year INTEGER, 
                      weight REAL, 
                      height REAL, 
                      bmi REAL, 
                      goals TEXT, 
                      diseases TEXT, 
                      allergies TEXT,
                      blood_sugar REAL, 
                      blood_pressure TEXT, 
                      streak_count INTEGER DEFAULT 1, 
                      last_login_date TEXT, 
                      freeze_used_month TEXT);''')
        conn.commit()

        columns = [
            ("streak_count", "INTEGER DEFAULT 1"),
            ("last_login_date", "TEXT"),
            ("freeze_used_month", "TEXT")
        ]
        for col_name, col_type in columns:
            try:
                cur.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type};")
                conn.commit()
            except Exception:
                conn.rollback()

        cur.execute('''CREATE TABLE IF NOT EXISTS daily_logs 
                     (id SERIAL PRIMARY KEY, 
                      email TEXT, 
                      log_date TEXT, 
                      breakfast TEXT, 
                      lunch TEXT, 
                      dinner TEXT, 
                      water_ml INTEGER DEFAULT 0);''')
        conn.commit()

        cur.execute('''CREATE TABLE IF NOT EXISTS health_history 
                     (id SERIAL PRIMARY KEY, 
                      email TEXT, 
                      record_date TEXT, 
                      weight REAL, 
                      blood_sugar REAL, 
                      blood_pressure TEXT);''')
        conn.commit()

        cur.close()
    except Exception as e:
        if conn:
            conn.rollback()
        st.error(f"เกิดข้อผิดพลาดในการเชื่อมต่อฐานข้อมูล: {e}")
    finally:
        if conn:
            conn.close()

# เรียกใช้งานฐานข้อมูลครั้งแรก
setup_database_schema()

# --- Helper Functions ---
def generate_ai_response_with_retry(prompt, config=None, retries=3):
    models_to_try = [MODEL_NAME, FALLBACK_MODEL]
    
    for model in models_to_try:
        for attempt in range(retries):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )
                return response.text
            except Exception as e:
                err_msg = str(e)
                if ("503" in err_msg or "UNAVAILABLE" in err_msg or "high demand" in err_msg) and attempt < retries - 1:
                    time.sleep(2)
                    continue
                elif model == models_to_try[-1] and attempt == retries - 1:
                    return f"⚠️ ระบบ AI ขัดข้องชั่วคราวเนื่องจากปริมาณการใช้งานสูง กรุณาลองใหม่อีกครั้ง ({err_msg})"
                else:
                    break

def calculate_bmi(weight, height):
    if height and weight and height > 0 and weight > 0:
        height_m = height / 100
        bmi = weight / (height_m ** 2)
        if bmi < 18.5:
            status = "บาง (น้ำหนักน้อย)"
            color_text = ":blue[บาง (น้ำหนักน้อย)]"
            hex_color = "#0369A1"
        elif 18.5 <= bmi < 23:
            status = "มาตรฐาน (ปกติ)"
            color_text = ":green[มาตรฐาน (ปกติ)]"
            hex_color = "#15803D"
        elif 23 <= bmi < 25:
            status = "สูง (ท้วม)"
            color_text = ":orange[เริ่มสูง (ท้วม)]"
            hex_color = "#C2410C"
        else:
            status = "สูงเกินไป (อ้วน)"
            color_text = ":red[สูงเกินไป (อ้วน)]"
            hex_color = "#B91C1C"
        return round(bmi, 1), status, color_text, hex_color
    return 0, "ไม่มีข้อมูล", "ไม่มีข้อมูล", "#475569"

def get_sugar_status(sugar_val):
    if sugar_val < 100:
        return "ปกติ (มาตรฐาน)", ":green[ปกติ (มาตรฐาน)]", "#15803D"
    elif 100 <= sugar_val <= 125:
        return "เริ่มสูง (เสี่ยง)", ":orange[เริ่มสูง (เสี่ยง)]", "#C2410C"
    else:
        return "สูงเกินไป (เสี่ยงเบาหวาน)", ":red[สูงเกินไป (เสี่ยงเบาหวาน)]", "#B91C1C"

def get_bp_status(bp_str):
    try:
        sys = float(bp_str.split('/')[0])
    except:
        sys = 120
    if sys < 120:
        return "ปกติ (มาตรฐาน)", ":green[ปกติ (มาตรฐาน)]", "#15803D"
    elif 120 <= sys <= 139:
        return "เริ่มสูง (ค่อนข้างสูง)", ":orange[เริ่มสูง (ค่อนข้างสูง)]", "#C2410C"
    else:
        return "สูงเกินไป (ความดันสูง)", ":red[สูงเกินไป (ความดันสูง)]", "#B91C1C"

def update_streak(email):
    today = date.today()
    today_str = str(today)
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT streak_count, last_login_date, freeze_used_month FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        
        if user:
            last_date_str = user['last_login_date']
            streak = user['streak_count'] or 1
            freeze_month = user['freeze_used_month'] or ""
            current_month = today.strftime("%Y-%m")
            
            if last_date_str != today_str:
                if last_date_str:
                    last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
                    delta = (today - last_date).days
                    
                    if delta == 1:
                        streak += 1
                    elif delta == 2:
                        if freeze_month != current_month:
                            freeze_month = current_month
                            streak += 1
                            st.toast("❄️ ระบบใช้ Streak Freeze ช่วยรักษาสถิติความต่อเนื่องของคุณ!", icon="❄️")
                        else:
                            streak = 1
                    elif delta > 2:
                        streak = 1
                else:
                    streak = 1
                    
                cur.execute("UPDATE users SET streak_count = %s, last_login_date = %s, freeze_used_month = %s WHERE email = %s", 
                            (streak, today_str, freeze_month, email))
                conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error updating streak: {e}")
    finally:
        cur.close()
        conn.close()

def get_streak_badges(streak):
    badges = [
        {"name": "เริ่มก้าวแรก", "desc": "เข้าใช้งานต่อเนื่อง 3 วัน", "icon": "🥦", "target": 3},
        {"name": "มุ่งมั่นกินดี", "desc": "เข้าใช้งานต่อเนื่อง 7 วัน", "icon": "🍎", "target": 7},
        {"name": "นักสร้างวินัย", "desc": "เข้าใช้งานต่อเนื่อง 14 วัน", "icon": "🥗", "target": 14},
        {"name": "ปรมาจารย์สุขภาพ", "desc": "เข้าใช้งานต่อเนื่อง 30 วัน", "icon": "🏆", "target": 30},
    ]
    for b in badges:
        b["unlocked"] = streak >= b["target"]
    return badges

# --- Visual Gauge Bar Functions ---
def render_bmi_bar(bmi_value):
    _, status, color_text, hex_color = calculate_bmi(bmi_value, 100) if bmi_value > 0 else (0, "ไม่มีข้อมูล", "ไม่มีข้อมูล", "#475569")
    header_title = f"BMI: {bmi_value if bmi_value > 0 else 'ไม่ได้ระบุ'} — {color_text}"
    
    with st.expander(header_title, expanded=False):
        fig = go.Figure()
        fig.add_trace(go.Bar(y=['BMI'], x=[6.5], base=12, orientation='h', marker=dict(color='#38BDF8'), hoverinfo='none', showlegend=False, width=0.3))
        fig.add_trace(go.Bar(y=['BMI'], x=[4.5], base=18.5, orientation='h', marker=dict(color='#22C55E'), hoverinfo='none', showlegend=False, width=0.3))
        fig.add_trace(go.Bar(y=['BMI'], x=[2.0], base=23.0, orientation='h', marker=dict(color='#FB923C'), hoverinfo='none', showlegend=False, width=0.3))
        fig.add_trace(go.Bar(y=['BMI'], x=[7.0], base=25.0, orientation='h', marker=dict(color='#EF4444'), hoverinfo='none', showlegend=False, width=0.3))
        
        display_bmi = max(12.2, min(bmi_value if bmi_value > 0 else 12.2, 31.8))
        
        fig.add_trace(go.Scatter(
            x=[display_bmi], y=['BMI'], 
            mode='markers+text', 
            text=[f"<b>{bmi_value}</b>"],
            textposition="top center",
            textfont=dict(color=hex_color, size=12, family="Kanit"),
            marker=dict(color='#1E293B', size=10, line=dict(color='white', width=1.5)), 
            hoverinfo='none', showlegend=False
        ))
        
        fig.update_layout(
            barmode='stack', height=70, margin=dict(l=0, r=0, t=30, b=5), 
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
            xaxis=dict(visible=False, range=[12, 32]), yaxis=dict(visible=False)
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

def render_sugar_bar(sugar_val):
    status, color_text, hex_color = get_sugar_status(sugar_val)
    header_title = f"ระดับน้ำตาลในเลือด (FBS): {sugar_val} mg/dL — {color_text}"

    with st.expander(header_title, expanded=False):
        fig = go.Figure()
        fig.add_trace(go.Bar(y=['Sugar'], x=[30], base=70, orientation='h', marker=dict(color='#22C55E'), hoverinfo='none', showlegend=False, width=0.3))
        fig.add_trace(go.Bar(y=['Sugar'], x=[25], base=100, orientation='h', marker=dict(color='#FB923C'), hoverinfo='none', showlegend=False, width=0.3))
        fig.add_trace(go.Bar(y=['Sugar'], x=[45], base=125, orientation='h', marker=dict(color='#EF4444'), hoverinfo='none', showlegend=False, width=0.3))
        
        display_val = max(70, min(sugar_val, 170))
        
        fig.add_trace(go.Scatter(
            x=[display_val], y=['Sugar'], 
            mode='markers+text', 
            text=[f"<b>{sugar_val}</b>"],
            textposition="top center",
            textfont=dict(color=hex_color, size=12, family="Kanit"),
            marker=dict(color='#1E293B', size=10, line=dict(color='white', width=1.5)), 
            hoverinfo='none', showlegend=False
        ))
        
        fig.update_layout(
            barmode='stack', height=70, margin=dict(l=0, r=0, t=30, b=5), 
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
            xaxis=dict(visible=False, range=[70, 170]), yaxis=dict(visible=False)
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

def render_bp_bar(bp_str):
    try:
        sys = float(bp_str.split('/')[0])
    except:
        sys = 120

    status, color_text, hex_color = get_bp_status(bp_str)
    header_title = f"ความดันโลหิต (Sys): {bp_str} mmHg — {color_text}"

    with st.expander(header_title, expanded=False):
        fig = go.Figure()
        fig.add_trace(go.Bar(y=['BP'], x=[30], base=90, orientation='h', marker=dict(color='#22C55E'), hoverinfo='none', showlegend=False, width=0.3))
        fig.add_trace(go.Bar(y=['BP'], x=[20], base=120, orientation='h', marker=dict(color='#FB923C'), hoverinfo='none', showlegend=False, width=0.3))
        fig.add_trace(go.Bar(y=['BP'], x=[40], base=140, orientation='h', marker=dict(color='#EF4444'), hoverinfo='none', showlegend=False, width=0.3))
        
        display_val = max(90, min(sys, 180))
        
        fig.add_trace(go.Scatter(
            x=[display_val], y=['BP'], 
            mode='markers+text', 
            text=[f"<b>{sys}</b>"],
            textposition="top center",
            textfont=dict(color=hex_color, size=12, family="Kanit"),
            marker=dict(color='#1E293B', size=10, line=dict(color='white', width=1.5)), 
            hoverinfo='none', showlegend=False
        ))
        
        fig.update_layout(
            barmode='stack', height=70, margin=dict(l=0, r=0, t=30, b=5), 
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
            xaxis=dict(visible=False, range=[90, 180]), yaxis=dict(visible=False)
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

def play_audio_from_text(text):
    try:
        clean_text = re.sub(r'<[^>]*>', '', text)
        clean_text = re.sub(r'[|:─\-\*#_`~]', ' ', clean_text)
        clean_text = ' '.join(clean_text.split())
        if len(clean_text) > 1500:
            clean_text = clean_text[:1500]
        tts = gTTS(text=clean_text, lang='th')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        b64_audio = base64.b64encode(fp.read()).decode('utf-8')
        md_audio = f"""<audio controls autoplay style="width: 100%; border-radius: 10px; margin-top: 10px;">
                <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
            </audio>"""
        st.markdown(md_audio, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"ไม่สามารถสร้างเสียงพูดได้: {e}")

# --- 3. AI LOGIC ---
def ask_ai_nutritionist(profile):
    current_year = datetime.now().year
    age = current_year - profile['birth_year']
    
    user_w = profile['weight'] if profile['weight'] is not None else 60.0
    user_h = profile['height'] if profile['height'] is not None else 165.0
    bmi_val, bmi_status, _, _ = calculate_bmi(user_w, user_h)
    
    bs_str = f"{profile['blood_sugar']} mg/dL" if profile.get('blood_sugar') and profile['blood_sugar'] > 0 else "ไม่ได้ระบุ"
    bp_str = profile.get('blood_pressure') if profile.get('blood_pressure') and str(profile['blood_pressure']).strip() != "" else "ไม่ได้ระบุ"
    
    prompt = f"""
    คุณคือนักโภชนาการมืออาชีพ กรุณาสรุปคำแนะนำสั้น กระชับ ความยาวไม่เกิน 2-3 บรรทัดต่อหัวข้อ
    
    [ข้อมูลผู้ใช้งาน]
    - ชื่อ: {profile['nickname']}, เพศ: {profile['gender']}, อายุ: {age} ปี
    - BMI: {bmi_val} ({bmi_status})
    - เป้าหมายสุขภาพ: {profile['goals']}
    - โรคประจำตัว: {profile['diseases'] if profile['diseases'] else 'ไม่มี'}
    - อาหารที่แพ้: {profile['allergies'] if profile['allergies'] else 'ไม่มี'}
    - ผลตรวจน้ำตาล (FBS): {bs_str}, ความดันโลหิต: {bp_str}
    
    ตอบกลับโดยคั่นแต่ละหัวข้อด้วยตัวคั่น [SECTION_BREAK] ตามโครงสร้างต่อไปนี้อย่างเคร่งครัด:

    [SECTION_1]
    (สรุปประเมินสุขภาพภาพรวม สั้นๆ กระชับ ไม่เกิน 2-3 บรรทัด)
    [SECTION_BREAK]
    [SECTION_2]
    จัดทำสรุปมื้ออาหารแนะนำประจำวัน ในรูปแบบตาราง Markdown โดยระบุชื่อเมนูอาหารไทยสั้นๆ ชัดเจน:
    | มื้ออาหาร | เมนูแนะนำ | พลังงาน | เหตุผลสั้นๆ |
    | :--- | :--- | :--- | :--- |
    | มื้อเช้า | [ชื่อเมนู] | [XXX kcal] | [เหตุผลสั้น] |
    | มื้อกลางวัน | [ชื่อเมนู] | [XXX kcal] | [เหตุผลสั้น] |
    | มื้อเย็น | [ชื่อเมนู] | [XXX kcal] | [เหตุผลสั้น] |
    | รวมพลังงาน | [เป้าหมาย] | [XXXX kcal] | [เหมาะสม] |
    [SECTION_BREAK]
    [SECTION_3]
    (ระบุอาหารที่ควรหลีกเลี่ยงเป็นข้อๆ สั้นๆ 2-3 ข้อ)
    [SECTION_BREAK]
    [SECTION_4]
    (คำแนะนำการปฏิบัติตัว 3 ข้อ)
    """
    
    config = types.GenerateContentConfig(temperature=0.7)
    return generate_ai_response_with_retry(prompt, config=config)

def extract_meals_from_ai(ai_text):
    bf, lu, dn = "", "", ""
    lines = ai_text.split('\n')
    for line in lines:
        if '| มื้อเช้า |' in line:
            parts = line.split('|')
            if len(parts) > 2: bf = parts[2].strip()
        elif '| มื้อกลางวัน |' in line:
            parts = line.split('|')
            if len(parts) > 2: lu = parts[2].strip()
        elif '| มื้อเย็น |' in line:
            parts = line.split('|')
            if len(parts) > 2: dn = parts[2].strip()
    return bf, lu, dn

def render_ai_result_expanders(ai_text):
    sections = ai_text.split("[SECTION_BREAK]")
    sec1 = sections[0].replace("[SECTION_1]", "").strip() if len(sections) > 0 else "ไม่มีข้อมูล"
    sec2 = sections[1].replace("[SECTION_2]", "").strip() if len(sections) > 1 else "ไม่มีข้อมูล"
    sec3 = sections[2].replace("[SECTION_3]", "").strip() if len(sections) > 2 else "ไม่มีข้อมูล"
    sec4 = sections[3].replace("[SECTION_4]", "").strip() if len(sections) > 3 else "ไม่มีข้อมูล"

    with st.expander("1. สรุปภาวะสุขภาพ & คำแนะนำโภชนาการภาพรวม", expanded=True):
        st.markdown(sec1)
        
    with st.expander("2. เมนูอาหารไทยแนะนำประจำวัน & สรุปพลังงาน", expanded=True):
        st.markdown(sec2)

    with st.expander("3. อาหารและวัตถุดิบที่ควรหลีกเลี่ยง / ลด ละ เลิก", expanded=False):
        st.markdown(sec3)
    with st.expander("4. คำแนะนำการดูแลตัวเอง & ไลฟ์สไตล์ (Actionable Advice)", expanded=False):
        st.markdown(sec4)

# --- 4. UI PAGES ---
def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="text-align: center; padding: 40px 20px 20px 20px;">
            <h2 style="color: #00A86B; font-weight: 700; margin-bottom: 5px;">ไทยกินดี AI Plus</h2>
            <p style="color: #718096; font-size: 0.95rem; margin-bottom: 25px;">แอปคู่หูโภชนาการและสุขภาพส่วนบุคคล</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            email = st.text_input("อีเมลของคุณ (Gmail)", placeholder="yourname@gmail.com")
            submit_login = st.form_submit_button("เข้าสู่ระบบ / สมัครสมาชิก", type="primary", use_container_width=True)
            if submit_login:
                if "@" in email:
                    st.session_state.user_email = email.strip()
                    update_streak(email.strip())
                    st.session_state.active_tab = "my_meal"
                    st.rerun()
                else:
                    st.error("กรุณากรอกอีเมลให้ถูกต้อง")

def profile_form(existing_data=None):
    is_edit = existing_data is not None
    st.markdown(f"""
    <div class="health-card">
        <h3 style="margin:0; color:#00A86B;">{"แก้ไขโปรไฟล์สุขภาพ" if is_edit else "ลงทะเบียนโปรไฟล์สุขภาพ"}</h3>
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("user_profile_form"):
        col1, col2 = st.columns(2)
        with col1:
            nickname = st.text_input("ชื่อเล่น*", value=existing_data['nickname'] if is_edit else "")
            gender_options = ["-- กรุณาเลือกเพศ --", "ชาย", "หญิง"]
            default_g_idx = gender_options.index(existing_data['gender']) if is_edit and existing_data['gender'] in ["ชาย", "หญิง"] else 0
            gender = st.selectbox("เพศ*", gender_options, index=default_g_idx)
            default_year = (existing_data['birth_year'] + 543) if (is_edit and existing_data['birth_year']) else None
            birth_year = st.number_input("ปีเกิด (พ.ศ.)*", min_value=2450, max_value=datetime.now().year + 543, value=default_year, placeholder="เช่น 2535")

        with col2:
            w_val = existing_data['weight'] if (is_edit and existing_data['weight']) else None
            h_val = existing_data['height'] if (is_edit and existing_data['height']) else None
            weight = st.number_input("น้ำหนัก (กก.)*", min_value=1.0, max_value=300.0, value=w_val, step=0.1, placeholder="เช่น 60.5")
            height = st.number_input("ส่วนสูง (ซม.)*", min_value=50.0, max_value=250.0, value=h_val, step=0.1, placeholder="เช่น 165.0")

        all_goals = ["ลดน้ำหนัก", "ลดไขมัน", "เพิ่มกล้ามเนื้อ", "สร้างความแข็งแรง", "ดูแลสุขภาพองค์รวม"]
        default_goals = [g for g in [g.strip() for g in existing_data['goals'].split(",")] if g in all_goals] if is_edit and existing_data['goals'] else []
        goals = st.multiselect("เป้าหมายสุขภาพ*", all_goals, default=default_goals)
        
        diseases = st.text_input("โรคประจำตัว (เว้นว่างได้)", value=existing_data['diseases'] if is_edit else "")
        allergies = st.text_input("อาหารที่แพ้ (เว้นว่างได้)", value=existing_data['allergies'] if is_edit else "")
        
        raw_bs = existing_data['blood_sugar'] if (is_edit and 'blood_sugar' in existing_data.keys()) else None
        bs_val = float(raw_bs) if (raw_bs is not None and float(raw_bs) > 0) else None
        bp_val = existing_data['blood_pressure'] if (is_edit and 'blood_pressure' in existing_data.keys() and existing_data['blood_pressure']) else ""
        
        col_bs, col_bp = st.columns(2)
        with col_bs:
            blood_sugar = st.number_input("ระดับน้ำตาล FBS (mg/dL)", value=bs_val, placeholder="ไม่ระบุ")
        with col_bp:
            blood_pressure = st.text_input("ความดันโลหิต (mmHg)", value=bp_val, placeholder="เช่น 120/80")

        col_sub1, col_sub2 = st.columns([1, 1])
        with col_sub1:
            submit = st.form_submit_button("บันทึกข้อมูล", type="primary", use_container_width=True)
        with col_sub2:
            if is_edit:
                cancel = st.form_submit_button("ยกเลิก", type="secondary", use_container_width=True)
                if cancel:
                    del st.session_state.edit_my_profile
                    st.rerun()

        if submit:
            if not nickname.strip() or gender not in ["ชาย", "หญิง"] or not birth_year or not weight or not height or not goals:
                st.error("กรุณากรอกข้อมูลที่จำเป็น (*) ให้ครบถ้วน")
            else:
                bmi_calc, _, _, _ = calculate_bmi(weight, height)
                conn = get_db_connection()
                cur = conn.cursor()
                
                sql_upsert_user = """
                INSERT INTO users 
                (email, nickname, gender, birth_year, weight, height, bmi, goals, diseases, allergies, blood_sugar, blood_pressure, last_login_date) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (email) DO UPDATE SET
                    nickname = EXCLUDED.nickname,
                    gender = EXCLUDED.gender,
                    birth_year = EXCLUDED.birth_year,
                    weight = EXCLUDED.weight,
                    height = EXCLUDED.height,
                    bmi = EXCLUDED.bmi,
                    goals = EXCLUDED.goals,
                    diseases = EXCLUDED.diseases,
                    allergies = EXCLUDED.allergies,
                    blood_sugar = EXCLUDED.blood_sugar,
                    blood_pressure = EXCLUDED.blood_pressure,
                    last_login_date = EXCLUDED.last_login_date;
                """
                
                cur.execute(sql_upsert_user, (
                    st.session_state.user_email, nickname.strip(), gender, int(birth_year) - 543, 
                    weight, height, bmi_calc, ", ".join(goals), diseases, allergies, 
                    float(blood_sugar) if blood_sugar else None, blood_pressure, str(date.today())
                ))
                
                cur.execute('''INSERT INTO health_history (email, record_date, weight, blood_sugar, blood_pressure) 
                             VALUES (%s, %s, %s, %s, %s)''', 
                             (st.session_state.user_email, str(date.today()), weight, float(blood_sugar) if blood_sugar else None, blood_pressure))
                
                conn.commit()
                cur.close()
                conn.close()
                st.success("บันทึกข้อมูลสำเร็จ")
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
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (st.session_state.user_email,))
        user_data = cur.fetchone()
        cur.close()
        conn.close()
        profile_form(user_data)
    else:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (st.session_state.user_email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user:
            profile_form()
        else:
            # --- TOP HEADER BAR ---
            st.markdown("""
            <div class="top-navbar">
                <h2>ไทยกินดี AI Plus</h2>
            </div>
            """, unsafe_allow_html=True)

            # --- USER PROFILE & STREAK CARD ---
            streak = user['streak_count'] or 1
            col_prof, col_str = st.columns([3, 1])
            with col_prof:
                st.markdown(f"""
                <div class="health-card" style="margin-bottom:0px;">
                    <h2 style="margin: 0; color: #2D3748; font-weight: 700; font-size: 1.5rem;">{user['nickname']}</h2>
                    <p style="margin: 2px 0 0 0; color: #718096; font-size: 0.85rem;">{st.session_state.user_email}</p>
                </div>
                """, unsafe_allow_html=True)
            with col_str:
                st.markdown(f"""
                <div class="streak-card">
                    <div style="font-size: 0.75rem; opacity: 0.95;">🔥 ความต่อเนื่อง</div>
                    <div style="font-size: 1.5rem; font-weight: 700;">{streak} วัน</div>
                </div>
                """, unsafe_allow_html=True)

            # --- STREAK BADGES & ACHIEVEMENTS EXPANDER ---
            badges = get_streak_badges(streak)
            current_month = date.today().strftime("%Y-%m")
            has_freeze = (user['freeze_used_month'] or "") != current_month

            with st.expander("🎖️ รางวัลความต่อเนื่อง & สถานะ Streak Freeze", expanded=False):
                col_fz1, col_fz2 = st.columns([3, 1])
                with col_fz1:
                    st.markdown("**❄️ Streak Freeze (เกราะป้องกันวันขาด)**")
                    st.caption("ช่วยรักษาสถิติความต่อเนื่องฟรีเดือนละ 1 วัน หากข้ามการเข้าแอปไม่เกิน 24 ชม.")
                with col_fz2:
                    if has_freeze:
                        st.success("พร้อมใช้งาน ❄️")
                    else:
                        st.info("ใช้ไปแล้วเดือนนี้ 🔒")

                st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
                st.markdown("**เหรียญรางวัลของคุณ (Badges):**")
                
                b_cols = st.columns(4)
                for idx, b in enumerate(badges):
                    with b_cols[idx]:
                        if b["unlocked"]:
                            st.markdown(f"""
                            <div class="badge-card" style="border-color: #00A86B; background-color: #F0FDF4;">
                                <div style="font-size: 1.8rem;">{b['icon']}</div>
                                <div style="font-weight: 600; color: #00875A; font-size: 0.85rem;">{b['name']}</div>
                                <div style="font-size: 0.75rem; color: #718096;">{b['desc']}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown(f"""
                            <div class="badge-card" style="opacity: 0.45; background-color: #F8FAFC;">
                                <div style="font-size: 1.8rem;">🪙</div>
                                <div style="font-weight: 600; font-size: 0.85rem;">{b['name']}</div>
                                <div style="font-size: 0.75rem; color: #718096;">{b['desc']}</div>
                            </div>
                            """, unsafe_allow_html=True)

            st.write(" ")

            # --- TABS NAVIGATION ---
            tab_col1, tab_col2, tab_col3, tab_col4, tab_col5 = st.columns(5)
            with tab_col1:
                btn_type = "primary" if st.session_state.active_tab == "my_meal" else "secondary"
                if st.button("สรุปแผนสุขภาพ", type=btn_type, use_container_width=True):
                    st.session_state.active_tab = "my_meal"
                    st.rerun()
            with tab_col2:
                btn_type = "primary" if st.session_state.active_tab == "daily_log" else "secondary"
                if st.button("บันทึกประจำวัน", type=btn_type, use_container_width=True):
                    st.session_state.active_tab = "daily_log"
                    st.rerun()
            with tab_col3:
                btn_type = "primary" if st.session_state.active_tab == "tracker" else "secondary"
                if st.button("กราฟติดตามสุขภาพ", type=btn_type, use_container_width=True):
                    st.session_state.active_tab = "tracker"
                    st.rerun()
            with tab_col4:
                btn_type = "primary" if st.session_state.active_tab == "ai_chat" else "secondary"
                if st.button("ถาม AI โภชนาการ", type=btn_type, use_container_width=True):
                    st.session_state.active_tab = "ai_chat"
                    st.rerun()
            with tab_col5:
                if st.button("ออกจากระบบ", type="secondary", use_container_width=True):
                    del st.session_state.user_email
                    st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)

            # ================= TAB 1: สรุปแผนสุขภาพประจำวัน =================
            if st.session_state.active_tab == "my_meal":
                user_w = user['weight'] if user['weight'] is not None else 60.0
                user_h = user['height'] if user['height'] is not None else 165.0
                bmi_val, _, _, _ = calculate_bmi(user_w, user_h)
                
                render_bmi_bar(bmi_val)
                
                if user['blood_sugar'] and float(user['blood_sugar']) > 0:
                    render_sugar_bar(float(user['blood_sugar']))
                    
                if user['blood_pressure'] and str(user['blood_pressure']).strip() != "":
                    render_bp_bar(str(user['blood_pressure']))

                col_det, col_btn = st.columns([3, 1])
                with col_det:
                    st.caption(f"เป้าหมาย: {user['goals']} | โรคประจำตัว: {user['diseases'] if user['diseases'] else 'ไม่มี'} | แพ้อาหาร: {user['allergies'] if user['allergies'] else 'ไม่มี'}")
                with col_btn:
                    if st.button("แก้ไขโปรไฟล์", type="secondary", use_container_width=True):
                        st.session_state.edit_my_profile = True
                        st.rerun()

                st.markdown("<br>", unsafe_allow_html=True)
                
                if st.button("สรุปแผนสุขภาพประจำวัน", type="primary", use_container_width=True):
                    with st.spinner("AI กำลังวิเคราะห์และประมวลผลข้อมูลสุขภาพ..."):
                        result = ask_ai_nutritionist(dict(user))
                        st.session_state.last_ai_result = result
                
                if 'last_ai_result' in st.session_state:
                    st.markdown("<br>", unsafe_allow_html=True)
                    render_ai_result_expanders(st.session_state.last_ai_result)
                    st.write(" ")
                    
                    col_act1, col_act2 = st.columns(2)
                    with col_act1:
                        if st.button("ฟังเสียงคำแนะนำจาก AI", type="secondary", key="btn_play_mymeal", use_container_width=True):
                            with st.spinner("กำลังแปลงข้อความเป็นเสียงพูด..."):
                                play_audio_from_text(st.session_state.last_ai_result)
                    with col_act2:
                        if st.button("บันทึกไปยังบันทึกประจำวัน", type="primary", use_container_width=True):
                            bf, lu, dn = extract_meals_from_ai(st.session_state.last_ai_result)
                            today_str = str(date.today())
                            conn = get_db_connection()
                            cur = conn.cursor()
                            cur.execute("SELECT id, water_ml FROM daily_logs WHERE email=%s AND log_date=%s", (st.session_state.user_email, today_str))
                            existing = cur.fetchone()
                            
                            if existing:
                                cur.execute("UPDATE daily_logs SET breakfast=%s, lunch=%s, dinner=%s WHERE id=%s", (bf, lu, dn, existing['id']))
                            else:
                                cur.execute("INSERT INTO daily_logs (email, log_date, breakfast, lunch, dinner, water_ml) VALUES (%s, %s, %s, %s, %s, 0)", 
                                             (st.session_state.user_email, today_str, bf, lu, dn))
                            conn.commit()
                            cur.close()
                            conn.close()
                            st.success("บันทึกรายการอาหารลงในหน้าบันทึกประจำวันเรียบร้อยแล้ว!")

            # ================= TAB 2: บันทึกประจำวัน =================
            elif st.session_state.active_tab == "daily_log":
                today_str = str(date.today())
                
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("SELECT * FROM daily_logs WHERE email = %s AND log_date = %s", (st.session_state.user_email, today_str))
                log = cur.fetchone()
                
                water_val = log['water_ml'] if log else 0
                bf_val = log['breakfast'] if log else ""
                lu_val = log['lunch'] if log else ""
                dn_val = log['dinner'] if log else ""
                
                target_water = 2000
                cups_curr = round(water_val / 250, 1)
                cups_target = int(target_water / 250)
                
                st.markdown(f"**เป้าหมายการดื่มน้ำประจำวัน (2,000 ml / เทียบเท่า {cups_target} แก้ว)**")
                progress = min(1.0, max(0.0, water_val / target_water))
                st.progress(progress)
                st.caption(f"💧 ดื่มไปแล้ว: **{water_val}** / {target_water} ml (ประมาณ **{cups_curr}** / {cups_target} แก้ว)")
                
                col_w1, col_w2 = st.columns(2)
                with col_w1:
                    if st.button("เติมน้ำ 1 แก้ว (+250 ml)", type="primary", use_container_width=True):
                        new_water = water_val + 250
                        if log:
                            cur.execute("UPDATE daily_logs SET water_ml = %s WHERE id = %s", (new_water, log['id']))
                        else:
                            cur.execute("INSERT INTO daily_logs (email, log_date, water_ml) VALUES (%s, %s, %s)", (st.session_state.user_email, today_str, new_water))
                        conn.commit()
                        cur.close()
                        conn.close()
                        st.rerun()
                with col_w2:
                    if st.button("ลดน้ำ 1 แก้ว (-250 ml)", type="secondary", use_container_width=True):
                        new_water = max(0, water_val - 250)
                        if log:
                            cur.execute("UPDATE daily_logs SET water_ml = %s WHERE id = %s", (new_water, log['id']))
                        else:
                            cur.execute("INSERT INTO daily_logs (email, log_date, water_ml) VALUES (%s, %s, %s)", (st.session_state.user_email, today_str, new_water))
                        conn.commit()
                        cur.close()
                        conn.close()
                        st.rerun()

                st.markdown("<br>", unsafe_allow_html=True)

                st.markdown("**บันทึกสิ่งที่รับประทานวันนี้**")
                bf = st.text_input("มื้อเช้า", value=bf_val, placeholder="เช่น โจ๊กหมูใส่ไข่, กาแฟดำ")
                lu = st.text_input("มื้อกลางวัน", value=lu_val, placeholder="เช่น ข้าวมันไก่เนื้ออก, ชามะนาวหวานน้อย")
                dn = st.text_input("มื้อเย็น", value=dn_val, placeholder="เช่น ส้มตำไทย, ไก่ย่าง")
                
                if st.button("บันทึกมื้ออาหาร", type="primary", use_container_width=True):
                    if log:
                        cur.execute("UPDATE daily_logs SET breakfast=%s, lunch=%s, dinner=%s WHERE id=%s", (bf, lu, dn, log['id']))
                    else:
                        cur.execute("INSERT INTO daily_logs (email, log_date, breakfast, lunch, dinner, water_ml) VALUES (%s, %s, %s, %s, %s, %s)", 
                                     (st.session_state.user_email, today_str, bf, lu, dn, water_val))
                    conn.commit()
                    cur.close()
                    conn.close()
                    st.success("บันทึกข้อมูลสำเร็จ!")
                    st.rerun()
                else:
                    cur.close()
                    conn.close()

                st.markdown("<br>**ปฏิทินประวัติการรับประทานอาหารรายเดือน**", unsafe_allow_html=True)
                
                col_sel_m, col_sel_y = st.columns([2, 1])
                months_th = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
                now = datetime.now()
                
                with col_sel_m:
                    selected_m_idx = st.selectbox("เลือกเดือน", range(1, 13), index=now.month - 1, format_func=lambda x: months_th[x-1])
                with col_sel_y:
                    selected_year = st.selectbox("เลือกปี (ค.ศ.)", range(now.year - 2, now.year + 2), index=2)

                month_calendar = calendar.monthcalendar(selected_year, selected_m_idx)
                
                conn = get_db_connection()
                cur = conn.cursor()
                month_prefix = f"{selected_year}-{selected_m_idx:02d}-%"
                cur.execute("SELECT * FROM daily_logs WHERE email = %s AND log_date LIKE %s", (st.session_state.user_email, month_prefix))
                logs_in_month = cur.fetchall()
                cur.close()
                conn.close()
                
                logs_dict = {l['log_date']: l for l in logs_in_month}

                days_header = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
                cols = st.columns(7)
                for i, h in enumerate(days_header):
                    cols[i].markdown(f"**<div style='text-align:center;'>{h}</div>**", unsafe_allow_html=True)

                for week in month_calendar:
                    cols = st.columns(7)
                    for idx, day in enumerate(week):
                        if day == 0:
                            cols[idx].write(" ")
                        else:
                            date_s = f"{selected_year}-{selected_m_idx:02d}-{day:02d}"
                            has_data = date_s in logs_dict
                            btn_label = f"🟢 {day}" if has_data else f"{day}"
                            
                            if cols[idx].button(btn_label, key=f"cal_day_{date_s}", use_container_width=True):
                                st.session_state.selected_cal_date = date_s

                if "selected_cal_date" in st.session_state and st.session_state.selected_cal_date:
                    sel_d = st.session_state.selected_cal_date
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM daily_logs WHERE email = %s AND log_date = %s", (st.session_state.user_email, sel_d))
                    d_log = cur.fetchone()
                    cur.close()
                    conn.close()
                    
                    with st.expander(f"📋 รายละเอียดเมนูอาหารประจำวันที่ {sel_d}", expanded=True):
                        if d_log:
                            st.write(f"🥣 **มื้อเช้า:** {d_log['breakfast'] if d_log['breakfast'] else '-'}")
                            st.write(f"🥗 **มื้อกลางวัน:** {d_log['lunch'] if d_log['lunch'] else '-'}")
                            st.write(f"🍲 **มื้อเย็น:** {d_log['dinner'] if d_log['dinner'] else '-'}")
                            st.write(f"💧 **น้ำดื่ม:** {d_log['water_ml']} ml (ประมาณ {round(d_log['water_ml']/250, 1)} แก้ว)")
                        else:
                            st.write("ไม่มีข้อมูลการบันทึกอาหารในวันนี้")
                        
                        if st.button("ปิดรายละเอียด", type="secondary"):
                            del st.session_state.selected_cal_date
                            st.rerun()

            # ================= TAB 3: กราฟติดตามสุขภาพ =================
            elif st.session_state.active_tab == "tracker":
                st.markdown("##### ติดตามแนวโน้มสุขภาพและพัฒนาการ")
                
                with st.expander("บันทึกค่าน้ำหนัก / ผลเลือด วันนี้"):
                    col_h1, col_h2 = st.columns(2)
                    with col_h1:
                        rec_w = st.number_input("น้ำหนัก (กก.)", value=float(user['weight']) if user['weight'] else 60.0, step=0.1)
                    with col_h2:
                        rec_bs = st.number_input("ระดับน้ำตาล FBS (mg/dL)", value=float(user['blood_sugar']) if user['blood_sugar'] else 0.0)
                    
                    if st.button("บันทึกสถิติ", type="primary", use_container_width=True):
                        conn = get_db_connection()
                        cur = conn.cursor()
                        cur.execute("INSERT INTO health_history (email, record_date, weight, blood_sugar) VALUES (%s, %s, %s, %s)",
                                     (st.session_state.user_email, str(date.today()), rec_w, rec_bs if rec_bs > 0 else None))
                        cur.execute("UPDATE users SET weight=%s, blood_sugar=%s WHERE email=%s",
                                     (rec_w, rec_bs if rec_bs > 0 else None, st.session_state.user_email))
                        conn.commit()
                        cur.close()
                        conn.close()
                        st.success("บันทึกสถิติสำเร็จ!")
                        st.rerun()

                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("""
                    SELECT record_date, weight 
                    FROM health_history 
                    WHERE id IN (
                        SELECT MAX(id) 
                        FROM health_history 
                        WHERE email = %s AND weight IS NOT NULL AND weight > 0 
                        GROUP BY record_date
                    ) 
                    ORDER BY record_date ASC
                """, (st.session_state.user_email,))
                hist_df = cur.fetchall()
                cur.close()
                conn.close()

                if hist_df and len(hist_df) > 0:
                    dates_list = []
                    weights_list = []
                    text_labels = []
                    
                    for h in hist_df:
                        try:
                            d_obj = datetime.strptime(h['record_date'], "%Y-%m-%d")
                            dates_list.append(d_obj.strftime("%b %d, %Y"))
                            
                            w_val = float(h['weight'])
                            formatted_w = f"{int(w_val)}" if w_val.is_integer() else f"{round(w_val, 2)}"
                            
                            weights_list.append(w_val)
                            text_labels.append(f"{formatted_w} kg")
                        except:
                            continue

                    st.markdown("**แนวโน้มน้ำหนักตัว (kg)**")
                    
                    fig_w = go.Figure()
                    fig_w.add_trace(go.Scatter(
                        x=dates_list,
                        y=weights_list,
                        mode='lines+markers+text',
                        text=text_labels,
                        textposition="top center",
                        line=dict(color='#00A86B', width=3),
                        marker=dict(size=10, color='#00875A', symbol='circle')
                    ))
                    
                    min_w = min(weights_list) - 2
                    max_w = max(weights_list) + 2
                    
                    fig_w.update_layout(
                        height=350,
                        margin=dict(l=20, r=20, t=25, b=20),
                        yaxis=dict(title="น้ำหนัก (กก.)", range=[min_w, max_w]),
                        xaxis=dict(title="วันที่", type="category"),
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_w, use_container_width=True)
                else:
                    st.info("ยังไม่มีข้อมูลบันทึกน้ำหนักย้อนหลัง กรุณากรอกบันทึกสถิติด้านบนเพื่อเริ่มติดตามกราฟ")

            # ================= TAB 4: ถาม-ตอบ AI โภชนาการ =================
            elif st.session_state.active_tab == "ai_chat":
                st.markdown("##### ถาม-ตอบ เรื่องอาหารและสุขภาพกับ AI")
                st.caption("สอบถามเมนูอาหารเฉพาะหน้า เช่น 'มื้อนี้กินอะไรดีในเซเว่น?' หรือ 'ชานมไข่มุกกี่แคล?'")
                
                if "messages" not in st.session_state:
                    st.session_state.messages = []

                for message in st.session_state.messages:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])

                if user_prompt := st.chat_input("พิมพ์คำถามเรื่องอาหารและสุขภาพที่นี่..."):
                    st.session_state.messages.append({"role": "user", "content": user_prompt})
                    with st.chat_message("user"):
                        st.markdown(user_prompt)

                    with st.chat_message("assistant"):
                        with st.spinner("AI กำลังคิดคำตอบ..."):
                            user_nickname = user['nickname'] if user['nickname'] else "ผู้ใช้งาน"
                            user_diseases = user['diseases'] if user['diseases'] else 'ไม่มี'
                            user_allergies = user['allergies'] if user['allergies'] else 'ไม่มี'
                            user_goals = user['goals'] if user['goals'] else 'ดูแลสุขภาพ'

                            chat_prompt = f"""
                            คุณคือนักโภชนาการประจำตัวของผู้ใช้ชื่อ {user_nickname} 
                            - ข้อจำกัดสุขภาพ: โรคประจำตัว ({user_diseases}), แพ้อาหาร ({user_allergies})
                            - เป้าหมาย: {user_goals}
                            
                            คำถามจากผู้ใช้: "{user_prompt}"
                            ตอบคำถามให้ตรงประเด็น สั้น กระชับ เป็นกันเอง สอดคล้องกับสุขภาพของผู้ใช้
                            """
                            
                            ans_text = generate_ai_response_with_retry(chat_prompt)
                            
                            st.markdown(ans_text)
                            st.session_state.messages.append({"role": "assistant", "content": ans_text})
