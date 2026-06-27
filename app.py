# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐•
# 專案名稱 : 台股戰情室 Streamlit 監控儀表板 (UI 側邊欄優化版)
# 檔案名稱 : app.py
# 策略版本 : v03.13 (同步後台 v02.16 真實 Portfolio Equity 演算法與查詢標籤)
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

# --- 頁面基本設定 ---
st.set_page_config(
    page_title="台股戰情室監控大廳",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

APP_VERSION = "v03.13"
TAIPEI_TZ = pytz.timezone('Asia/Taipei')

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
# Prt.02 頂級深色優化視覺 CSS (側邊欄白色框線版)
# ==============================
st.markdown(r'''
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [data-testid="stAppViewContainer"] { font-family: 'Inter', sans-serif !important; }
[data-testid="stActionElements"] { display: none !important; }
header[data-testid="stHeader"] { background-color: transparent !important; }
.main .block-container { padding-top: 1.5rem !important; margin-top: -30px !important; }
h1.main-title { color: #f8fafc; font-weight: 800; text-align: left; padding-bottom: 10px; border-bottom: 2px solid #1e293b; margin-bottom: 20px; font-size: 1.8rem; }
html, body, [data-testid="stAppViewContainer"] { background-color: #0e1117 !important; color: #f1f5f9 !important; }
[data-testid="stSidebar"] { background-color: #171a23 !important; border-right: 1px solid #2d3748 !important; }

/* 1 & 3. 側邊欄常規功能區塊：改為白色框線 */
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] { 
    background-color: #171a23 !important; 
    border: 1px solid #ffffff !important; 
    border-radius: 12px !important; 
    padding: 15px !important; 
    margin-bottom: 15px !important; 
}

/* 2. 左下角獨立功能區塊：灰色底、白色框線 */
.sidebar-bottom-block {
    background-color: #2d3748 !important; 
    border: 1px solid #ffffff !important; 
    border-radius: 12px !important; 
    padding: 15px !important; 
    margin-top: 40px !important; 
}

.stTextInput div[data-baseweb="input"] { background-color: #0f172a !important; border: 1px solid #475569 !important; border-radius: 8px !important; }
.stTextInput input { color: #ffffff !important; background-color: transparent !important; }
[data-testid="stSidebar"] h3 { color: #ffffff !important; font-size: 1.1rem !important; font-weight: 700 !important; margin-bottom: 15px !important; margin-top: 0px !important; padding-top: 0px !important; }
.stButton > button { background: linear-gradient(135deg, #3b82f6, #1d4ed8) !important; color: white !important; border: none !important; border-radius: 8px !important; font-weight: 600 !important; transition: all 0.2s ease !important; }
.stButton > button:hover { box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4) !important; transform: translateY(-1px) !important; }

/* 網格與卡片設計 */
.flex-matrix-container { display: flex; flex-wrap: wrap; gap: 14px; width: 100%; justify-content: flex-start !important; margin-bottom: 15px; }
.stock-compact-card { background-color: #171a23; border: 1px solid #2d3748; border-radius: 12px; padding: 16px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2); width: 295px !important; max-width: 295px !important; min-width: 295px !important; box-sizing: border-box; transition: transform 0.2s, border-color 0.2s; }
.stock-compact-card:hover { transform: translateY(-3px); border-color: #3b82f6; }

.card-title-txt { margin: 0 0 2px 0; font-size: 1.25rem; font-weight: 700; color: #ffffff; display: flex; justify-content: space-between; align-items: baseline; }
.card-price-txt { color: #38bdf8; margin: 0 0 10px 0; font-size: 1.9rem; font-weight: 700; }
.score-highlight { color: #facc15; font-size: 1.6rem; font-weight: 900; }

.card-middle-layout { display: flex; justify-content: space-between; margin-bottom: 4px; }
.layout-left-col { flex: 1; border-right: 1px dashed #2d3748; padding-right: 4px; text-align: left !important; line-height: 1.6; }
.layout-right-col { flex: 1; text-align: left !important; padding-left: 12px; line-height: 1.6; }
.txt-label { color: #94a3b8; font-size: 0.8rem; white-space: nowrap; }
.txt-label-rsi { color: #a78bfa; font-size: 0.8rem; white-space: nowrap; }
.txt-bold-val { color: #f1f5f9; font-size: 0.8rem; font-weight: 600; padding-left: 4px; }

/* 行動警示框 */
.custom-alert-box { min-height: 38px; display: flex; align-items: center; justify-content: center; border-radius: 6px; margin-top: 10px; font-size: 0.85rem; font-weight: 700; box-sizing: border-box; }
.action-buy { color: #f2cc60; background-color: rgba(242, 204, 96, 0.15) !important; border: 1px dashed #f2cc60; }
.action-wait { color: #94a3b8; background-color: rgba(148, 163, 184, 0.1) !important; border: 1px dashed #475569; }
</style>
''', unsafe_allow_html=True)

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
# Prt.04 技術指標與 v02.12 安全評分
# ==============================
def calculate_v0212_score(df_stock):
    df = df_stock.dropna(subset=['Close']).sort_values('Date').copy()
    if len(df) < 2: return None

    df['MA20'] = df['Close'].rolling(window=min(20, len(df))).mean().fillna(0)
    df['MA60'] = df['Close'].rolling(window=min(60, len(df))).mean().fillna(0)
    df['V_MA5'] = df['Volume'].rolling(window=min(5, len(df))).mean().fillna(0)
    
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

    today_close = today.get('Close', 0)
    today_vol = today.get('Volume', 0)
    today_macd = today.get('MACD_Hist', 0)
    yest_macd = yest.get('MACD_Hist', 0)
    today_ma20 = today.get('MA20', 0)
    today_ma60 = today.get('MA60', 0)
    today_vma5 = today.get('V_MA5', 0)

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
# Prt.05 總體績效結算模組 (已升級為 Portfolio Equity 演算法)
# ==============================
def generate_performance_report(conn, version):
    try:
        # 新增抓取 entry_date 以利建立每日時間軸
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
        
        avg_win = win_trades['profit_pct'].mean() if not win_trades.empty else 0
        avg_loss = loss_trades['profit_pct'].mean() if not loss_trades.empty else 0
        expectancy = (avg_win * (len(win_trades) / total_trades)) + (avg_loss * (len(loss_trades) / total_trades))
        
        # --- 🎯 資金組合曲線 (Portfolio Equity Curve) 模擬 ---
        # 假設資金管理設定：每筆交易固定投入總資產的 10%
        weight_per_trade = 0.10
        
        df['entry_date'] = pd.to_datetime(df['entry_date'])
        df['exit_date'] = pd.to_datetime(df['exit_date'])
        
        daily_records = []
        
        # 將每筆交易利潤依持倉天數「線性平攤」，模擬每日標記回溯 (Daily Mark-to-Market)
        for _, row in df.iterrows():
            dr = pd.date_range(start=row['entry_date'], end=row['exit_date'], freq='D')
            hold_days = len(dr) - 1
            if hold_days > 0:
                daily_pnl = (row['profit_pct'] * weight_per_trade) / hold_days
                for d in dr[1:]:
                    daily_records.append({'date': d, 'pnl': daily_pnl})
            else:
                daily_records.append({'date': row['exit_date'], 'pnl': row['profit_pct'] * weight_per_trade})
                
        if daily_records:
            daily_df = pd.DataFrame(daily_records)
            # 依照日期將所有平行持倉的 PnL 加總
            port_daily = daily_df.groupby('date')['pnl'].sum().reset_index()
            port_daily = port_daily.sort_values('date')
            
            # 建立每日真實總體淨值
            port_daily['equity'] = 1.0 + port_daily['pnl'].cumsum()
            port_daily['peak'] = port_daily['equity'].cummax()
            port_daily['drawdown'] = (port_daily['equity'] - port_daily['peak']) / port_daily['peak']
            
            sys_mdd = port_daily['drawdown'].min() * 100
            
            days = (port_daily['date'].max() - port_daily['date'].min()).days
            final_equity = port_daily['equity'].iloc[-1]
            if days > 0 and final_equity > 0:
                cagr = ((final_equity ** (365.25 / days)) - 1) * 100
            else:
                cagr = (final_equity - 1) * 100 
        else:
            sys_mdd = 0
            cagr = 0
        
        report = (
            f"================\n"
            f"📈 <b>策略歷史績效健檢 (System Metrics)</b>\n"
            f"• 總交易筆數: {total_trades} 筆\n"
            f"• 勝率 (Win Rate): {win_rate:.1f}%\n"
            f"• 獲利因子 (Profit Factor): {profit_factor:.2f}\n"
            f"• 期望值 (Expectancy): {expectancy*100:.2f}%\n"
            f"• 年化報酬 (CAGR): {cagr:.1f}%\n"
            f"• 系統最大回撤 (Max DD): {sys_mdd:.1f}%\n"
            f"<i>*註: CAGR與MDD採固定10%資金平鋪持倉進行每日淨值模擬</i>"
        )
        return report
    except Exception as e:
        return f"================\n⚠️ 績效統計發生錯誤: {e}"

# ==============================
# Prt.06 主程式與渲染大廳
# ==============================
def main():
    st.markdown('<h1 class="main-title">📈 台股 50 戰情室監控大廳</h1>', unsafe_allow_html=True)
    st_autorefresh(interval=60 * 1000, key="refresh")
    
    df_raw, status_msg = load_csv_data()
    
    # 預設歷史區間顯示，若讀取到資料則動態更新
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
            data = calculate_v0212_score(df_tk)
            if data:
                data['ticker'] = tk
                display_list.append(data)
        except Exception as e:
            pass

    display_list = sorted(display_list, key=lambda x: x.get('Score', 0), reverse=True)

    # --- 側邊欄優化區塊 ---
    with st.sidebar:
        # 1. 控制與設定面板 (白色框線)
        with st.container(border=True):
            st.markdown("### ⚙️ 控制與設定面板")
            
            if st.button("🔄 刷新數據", use_container_width=True): 
                st.cache_data.clear()
                safe_rerun()
                
            # 🎯 更改按鈕名稱為「手動回測」
            if st.button("▶️ 手動回測", use_container_width=True):
                with st.spinner("🚀 正在執行判定與通報..."):
                    now_str = datetime.datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d %I.%M.%S %p")
                    msg = f"📊 <b>台股 50 戰情室 (手動健康檢查)</b>\n"
                    msg += f"🕒 {now_str} 回測\n================\n"
                    
                    setups = [d for d in display_list if d.get('Score', 0) >= 45]
                    if setups:
                        msg += "🎯 <b>滿足潛力起漲 (Score >= 45)</b>\n"
                        for s in setups:
                            msg += f"• {s['ticker']} (Score: {s['Score']}, 明日突破 {s.get('High', 0.0):.2f} 買進)\n"
                    else:
                        msg += "盤後無新增訊號。\n"
                    
                    # 🎯 對齊 v02.16 查詢標籤
                    try:
                        if os.path.exists("tw50_strategy.db"):
                            conn = sqlite3.connect("tw50_strategy.db")
                            report = generate_performance_report(conn, "v02.16")
                            msg += f"\n{report}\n"
                            conn.close()
                        else:
                            msg += "\n================\n⚠️ 找不到策略資料庫 (tw50_strategy.db)，請確認後台回測已執行。\n"
                    except Exception as db_e:
                        msg += f"\n================\n⚠️ 讀取策略資料庫失敗: {db_e}\n"
                        
                    msg += "================\n✅ 系統目前正常運作中"
                    is_success, error_reason = send_telegram_alert(msg)
                    
                    if is_success:
                        st.success("✅ 回測通報已成功發送至 Telegram！")
                    else:
                        st.error(f"❌ 發送失敗：{error_reason}")

        # 3. 新增監控 (白色框線)
        with st.container(border=True):
            st.markdown("### ➕ 新增監控")
            with st.form("add_tk"):
                nt = st.text_input("輸入代號 (例: 2330.TW)", label_visibility="collapsed")
                if st.form_submit_button("➕ 加入監控", use_container_width=True) and nt:
                    if 'custom_watch' not in st.session_state: 
                        st.session_state.custom_watch = []
                    if nt.upper() not in st.session_state.custom_watch:
                        st.session_state.custom_watch.append(nt.upper())
                    safe_rerun()

        # 2. 版本與歷史區間移至左下角 (灰色底 + 白色框線)
        st.markdown(f'''
        <div class="sidebar-bottom-block">
            <div style="font-weight: 700; color: #ffffff; margin-bottom: 6px; font-size: 0.95rem;">ℹ️ 系統狀態</div>
            <div style="color: #e2e8f0; font-size: 0.82rem;">系統版本: {APP_VERSION}</div>
            <div style="color: #e2e8f0; font-size: 0.82rem; margin-top: 4px; line-height: 1.4;">
                🕒 歷史資料區間:<br><span style="font-family: monospace;">{date_range_str}</span>
            </div>
        </div>
        ''', unsafe_allow_html=True)

    # 畫面渲染：主要資料大廳
    html_cards = '<div class="flex-matrix-container">'
    for d in display_list:
        score = d.get('Score', 0)
        price = d.get('Close', 0.0)
        high_today = d.get('High', 0.0)
        
        price_str = f"NT$ {price:.2f}" if price > 0 else "N/A"
        high_str = f"{high_today:.2f}" if high_today > 0 else "N/A"
        
        # 判斷多頭動能
        rsi_msg = "<span style='color:#10b981; font-weight:700;'>🚀 多頭排列</span>" if (d.get('RSI_6', 0) > d.get('RSI_14', 0) > d.get('RSI_24', 0)) else "<span style='color:#64748b;'>🔄 震盪整理</span>"
        
        # 行動提示框
        if score >= 45:
            action_html = f'<div class="custom-alert-box action-buy">🎯 明日突破 {high_str} 買進</div>'
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

if __name__ == "__main__":
    main()
