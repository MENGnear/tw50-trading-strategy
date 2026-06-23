# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : 台股戰情室 Streamlit 監控儀表板
# 檔案名稱 : app.py
# 策略版本 : v03.00 (完美對接 main.py v02.12)
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 功能說明：
# 1. 自動讀取 main.py 產出的 temp_data.csv
# 2. 具備完整的防呆機制 (讀取失敗提示、日期格式校正)
# 3. 科技深色儀表板切版與股票小卡渲染
# 4. Telegram 5 分鐘區塊防洗版推播
# 5. 模組化區塊 (Prt.00 ~ Prt.06) 方便後續擴充
# ==========================================================

# ==============================
# Prt.00 系統設定與套件匯入
# ==============================
import streamlit as st
import pandas as pd
import numpy as np
import os
import requests
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

APP_VERSION = "v03.00"
TAIPEI_TZ = pytz.timezone('Asia/Taipei')

# --- Telegram API 設定 ---
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN" # ⚠️請替換為您的 Token
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"         # ⚠️請替換為您的 Chat ID

def send_telegram_alert(message: str):
    if TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        return # 尚未設定則跳過
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"推播失敗: {e}")

# ==============================
# Prt.01 頁面與 CSS 全域設定
# ==============================
# 深色科技感主題、股票卡片自動換行、左側發光指示條
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
    /* 股票小卡網格容器：自動換行對齊 */
    .stock-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 20px;
        justify-content: flex-start;
    }
    /* 單張股票小卡：固定高度、深色底、發光邊框 */
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
    .stock-title {
        font-size: 1.2rem;
        font-weight: bold;
        color: #ffffff;
        margin-bottom: 10px;
    }
    .stock-price {
        font-size: 1.8rem;
        font-weight: bold;
        color: #ff7b72;
    }
    /* 警報提示文字區塊 (固定高度防破版) */
    .alert-box {
        margin-top: 10px;
        min-height: 40px; 
        font-size: 0.9rem;
        color: #f2cc60;
        border-top: 1px dashed #30363d;
        padding-top: 8px;
    }
    /* 無警報的佔位區塊 (保持小卡高度一致) */
    .empty-alert {
        margin-top: 10px;
        min-height: 40px; 
        border-top: 1px dashed #30363d;
        padding-top: 8px;
        color: transparent;
    }
</style>
''', unsafe_allow_html=True)

# ==============================
# Prt.02 資料讀取與防呆機制
# ==============================
@st.cache_data(ttl=60) # 每 60 秒刷新一次快取，避免過度讀寫
def load_data():
    file_path = "temp_data.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame(), "⚠️ 找不到資料檔 (temp_data.csv)，請確認 main.py 是否已執行並成功產出檔案。"
    
    try:
        df = pd.read_csv(file_path)
        # 日期格式強制校正
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
        # 確保必要的欄位存在
        required_cols = ['ticker', 'Close']
        if not all(col in df.columns for col in required_cols):
            return pd.DataFrame(), f"⚠️ CSV 缺少必要欄位，現有欄位：{list(df.columns)}"
        
        return df, "✅ 資料載入成功"
    except Exception as e:
        return pd.DataFrame(), f"❌ 讀取資料失敗: {e}"

# ==============================
# Prt.03 技術指標計算 (動態附加)
# ==============================
def calculate_indicators(df_stock):
    '''計算單檔股票的 RSI 與 MA (依照日期排序計算)'''
    df_stock = df_stock.sort_values('Date').copy()
    
    # 計算漲跌
    delta = df_stock['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    
    # 計算 RSI 06, 14, 24
    for period in [6, 14, 24]:
        ema_up = up.ewm(com=period-1, adjust=False).mean()
        ema_down = down.ewm(com=period-1, adjust=False).mean()
        rs = ema_up / ema_down
        df_stock[f'RSI_{period}'] = 100 - (100 / (1 + rs))
        
    return df_stock.iloc[-1] # 回傳最新一天的資料，供首頁渲染

# ==============================
# Prt.04 推播防呆機制 (5分鐘區塊)
# ==============================
def check_and_push_alert(ticker, price, rsi_status):
    '''5 分鐘區間鎖定防呆推播，避免洗版'''
    now = datetime.datetime.now(TAIPEI_TZ)
    current_minute = now.minute
    interval_block = current_minute // 5  # 將一小時切成 12 個 5 分鐘區塊 (0~11)
    
    # 初始化 session_state
    if 'push_history' not in st.session_state:
        st.session_state.push_history = {}
        
    history_key = f"{ticker}_block"
    last_pushed_block = st.session_state.push_history.get(history_key, -1)
    
    # 判斷是否需要推播 (如果在同一個 5 分鐘區塊內，則不重複推播)
    if interval_block != last_pushed_block and "多頭完全排列" in rsi_status:
        msg = f"🔥 <b>{ticker} 觸發強勢警報</b>\n價格: {price:.2f}\n狀態: {rsi_status}\n時間: {now.strftime('%H:%M')}"
        send_telegram_alert(msg)
        st.session_state.push_history[history_key] = interval_block # 記錄已推播區塊

# ==============================
# Prt.05 側邊欄控制
# ==============================
with st.sidebar:
    st.markdown(f"### ⚙️ 控制台 ({APP_VERSION})")
    
    # 手動更新按鈕
    if st.button("🔄 強制刷新資料", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
        
    st.divider()
    
    # 新增監測股票區塊 (深色封裝版)
    st.markdown('''
        <div style="background-color: #161b22; border: 1px solid #30363d; border-left: 5px solid #00b894; padding: 10px; border-radius: 5px;">
            <h4 style="margin-top: 0; color: #c9d1d9;">➕ 新增監測股票</h4>
            <p style="font-size: 0.8rem; color: #8b949e;">未來可擴充對接資料庫或 Watchlist</p>
        </div>
    ''', unsafe_allow_html=True)
    
    new_stock = st.text_input("輸入股票代號 (如 2330.TW)", key="new_stock_input")
    
    st.divider()
    st.caption(f"上次更新時間: {datetime.datetime.now(TAIPEI_TZ).strftime('%Y-%m-%d %H:%M:%S')}")

# ==============================
# Prt.06 主程式與畫面渲染
# ==============================
def main():
    st.markdown('<h1 class="main-title">📈 台股 50 戰情室監控大廳</h1>', unsafe_allow_html=True)
    
    # 自動刷新 (每 30 秒)
    st_autorefresh(interval=30 * 1000, key="stock_dashboard_refresh")
    
    # 1. 讀取資料
    df, status_msg = load_data()
    
    if df.empty:
        st.error(status_msg)
        return
        
    st.success(status_msg)
    
    # 2. 獲取唯一的股票清單
    tickers = df['ticker'].unique()
    
    # 3. 渲染 HTML 網格容器
    html_cards = '<div class="stock-grid">'
    
    # 4. 迴圈處理每檔股票
    for ticker in tickers:
        df_stock = df[df['ticker'] == ticker]
        
        # 確保資料量足夠計算指標 (RSI 至少需要 24 天)
        if len(df_stock) < 30:
            continue
            
        latest_data = calculate_indicators(df_stock)
        price = latest_data.get('Close', 0.0)
        
        # --- 判斷排列組合 ---
        rsi_06 = latest_data.get('RSI_6', 0)
        rsi_14 = latest_data.get('RSI_14', 0)
        rsi_24 = latest_data.get('RSI_24', 0)
        
        rsi_status = ""
        alert_html = '<div class="empty-alert">無警報</div>'
        
        if rsi_06 > rsi_14 > rsi_24:
            rsi_status = "🚀 多頭完全排列 (最強多頭)"
            alert_html = f'<div class="alert-box">{rsi_status}</div>'
            # 觸發防呆推播
            check_and_push_alert(ticker, price, rsi_status)
        elif rsi_14 > rsi_06 > rsi_24:
            rsi_status = "📈 多頭漲多拉回 (良性修正)"
            alert_html = f'<div class="alert-box" style="color: #58a6ff;">{rsi_status}</div>'
            
        # --- 組合卡片 HTML ---
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
    
    # 5. 將組合好的 HTML 渲染到畫面上
    st.markdown(html_cards, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
