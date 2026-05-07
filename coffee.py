import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import date, timedelta
import io

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False

# === 1. НАСТРОЙКИ СТРАНИЦЫ И COFFEE-ДИЗАЙН ===
st.set_page_config(page_title="Горький Кофе | BI Аналитика", page_icon="☕", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@500;700;800&family=Inter:wght@400;500;600&display=swap');
    
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    
    html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; color: #f5f5f4 !important; }
    .stApp { background-color: #161210; } 
    [data-testid="stSidebar"] { background-color: #0f0c0a !important; border-right: 1px solid #292524; }
    
    label, div[data-testid="stWidgetLabel"] p { color: #d6d3d1 !important; font-size: 14px !important; font-weight: 600 !important; }
    
    div[data-testid="metric-container"] {
        background: linear-gradient(145deg, rgba(35, 28, 25, 0.9), rgba(20, 16, 14, 0.95));
        border: 1px solid rgba(245, 158, 11, 0.25); padding: 20px; border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3); transition: transform 0.2s;
    }
    div[data-testid="metric-container"]:hover { transform: translateY(-5px); border: 1px solid rgba(245, 158, 11, 0.8); }
    
    [data-testid="stMetricValue"] { font-family: 'Montserrat', sans-serif !important; font-size: 34px !important; color: #F59E0B !important; font-weight: 800 !important; }
    [data-testid="stMetricLabel"] p { font-size: 13px !important; color: #a8a29e !important; text-transform: uppercase; letter-spacing: 1px; font-weight: 600 !important;}
    
    .insight-box { padding: 16px; border-radius: 8px; margin-bottom: 12px; border-left: 5px solid; font-size: 15px; background: rgba(255,255,255,0.05); }
    .insight-danger { border-color: #ef4444; color: #fca5a5;} 
    .insight-warning { border-color: #f59e0b; color: #fcd34d;} 
    .insight-success { border-color: #10b981; color: #6ee7b7;}
    
    .stTabs [data-baseweb="tab-list"] { background-color: transparent; border-bottom: 1px solid #292524; }
    .stTabs [data-baseweb="tab"] { color: #a8a29e !important; font-family: 'Montserrat', sans-serif !important; font-weight: 600 !important; font-size: 15px !important; padding: 12px 20px; }
    .stTabs [aria-selected="true"] { color: #F59E0B !important; border-bottom: 3px solid #F59E0B !important; }
    </style>
    """, unsafe_allow_html=True)

CUSTOM_COLORS = ["#F59E0B", "#FEF3C7", "#10B981", "#F43F5E", "#8B5CF6", "#38BDF8"]
PLOTLY_FONT = dict(family="Inter", size=13, color="#f5f5f4")

# === 2. ГЕНЕРАТОР ПРОДВИНУТЫХ ДАННЫХ ===
@st.cache_data
def generate_coffee_demo():
    np.random.seed(42)
    days = pd.date_range(end=date.today(), periods=60)
    cats = ["Классика", "Авторский кофе", "Выпечка", "Десерты", "Сэндвичи", "Чай"]
    staff = ["Бариста: Иван", "Бариста: Анна", "Бариста: Олег", "Стажер: Мария"]
    loyal_clients = [f"GUEST-{i}" for i in range(100, 400)] # База из 300 постоянников
    
    data = []
    for i in range(2500):
        receipt_id = f"CHK-{10000+i}"
        day = np.random.choice(days)
        hour = max(7, min(22, int(np.random.normal(12, 3))))
        timestamp = pd.Timestamp(day) + pd.Timedelta(hours=hour, minutes=np.random.randint(0, 59))
        
        temp = np.random.randint(-5, 25)
        is_raining = "Да" if np.random.random() > 0.8 else "Нет"
        barista = np.random.choice(staff)
        
        # Симуляция постоянников vs новых
        is_loyal = np.random.choice([True, False], p=[0.65, 0.35])
        client_id = np.random.choice(loyal_clients) if is_loyal else f"NEW-{np.random.randint(1000,9999)}"
        
        items_in_check = np.random.choice([1, 2, 3], p=[0.5, 0.3, 0.2]) 
        
        for _ in range(items_in_check):
            cat = np.random.choice(cats, p=[0.4, 0.15, 0.15, 0.1, 0.1, 0.1])
            price = np.random.randint(180, 400)
            cost = price * np.random.uniform(0.2, 0.45) 
            
            data.append({
                "Дата и Время": timestamp, "Чек": receipt_id, "Карта Гостя": client_id, "Бариста": barista,
                "Категория/Товар": cat, "Сумма": price, "Фудкост": cost, 
                "Погода (°C)": temp, "Осадки": is_raining
            })
    return pd.DataFrame(data)

def detect_columns(df):
    cols = [str(c).lower() for c in df.columns]
    mapping = {k: None for k in ['date', 'receipt', 'client', 'staff', 'item', 'rev', 'cost', 'temp']}
    for i, c in enumerate(cols):
        if any(w in c for w in ['дат', 'врем', 'date']): mapping['date'] = df.columns[i]
        elif any(w in c for w in ['чек', 'заказ']): mapping['receipt'] = df.columns[i]
        elif any(w in c for w in ['клиент', 'гость', 'карта', 'id']): mapping['client'] = df.columns[i]
        elif any(w in c for w in ['бариста', 'кассир', 'сотрудник']): mapping['staff'] = df.columns[i]
        elif any(w in c for w in ['категор', 'товар', 'наименован']): mapping['item'] = df.columns[i]
        elif any(w in c for w in ['сумм', 'выруч', 'оплат']): mapping['rev'] = df.columns[i]
        elif any(w in c for w in ['фудкост', 'себест']): mapping['cost'] = df.columns[i]
        elif any(w in c for w in ['погод', 'темп']): mapping['temp'] = df.columns[i]
    return mapping

# === 3. САЙДБАР ===
with st.sidebar:
    st.markdown("<h2 style='color:#F59E0B; font-weight:800;'>☕ ГОРЬКИЙ КОФЕ</h2>", unsafe_allow_html=True)
    st.markdown("<span style='color:#a8a29e; font-size:14px;'>BI-Панель Управления</span>", unsafe_allow_html=True)
    st.markdown("---")
    
    uploaded_file = st.file_uploader("📂 Загрузить выгрузку", type=['xlsx', 'csv'])
    if uploaded_file is None:
        st.info("💡 Включен Демо-режим")
        df_raw = generate_coffee_demo()
    else:
        df_raw = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        st.success("✅ Файл загружен")

    det = detect_columns(df_raw)
    all_cols = ['--- Нет ---'] + list(df_raw.columns)
    
    with st.expander("⚙️ Разметка колонок", expanded=False):
        c_date = st.selectbox("📅 Дата и время", df_raw.columns, index=df_raw.columns.get_loc(det['date']) if det['date'] else 0)
        c_rec = st.selectbox("🧾 Чек", df_raw.columns, index=df_raw.columns.get_loc(det['receipt']) if det['receipt'] else 0)
        c_client = st.selectbox("💳 Карта Гостя / Телефон", all_cols, index=all_cols.index(det['client']) if det['client'] in all_cols else 0)
        c_staff = st.selectbox("🧑‍🍳 Бариста", df_raw.columns, index=df_raw.columns.get_loc(det['staff']) if det['staff'] else 0)
        c_item = st.selectbox("🥐 Категория/Товар", df_raw.columns, index=df_raw.columns.get_loc(det['item']) if det['item'] else 0)
        c_rev = st.selectbox("💰 Сумма", df_raw.columns, index=df_raw.columns.get_loc(det['rev']) if det['rev'] else 0)
        c_cost = st.selectbox("📉 Фудкост (Себестоимость)", all_cols, index=all_cols.index(det['cost']) if det['cost'] in all_cols else 0)
        c_temp = st.selectbox("🌡 Погода (°C)", all_cols, index=all_cols.index(det['temp']) if det['temp'] in all_cols else 0)

    # ДИНАМИЧЕСКИЙ ФУДКОСТ (Если колонки нет в базе)
    global_fc = 0.3
    if c_cost == '--- Нет ---':
        st.markdown("---")
        st.warning("В базе нет колонки себестоимости.")
        global_fc = st.slider("Укажите средний фудкост сети (%):", 10, 60, 30) / 100.0

# Подготовка данных
df = df_raw.copy()
df['__Date'] = pd.to_datetime(df[c_date], errors='coerce').dropna()
df['__Receipt'] = df[c_rec].astype(str)
df['__Staff'] = df[c_staff].astype(str)
df['__Item'] = df[c_item].astype(str)
df['__Rev'] = pd.to_numeric(df[c_rev], errors='coerce').fillna(0)

if c_cost != '--- Нет ---': df['__Cost'] = pd.to_numeric(df[c_cost], errors='coerce').fillna(df['__Rev'] * global_fc)
else: df['__Cost'] = df['__Rev'] * global_fc

if c_client != '--- Нет ---': df['__Client'] = df[c_client].astype(str)
if c_temp != '--- Нет ---': df['__Temp'] = pd.to_numeric(df[c_temp], errors='coerce').fillna(15)

df['Date_Only'] = df['__Date'].dt.date

with st.sidebar:
    st.markdown("---")
    st.markdown("🎯 **Фильтры**")
    min_d, max_d = df['Date_Only'].min(), df['Date_Only'].max()
    date_range = st.date_input("Период", [min_d, max_d], min_value=min_d, max_value=max_d)

if len(date_range) == 2: df_f = df[(df['Date_Only'] >= date_range[0]) & (df['Date_Only'] <= date_range[1])]
else: df_f = df.copy()

# === 4. ИНТЕРФЕЙС ===
st.title("Операционная Аналитика")

total_rev = df_f['__Rev'].sum()
total_margin = total_rev - df_f['__Cost'].sum()
unique_receipts = df_f['__Receipt'].nunique()
avg_check = total_rev / unique_receipts if unique_receipts > 0 else 0
upt = len(df_f) / unique_receipts if unique_receipts > 0 else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("💰 Выручка", f"{int(total_rev):,} ₽".replace(",", " "))
c2.metric("✨ Маржинальная прибыль", f"{int(total_margin):,} ₽".replace(",", " "))
c3.metric("💳 Средний чек", f"{int(avg_check):,} ₽".replace(",", " "))
c4.metric("📈 UPT (Позиций в чеке)", f"{upt:.2f} шт")

# Авто-Инсайты
html = ""
if upt < 1.3: html += f"<div class='insight-box insight-danger'>🚨 <b>Слабые допродажи!</b> UPT = {upt:.2f}. Большинство гостей берут только 1 напиток и уходят без десерта. Проведите тренинг с бариста.</div>"
margin_pct = (total_margin / total_rev) * 100
if margin_pct < 60: html += f"<div class='insight-box insight-warning'>⚠️ <b>Высокий фудкост:</b> Ваша рентабельность по сырью упала до {margin_pct:.1f}%. Проверьте списания и рецептуры.</div>"
else: html += f"<div class='insight-box insight-success'>💎 <b>Здоровый фудкост:</b> Маржа {margin_pct:.1f}%. Отличный показатель для кофейни.</div>"
st.markdown(html, unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# ВКЛАДКИ
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🌤 Погода и Спрос", "👥 База Гостей (Лояльность)", "🧑‍🍳 Матрица Бариста", "🎯 Инжиниринг Меню", "🔮 ИИ-Прогноз"])

# --- ВКЛАДКА 1: ПОГОДА ---
with tab1:
    st.subheader("Как погода влияет на вашу кассу?")
    if c_temp != '--- Нет ---':
        weather_df = df_f.groupby('Date_Only').agg(Rev=('__Rev', 'sum'), Temp=('__Temp', 'mean')).reset_index()
        fig_w = make_subplots(specs=[[{"secondary_y": True}]])
        fig_w.add_trace(go.Bar(x=weather_df['Date_Only'], y=weather_df['Rev'], name="Выручка (₽)", marker_color="#F59E0B", opacity=0.8), secondary_y=False)
        fig_w.add_trace(go.Scatter(x=weather_df['Date_Only'], y=weather_df['Temp'], name="Температура (°C)", mode="lines+markers", marker_color="#10B981", line=dict(width=3)), secondary_y=True)
        
        fig_w.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=PLOTLY_FONT, legend=dict(font=dict(color="#fff")))
        fig_w.update_yaxes(title_text="Выручка", secondary_y=False, tickfont=dict(color="#F59E0B"))
        fig_w.update_yaxes(title_text="Температура (°C)", secondary_y=True, tickfont=dict(color="#10B981"))
        st.plotly_chart(fig_w, use_container_width=True, theme=None)
    else: st.warning("Загрузите данные с колонкой температуры.")

# --- ВКЛАДКА 2: ЛОЯЛЬНОСТЬ (RETENTION) - НОВАЯ ФИЧА ---
with tab2:
    st.subheader("Лояльность и Возвращаемость гостей")
    if c_client != '--- Нет ---':
        st.markdown("<span style='color:#a8a29e'>Сравнение выручки от Постоянных гостей (кто был больше 1 раза) и Новых.</span>", unsafe_allow_html=True)
        
        # Определяем новых и постоянных
        visits = df_f.groupby('__Client')['__Receipt'].nunique().reset_index()
        visits['Тип гостя'] = np.where(visits['__Receipt'] > 1, 'Постоянные гости', 'Новые гости')
        
        # Считаем выручку по типам
        client_rev = df_f.groupby('__Client')['__Rev'].sum().reset_index()
        merged_clients = pd.merge(visits, client_rev, on='__Client')
        
        type_summary = merged_clients.groupby('Тип гостя')['__Rev'].sum().reset_index()
        
        c_pie, c_bar = st.columns(2)
        with c_pie:
            fig_loyalty = px.pie(type_summary, names='Тип гостя', values='__Rev', hole=0.6, color_discrete_sequence=["#10B981", "#8B5CF6"])
            fig_loyalty.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=PLOTLY_FONT, margin=dict(t=20, b=20))
            st.plotly_chart(fig_loyalty, use_container_width=True, theme=None)
            
        with c_bar:
            freq = visits[visits['__Receipt'] > 1].groupby('__Receipt').size().reset_index(name='Кол-во гостей').head(10)
            fig_freq = px.bar(freq, x='__Receipt', y='Кол-во гостей', title="Частота визитов (Сколько раз возвращались)", color_discrete_sequence=["#F59E0B"])
            fig_freq.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=PLOTLY_FONT, xaxis_title="Кол-во визитов", yaxis_title="Гостей")
            st.plotly_chart(fig_freq, use_container_width=True, theme=None)
    else: st.warning("В загруженных данных нет колонки ID клиента / Карты лояльности.")

# --- ВКЛАДКА 3: МАТРИЦА БАРИСТА (ИСПРАВЛЕНА) ---
with tab3:
    st.subheader("Кто из персонала Кассир, а кто — Продавец?")
    st.markdown("<span style='color:#a8a29e'>Если бариста в левом нижнем углу — он просто пробивает эспрессо. Ищите тех, кто справа сверху! Наведите мышку на точку.</span>", unsafe_allow_html=True)
    
    staff_df = df_f.groupby('__Staff').agg(Rev=('__Rev', 'sum'), Checks=('__Receipt', 'nunique'), Items=('__Item', 'count')).reset_index()
    staff_df['Avg_Check'] = staff_df['Rev'] / staff_df['Checks']
    staff_df['UPT'] = staff_df['Items'] / staff_df['Checks']
    
    fig_staff = px.scatter(staff_df, x='UPT', y='Avg_Check', size='Rev', color='__Staff', 
                           hover_name='__Staff', text='__Staff', color_discrete_sequence=CUSTOM_COLORS)
    # Фикс наложения: обводка, прозрачность, позиция текста
    fig_staff.update_traces(textposition='top center', marker=dict(opacity=0.85, line=dict(width=1.5, color='rgba(255,255,255,0.8)')))
    fig_staff.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=PLOTLY_FONT, xaxis_title="UPT (Допродажи в чеке)", yaxis_title="Средний Чек (₽)", showlegend=False)
    st.plotly_chart(fig_staff, use_container_width=True, theme=None)

# --- ВКЛАДКА 4: ИНЖИНИРИНГ МЕНЮ ---
with tab4:
    st.subheader("Оптимизация Меню (Поиск 'Собак' и 'Звезд')")
    menu_df = df_f.groupby('__Item').agg(Rev=('__Rev', 'sum'), Cost=('__Cost', 'sum'), Qty=('__Item', 'count')).reset_index()
    menu_df['Margin'] = menu_df['Rev'] - menu_df['Cost']
    menu_df = menu_df.sort_values('Margin', ascending=False)
    
    menu_df['Доля %'] = (menu_df['Margin'] / menu_df['Margin'].sum()) * 100
    menu_df['Класс'] = np.where(menu_df['Доля %'].cumsum() <= 80, 'A (Звезды - Продвигать)', np.where(menu_df['Доля %'].cumsum() <= 95, 'B (Рабочие лошадки)', 'C (Собаки - Убрать)'))
    
    def color_menu(val):
        if 'A' in val: return 'color: #10B981; font-weight:bold;'
        elif 'C' in val: return 'color: #ef4444; font-weight:bold;'
        return 'color: #F59E0B;'
        
    try: st.dataframe(menu_df[['__Item', 'Margin', 'Qty', 'Класс']].rename(columns={'__Item': 'Позиция', 'Margin': 'Валовая Маржа (₽)', 'Qty': 'Продано (шт)'}).style.map(color_menu, subset=['Класс']), hide_index=True, use_container_width=True)
    except: st.dataframe(menu_df[['__Item', 'Margin', 'Qty', 'Класс']].rename(columns={'__Item': 'Позиция', 'Margin': 'Валовая Маржа (₽)', 'Qty': 'Продано (шт)'}).style.applymap(color_menu, subset=['Класс']), hide_index=True, use_container_width=True)

# --- ВКЛАДКА 5: ML-ПРОГНОЗ ---
with tab5:
    st.subheader("ИИ-Прогноз спроса (Для Закупок)")
    df_prophet = df_f.groupby('Date_Only')["__Rev"].sum().reset_index()
    df_prophet.columns = ['ds', 'y']
    
    if PROPHET_AVAILABLE and len(df_prophet) > 14:
        m = Prophet(yearly_seasonality=False, daily_seasonality=False)
        m.fit(df_prophet)
        forecast = m.predict(m.make_future_dataframe(periods=14))
        
        fig_ml = go.Figure()
        fig_ml.add_trace(go.Scatter(x=df_prophet['ds'], y=df_prophet['y'], mode='lines', name='Факт', line=dict(color='#F59E0B', width=3)))
        fig_ml.add_trace(go.Scatter(x=forecast['ds'].iloc[-14:], y=forecast['yhat'].iloc[-14:], mode='lines', name='Прогноз', line=dict(color='#10B981', width=3, dash='dash')))
        
        fig_ml.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=PLOTLY_FONT, hovermode="x unified", legend=dict(font=dict(color="#fff")))
        st.plotly_chart(fig_ml, use_container_width=True, theme=None)
    else:
        st.info("💡 Недостаточно данных для прогноза (нужно > 14 дней).")
