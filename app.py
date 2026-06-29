# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : 台股戰情室 Streamlit 監控儀表板 (UI 側邊欄優化版)
# 檔案名稱 : app.py
# 程式版本 : v03.24 (100% 退回 Showmethemoney 樣板原生 CSS)
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
# Prt.00 全域常數與設定 (對齊後台 main.py)
# ==============================
APP_VERSION = "v03.24"
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

# --- 相容性 Rerun 處理 ---
def safe_rerun():
    if hasattr(st, 'rerun'): st.rerun()
    else: st.experimental_rerun()

# ==============================
# Prt.01 Telegram API 設定
# ==============================
def send_telegram_alert(message):
    token = None
    chat_id = None
    
    try:
        token = st.secrets["TELEGRAM_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
    except:
        pass
        
    if not token or not chat_id:
        token = os.environ.get('TELEGRAM_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        
    if not token or not chat_id: 
        return False, "找不到 Telegram Token 或 Chat ID 設定"
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": str(chat_id), "text": message, "parse_mode": "HTML"}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    
    try: 
        urllib.request.urlopen(req)
        return True, "發送成功"
    except Exception as e: 
        return False, f"Telegram API 拒絕請求: {e}"

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
h1 { margin-top: 0px !important; padding-top: 0px !important; margin-bottom: 5px !important; }
html, body, [data-testid="stAppViewContainer"] { background-color: #0e1117 !important; color: #f1f5f9 !important; }
[data-testid="stSidebar"] { background-color: #171a23 !important; border-right: 1px solid #2d3748 !important; }

[data-testid="stVerticalBlockBorderWrapper"] { background-color: #1e293b !important; border: 1px solid #94a3b8 !important; border-radius: 12px !important; padding: 15px !important; margin-bottom: 10px !important; }
[data-testid="collapsedControl"] svg, [data-testid="stSidebarCollapseButton"] svg, button[kind="header"] svg { color: #ffffff !important; fill: #ffffff !important; }
.stTextInput div[data-baseweb="input"], .stSelectbox div[data-baseweb="select"] > div { background-color: #0f172a !important; border: 1px solid #475569 !important; border-radius: 8px !important;  }
.stTextInput input { color: #ffffff !important; background-color: transparent !important; }
.stSelectbox div[data-baseweb="select"] span { color: #ffffff !important; }
[data-testid="stSidebar"] h3 { color: #ffffff !important; font-size: 1.1rem !important; font-weight: 700 !important; margin-bottom: 15px !important; margin-top: 0px !important; padding-top: 0px !important; }
[data-testid="stWidgetLabel"] p, div[data-testid="stMarkdownContainer"] p, .stSlider label { color: #cbd5e1 !important; font-weight: 600 !important; font-size: 0.95rem !important; }
div[role="radiogroup"] label { color: #f1f5f9 !important; font-weight: 600 !important; }
.stButton > button { background: linear-gradient(135deg, #3b82f6, #1d4ed8) !important; color: white !important; border: none !important; border-radius: 8px !important; font-weight: 600 !important; transition: all 0.2s ease !important; }
.stButton > button:hover { box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4) !important; transform: translateY(-1px) !important; }

/* TW50 專用卡片排版樣式 */
h1.main-title { color: #f8fafc; font-weight: 800; text-align: left; padding-bottom: 10px; border-bottom: 2px solid #1e293b; margin-bottom: 20px; font-size: 1.8rem; }
.flex-matrix-container { display: flex; flex-wrap: wrap; gap: 14px; width: 100%; justify-content: flex-start !important; margin-bottom: 15px; }
.stock-compact-card { background-color: #171a23; border: 1px solid #2d3748; border-radius: 12px; padding: 16px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2); width: 295px !important; max-width: 295px !important; min-width: 295px !important; box-sizing: border-box; }
.card-title-txt { margin: 0 0 2px 0; font-size: 1.25rem; font-weight: 700; color: #ffffff; display: flex; justify-content: space-between; align-items: baseline; }
.card-price-txt { color: #38bdf8; margin: 0 0 10px 0; font-size: 1.9rem; font-weight: 700; }
.score-highlight { color: #facc15; font-size: 1.6rem; font-weight: 900; }
.card-middle-layout { display: flex; justify-content: space-between; margin-bottom: 4px; }
.layout-left-col { flex: 1.1; border-right: 1px dashed #2d3748; padding-right: 4px; text-align: left !important; line-height: 1.7; }
.layout-right-col { flex: 0.9; text-align: left !important; padding-left: 12px; line-height: 1.7; }
.txt-label { color: #94a3b8; font-size: 0.82rem; white-space: nowrap; }
.txt-label-rsi { color: #a78bfa; font-size: 0.82rem; white-space: nowrap; }
.txt-bold-val { color: #f1f5f9; font-size: 0.82rem; font-weight: 600; }
.custom-alert-box { min-height: 38px; display: flex; align-items: center; justify-content: center; border-radius: 6px; margin-top: 10px; font-size: 0.82rem; font-weight: 700; box-sizing: border-box; }
.action-buy { color: #f2cc60; background-color: rgba(242, 204, 96, 0.15) !important; border: 1px dashed #f2cc60; }
.action-wait { color: #94a3b8; background-color: rgba(148, 163, 184, 0.1) !important; border: 1px dashed #475569; }
</style>
''' , unsafe_allow_html=True)

# ==============================
# Prt.03 資料讀取與暴力清洗
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
# Prt.04 核心儀表板指標與評分模組
# ==============================
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
        np.maximum(
            abs(df['High'] - df['Prev_Close']),
            abs(df['Low'] - df['Prev_Close'])
        )
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

    res = {
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
    return res

# ==============================
# Prt.05 總體績效結算模組
# ==============================
def generate_performance_report(version, config: StrategyConfig, db_name=DB_NAME):
    try:
        with sqlite3.connect(db_name) as conn:
            df = pd.read_sql_query(
                "SELECT entry_date, exit_date, profit_pct FROM backtest_trades WHERE version = ? ORDER BY exit_date ASC", 
                conn, params=(version,)
            )
            
        if df.empty:
            return "================\n📈 <b>策略績效健檢</b>\n目前無足夠歷史交易資料可供統計。"
            
        total_trades = len(df)
        win_trades = df[df['profit_pct'] > 0]
        loss_trades = df[df['profit_pct'] <= 0]
        
        win_rate = (len(win_trades) / total_trades) * 100 if total_trades > 0 else 0
        
        gross_profit = win_trades['profit_pct'].sum()
        gross_loss = abs(loss_trades['profit_pct'].sum())
        profit_factor = (gross_profit / gross_loss) if gross_loss != 0 else float('inf')
        
        example_win = win_trades['profit_pct'].mean() if not win_trades.empty else 0
        example_loss = loss_trades['profit_pct'].mean() if not loss_trades.empty else 0
        expectancy = (example_win * (len(win_trades) / total_trades)) + (example_loss * (len(loss_trades) / total_trades))
        
        weight_per_trade = config.capital_weight_per_trade
        
        df['exit_date'] = pd.to_datetime(df['exit_date'])
        df['realized_pnl'] = df['profit_pct'] * weight_per_trade
        df['equity'] = 1.0 + df['realized_pnl'].cumsum()
        
        df['peak'] = df['equity'].cummax()
        df['drawdown'] = (df['equity'] - df['peak']) / df['peak']
        
        sys_mdd = df['drawdown'].min() * 100 if not df.empty else 0
        
        days = (df['exit_date'].max() - df['exit_date'].min()).days if not df.empty else 0
        final_equity = df['equity'].iloc[-1] if not df.empty else 1.0
        
        if days > 0 and final_equity > 0:
            cagr = ((final_equity ** (365.25 / days)) - 1) * 100
        else:
            cagr = (final_equity - 1) * 100 
        
        report = (
            f"================\n"
            f"📈 <b>策略已實現績效 (Trade-Based Metrics)</b>\n"
            f"• 總交易筆數: {total_trades} 筆\n"
            f"• 勝率 (Win Rate): {win_rate:.1f}%\n"
            f"• 獲利因子 (Profit Factor): {profit_factor:.2f}\n"
            f"• 期望值 (Expectancy): {expectancy*100:.2f}%\n"
            f"• 年化報酬 (CAGR): {cagr:.1f}%\n"
            f"• 系統最大回撤 (Max DD): {sys_mdd:.1f}%\n"
            f"<i>*註: 採用 Sequential Trade Equity 算法，依據設定每筆固定投入 {weight_per_trade*100:.0f}% 資金計算。</i>"
        )
        return report
    except sqlite3.Error as db_e:
        return f"================\n⚠️ 績效統計資料庫錯誤: {db_e}"
    except Exception as e:
        return f"================\n⚠️ 績效統計發生未預期錯誤: {e}"

# ==============================
# Prt.06 主程式與渲染大廳
# ==============================
def main():
    st.markdown('<h1 class="main-title">📈 台股 50 戰情室監控大廳</h1>', unsafe_allow_html=True)
    
    config = StrategyConfig()
    df_raw, status_msg = load_csv_data()
    
    date_range_str = "2021/06/25 ~ 2026/06/24"
    if not df_raw.empty and 'Date' in df_raw.columns:
        valid_dates = df_raw['Date'].dropna()
        if not valid_dates.empty:
            min_date = valid_dates.min().strftime('%Y/%m/%d')
            max_date = valid_dates.max().strftime('%Y/%m/%d')
            date_range_str = f"{min_date} ~ {max_date}"

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
    
    for tk in tickers:
        if pd.isna(tk): continue 
        try:
            df_tk = combined_df[combined_df['ticker'] == tk]
            data = calculate_dashboard_metrics(df_tk, config)
            if data:
                data['ticker'] = tk
                display_list.append(data)
        except Exception as e:
            pass

    display_list = sorted(display_list, key=lambda x: x.get('Score', 0), reverse=True)

    # ==============================
    # 🌟 側邊欄優化區塊
    # ==============================
    with st.sidebar:
        
        # 1. 控制與設定面板
        with st.container(border=True):
            st.markdown("### ⚙️ 控制與設定面板")

        # 2. 新增監測股票
        with st.container(border=True):
            st.markdown("### ➕ 新增監測股票")
            with st.form("add_tk"):
                nt = st.text_input("輸入代號 (例: 2330.TW)", label_visibility="collapsed")
                if st.form_submit_button("➕ 確認輸入", use_container_width=True) and nt:
                    if 'custom_watch' not in st.session_state: 
                        st.session_state.custom_watch = []
                    if nt.upper() not in st.session_state.custom_watch:
                        st.session_state.custom_watch.append(nt.upper())
                    safe_rerun()

        # 3. 移除監測清單
        with st.container(border=True):
            st.markdown("### 🗑️ 移除監測清單")
            if 'custom_watch' in st.session_state and st.session_state.custom_watch:
                del_sym = st.selectbox("刪除目標", ["--- 請選擇 ---"] + st.session_state.custom_watch)
                if st.button("確認刪除", use_container_width=True) and del_sym != "--- 請選擇 ---":
                    st.session_state.custom_watch.remove(del_sym)
                    safe_rerun()
            else:
                st.selectbox("刪除目標", ["--- 請選擇 ---"], disabled=True)
                st.button("確認刪除", use_container_width=True, disabled=True)

        # 4. 網頁刷新頻率
        with st.container(border=True):
            st.markdown("### ⏱️ 網頁刷新頻率")
            refresh_sec = st.slider("秒", 5, 60, 30, label_visibility="collapsed")
            if st.button("🔄 手動立即刷新", use_container_width=True):
                st.cache_data.clear()
                safe_rerun()
                
        # 5. 手動測試推播
        with st.container(border=True):
            st.markdown("### 🛠️ 手動測試推播")
            if st.button("發送目前小卡狀態", use_container_width=True):
                with st.spinner("🚀 正在執行判定與通報..."):
                    now_str = datetime.datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d %I.%M.%S %p")
                    msg = f"📊 <b>{STRATEGY_VERSION} 台股 50 戰情室 (手動健康檢查)</b>\n"
                    msg += f"🕒 {now_str} 回測\n================\n"
                    
                    setups = [d for d in display_list if d.get('Score', 0) >= config.setup_score_threshold]
                    if setups:
                        msg += f"🎯 <b>滿足潛力起漲 (Score >= {config.setup_score_threshold})</b>\n"
                        for s in setups:
                            stop_tgt = s.get('High', 0.0) - (config.atr_multiplier * s.get('ATR', 0))
                            risk_pct = (s.get('High', 0.0) - stop_tgt) / s.get('High', 1e-9) * 100 if s.get('High', 0.0) > 0 else 0
                            msg += f"• {s['ticker']} (Score: {s['Score']}, 明日突破 {s.get('High', 0.0):.2f} 買進, 防守 {stop_tgt:.2f} [-{risk_pct:.1f}%])\n"
                    else:
                        msg += "盤後無新增訊號。\n"
                    
                    try:
                        if os.path.exists(DB_NAME):
                            report = generate_performance_report(STRATEGY_VERSION, config, DB_NAME)
                            msg += f"\n{report}\n"
                        else:
                            msg += f"\n================\n⚠️ 找不到策略資料庫 ({DB_NAME})，請確認後台回測已執行。\n"
                    except Exception as db_e:
                        msg += f"\n================\n⚠️ 讀取策略資料庫失敗: {db_e}\n"
                        
                    msg += "================\n✅ 系統目前正常運作中"
                    is_success, error_reason = send_telegram_alert(msg)
                    
                    if is_success:
                        st.success("✅ 回測通報已成功發送至 Telegram！")
                    else:
                        st.error(f"❌ 發送失敗：{error_reason}")

        # 6. 系統狀態與版本
        st.markdown(
            f"""
            <div style="background-color:#1e293b; padding:12px; border-radius:8px; border:1px solid #475569; text-align:center; margin-top:15px; margin-bottom:15px;">
                <div style="color:#94a3b8; font-size:0.8rem; font-weight:600; margin-bottom:4px;">系統當前版本</div>
                <div style="color:#38bdf8; font-size:1.1rem; font-weight:700; margin-bottom:10px;">{APP_VERSION}</div>
                <div style="color:#94a3b8; font-size:0.8rem; font-weight:600; margin-bottom:4px;">核心策略版本</div>
                <div style="color:#e2e8f0; font-size: 0.88rem; font-weight:600; margin-bottom:10px;">{STRATEGY_VERSION}</div>
                <div style="color:#94a3b8; font-size:0.8rem; font-weight:600; margin-bottom:8px;">🕒 歷史資料區間</div>
                <div style="color:#f1f5f9; font-size:0.75rem; font-weight:600; margin-bottom:2px; font-family: monospace;">{date_range_str}</div>
            </div>
            """, unsafe_allow_html=True
        )

    # 畫面渲染：主要資料大廳
    html_cards = '<div class="flex-matrix-container">'
    for d in display_list:
        score = d.get('Score', 0)
        price = d.get('Close', 0.0)
        high_today = d.get('High', 0.0)
        atr = d.get('ATR', 0.0)
        
        price_str = f"NT$ {price:.2f}" if price > 0 else "N/A"
        high_str = f"{high_today:.2f}" if high_today > 0 else "N/A"
        
        # 判斷多頭動能
        rsi_msg = "<span style='color:#10b981; font-weight:700;'>🚀 多頭排列</span>" if (d.get('RSI_6', 0) > d.get('RSI_14', 0) > d.get('RSI_24', 0)) else "<span style='color:#64748b;'>🔄 震盪整理</span>"
        
        if score >= config.setup_score_threshold:
            stop_tgt = high_today - (config.atr_multiplier * atr)
            risk_pct = (high_today - stop_tgt) / high_today * 100 if high_today > 0 else 0
            action_html = f'<div class="custom-alert-box action-buy">🎯 突破 {high_str} 買進 | 守 {stop_tgt:.1f} (-{risk_pct:.1f}%)</div>'
        else:
            action_html = f'<div class="custom-alert-box action-wait">⏳ 觀察多頭動能續航</div>'

        # 組裝 HTML 小卡
        card = (
            f'<div class="stock-compact-card">'
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

if __name__ == "__main__":
    main()
