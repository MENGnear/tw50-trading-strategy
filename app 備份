# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : 台股戰情室 Streamlit 監控儀表板
# 檔案名稱 : app.py
# 程式版本 : TW50_V3.32 (純淨生命週期對齊，捨棄所有 CSS Hack)
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
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

# ⚠️ 1. 頁面設定必須是第一步，確保環境與主題正確載入
st.set_page_config(
    page_title="台股戰情室監控大廳",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ⚠️ 2. 緊接著注入 CSS，完全對齊 MON 樣板，不加任何破壞性 Hack
st.markdown(r'''
<style>
/* =========================================
   1. 全域與基礎設定 (字體與網頁背景)
   ========================================= */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [data-testid="stAppViewContainer"] { 
    font-family: 'Inter', sans-serif !important; 
    background-color: #0e1117 !important; 
    color: #f1f5f9 !important; 
}
[data-testid="stActionElements"] { display: none !important; }
header[data-testid="stHeader"] { background-color: transparent !important; }
.main .block-container { padding-top: 1.5rem !important; margin-top: -30px !important; }
h1 { margin-top: 0px !important; padding-top: 0px !important; margin-bottom: 5px !important; }

/* =========================================
   2. 側邊欄與元件視覺 (輸入框、選單、按鈕)
   ========================================= */
[data-testid="stSidebar"] { 
    background-color: #171a23 !important; 
    border-right: 1px solid #2d3748 !important; 
}
[data-testid="stVerticalBlockBorderWrapper"] { 
    background-color: #1e293b !important; 
    border: 1px solid #94a3b8 !important; 
    border-radius: 12px !important; 
    padding: 15px !important; 
    margin-bottom: 10px !important; 
}
[data-testid="collapsedControl"] svg, [data-testid="stSidebarCollapseButton"] svg, button[kind="header"] svg { 
    color: #ffffff !important; fill: #ffffff !important; 
}
.stTextInput div[data-baseweb="input"], .stSelectbox div[data-baseweb="select"] > div { 
    background-color: #0f172a !important; 
    border: 1px solid #475569 !important; 
    border-radius: 8px !important;  
}
.stTextInput input { color: #ffffff !important; background-color: transparent !important; }
.stSelectbox div[data-baseweb="select"] span { color: #ffffff !important; }
[data-testid="stSidebar"] h3 { color: #ffffff !important; font-size: 1.1rem !important; font-weight: 700 !important; margin-bottom: 15px !important; margin-top: 0px !important; padding-top: 0px !important; }
[data-testid="stWidgetLabel"] p, div[data-testid="stMarkdownContainer"] p, .stSlider label { color: #cbd5e1 !important; font-weight: 600 !important; font-size: 0.95rem !important; }
div[role="radiogroup"] label { color: #f1f5f9 !important; font-weight: 600 !important; }

.stButton > button { 
    background: linear-gradient(135deg, #3b82f6, #1d4ed8) !important; 
    color: white !important; border: none !important; border-radius: 8px !important; font-weight: 600 !important; transition: all 0.2s ease !important; 
}
.stButton > button:hover { box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4) !important; transform: translateY(-1px) !important; }

/* =========================================
   3. 矩陣排版與個股卡片基礎外觀
   ========================================= */
.section-title { font-size: 1.3rem; font-weight: 700; color: #f8fafc; margin: 15px 0 10px 0; padding-left: 8px; border-left: 4px solid #3b82f6; }
.flex-matrix-container { display: flex; flex-wrap: wrap; gap: 14px; width: 100%; justify-content: flex-start !important; margin-bottom: 15px; }
.stock-compact-card { 
    background-color: #171a23; 
    border: 1px solid #2d3748; 
    border-radius: 12px; padding: 16px; 
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2); 
    width: 295px !important; max-width: 295px !important; min-width: 295px !important; box-sizing: border-box; 
}

.card-tw-up { background-color: rgba(239, 68, 68, 0.12) !important; border: 1px solid rgba(239, 68, 68, 0.35) !important; }
.card-tw-down { background-color: rgba(16, 185, 129, 0.12) !important; border: 1px solid rgba(16, 185, 129, 0.35) !important; }
.card-us-up { background-color: rgba(16, 185, 129, 0.12) !important; border: 1px solid rgba(16, 185, 129, 0.35) !important; }
.card-us-down { background-color: rgba(239, 68, 68, 0.12) !important; border: 1px solid rgba(239, 68, 68, 0.35) !important; }

.alert-tw-up { color: #ef4444; background-color: rgba(239, 68, 68, 0.2) !important; width: 100%; text-align: center; padding: 5px; border-radius: 6px; }
.alert-tw-down { color: #10b981; background-color: rgba(16, 185, 129, 0.2) !important; width: 100%; text-align: center; padding: 5px; border-radius: 6px; }
.alert-us-up { color: #10b981; background-color: rgba(16, 185, 129, 0.2) !important; width: 100%; text-align: center; padding: 5px; border-radius: 6px; }
.alert-us-down { color: #ef4444; background-color: rgba(239, 68, 68, 0.2) !important; width: 100%; text-align: center; padding: 5px; border-radius: 6px; }

.card-title-txt { margin: 0 0 2px 0; font-size: 1.25rem; font-weight: 700; color: #ffffff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; justify-content: space-between; align-items: baseline; }
.card-price-txt { color: #38bdf8; margin: 0 0 10px 0; font-size: 1.9rem; font-weight: 700; }
.card-middle-layout { display: flex; justify-content: space-between; margin-bottom: 4px; }
.layout-left-col { flex: 1.1; border-right: 1px dashed #2d3748; padding-right: 4px; text-align: left !important; line-height: 1.7; }
.layout-right-col { flex: 0.9; text-align: left !important; padding-left: 12px; line-height: 1.7; }
.txt-label { color: #94a3b8; font-size: 0.82rem; white-space: nowrap; } 
.txt-label-rsi { color: #a78bfa; font-size: 0.82rem; white-space: nowrap; } 
.txt-bold-val { color: #f1f5f9; font-size: 0.82rem; font-weight: 600; }
.custom-alert-box { min-height: 38px; display: flex; align-items: center; justify-content: center; border-radius: 6px; margin-top: 10px; font-size: 0.82rem; font-weight: 700; box-sizing: border-box; }
.alert-empty { background-color: transparent; color: transparent; }

/* =========================================
   TW50 專屬卡片細節 (不破壞原架構，對齊類別)
   ========================================= */
h1.main-title { color: #f8fafc; font-weight: 800; text-align: left; padding-bottom: 10px; border-bottom: 2px solid #1e293b; margin-bottom: 20px; font-size: 1.8rem; }
.score-highlight { color: #facc15; font-size: 1.6rem; font-weight: 900; }
.action-wait { color: #94a3b8; background-color: rgba(148, 163, 184, 0.1) !important; border: 1px dashed #475569; width: 100%; text-align: center; padding: 5px; border-radius: 6px; margin-top: 10px; font-size: 0.82rem; font-weight: 700; box-sizing: border-box; }
</style>
''', unsafe_allow_html=True)

# ==========================================================
# 3️⃣ 🚀 系統全域設定與通報模組
# ==========================================================
APP_VERSION = "TW50_V3.32"
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

config = StrategyConfig()

def safe_rerun():
    if hasattr(st, 'rerun'): st.rerun()
    else: st.experimental_rerun()

def send_telegram_alert(message):
    token = None
    chat_id = None
    try:
        token = st.secrets["TELEGRAM_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
    except: pass
    if not token or not chat_id:
        token = os.environ.get('TELEGRAM_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id: return False, "找不到 Telegram 設定"
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": str(chat_id), "text": message, "parse_mode": "HTML"}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try: 
        urllib.request.urlopen(req)
        return True, "發送成功"
    except Exception as e: 
        return False, f"Telegram 發送失敗: {e}"

# ==========================================================
# 4️⃣ 🧠 資料讀取與暴力清洗 (TW50 專用)
# ==========================================================
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

# ==========================================================
# 5️⃣ 📊 核心技術指標與績效引擎
# ==========================================================
def calculate_dashboard_metrics(df_stock, config: StrategyConfig):
    df = df_stock.dropna(subset=['Close']).sort_values('Date').copy()
    if len(df) < 2: return None

    df['MA_Fast'] = df['Close'].rolling(config.ma_fast).mean().fillna(0)
    df['MA_Slow'] = df['Close'].rolling(config.ma_slow).mean().fillna(0)
    df['V_MA'] = df['Volume'].rolling(config.vma_period).mean().fillna(0)

    ema_fast = df['Close'].ewm(span=config.macd_fast, adjust=False).mean()
    ema_slow = df['Close'].ewm(span=config.macd_slow, adjust=False).mean()
    df['DIF'] = ema_fast - ema_slow
    df['DEA'] = df['DIF'].ewm(span=config.macd_signal, adjust=False).mean()
    df['MACD_Hist'] = (df['DIF'] - df['DEA']).fillna(0)

    df['Prev_Close'] = df['Close'].shift(1).fillna(df['Close'])
    df['TR'] = np.maximum(
        df['High'] - df['Low'],
        np.maximum(abs(df['High'] - df['Prev_Close']), abs(df['Low'] - df['Prev_Close']))
    )
    df['ATR'] = df['TR'].rolling(window=config.atr_period).mean().fillna(0)

    df['RSI_6'], df['RSI_14'], df['RSI_24'] = 50.0, 50.0, 50.0
    if len(df) >= 24:
        delta = df['Close'].diff()
        up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
        for p in [6, 14, 24]:
            ema_up = up.ewm(com=p-1, adjust=False).mean()
            ema_down = down.ewm(com=p-1, adjust=False).mean()
            df[f'RSI_{p}'] = 100 - (100 / (1 + ema_up / ema_down.replace(0, 1e-9)))

    today = df.iloc[-1]
    yest = df.iloc[-2] if len(df) > 1 else today

    score_macd_trend = 15 if (today['MACD_Hist'] > yest['MACD_Hist']) else 0
    score_ma20_cross = 10 if (today['MA_Fast'] > 0 and today['Close'] > today['MA_Fast']) else 0
    score_ma20_slope = 0
    if len(df) >= 6:
        ma_fast_past = df['MA_Fast'].iloc[-6]
        if ma_fast_past > 0 and ((today['MA_Fast'] / ma_fast_past) - 1) > 0.01:
            score_ma20_slope = 15
    score_ma60_trend = 10 if (today['MA_Slow'] > 0 and today['MA_Fast'] > today['MA_Slow']) else 0
    score_volume_burst = 10 if (today['V_MA'] > 0 and today['Volume'] > (today['V_MA'] * config.vol_ratio)) else 0
    
    total_score = int(sum([score_macd_trend, score_ma20_cross, score_ma20_slope, score_ma60_trend, score_volume_burst]))

    return {
        'Date': today.get('Date', pd.Timestamp.now()),
        'Close': today.get('Close', 0),
        'High': today.get('High', 0),
        'Score': total_score,
        's1': score_macd_trend, 
        's2': score_ma20_cross, 
        's3': score_ma20_slope, 
        's4': score_ma60_trend, 
        's5': score_volume_burst,
        'RSI_6': today['RSI_6'], 
        'RSI_14': today['RSI_14'], 
        'RSI_24': today['RSI_24'],
        'ATR': today['ATR']
    }

def generate_performance_report(version, config: StrategyConfig, db_name=DB_NAME):
    try:
        with sqlite3.connect(db_name) as conn:
            df = pd.read_sql_query("SELECT entry_date, exit_date, profit_pct FROM backtest_trades WHERE version = ? ORDER BY exit_date ASC", conn, params=(version,))
        if df.empty: return "================\n📈 <b>策略績效健檢</b>\n目前無足夠歷史交易資料可供統計。"
        
        total_trades = len(df)
        win_trades = df[df['profit_pct'] > 0]
        win_rate = (len(win_trades) / total_trades) * 100 if total_trades > 0 else 0
        weight_per_trade = config.capital_weight_per_trade
        df['exit_date'] = pd.to_datetime(df['exit_date'])
        df['realized_pnl'] = df['profit_pct'] * weight_per_trade
        df['equity'] = 1.0 + df['realized_pnl'].cumsum()
        df['peak'] = df['equity'].cummax()
        df['drawdown'] = (df['equity'] - df['peak']) / df['peak']
        sys_mdd = df['drawdown'].min() * 100 if not df.empty else 0
        
        return (
            f"================\n"
            f"📈 <b>策略已實現績效</b>\n"
            f"• 總交易筆數: {total_trades} 筆\n"
            f"• 勝率: {win_rate:.1f}%\n"
            f"• 系統最大回撤: {sys_mdd:.1f}%\n"
        )
    except Exception as e:
        return f"================\n⚠️ 績效統計錯誤: {e}"

# ==========================================================
# 6️⃣ 💾 初始化監測清單與記憶狀態
# ==========================================================
if 'custom_watch' not in st.session_state: 
    st.session_state.custom_watch = []

# ==========================================================
# 7️⃣ ⚙️ 側邊欄選單 
# ==========================================================
with st.sidebar:
    
    with st.container(border=True):
        st.markdown("### ⚙️ 控制與設定面板")

    with st.container(border=True):
        st.markdown("### ➕ 新增監測股票")
        st.markdown("<div style='color:#38bdf8; font-size:1.0rem; font-weight:700; margin-bottom:5px;'>✍️ 手動輸入股票</div>", unsafe_allow_html=True)
        # 嚴格對齊 MON，使用標準的 st.text_input，不加 label_visibility="collapsed"
        nt = st.text_input("輸入股票代碼", value="", placeholder="例: 2330.TW", key="sym_manual").strip().upper()
        if st.button("確認輸入", use_container_width=True, key="btn_manual"):
            if nt and nt not in st.session_state.custom_watch:
                st.session_state.custom_watch.append(nt)
            safe_rerun()

    with st.container(border=True):
        st.markdown("### 🗑️ 移除監測清單")
        if st.session_state.custom_watch:
            del_sym = st.selectbox("刪除目標", ["--- 請選擇 ---"] + st.session_state.custom_watch)
            if st.button("確認刪除", use_container_width=True) and del_sym != "--- 請選擇 ---":
                st.session_state.custom_watch.remove(del_sym)
                safe_rerun()
        else:
            st.selectbox("刪除目標", ["--- 請選擇 ---"], disabled=True)
            st.button("確認刪除", use_container_width=True, disabled=True)

    with st.container(border=True):
        st.markdown("### ⏱️ 網頁刷新頻率")
        # 這裡的 Slider 依然保持原生設計
        refresh_sec = st.slider("秒", 5, 60, 30, label_visibility="collapsed")
        if st.button("🔄 手動立即刷新", use_container_width=True):
            st.cache_data.clear()
            safe_rerun()
            
    with st.container(border=True):
        st.markdown("### 🛠️ 手動測試推播")
        if st.button("發送目前小卡狀態", use_container_width=True):
            with st.spinner("🚀 正在執行判定與通報..."):
                now_str = datetime.datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d %I.%M.%S %p")
                msg = f"📊 <b>{STRATEGY_VERSION} 台股 50 戰情室 (手動健康檢查)</b>\n🕒 {now_str} 回測\n================\n"
                msg += "================\n✅ 系統目前正常運作中"
                send_telegram_alert(msg)
                st.success("✅ 回測通報已成功發送至 Telegram！")

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    tpe_now = now_utc.astimezone(pytz.timezone('Asia/Taipei'))
    tpe_time_str = tpe_now.strftime("%H:%M:%S %m/%d/%Y")

    st.markdown(
        f"""
        <div style="background-color:#1e293b; padding:12px; border-radius:8px; border:1px solid #475569; text-align:center; margin-top:15px; margin-bottom:15px;">
            <div style="color:#94a3b8; font-size:0.8rem; font-weight:600; margin-bottom:4px;">系統當前版本</div>
            <div style="color:#38bdf8; font-size:1.1rem; font-weight:700; margin-bottom:10px;">{APP_VERSION}</div>
            <div style="color:#94a3b8; font-size:0.8rem; font-weight:600; margin-bottom:8px;">🕒 最後資料更新</div>
            <div style="color:#f1f5f9; font-size:0.88rem; font-weight:600; margin-bottom:2px;">Tw {tpe_time_str}</div>
        </div>
        """, unsafe_allow_html=True
    )

# ==========================================================
# 8️⃣ 📈 主畫面看盤終端矩陣
# ==========================================================
st.markdown('<h1 class="main-title">📈 台股 50 戰情室監控大廳</h1>', unsafe_allow_html=True)

df_raw, status_msg = load_csv_data()
combined_df = df_raw.copy() if not df_raw.empty else pd.DataFrame()

if 'custom_watch' in st.session_state:
    for ct in st.session_state.custom_watch:
        cdf = fetch_custom_stock(ct)
        if cdf is not None and not cdf.empty:
            combined_df = pd.concat([combined_df, cdf], ignore_index=True)

if combined_df.empty:
    st.error(status_msg)
else:
    display_list = []
    tickers = combined_df['ticker'].unique() if 'ticker' in combined_df.columns else []
    
    for tk in tickers:
        if pd.isna(tk): continue 
        try:
            df_tk = combined_df[combined_df['ticker'] == tk]
            data = calculate_dashboard_metrics(df_tk, config)
            if data:
                data['ticker'] = tk
                display_list.append(data)
        except Exception as e: pass

    display_list = sorted(display_list, key=lambda x: x.get('Score', 0), reverse=True)
    
    html_cards = '<div class="flex-matrix-container">'
    for d in display_list:
        score = d.get('Score', 0)
        price = d.get('Close', 0.0)
        high_today = d.get('High', 0.0)
        atr = d.get('ATR', 0.0)
        
        price_str = f"NT$ {price:.2f}" if price > 0 else "N/A"
        high_str = f"{high_today:.2f}" if high_today > 0 else "N/A"
        rsi_msg = "<span style='color:#10b981; font-weight:700;'>🚀 多頭排列</span>" if (d.get('RSI_6', 0) > d.get('RSI_14', 0) > d.get('RSI_24', 0)) else "<span style='color:#64748b;'>🔄 震盪整理</span>"
        
        # 嚴格使用 MON 原生定義的 alert 樣式，確保背景色不會跑掉
        if score >= config.setup_score_threshold:
            stop_tgt = high_today - (config.atr_multiplier * atr)
            risk_pct = (high_today - stop_tgt) / high_today * 100 if high_today > 0 else 0
            action_html = f'<div class="custom-alert-box alert-tw-up">🎯 突破 {high_str} 買進 | 守 {stop_tgt:.1f} (-{risk_pct:.1f}%)</div>'
            card_bg_class = "card-tw-up"
        else:
            action_html = f'<div class="action-wait">⏳ 觀察多頭動能續航</div>'
            card_bg_class = ""

        card = (
            f'<div class="stock-compact-card {card_bg_class}">'
            f'<div class="card-title-txt">{d["ticker"]} <span class="score-highlight">{score}</span></div>'
            f'<div class="card-price-txt">{price_str}</div>'
            f'<div class="card-middle-layout">'
            f'<div class="layout-left-col">'
            f'<span class="txt-label">MACD:</span><span class="txt-bold-val">{d["s1"]}</span><br>'
            f'<span class="txt-label">MA20:</span><span class="txt-bold-val">{d["s2"]}</span><br>'
            f'<span class="txt-label">斜率:</span><span class="txt-bold-val">{d["s3"]}</span><br>'
            f'<span class="txt-label">趨勢:</span><span class="txt-bold-val">{d["s4"]}</span><br>'
            f'<span class="txt-label">量能:</span><span class="txt-bold-val">{d["s5"]}</span>'
            f'</div>'
            f'<div class="layout-right-col">'
            f'<span class="txt-label-rsi">R6:</span><span class="txt-bold-val">{d["RSI_6"]:.1f}</span><br>'
            f'<span class="txt-label-rsi">R14:</span><span class="txt-bold-val">{d["RSI_14"]:.1f}</span><br>'
            f'<span class="txt-label-rsi">R24:</span><span class="txt-bold-val">{d["RSI_24"]:.1f}</span><br>'
            f'<div style="margin-top:6px; font-size:0.8rem;">{rsi_msg}</div>'
            f'</div>'
            f'</div>'
            f'{action_html}'
            f'</div>'
        )
        html_cards += card
        
    html_cards += '</div>'
    st.markdown(html_cards, unsafe_allow_html=True)
    
    st_autorefresh(interval=refresh_sec * 1000, key="stock_refresh")
