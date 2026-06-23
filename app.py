# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : 台股戰情室 Streamlit 監控儀表板
# 檔案名稱 : app.py
# 策略版本 : v03.02 (自訂股票輸入修復與動態抓取版)
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 功能說明：
# 1. 自動讀取 main.py 產出的 temp_data.csv
# 2. 側邊欄支援動態新增股票 (使用 st.form 防刷新干擾)
# 3. 科技深色儀表板切版與股票小卡渲染
# 4. Telegram 5 分鐘區塊防洗版推播 (整合環境變數讀取)
# 5. 模組化區塊 (Prt.00 ~ Prt.07) 方便後續擴充
# ==========================================================

# ==============================
# Prt.00 系統設定與套件匯入
# ==============================
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import os
import json
import urllib.request
import datetime
import pytz
from streamlit_autorefresh import st_autorefresh

# --- 頁面基本設定 ---
st.set_page_config(
    page_title="台股戰情室監控大廳",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

APP_VERSION = "v03.02"
TAIPEI_TZ = pytz.timezone('Asia/Taipei')

# ==============================
# Prt.01 Telegram API 設定
# ==============================
def send_telegram_alert(message):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("未設定 Telegram 金鑰，跳過推播。")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"❌ Telegram 推播失敗: {e}")

# ==============================
# Prt.02 頁面與 CSS 全域設定
# ==============================
st.markdown('''
<style>
    .stApp {
        background-color: #0e1117;
        color: #c9d1d9;
    }
    .main-title {
        color: #58a6ff;
        font-weight: 800;
        text-align: center;
        padding-bottom: 20px;
        border-bottom: 2px solid #30363d;
        margin-bottom: 20px;
    }
    .stock-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 20px;
        justify-content: flex-start;
    }
    .stock-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-left: 4px solid #58a6ff;
        border-radius: 8px;
        padding: 15px;
        width: 300px;
        min-height: 180px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .stock-card:hover {
        border-left: 4px solid #3fb950;
        box-shadow: 0 4px 12px rgba(63, 185, 80, 0.2);
    }
    .stock-title { font-size: 1.2rem; font-weight: bold; color: #ffffff; margin-bottom: 10px; }
    .stock-price { font-size: 1.8rem; font-weight: bold; color: #ff7b72; }
    .alert-box { margin-top: 10px; min-height: 40px; font-size: 0.9rem; color: #f2cc60; border-top: 1px dashed #30363d; padding-top: 8px; }
    .empty-alert { margin-top: 10px; min-height: 40px; border-top: 1px dashed #30363d; padding-top: 8px; color: transparent; }
</style>
''', unsafe_allow_html=True)

# ==============================
# Prt.03 資料讀取 (CSV 與動態 yfinance)
# ==============================
@st.cache_data(ttl=60)
def load_csv_data():
    file_path = "temp_data.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame(), "⚠️ 找不到資料檔 (temp_data.csv)。"
    try:
        df = pd.read_csv(file_path)
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
        return df, "✅ 資料載入成功"
    except Exception as e:
        return pd.DataFrame(), f"❌ 讀取失敗: {e}"

@st.cache_data(ttl=300) # 自訂股票每 5 分鐘抓一次避免限制
def fetch_custom_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="3mo") # 抓3個月計算RSI24
        if df.empty: return None
        df = df.reset_index()
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
        df['ticker'] = ticker
        return df[['ticker', 'Date', 'Close']]
    except:
        return None

# ==============================
# Prt.04 技術指標計算
# ==============================
def calculate_indicators(df_stock):
    df_stock = df_stock.sort_values('Date').copy()
    delta = df_stock['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    
    for period in [6, 14, 24]:
        ema_up = up.ewm(com=period-1, adjust=False).mean()
        ema_down = down.ewm(com=period-1, adjust=False).mean()
        rs = ema_up / ema_down
        df_stock[f'RSI_{period}'] = 100 - (100 / (1 + rs))
        
    return df_stock.iloc[-1]

# ==============================
# Prt.05 推播防呆機制
# ==============================
def check_and_push_alert(ticker, price, rsi_status):
    now = datetime.datetime.now(TAIPEI_TZ)
    interval_block = now.minute // 5 
    
    if 'push_history' not in st.session_state:
        st.session_state.push_history = {}
        
    history_key = f"{ticker}_block"
    last_pushed_block = st.session_state.push_history.get(history_key, -1)
    
    if interval_block != last_pushed_block and "多頭完全排列" in rsi_status:
        msg = f"🔥 <b>{ticker} 觸發強勢警報</b>\n價格: {price:.2f}\n狀態: {rsi_status}\n時間: {now.strftime('%H:%M')}"
        send_telegram_alert(msg)
        st.session_state.push_history[history_key] = interval_block 

# ==============================
# Prt.06 側邊欄控制 (新增表單防護)
# ==============================
with st.sidebar:
    st.markdown(f"### ⚙️ 控制台 ({APP_VERSION})")
    
    if st.button("🔄 強制刷新資料", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
        
    st.divider()
    
    st.markdown('''
        <div style="background-color: #161b22; border: 1px solid #30363d; border-left: 5px solid #00b894; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
            <h4 style="margin-top: 0; color: #c9d1d9;">➕ 新增自訂監測</h4>
            <p style="font-size: 0.8rem; color: #8b949e; margin-bottom: 0;">透過 Yahoo 歷史資料即時運算</p>
        </div>
    ''', unsafe_allow_html=True)
    
    # 確保清單存在
    if 'custom_watch' not in st.session_state:
        st.session_state.custom_watch = []
    
    # 【關鍵修復】使用 st.form 包裝，阻擋自動刷新干擾打字！
    with st.form(key="add_stock_form", clear_on_submit=True):
        new_stock = st.text_input("輸入股票代號 (如 2330.TW, AAPL)")
        submit_btn = st.form_submit_button("➕ 增加監控小卡", use_container_width=True)
        
        if submit_btn and new_stock:
            clean_ticker = new_stock.strip().upper()
            if clean_ticker not in st.session_state.custom_watch:
                st.session_state.custom_watch.append(clean_ticker)
                st.success(f"已加入 {clean_ticker}")
            else:
                st.warning("已在清單中")
                
    # 顯示並刪除自訂清單
    if st.session_state.custom_watch:
        st.markdown("**👀 你的自訂監控:**")
        for ts in st.session_state.custom_watch:
            cols = st.columns([3, 1])
            cols[0].write(f"📌 {ts}")
            if cols[1].button("❌", key=f"del_{ts}"):
                st.session_state.custom_watch.remove(ts)
                st.rerun()

    st.divider()
    st.caption(f"上次更新時間: {datetime.datetime.now(TAIPEI_TZ).strftime('%Y-%m-%d %H:%M:%S')}")

# ==============================
# Prt.07 主程式與畫面渲染
# ==============================
def main():
    st.markdown('<h1 class="main-title">📈 台股 50 戰情室監控大廳</h1>', unsafe_allow_html=True)
    
    # 自動刷新 (每 30 秒)
    st_autorefresh(interval=30 * 1000, key="stock_dashboard_refresh")
    
    # 1. 讀取 CSV 基礎資料
    df, status_msg = load_csv_data()
    
    # 2. 融合側邊欄新增的自訂股票資料
    custom_dfs = []
    if 'custom_watch' in st.session_state and st.session_state.custom_watch:
        for ct in st.session_state.custom_watch:
            cdf = fetch_custom_stock(ct)
            if cdf is not None:
                custom_dfs.append(cdf)
            else:
                st.sidebar.error(f"找不到 {ct} 的資料")
                
    if custom_dfs:
        custom_df_combined = pd.concat(custom_dfs, ignore_index=True)
        if not df.empty:
            df = pd.concat([df, custom_df_combined], ignore_index=True)
        else:
            df = custom_df_combined

    # 檢查是否完全沒有資料
    if df.empty:
        st.error(status_msg)
        return
        
    # 3. 開始渲染網格
    tickers = df['ticker'].unique()
    html_cards = '<div class="stock-grid">'
    
    for ticker in tickers:
        df_stock = df[df['ticker'] == ticker]
        
        # 資料天數不夠算 RSI，就跳過
        if len(df_stock) < 30:
            continue
            
        latest_data = calculate_indicators(df_stock)
        price = latest_data.get('Close', 0.0)
        
        rsi_06 = latest_data.get('RSI_6', 0)
        rsi_14 = latest_data.get('RSI_14', 0)
        rsi_24 = latest_data.get('RSI_24', 0)
        
        rsi_status = ""
        alert_html = '<div class="empty-alert">無警報</div>'
        
        if rsi_06 > rsi_14 > rsi_24:
            rsi_status = "🚀 多頭完全排列 (最強多頭)"
            alert_html = f'<div class="alert-box">{rsi_status}</div>'
            check_and_push_alert(ticker, price, rsi_status)
        elif rsi_14 > rsi_06 > rsi_24:
            rsi_status = "📈 多頭漲多拉回 (良性修正)"
            alert_html = f'<div class="alert-box" style="color: #58a6ff;">{rsi_status}</div>'
            
        card = f'''
            <div class="stock-card">
                <div>
                    <div class="stock-title">{ticker}</div>
                    <div class="stock-price">{price:.2f}</div>
                </div>
                {alert_html}
            </div>
        '''
        html_cards += card
        
    html_cards += '</div>'
    st.markdown(html_cards, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
