# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : 台股戰情室 Streamlit 監控儀表板 (UI 側邊欄優化版)
# 檔案名稱 : app.py
# 程式版本 : v03.26 (拆除 form 結構並強化 SVG 鎖白渲染)
# ==========================================================

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import os
import json
import urllib.request
import datetime
import pytz
import sqlite3
from streamlit_autorefresh import st_autorefresh
from dataclasses import dataclass

# --- 頁面基本設定 ---
st.set_page_config(
    page_title="台股戰情室監控大廳",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================
# Prt.00 全域常數與設定
# ==============================
APP_VERSION = "v03.26"
STRATEGY_VERSION = "v02.23"
DB_NAME = "tw50_strategy.db"
TAIPEI_TZ = pytz.timezone('Asia/Taipei')

@dataclass
class StrategyConfig:
    ma_fast: int = 20
    ma_slow: int = 60
    vma_period: int = 5
    vol_ratio: float = 1.3
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 20
    atr_multiplier: float = 2.0
    setup_score_threshold: int = 45
    max_setup_days: int = 5
    capital_weight_per_trade: float = 0.10

def safe_rerun():
    if hasattr(st, 'rerun'): st.rerun()
    else: st.experimental_rerun()

# ==============================
# Prt.01 Telegram API 設定
# ==============================
def send_telegram_alert(message):
    token = os.environ.get('TELEGRAM_TOKEN', st.secrets.get("TELEGRAM_TOKEN"))
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', st.secrets.get("TELEGRAM_CHAT_ID"))
    if not token or not chat_id: return False, "找不到設定"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": str(chat_id), "text": message, "parse_mode": "HTML"}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try: 
        urllib.request.urlopen(req)
        return True, "發送成功"
    except Exception as e: return False, str(e)

# ==============================
# Prt.02 頂級深色優化視覺 CSS 
# ==============================
st.markdown(r'''
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [data-testid="stAppViewContainer"] { font-family: 'Inter', sans-serif !important; }
[data-testid="stActionElements"] { display: none !important; }
header[data-testid="stHeader"] { background-color: transparent !important; }
.main .block-container { padding-top: 1.5rem !important; margin-top: -30px !important; }
html, body, [data-testid="stAppViewContainer"] { background-color: #0e1117 !important; color: #f1f5f9 !important; }
[data-testid="stSidebar"] { background-color: #171a23 !important; border-right: 1px solid #2d3748 !important; }
[data-testid="stVerticalBlockBorderWrapper"] { background-color: #1e293b !important; border: 1px solid #94a3b8 !important; border-radius: 12px !important; padding: 15px !important; margin-bottom: 10px !important; }
[data-testid="collapsedControl"] svg, [data-testid="stSidebarCollapseButton"] svg, button[kind="header"] svg, [data-testid="stSidebar"] svg { color: #ffffff !important; fill: #ffffff !important; stroke: #ffffff !important; }
.stTextInput div[data-baseweb="input"], .stSelectbox div[data-baseweb="select"] > div { background-color: #0f172a !important; border: 1px solid #475569 !important; border-radius: 8px !important;  }
.stTextInput input { color: #ffffff !important; background-color: transparent !important; }
.stSelectbox div[data-baseweb="select"] span { color: #ffffff !important; }
[data-testid="stSidebar"] h3 { color: #ffffff !important; font-size: 1.1rem !important; font-weight: 700 !important; margin-bottom: 15px !important; }
.stButton > button { background: linear-gradient(135deg, #3b82f6, #1d4ed8) !important; color: white !important; border: none !important; border-radius: 8px !important; font-weight: 600 !important; }
/* TW50 專用卡片 */
h1.main-title { color: #f8fafc; font-weight: 800; border-bottom: 2px solid #1e293b; margin-bottom: 20px; font-size: 1.8rem; }
.flex-matrix-container { display: flex; flex-wrap: wrap; gap: 14px; width: 100%; }
.stock-compact-card { background-color: #171a23; border: 1px solid #2d3748; border-radius: 12px; padding: 16px; width: 295px !important; box-sizing: border-box; }
.card-title-txt { font-size: 1.25rem; font-weight: 700; color: #ffffff; }
.card-price-txt { color: #38bdf8; font-size: 1.9rem; font-weight: 700; }
.score-highlight { color: #facc15; font-size: 1.6rem; font-weight: 900; }
.custom-alert-box { min-height: 38px; display: flex; align-items: center; justify-content: center; border-radius: 6px; margin-top: 10px; font-size: 0.82rem; font-weight: 700; }
.action-buy { color: #f2cc60; background-color: rgba(242, 204, 96, 0.15) !important; border: 1px dashed #f2cc60; }
.action-wait { color: #94a3b8; background-color: rgba(148, 163, 184, 0.1) !important; border: 1px dashed #475569; }
</style>
''', unsafe_allow_html=True)

# ==============================
# Prt.03~05 邏輯層 (與 v03.25 一致)
# ==============================
def clean_dataframe(df):
    if df.empty: return df
    if 'Datetime' in df.columns: df = df.rename(columns={'Datetime': 'Date'})
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        try:
            if hasattr(df['Date'].dt, 'tz') and df['Date'].dt.tz is not None:
                df['Date'] = df['Date'].dt.tz_localize(None)
        except: pass
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
    return df

@st.cache_data(ttl=60)
def load_csv_data():
    file_path = "temp_data.csv"
    if not os.path.exists(file_path): return pd.DataFrame(), "⚠️ 找不到資料檔"
    try:
        df = pd.read_csv(file_path)
        return clean_dataframe(df), "✅ 載入成功"
    except Exception as e: return pd.DataFrame(), str(e)

@st.cache_data(ttl=300)
def fetch_custom_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo").reset_index()
        df['ticker'] = ticker
        return clean_dataframe(df)
    except: return None

def calculate_dashboard_metrics(df_stock, config: StrategyConfig):
    df = df_stock.dropna(subset=['Close']).sort_values('Date').copy()
    if len(df) < 24: return None
    df['MA_Fast'] = df['Close'].rolling(config.ma_fast).mean().fillna(0)
    df['MA_Slow'] = df['Close'].rolling(config.ma_slow).mean().fillna(0)
    df['V_MA'] = df['Volume'].rolling(config.vma_period).mean().fillna(0)
    ema_fast = df['Close'].ewm(span=config.macd_fast, adjust=False).mean()
    ema_slow = df['Close'].ewm(span=config.macd_slow, adjust=False).mean()
    df['DIF'] = ema_fast - ema_slow
    df['DEA'] = df['DIF'].ewm(span=config.macd_signal, adjust=False).mean()
    df['MACD_Hist'] = (df['DIF'] - df['DEA']).fillna(0)
    df['TR'] = np.maximum(df['High']-df['Low'], np.maximum(abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))))
    df['ATR'] = df['TR'].rolling(window=config.atr_period).mean().fillna(0)
    delta = df['Close'].diff()
    up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
    for p in [6, 14, 24]:
        df[f'RSI_{p}'] = 100 - (100 / (1 + (up.ewm(com=p-1).mean() / down.ewm(com=p-1).mean().replace(0, 1e-9))))
    today = df.iloc[-1]
    yest = df.iloc[-2]
    res = {
        'Date': today['Date'], 'Close': today['Close'], 'High': today['High'],
        'Score': int(sum([15 if today['MACD_Hist'] > yest['MACD_Hist'] else 0, 10 if today['Close'] > today['MA_Fast'] else 0, 15 if today['MA_Fast'] > df['MA_Fast'].iloc[-6] else 0, 10 if today['MA_Fast'] > today['MA_Slow'] else 0, 10 if today['Volume'] > (today['V_MA'] * config.vol_ratio) else 0])),
        's1': 15 if today['MACD_Hist'] > yest['MACD_Hist'] else 0, 's2': 10 if today['Close'] > today['MA_Fast'] else 0, 's3': 15 if today['MA_Fast'] > df['MA_Fast'].iloc[-6] else 0, 's4': 10 if today['MA_Fast'] > today['MA_Slow'] else 0, 's5': 10 if today['Volume'] > (today['V_MA'] * config.vol_ratio) else 0,
        'RSI_6': today['RSI_6'], 'RSI_14': today['RSI_14'], 'RSI_24': today['RSI_24'], 'ATR': today['ATR']
    }
    return res

def generate_performance_report(version, config: StrategyConfig, db_name=DB_NAME):
    try:
        with sqlite3.connect(db_name) as conn:
            df = pd.read_sql_query("SELECT profit_pct FROM backtest_trades WHERE version = ?", conn, params=(version,))
        if df.empty: return "無回測資料"
        return f"勝率: {(len(df[df['profit_pct']>0])/len(df))*100:.1f}%, 總交易: {len(df)} 筆"
    except: return "資料庫錯誤"

# ==============================
# Prt.06 主程式
# ==============================
def main():
    st.markdown('<h1 class="main-title">📈 台股 50 戰情室監控大廳</h1>', unsafe_allow_html=True)
    config = StrategyConfig()
    df_raw, _ = load_csv_data()
    combined_df = df_raw.copy()
    if 'custom_watch' in st.session_state:
        for ct in st.session_state.custom_watch:
            cdf = fetch_custom_stock(ct)
            if cdf is not None: combined_df = pd.concat([combined_df, cdf], ignore_index=True)
    
    display_list = []
    for tk in combined_df['ticker'].unique():
        df_tk = combined_df[combined_df['ticker'] == tk]
        data = calculate_dashboard_metrics(df_tk, config)
        if data:
            data['ticker'] = tk
            display_list.append(data)
    display_list = sorted(display_list, key=lambda x: x.get('Score', 0), reverse=True)

    with st.sidebar:
        with st.container(border=True): st.markdown("### ⚙️ 控制與設定面板")
        with st.container(border=True):
            st.markdown("### ➕ 新增監測股票")
            nt = st.text_input("輸入代號 (例: 2330.TW)")
            if st.button("➕ 確認輸入", use_container_width=True) and nt:
                if 'custom_watch' not in st.session_state: st.session_state.custom_watch = []
                if nt.upper() not in st.session_state.custom_watch: st.session_state.custom_watch.append(nt.upper())
                safe_rerun()
        with st.container(border=True):
            st.markdown("### 🗑️ 移除監測清單")
            if 'custom_watch' in st.session_state and st.session_state.custom_watch:
                del_sym = st.selectbox("刪除目標", st.session_state.custom_watch)
                if st.button("確認刪除", use_container_width=True):
                    st.session_state.custom_watch.remove(del_sym)
                    safe_rerun()
        with st.container(border=True):
            st.markdown("### 🛠️ 手動測試推播")
            if st.button("發送測試", use_container_width=True):
                send_telegram_alert("測試訊息：系統正常")
                st.success("已送出")
        st.markdown(
            f"""<div style="background-color:#1e293b; padding:12px; border-radius:8px; border:1px solid #475569; text-align:center;">
                <div style="color:#94a3b8; font-size:0.8rem;">系統當前版本</div>
                <div style="color:#38bdf8; font-size:1.1rem; font-weight:700;">{APP_VERSION}</div>
            </div>""", unsafe_allow_html=True
        )

    html_cards = '<div class="flex-matrix-container">'
    for d in display_list:
        action_html = f'<div class="custom-alert-box {("action-buy" if d["Score"] >= config.setup_score_threshold else "action-wait")}">{"🎯 突破買進" if d["Score"] >= config.setup_score_threshold else "⏳ 觀察動能"}</div>'
        html_cards += f'''<div class="stock-compact-card">
            <div class="card-title-txt">{d["ticker"]} <span class="score-highlight">{d["Score"]}</span></div>
            <div class="card-price-txt">NT$ {d["Close"]:.2f}</div>
            {action_html}</div>'''
    st.markdown(html_cards + '</div>', unsafe_allow_html=True)
    st_autorefresh(interval=30000)

if __name__ == "__main__":
    main()
