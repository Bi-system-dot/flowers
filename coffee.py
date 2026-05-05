import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import date, timedelta
import io

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False

# === 1. НАСТРОЙКИ СТРАНИЦЫ И COFFEE-ДИЗАЙН ===
st.set_page_config(page_title="NEXUS | Управление Кофейней", page_icon="☕", layout="wide")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    /* Глубокий темный фон (Эспрессо) */
    .stApp { background-color: #161210; color: #f5f5f4; font-family: 'Inter', sans-serif; }
    
    /* Карточки KPI (Glassmorphism с золотым свечением) */
    div[data-testid="metric-container"] {
        background: linear-gradient(145deg, rgba(35, 28, 25, 0.9) 0%, rgba(20, 16, 14, 0.95) 100%);
        border: 1px solid rgba(245, 158, 11, 0.25);
        padding: 20px;
        border-radius: 16px;
        box-shadow: 0 10px 30px -10px rgba(245, 158, 11, 0.2);
        transition: all 0.3s ease;
    }
    div[data-testid="metric-container"]:hover { 
        transform: translateY(-5px); 
        border: 1px solid rgba(245, 158, 11, 0.8); 
        box-shadow: 0 15px 35px -10px rgba(245, 158, 11, 0.4);
    }
    [data-testid="stMetricValue"] { font-size: 34px !important; color: #F59E0B !important; font-weight: 800 !important; letter-spacing: -1px;}
    [data-testid="stMetricLabel"] { color: #d6d3d1 !important; font-weight: 600 !important; font-size: 15px !important; }
    
    /* Плашки Auto-Аналитика */
    .insight-box { padding: 18px; border-radius: 12px; margin-bottom: 12px; border-left: 5px solid; font-weight: 500; font-size: 15px;}
    .insight-danger { background: rgba(239, 68, 68, 0.1); border-color: #ef4444; color: #fca5a5; }
    .insight-warning { background: rgba(245, 158, 11, 0.1); border-color: #f59e0b; color: #fcd34d; }
    .insight-success { background: rgba(16, 185, 129, 0.1); border-color: #10b981; color: #6ee7b7; }
    
    /* Вкладки */
    .stTabs [data-baseweb="tab-list"] { background-color: transparent; border-bottom: 1px solid #444; }
    .stTabs [data-baseweb="tab"] { color: #a8a29e; font-weight: 600; padding-top: 15px; padding-bottom: 15px; }
    .stTabs [aria-selected="true"] { color: #F59E0B !important; border-bottom: 3px solid #F59E0B !important; }
    </style>
    """, unsafe_allow_html=True)

# Новая контрастная палитра (Карамель, Сливки, Ягода, Матча, Лаванда, Голубика)
CUSTOM_COLORS = ["#F59E0B", "#FEF3C7", "#F43F5E", "#10B981", "#8B5CF6", "#38BDF8"]

# === ОСТАВЛЯЕМ ВЕСЬ БЭКЕНД БЕЗ ИЗМЕНЕНИЙ ===
def detect_coffee_columns(df):
    mapping = {'date': None, 'value': None, 'category': None, 'shop': None}
    cols = [c.lower() for c in df.columns]
    for i, col in enumerate(cols):
        if any(w in col for w in ['дат', 'врем', 'date', 'time', 'открыт']): mapping['date'] = df.columns[i]
        elif any(w in col for w in ['заведен', 'точк', 'касса', 'магазин']): mapping['shop'] = df.columns[i]
        elif any(w in col for w in ['категор', 'блюд', 'наименован', 'товар']): mapping['category'] = df.columns[i]
    num_cols = df.select_dtypes(include=[np.number]).columns
    for col in num_cols:
        if any(w in col.lower() for w in ['сумм', 'выруч', 'итого', 'оплат', 'total']):
            mapping['value'] = col
            break
    if not mapping['value'] and len(num_cols) > 0: mapping['value'] = num_cols[0]
    return mapping

@st.cache_data
def generate_coffee_demo():
    np.random.seed(42)
    days = pd.date_range(end=date.today(), periods=60)
    cats = ["Кофе (Классика)", "Авторские напитки", "Выпечка (Круассаны)", "Десерты", "Сэндвичи / Завтраки", "Чай / Матча"]
    shops = ["Точка: БЦ (Офисы)", "Точка: Парк", "Точка: Спальный р-н"]
    data = []
    for _ in range(6000):
        shop = np.random.choice(shops, p=[0.4, 0.3, 0.3])
        day = np.random.choice(days)
        if "БЦ" in shop: hour = int(np.random.normal(9, 1.5))
        elif "Парк" in shop: hour = int(np.random.normal(15, 3))
        else: hour = int(np.random.normal(12, 4))
        hour = max(7, min(22, hour))
        timestamp = pd.Timestamp(day) + pd.Timedelta(hours=hour, minutes=np.random.randint(0, 59))
        cat = np.random.choice(cats, p=[0.4, 0.15, 0.15, 0.1, 0.1, 0.1])
        price = np.random.randint(180, 450) if "Кофе" in cat or "Чай" in cat else np.random.randint(250, 600)
        has_food = "Да" if cat in ["Выпечка (Круассаны)", "Десерты", "Сэндвичи / Завтраки"] else np.random.choice(["Да", "Нет"], p=[0.25, 0.75])
        data.append({"Дата и Время": timestamp, "Кофейня": shop, "Категория": cat, "Сумма чека": price, "Еда в чеке (Допродажа)": has_food})
    return pd.DataFrame(data)

with st.sidebar:
    st.markdown("## ☕ NEXUS Coffee")
    st.markdown("Аналитика сети кофеен")
    st.markdown("---")
    uploaded_file = st.file_uploader("📂 Загрузить файл (iiko/Excel)", type=['xlsx', 'csv'])
    if uploaded_file is None:
        st.info("💡 Демо-режим (Сеть из 3 кофеен)")
        df_raw = generate_coffee_demo()
    else:
        df_raw = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        st.success("✅ Файл загружен")

    detected = detect_coffee_columns(df_raw)
    with st.expander("⚙️ Настройка колонок", expanded=False):
        col_date = st.selectbox("📅 Дата и время:", df_raw.columns, index=df_raw.columns.get_loc(detected['date']) if detected['date'] else 0)
        col_val = st.selectbox("💰 Сумма чека:", df_raw.columns, index=df_raw.columns.get_loc(detected['value']) if detected['value'] else 0)
        col_cat = st.selectbox("🥐 Категория:", df_raw.columns, index=df_raw.columns.get_loc(detected['category']) if detected['category'] else 0)
        shop_opts = ['Без разделения (1 точка)'] + list(df_raw.columns)
        shop_idx = (df_raw.columns.get_loc(detected['shop']) + 1) if detected['shop'] else 0
        col_shop = st.selectbox("🏪 Точка продаж:", shop_opts, index=shop_idx)
        col_food = [c for c in df_raw.columns if 'допродаж' in c.lower() or 'еда' in c.lower()]
        col_upsell = st.selectbox("🛍️ Метка допродажи (Опц.):", ['Нет'] + list(df_raw.columns), index=df_raw.columns.get_loc(col_food[0])+1 if col_food else 0)

df = df_raw.copy()
df['__Date'] = pd.to_datetime(df[col_date], errors='coerce').dropna()
df['__Value'] = pd.to_numeric(df[col_val], errors='coerce').fillna(0)
df['__Category'] = df[col_cat].astype(str)
df['__Shop'] = df[col_shop].astype(str) if col_shop != 'Без разделения (1 точка)' else 'Главная кофейня'
df['__Upsell'] = df[col_upsell].astype(str) if col_upsell != 'Нет' else np.random.choice(["Да", "Нет"], p=[0.3, 0.7], size=len(df))

df['Date_Only'] = df['__Date'].dt.date
df['Hour'] = df['__Date'].dt.hour
df['Day_Name'] = df['__Date'].dt.day_name()

with st.sidebar:
    st.markdown("---")
    st.subheader("🎯 Фильтры")
    min_d, max_d = df['Date_Only'].min(), df['Date_Only'].max()
    date_range = st.date_input("Период", [min_d, max_d], min_value=min_d, max_value=max_d)
    selected_shops = st.multiselect("Кофейни", options=df['__Shop'].unique(), default=df['__Shop'].unique())
    st.markdown("---")
    st.subheader("🥐 Списания витрины (Брак)")
    spoil_pct = st.slider("% вечерних списаний", 0.0, 15.0, 6.0, 0.5)

if len(date_range) == 2: df_f = df[(df['Date_Only'] >= date_range[0]) & (df['Date_Only'] <= date_range[1])]
else: df_f = df.copy()
if selected_shops: df_f = df_f[df_f['__Shop'].isin(selected_shops)]

# === 5. ИНТЕРФЕЙС И ГРАФИКИ (ОБНОВЛЕННЫЙ ДИЗАЙН) ===
st.title("☕ Дашборд Владельца Кофейни")

total_rev = df_f['__Value'].sum()
total_checks = len(df_f)
avg_check = total_rev / total_checks if total_checks > 0 else 0
upsell_rate = (len(df_f[df_f['__Upsell'].isin(['Да', 'Yes', 'True', '1'])]) / total_checks) * 100 if total_checks > 0 else 0
spoilage_lost = total_rev * (spoil_pct / 100)

c1, c2, c3, c4 = st.columns(4)
c1.metric("💰 Выручка", f"{int(total_rev):,} ₽".replace(",", " "))
c2.metric("💳 Средний чек", f"{int(avg_check):,} ₽".replace(",", " "))
c3.metric("📈 Допродажи (Еда)", f"{upsell_rate:.1f}%")
c4.metric("🗑️ Убытки (Списание)", f"- {int(spoilage_lost):,} ₽".replace(",", " "))

insights = ""
if upsell_rate < 35:
    insights += f"<div class='insight-box insight-danger'>🚨 <b>Провал в допродажах:</b> {100-upsell_rate:.1f}% гостей берут ТОЛЬКО напиток. Бариста не предлагают десерты. Вы теряете прибыль!</div>"
else:
    insights += f"<div class='insight-box insight-success'>✨ <b>Отличные допродажи:</b> Бариста активно продают витрину. Так держать!</div>"
if spoil_pct > 5:
    insights += f"<div class='insight-box insight-warning'>⚠️ <b>Слишком много списаний:</b> Вы выбросили круассанов на {int(spoilage_lost):,} ₽. ИИ-прогноз поможет оптимизировать заказ.</div>"

st.markdown(insights, unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["🕒 Нагрузка (Графики бариста)", "🥐 Аналитика Меню", "🧠 ИИ-Прогноз заготовок"])

# Белый/Светло-бежевый цвет для всего текста на графиках
TEXT_COLOR = "#f5f5f4"
PLOTLY_FONT = dict(family="Inter, sans-serif", size=13, color=TEXT_COLOR)

# --- ВКЛАДКА 1: ТЕПЛОВАЯ КАРТА ---
with tab1:
    st.subheader("👥 Пиковые часы (Очереди)")
    st.markdown("<span style='color:#a8a29e'>Яркие квадраты — часы пик. Если бариста работает один, клиенты разворачиваются и уходят.</span>", unsafe_allow_html=True)
    
    if df_f['Hour'].nunique() > 1:
        pivot_hours = df_f.groupby(['Day_Name', 'Hour']).size().reset_index(name='Чеков')
        days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        rus_days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
        
        pivot_hours['Day_Name'] = pivot_hours['Day_Name'].map(dict(zip(days_order, rus_days)))
        heatmap_data = pivot_hours.pivot(index='Day_Name', columns='Hour', values='Чеков').fillna(0).reindex(rus_days)
        
        fig_heat = px.imshow(heatmap_data, text_auto=".0f", color_continuous_scale="solar", aspect="auto",
                             labels=dict(x="Время суток (Часы)", y="", color="Пробито чеков"))
        
        fig_heat.update_layout(
            template="plotly_dark", 
            plot_bgcolor='rgba(0,0,0,0)', 
            paper_bgcolor='rgba(0,0,0,0)',
            font=PLOTLY_FONT,
            xaxis=dict(tickfont=dict(color=TEXT_COLOR), title_font=dict(color=TEXT_COLOR)),
            yaxis=dict(tickfont=dict(color=TEXT_COLOR)),
            margin=dict(l=0, r=0, t=10, b=0)
        )
        # Отключаем принудительную тему Streamlit через theme=None
        st.plotly_chart(fig_heat, use_container_width=True, theme=None)
    else: 
        st.warning("⚠️ В данных нет времени пробития чеков.")

# --- ВКЛАДКА 2: МЕНЮ И ТОЧКИ ---
with tab2:
    col_cats, col_shops = st.columns(2)
    
    with col_cats:
        st.subheader("🍩 Структура продаж")
        cat_sales = df_f.groupby('__Category')['__Value'].sum().reset_index().sort_values('__Value', ascending=False)
        fig_cats = px.pie(cat_sales, names='__Category', values='__Value', hole=0.65, 
                          color_discrete_sequence=CUSTOM_COLORS)
        
        fig_cats.update_layout(
            template="plotly_dark",
            plot_bgcolor='rgba(0,0,0,0)', 
            paper_bgcolor='rgba(0,0,0,0)', 
            font=PLOTLY_FONT,
            # Явно красим легенду в белый цвет
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5, font=dict(color=TEXT_COLOR)), 
            margin=dict(t=10, b=10, l=0, r=0)
        )
        fig_cats.update_traces(textinfo='percent', textfont_size=14, hovertemplate="%{label}: %{value:,.0f} ₽")
        st.plotly_chart(fig_cats, use_container_width=True, theme=None)

    with col_shops:
        st.subheader("🏪 Выручка по филиалам")
        shop_sales = df_f.groupby('__Shop')['__Value'].sum().reset_index().sort_values('__Value', ascending=True)
        fig_shops = px.bar(shop_sales, x='__Value', y='__Shop', orientation='h', 
                           color='__Shop', color_discrete_sequence=CUSTOM_COLORS)
        
        fig_shops.update_layout(
            template="plotly_dark",
            showlegend=False, 
            plot_bgcolor='rgba(0,0,0,0)', 
            paper_bgcolor='rgba(0,0,0,0)', 
            font=PLOTLY_FONT,
            # Убираем технические названия осей (title="") и красим цифры в белый
            xaxis=dict(showgrid=False, title="", tickfont=dict(color=TEXT_COLOR)), 
            yaxis=dict(showgrid=False, title="", tickfont=dict(color=TEXT_COLOR)),
            margin=dict(t=10, b=10, l=0, r=0)
        )
        fig_shops.update_traces(width=0.4) 
        st.plotly_chart(fig_shops, use_container_width=True, theme=None)

# --- ВКЛАДКА 3: MACHINE LEARNING ---
with tab3:
    st.subheader("🔮 ИИ-Прогноз спроса (Для заготовок)")
    st.markdown("<span style='color:#a8a29e'>Помогает понять, сколько молока заказывать и сколько выпечки дефростировать на завтра.</span>", unsafe_allow_html=True)
    
    df_prophet = df_f.groupby('Date_Only')["__Value"].sum().reset_index()
    df_prophet.columns = ['ds', 'y']
    
    if PROPHET_AVAILABLE and len(df_prophet) > 14:
        with st.spinner("Анализируем тренды..."):
            m = Prophet(yearly_seasonality=False, daily_seasonality=False)
            m.fit(df_prophet)
            future = m.make_future_dataframe(periods=14)
            forecast = m.predict(future)
            
            fig_ml = go.Figure()
            fig_ml.add_trace(go.Scatter(x=df_prophet['ds'], y=df_prophet['y'], mode='lines', name='Факт', line=dict(color='#F59E0B', width=3, shape='spline')))
            fig_ml.add_trace(go.Scatter(x=forecast['ds'].iloc[-14:], y=forecast['yhat'].iloc[-14:], mode='lines', name='Прогноз', line=dict(color='#10B981', width=3, dash='dash', shape='spline')))
            fig_ml.add_trace(go.Scatter(x=forecast['ds'].iloc[-14:], y=forecast['yhat_upper'].iloc[-14:], mode='lines', line=dict(width=0), showlegend=False))
            fig_ml.add_trace(go.Scatter(x=forecast['ds'].iloc[-14:], y=forecast['yhat_lower'].iloc[-14:], fill='tonexty', mode='lines', line=dict(width=0), fillcolor='rgba(16, 185, 129, 0.15)', name='Дов. интервал'))
            
            fig_ml.update_layout(
                template="plotly_dark", 
                plot_bgcolor='rgba(0,0,0,0)', 
                paper_bgcolor='rgba(0,0,0,0)', 
                font=PLOTLY_FONT,
                hovermode="x unified",
                # Красим легенду и оси в белый
                legend=dict(font=dict(color=TEXT_COLOR)),
                xaxis=dict(showgrid=False, title="", tickfont=dict(color=TEXT_COLOR)), 
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", title="", tickfont=dict(color=TEXT_COLOR))
            )
            st.plotly_chart(fig_ml, use_container_width=True, theme=None)
    else:
        st.info("💡 Недостаточно данных для прогноза (нужно > 14 дней).")