# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : 台股戰情室 Streamlit 監控儀表板
# 檔案名稱 : Tw50_app_v03.36.py
# 程式版本 : TW50_app_v03.36 (動態撈取 Main 版本與動態推播組裝)
#
# 📋 進版說明 (Version Notes):
#   1. 優化手動推播：按鈕觸發時自動撈取 score >= 45 的標的，並以極簡 Emoji 格式發送。
#   2. 優化版本顯示：自動去資料庫 backtest_trades 撈取 Main 引擎的最新版本號，無需手動更改。
#
# 🏷️ 區塊說明 (Block Description):
#   - 1~2: 頁面設定與 MON 精美卡片 CSS 樣板 (完全保留不變)
#   - 3: 系統全域常數與動態版本號撈取函式
#   - 4: 💾 單一資料庫讀取 
#   - 6: 初始化監測清單
#   - 7: 側邊欄控制面板 (包含動態推播組裝與動態版本號顯示)
#   - 8: 📈 主畫面看盤終端矩陣 (直接讀取資料庫渲染 HTML)
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# ==========================================================

import streamlit as st
import pandas as pd
import numpy as np
import os
import json
import urllib.request
import datetime
import pytz
import sqlite3
from streamlit_autorefresh import st_autorefresh
from dataclasses import dataclass

# ==========================================================
# 1️⃣ 頁面設定與全域配置
# ==========================================================
st.set_page_config(
    page_title="台股戰情室監控大廳",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================================
# 2️⃣ CSS 樣板注入 (深色主題、小卡排版、側邊欄元件)
# ==========================================================
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

.alert-tw-up { color: #ef4444; background-color: rgba(239, 68, 68, 0.2) !important; width: 100%; text-align: center; padding: 5px; border-radius: 6px; }

.card-title-txt { margin: 0 0 2px 0; font-size: 1.25rem; font-weight: 700; color: #ffffff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; justify-content: space-between; align-items: baseline; }
.card-price-txt { color: #38bdf8; margin: 0 0 10px 0; font-size: 1.9rem; font-weight: 700; }
.card-middle-layout { display: flex; justify-content: space-between; margin-bottom: 4px; }
.layout-left-col { flex: 1.1; border-right: 1px dashed #2d3748; padding-right: 4px; text-align: left !important; line-height: 1.7; }
.layout-right-col { flex: 0.9; text-align: left !important; padding-left: 12px; line-height: 1.7; }
.txt-label { color: #94a3b8; font-size: 0.82rem; white-space: nowrap; } 
.txt-label-rsi { color: #a78bfa; font-size: 0.82rem; white-space: nowrap; } 
.txt-bold-val { color: #f1f5f9; font-size: 0.82rem; font-weight: 600; }
.custom-alert-box { min-height: 38px; display: flex; align-items: center; justify-content: center; border-radius: 6px; margin-top: 10px; font-size: 0.82rem; font-weight: 700; box-sizing: border-box; }

/* =========================================
   TW50 專屬卡片細節
   ========================================= */
h1.main-title { color: #f8fafc; font-weight: 800; text-align: left; padding-bottom: 10px; border-bottom: 2px solid #1e293b; margin-bottom: 20px; font-size: 1.8rem; }
.score-highlight { color: #facc15; font-size: 1.6rem; font-weight: 900; }
</style>
''', unsafe_allow_html=True)

# ==========================================================
# 3️⃣ 🚀 全域常數、動態版本撈取與 TG 通報模組
# ==========================================================
APP_VERSION = "TW50_app_v03.36"
DB_NAME = "tw50_strategy.db"
TAIPEI_TZ = pytz.timezone('Asia/Taipei')

@dataclass
class StrategyConfig:
    setup_score_threshold: int = 45

config = StrategyConfig()

def safe_rerun():
    if hasattr(st, 'rerun'): st.rerun()
    else: st.experimental_rerun()

def get_main_version_from_db():
    """
    🔍 偵測資料庫中 backtest_trades 表格留存的最高（最新）版本號
    """
    if os.path.exists(DB_NAME):
        try:
            with sqlite3.connect(DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(version) FROM backtest_trades")
                res = cursor.fetchone()
                if res and res[0]:
                    return res[0]
        except: pass
    return "vUnknown"

def get_db_last_update_time():
    """
    🔍 偵測 SQLite 資料庫的最後更新時間
    """
    if os.path.exists(DB_NAME):
        try:
            mtime = os.path.getmtime(DB_NAME)
            dt = datetime.datetime.fromtimestamp(mtime, tz=TAIPEI_TZ)
            return dt.strftime("%H:%M:%S %m/%d/%Y")
        except: pass
    return "N/A"

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
# 4️⃣ 💾 SSOT 直連資料庫讀取
# ==========================================================
@st.cache_data(ttl=60)
def load_signals_from_db():
    if not os.path.exists(DB_NAME):
        return pd.DataFrame(), f"⚠️ 找不到後端資料庫 ({DB_NAME})，請確認 Main 引擎已執行。"
    try:
        with sqlite3.connect(DB_NAME) as conn:
            # 直接讀取 Main 算好的終極結果
            df = pd.read_sql_query("SELECT * FROM dashboard_signals", conn)
        return df, "✅ 載入成功"
    except Exception as e: 
        return pd.DataFrame(), f"❌ 資料庫讀取錯誤: {e}"

# ==========================================================
# 6️⃣ 💾 初始化監測清單與記憶狀態
# ==========================================================
if 'custom_watch' not in st.session_state: 
    st.session_state.custom_watch = []

# ==========================================================
# 7️⃣ ⚙️ 側邊欄控制面板
# ==========================================================
with st.sidebar:
    
    with st.container(border=True):
        st.markdown("### ⚙️ 控制與設定面板")

    with st.container(border=True):
        st.markdown("### ➕ 自訂置頂股票")
        st.markdown("<div style='color:#38bdf8; font-size:1.0rem; font-weight:700; margin-bottom:5px;'>✍️ 從資料庫中強制顯示</div>", unsafe_allow_html=True)
        nt = st.text_input("輸入股票代碼", value="", placeholder="例: 2330.TW", key="sym_manual").strip().upper()
        if st.button("確認輸入", use_container_width=True, key="btn_manual"):
            if nt and nt not in st.session_state.custom_watch:
                st.session_state.custom_watch.append(nt)
            safe_rerun()

    with st.container(border=True):
        st.markdown("### 🗑️ 移除置頂清單")
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
        refresh_sec = st.slider("秒", 5, 60, 30, label_visibility="collapsed")
        if st.button("🔄 手動立即刷新", use_container_width=True):
            st.cache_data.clear()
            safe_rerun()
            
    with st.container(border=True):
        st.markdown("### 🛠️ 手動測試推播")
        if st.button("發送目前小卡狀態", use_container_width=True):
            with st.spinner("🚀 正在執行判定與通報..."):
                main_version_str = get_main_version_from_db()
                now_str = datetime.datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d %H:%M:%S")
                
                # 🎯 動態組裝 Telegram 報告
                msg_parts = [
                    f"📊 <b>{main_version_str} 台股戰情室回報</b>",
                    f"🕒 {now_str}",
                    "================"
                ]
                
                # 撈取並過濾目前達標清單
                df_signals_alert, _ = load_signals_from_db()
                alerts_setup = []
                
                if not df_signals_alert.empty:
                    df_setup = df_signals_alert[df_signals_alert['score'] >= config.setup_score_threshold].sort_values(by='score', ascending=False)
                    for _, row in df_setup.iterrows():
                        tk = row['ticker']
                        sc = int(row['score'])
                        hi = row['high']
                        st_tgt = row['stop_tgt']
                        rp = row['risk_pct']
                        alerts_setup.append(f"🔥{tk} | 📊{sc} | 🟢{hi:.2f} | 🔴 {st_tgt:.2f} (-{rp:.1f}%)")
                
                if alerts_setup:
                    msg_parts.append("🎯 <b>潛力突破 SETUP 標的</b>")
                    msg_parts.extend(alerts_setup)
                else:
                    msg_parts.append("🎯 盤面無達標突破標的。")
                    
                msg_parts.append("================")
                msg_parts.append("✅ 網頁與資料庫連線正常！")
                
                final_msg = "\n".join(msg_parts)
                send_telegram_alert(final_msg)
                st.success("✅ 回測通報已成功發送至 Telegram！")

    # 🕒 獲取動態版本號與時間戳
    main_display_ver = get_main_version_from_db()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    tpe_now = now_utc.astimezone(TAIPEI_TZ)
    tpe_time_str = tpe_now.strftime("%H:%M:%S %m/%d/%Y")
    db_update_time_str = get_db_last_update_time()

    st.markdown(
        f"""
        <div style="background-color:#1e293b; padding:12px; border-radius:8px; border:1px solid #475569; margin-top:15px; margin-bottom:15px;">
            <div style="color:#94a3b8; font-size:0.8rem; font-weight:600; margin-bottom:4px; text-align:center;">系統當前版本</div>
            <div style="color:#38bdf8; font-size:1.0rem; font-weight:700; text-align:center; margin-bottom:2px;">{APP_VERSION}</div>
            <div style="color:#38bdf8; font-size:1.0rem; font-weight:700; text-align:center; margin-bottom:10px;">TW50_main_{main_display_ver}</div>
            <div style="border-top: 1px dashed #475569; margin: 10px 0;"></div>
            <div style="color:#94a3b8; font-size:0.8rem; font-weight:600; margin-bottom:4px;">🤖 最後資料庫更新</div>
            <div style="color:#f1f5f9; font-size:0.88rem; font-weight:600; margin-bottom:8px; padding-left: 5px;">Tw {db_update_time_str}</div>
            <div style="color:#94a3b8; font-size:0.8rem; font-weight:600; margin-bottom:4px;">🕒 最後資料更新</div>
            <div style="color:#f1f5f9; font-size:0.88rem; font-weight:600; padding-left: 5px;">Tw {tpe_time_str}</div>
        </div>
        """, unsafe_allow_html=True
    )

# ==========================================================
# 8️⃣ 📈 主畫面看盤終端矩陣 (SSOT 極速渲染)
# ==========================================================
st.markdown('<h1 class="main-title">📈 台股 50 戰情室監控大廳</h1>', unsafe_allow_html=True)

df_signals, status_msg = load_signals_from_db()

if df_signals.empty:
    st.error(status_msg)
else:
    # 🎯 防呆檢查：確認自選股是否真的存在於後端資料庫中
    db_tickers = df_signals['ticker'].values
    not_found = [tk for tk in st.session_state.custom_watch if tk not in db_tickers]
    if not_found:
        st.warning(f"⚠️ 以下自選股未在後端 Main 引擎的監測清單中，無法取得資料：{', '.join(not_found)}")

    display_list = []
    
    for _, row in df_signals.iterrows():
        d = row.to_dict()
        ticker = d['ticker']
        score = d.get('score', 0)
        
        # 顯示條件：分數達標，或者是使用者強制加入的自選股
        is_setup = score >= config.setup_score_threshold
        is_custom = ticker in st.session_state.custom_watch
        
        if is_setup or is_custom:
            display_list.append(d)

    # 排序：高分優先
    display_list = sorted(display_list, key=lambda x: x.get('score', 0), reverse=True)
    
    if not display_list:
        st.info("📌 目前盤面上暫無動能評分達標之強勢標的，請持續觀察。")
    else:
        html_cards = '<div class="flex-matrix-container">'
        for d in display_list:
            score = d.get('score', 0)
            price = d.get('close', 0.0)
            high_today = d.get('high', 0.0)
            stop_tgt = d.get('stop_tgt', 0.0)
            risk_pct = d.get('risk_pct', 0.0)
            
            price_str = f"NT$ {price:.2f}" if price > 0 else "N/A"
            high_str = f"{high_today:.2f}" if high_today > 0 else "N/A"
            
            # 從資料庫提取 RSI
            r6, r14, r24 = d.get('rsi_6', 0), d.get('rsi_14', 0), d.get('rsi_24', 0)
            rsi_msg = "<span style='color:#10b981; font-weight:700;'>🚀 多頭排列</span>" if (r6 > r14 > r24) else "<span style='color:#64748b;'>🔄 震盪整理</span>"
            
            action_html = f'<div class="custom-alert-box alert-tw-up">🎯 突破 {high_str} 買進 | 守 {stop_tgt:.1f} (-{risk_pct:.1f}%)</div>'

            card = (
                f'<div class="stock-compact-card">'
                f'<div class="card-title-txt">{d["ticker"]} <span class="score-highlight">{score}</span></div>'
                f'<div class="card-price-txt">{price_str}</div>'
                f'<div class="card-middle-layout">'
                f'<div class="layout-left-col">'
                f'<span class="txt-label">MACD:</span><span class="txt-bold-val">{d.get("s1",0)}</span><br>'
                f'<span class="txt-label">MA20:</span><span class="txt-bold-val">{d.get("s2",0)}</span><br>'
                f'<span class="txt-label">斜率:</span><span class="txt-bold-val">{d.get("s3",0)}</span><br>'
                f'<span class="txt-label">趨勢:</span><span class="txt-bold-val">{d.get("s4",0)}</span><br>'
                f'<span class="txt-label">量能:</span><span class="txt-bold-val">{d.get("s5",0)}</span>'
                f'</div>'
                f'<div class="layout-right-col">'
                f'<span class="txt-label-rsi">R6:</span><span class="txt-bold-val">{r6:.1f}</span><br>'
                f'<span class="txt-label-rsi">R14:</span><span class="txt-bold-val">{r14:.1f}</span><br>'
                f'<span class="txt-label-rsi">R24:</span><span class="txt-bold-val">{r24:.1f}</span><br>'
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
