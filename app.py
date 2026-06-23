# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐•
# 專案名稱 : 台股戰情室 Streamlit 監控儀表板 (終極防護版)
# 檔案名稱 : app.py
# 策略版本 : v03.04 (修復長度過濾與空值防禦)
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
from streamlit_autorefresh import st_autorefresh

# --- 頁面基本設定 ---
st.set_page_config(
    page_title="台股戰情室監控大廳",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

APP_VERSION = "v03.04"
TAIPEI_TZ = pytz.timezone('Asia/Taipei')

# ==============================
# Prt.01 Telegram API 設定
# ==============================
def send_telegram_alert(message):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try: urllib.request.urlopen(req)
    except: pass

# ==============================
# Prt.02 頁面與 CSS 全域設定
# ==============================
st.markdown('''
<style>
    .stApp { background-color: #0e1117; color: #c9d1d9; }
    .main-title { color: #58a6ff; font-weight: 800; text-align: center; padding-bottom: 20px; border-bottom: 2px solid #30363d; margin-bottom: 20px; }
    .stock-grid { display: flex; flex-wrap: wrap; gap: 15px; justify-content: flex-start; }
    
    /* 股票小卡樣式優化 */
    .stock-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-left: 5px solid #58a6ff;
        border-radius: 12px;
        padding: 20px;
        width: 300px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        transition: transform 0.2s;
    }
    .stock-card:hover { transform: translateY(-5px); border-left-color: #3fb950; }
    
    .stock-header { display: flex; justify-content: space-between; align-items: flex-start; }
    .stock-title { font-size: 1.1rem; font-weight: bold; color: #8b949e; }
    
    /* 總分大字體 */
    .total-score { font-size: 3rem; font-weight: 900; color: #58a6ff; line-height: 1; margin: 10px 0; }
    
    .stock-price { font-size: 1.5rem; font-weight: bold; color: #ff7b72; margin-bottom: 10px; }
    
    /* 分項分數小字體 */
    .sub-scores { font-size: 0.75rem; color: #8b949e; display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 10px; border-top: 1px solid #30363d; padding-top: 8px; }
    .sub-score-item { background: #0d1117; padding: 2px 6px; border-radius: 4px; white-space: nowrap; }
    
    /* 黃色建議文字 */
    .action-text { font-size: 0.95rem; font-weight: bold; color: #f2cc60; background: rgba(242, 204, 96, 0.1); padding: 8px; border-radius: 6px; border: 1px dashed #f2cc60; }
    
    .alert-box { margin-top: 10px; font-size: 0.85rem; color: #3fb950; }
</style>
''', unsafe_allow_html=True)

# ==============================
# Prt.03 資料讀取
# ==============================
@st.cache_data(ttl=60)
def load_csv_data():
    file_path = "temp_data.csv"
    if not os.path.exists(file_path): return pd.DataFrame(), "⚠️ 找不到資料檔"
    try:
        df = pd.read_csv(file_path)
        df['Date'] = pd.to_datetime(df['Date'])
        return df, "✅ 載入成功"
    except Exception as e: return pd.DataFrame(), f"❌ 錯誤: {e}"

@st.cache_data(ttl=300)
def fetch_custom_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo")
        if df.empty: return None
        df = df.reset_index()
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
        df['ticker'] = ticker
        return df
    except: return None

# ==============================
# Prt.04 技術指標與 v02.12 評分安全計算
# ==============================
def calculate_v0212_score(df_stock):
    df = df_stock.sort_values('Date').copy()
    if len(df) < 6: return None  # 最少需要 6 天以防 iloc[-6] 溢位崩潰

    # 基礎指標 (動態適應長度，避免不足 60 天時產生全空值)
    df['MA20'] = df['Close'].rolling(window=min(20, len(df))).mean()
    df['MA60'] = df['Close'].rolling(window=min(60, len(df))).mean() if len(df) >= 60 else None
    df['V_MA5'] = df['Volume'].rolling(window=min(5, len(df))).mean()
    
    # MACD 結構安全計算
    if len(df) >= 26:
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = ema12 - ema26
        df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = df['DIF'] - df['DEA']
    else:
        df['MACD_Hist'] = 0.0

    today = df.iloc[-1]
    yest = df.iloc[-2] if len(df) > 1 else today

    # --- 五大評分邏輯 (引入全面空值安全保護機制) ---
    t1 = 15 if ('MACD_Hist' in today and 'MACD_Hist' in yest and today['MACD_Hist'] > yest['MACD_Hist']) else 0
    m1 = 10 if (pd.notna(today['MA20']) and today['Close'] > today['MA20']) else 0
    
    # 5日斜率安全防護
    m2 = 0
    if 'MA20' in df.columns:
        ma20_past = df['MA20'].iloc[-6]
        if pd.notna(today['MA20']) and pd.notna(ma20_past) and ma20_past != 0:
            m2 = 15 if (today['MA20'] / ma20_past - 1) > 0.01 else 0
            
    m3 = 10 if (df['MA60'] is not None and pd.notna(today['MA20']) and pd.notna(today['MA60']) and today['MA20'] > today['MA60']) else 0
    v1 = 10 if (pd.notna(today['Volume']) and pd.notna(today['V_MA5']) and today['Volume'] > today['V_MA5'] * 1.3) else 0
    
    total_score = t1 + m1 + m2 + m3 + v1

    # RSI 安全計算
    df['RSI_6'] = 0.0
    df['RSI_14'] = 0.0
    df['RSI_24'] = 0.0
    if len(df) >= 24:
        delta = df['Close'].diff()
        up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
        for p in [6, 14, 24]:
            ema_up = up.ewm(com=p-1, adjust=False).mean()
            ema_down = down.ewm(com=p-1, adjust=False).mean()
            # 避免除以 0 崩潰
            df[f'RSI_{p}'] = 100 - (100 / (1 + ema_up / ema_down.replace(0, 1e-9)))
    
    res = today.to_dict()
    res.update({
        'Score': total_score,
        's1': t1, 's2': m1, 's3': m2, 's4': m3, 's5': v1,
        'RSI_6': df['RSI_6'].iloc[-1] if len(df) >= 24 else 50.0,
        'RSI_14': df['RSI_14'].iloc[-1] if len(df) >= 24 else 50.0,
        'RSI_24': df['RSI_24'].iloc[-1] if len(df) >= 24 else 50.0
    })
    return res

# ==============================
# Prt.05 主程式與渲染
# ==============================
def main():
    st.markdown('<h1 class="main-title">📈 台股 50 戰情室監控大廳</h1>', unsafe_allow_html=True)
    st_autorefresh(interval=60 * 1000, key="refresh")
    
    df_raw, status_msg = load_csv_data()
    
    # 處理自訂股票
    if 'custom_watch' in st.session_state:
        for ct in st.session_state.custom_watch:
            cdf = fetch_custom_stock(ct)
            if cdf is not None: df_raw = pd.concat([df_raw, cdf], ignore_index=True)

    if df_raw.empty:
        st.error(status_msg)
        return

    # 計算所有股票得分
    display_list = []
    tickers = df_raw['ticker'].unique()
    for tk in tickers:
        df_tk = df_raw[df_raw['ticker'] == tk]
        data = calculate_v0212_score(df_tk)
        if data:
            data['ticker'] = tk
            display_list.append(data)

    # 🎯 依照分數高低排列 (高到低)
    display_list = sorted(display_list, key=lambda x: x['Score'], reverse=True)

    # 開始渲染小卡
    html_cards = '<div class="stock-grid">'
    for d in display_list:
        score = int(d['Score'])
        price = d.get('Close', 0.0)
        high_today = d.get('High', 0.0)
        
        # 安全字串格式化：防止 NaN 導致 string format 拋出 ValueError 崩潰
        price_str = f"NT$ {price:.2f}" if pd.notna(price) else "N/A"
        high_str = f"{high_today:.2f}" if pd.notna(high_today) else "N/A"
        
        # 🎯 建議文字邏輯 (黃字提示)
        action_html = ""
        if score >= 45:
            action_html = f'<div class="action-text">🎯 明日突破 {high_str} 買進</div>'
        elif score >= 30:
            action_html = f'<div class="action-text" style="color:#8b949e; border-color:#30363d; background:none;">⏳ 觀察多頭動能續航</div>'

        # RSI 狀態
        rsi_msg = ""
        if d['RSI_6'] > d['RSI_14'] > d['RSI_24']: 
            rsi_msg = "🚀 強勢多頭排列"

        # 🎯 畫面組裝 (大字體總分、小字體分項分數)
        card = f'''
            <div class="stock-card">
                <div class="stock-header">
                    <div class="stock-title">{d['ticker']}</div>
                    <div style="font-size: 0.8rem; color: #3fb950;">{rsi_msg}</div>
                </div>
                <div class="total-score">{score}</div>
                <div class="stock-price">{price_str}</div>
                
                <div class="sub-scores">
                    <span class="sub-score-item">1. MACD:{d['s1']}</span>
                    <span class="sub-score-item">2. MA20:{d['s2']}</span>
                    <span class="sub-score-item">3. 斜率:{d['s3']}</span>
                    <span class="sub-score-item">4. 趨勢:{d['s4']}</span>
                    <span class="sub-score-item">5. 量:{d['s5']}</span>
                </div>
                
                {action_html}
            </div>
        '''
        html_cards += card
        
    html_cards += '</div>'
    st.markdown(html_cards, unsafe_allow_html=True)

# 側邊欄控制
with st.sidebar:
    st.markdown(f"### ⚙️ 控制台 ({APP_VERSION})")
    if st.button("🔄 刷新數據"): st.cache_data.clear(); st.rerun()
    with st.form("add_tk"):
        nt = st.text_input("新增代號 (例: 2330.TW)")
        if st.form_submit_button("➕ 加入監控") and nt:
            if 'custom_watch' not in st.session_state: st.session_state.custom_watch = []
            st.session_state.custom_watch.append(nt.upper())
            st.rerun()

if __name__ == "__main__":
    main()
