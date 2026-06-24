# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : 台股戰情室 Streamlit 監控儀表板 (裝甲防禦版)
# 檔案名稱 : app.py
# 策略版本 : v03.06 (型別強制清洗與單點故障隔離)
# ==========================================================

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import os
import json
import urllib.request
import pytz
from streamlit_autorefresh import st_autorefresh

# --- 頁面基本設定 ---
st.set_page_config(
    page_title="台股戰情室監控大廳",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

APP_VERSION = "v03.06"
TAIPEI_TZ = pytz.timezone('Asia/Taipei')

# --- 相容性 Rerun 處理 ---
def safe_rerun():
    if hasattr(st, 'rerun'): st.rerun()
    else: st.experimental_rerun()

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
    .stock-card { background: #161b22; border: 1px solid #30363d; border-left: 5px solid #58a6ff; border-radius: 12px; padding: 20px; width: 300px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); transition: transform 0.2s; }
    .stock-card:hover { transform: translateY(-5px); border-left-color: #3fb950; }
    .stock-header { display: flex; justify-content: space-between; align-items: flex-start; }
    .stock-title { font-size: 1.2rem; font-weight: bold; color: #ffffff; }
    .total-score { font-size: 3.2rem; font-weight: 900; color: #58a6ff; line-height: 1; margin: 12px 0; }
    .stock-price { font-size: 1.4rem; font-weight: bold; color: #ff7b72; margin-bottom: 12px; }
    .sub-scores { font-size: 0.75rem; color: #8b949e; display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 12px; border-top: 1px solid #30363d; padding-top: 10px; }
    .sub-score-item { background: #0d1117; padding: 2px 6px; border-radius: 4px; white-space: nowrap; border: 1px solid #21262d; }
    .action-text { font-size: 0.95rem; font-weight: bold; color: #f2cc60; background: rgba(242, 204, 96, 0.08); padding: 10px; border-radius: 8px; border: 1px dashed #f2cc60; text-align: center; }
    .action-wait { font-size: 0.95rem; color: #8b949e; background: rgba(139, 148, 158, 0.05); padding: 10px; border-radius: 8px; border: 1px dashed #30363d; text-align: center; }
</style>
''', unsafe_allow_html=True)

# ==============================
# Prt.03 資料讀取與暴力清洗
# ==============================
def clean_dataframe(df):
    """ 強制清洗資料，避免字串(逗號)與時區問題 """
    if df.empty: return df
    
    # 統一時間欄位
    if 'Datetime' in df.columns:
        df = df.rename(columns={'Datetime': 'Date'})
        
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        try:
            if hasattr(df['Date'].dt, 'tz') and df['Date'].dt.tz is not None:
                df['Date'] = df['Date'].dt.tz_localize(None)
        except: pass

    # 強制數值轉換 (剔除逗號，避免 ValueError: Unknown format code 'f')
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
            
    return df

@st.cache_data(ttl=60)
def load_csv_data():
    file_path = "temp_data.csv"
    if not os.path.exists(file_path): return pd.DataFrame(), "⚠️ 找不到資料檔 (temp_data.csv)"
    try:
        df = pd.read_csv(file_path)
        df = clean_dataframe(df)
        return df, "✅ 載入成功"
    except Exception as e: return pd.DataFrame(), f"❌ 讀取錯誤: {e}"

@st.cache_data(ttl=300)
def fetch_custom_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo")
        if df.empty: return None
        df = df.reset_index()
        df['ticker'] = ticker
        return clean_dataframe(df)
    except: return None

# ==============================
# Prt.04 技術指標與 v02.12 安全評分
# ==============================
def calculate_v0212_score(df_stock):
    df = df_stock.dropna(subset=['Close']).sort_values('Date').copy()
    if len(df) < 2: return None

    # 均線安全計算 (補0以防爆開)
    df['MA20'] = df['Close'].rolling(window=min(20, len(df))).mean().fillna(0)
    df['MA60'] = df['Close'].rolling(window=min(60, len(df))).mean().fillna(0)
    df['V_MA5'] = df['Volume'].rolling(window=min(5, len(df))).mean().fillna(0)
    
    # MACD 結構計算
    if len(df) >= 26:
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = ema12 - ema26
        df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = (df['DIF'] - df['DEA']).fillna(0)
    else:
        df['MACD_Hist'] = 0.0

    today = df.iloc[-1]
    yest = df.iloc[-2] if len(df) > 1 else today

    # 提取安全數值，避免 KeyError 
    today_close = today.get('Close', 0)
    today_vol = today.get('Volume', 0)
    today_macd = today.get('MACD_Hist', 0)
    yest_macd = yest.get('MACD_Hist', 0)
    today_ma20 = today.get('MA20', 0)
    today_ma60 = today.get('MA60', 0)
    today_vma5 = today.get('V_MA5', 0)

    # --- 五大評分邏輯 (完全拔除異常風險) ---
    t1 = 15 if (today_macd > yest_macd) else 0
    m1 = 10 if (today_ma20 > 0 and today_close > today_ma20) else 0
    
    m2 = 0
    if len(df) >= 6:
        ma20_past = df['MA20'].iloc[-6]
        if ma20_past > 0 and ((today_ma20 / ma20_past) - 1) > 0.01:
            m2 = 15
            
    m3 = 10 if (today_ma60 > 0 and today_ma20 > today_ma60) else 0
    v1 = 10 if (today_vma5 > 0 and today_vol > (today_vma5 * 1.3)) else 0
    
    total_score = int(t1 + m1 + m2 + m3 + v1)

    # RSI 計算
    df['RSI_6'], df['RSI_14'], df['RSI_24'] = 50.0, 50.0, 50.0
    if len(df) >= 24:
        delta = df['Close'].diff()
        up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
        for p in [6, 14, 24]:
            ema_up = up.ewm(com=p-1, adjust=False).mean()
            ema_down = down.ewm(com=p-1, adjust=False).mean()
            df[f'RSI_{p}'] = 100 - (100 / (1 + ema_up / ema_down.replace(0, 1e-9)))
    
    res = {
        'Date': today.get('Date', pd.Timestamp.now()),
        'Close': today_close,
        'High': today.get('High', 0),
        'Score': total_score,
        's1': t1, 's2': m1, 's3': m2, 's4': m3, 's5': v1,
        'RSI_6': df['RSI_6'].iloc[-1], 
        'RSI_14': df['RSI_14'].iloc[-1], 
        'RSI_24': df['RSI_24'].iloc[-1]
    }
    return res

# ==============================
# Prt.05 主程式與渲染大廳
# ==============================
def main():
    st.markdown('<h1 class="main-title">📈 台股 50 戰情室監控大廳</h1>', unsafe_allow_html=True)
    st_autorefresh(interval=60 * 1000, key="refresh")
    
    df_raw, status_msg = load_csv_data()
    
    combined_df = df_raw.copy() if not df_raw.empty else pd.DataFrame()
    if 'custom_watch' in st.session_state:
        for ct in st.session_state.custom_watch:
            cdf = fetch_custom_stock(ct)
            if cdf is not None and not cdf.empty:
                combined_df = pd.concat([combined_df, cdf], ignore_index=True)

    if combined_df.empty:
        st.error(status_msg)
        return

    display_list = []
    tickers = combined_df['ticker'].unique() if 'ticker' in combined_df.columns else []
    
    # 🎯 核心防禦：隔離運算，單檔股票壞掉不影響全局
    for tk in tickers:
        if pd.isna(tk): continue # 跳過無效代號
        try:
            df_tk = combined_df[combined_df['ticker'] == tk]
            data = calculate_v0212_score(df_tk)
            if data:
                data['ticker'] = tk
                display_list.append(data)
        except Exception as e:
            st.sidebar.warning(f"⚠️ 標的 {tk} 資料解析異常，已暫時跳過。")

    display_list = sorted(display_list, key=lambda x: x.get('Score', 0), reverse=True)

    html_cards = '<div class="stock-grid">'
    for d in display_list:
        score = d.get('Score', 0)
        price = d.get('Close', 0.0)
        high_today = d.get('High', 0.0)
        
        # 安全數值格式化防護
        price_str = f"NT$ {price:.2f}" if price > 0 else "N/A"
        high_str = f"{high_today:.2f}" if high_today > 0 else "N/A"
        
        if score >= 45: action_html = f'<div class="action-text">🎯 明日突破 {high_str} 買進</div>'
        else: action_html = f'<div class="action-wait">⏳ 觀察多頭動能續航</div>'

        rsi_msg = "🚀 強勢多頭排列" if (d.get('RSI_6', 0) > d.get('RSI_14', 0) > d.get('RSI_24', 0)) else ""

        card = f'''
            <div class="stock-card">
                <div class="stock-header">
                    <div class="stock-title">{d['ticker']}</div>
                    <div style="font-size: 0.8rem; color: #3fb950; font-weight: bold;">{rsi_msg}</div>
                </div>
                <div class="total-score">{score}</div>
                <div class="stock-price">{price_str}</div>
                <div class="sub-scores">
                    <span class="sub-score-item">1.MACD: {d['s1']}</span>
                    <span class="sub-score-item">2.MA20: {d['s2']}</span>
                    <span class="sub-score-item">3.斜率: {d['s3']}</span>
                    <span class="sub-score-item">4.趨勢: {d['s4']}</span>
                    <span class="sub-score-item">5.量: {d['s5']}</span>
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
    if st.button("🔄 刷新數據"): 
        st.cache_data.clear()
        safe_rerun()
    with st.form("add_tk"):
        nt = st.text_input("新增代號 (例: 2330.TW)")
        if st.form_submit_button("➕ 加入監控") and nt:
            if 'custom_watch' not in st.session_state: 
                st.session_state.custom_watch = []
            st.session_state.custom_watch.append(nt.upper())
            safe_rerun()

if __name__ == "__main__":
    main()
