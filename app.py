# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
#  檔名：app.py
#  版次：v02.6 (視覺戰情室 - 效能與細節優化版)
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
#  新增與優化：
#  1. [效能A] 隨同後端引擎，移除網頁端不必要的 MA120 即時運算。
#  2. [視覺B] 全面套用 .format()，將價格、利潤、回撤皆精確控制至小數點後兩位。
#  3. [全域版本] 介面、預設搜尋器全面推進至 v02.6。
# ==========================================================

# ==========================================================
# 1️⃣ 🚀 系統全域設定與套件匯入
# ==========================================================
import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import plotly.graph_objects as gr
from plotly.subplots import make_subplots

st.set_page_config(page_title="V02.6 台股50戰情室", page_icon="🚀", layout="wide")
st.title("🚀 V02.6 台股 50 視覺化數據中心")
st.markdown("本網頁自動讀取雲端回測資料庫 `tw50_strategy.db`，展示包含單筆 MDD 等高階量化指標的即時分析。")

# ==========================================================
# 2️⃣ 🗄️ 資料庫讀取與快取模組
# ==========================================================
@st.cache_data(ttl=3600)
def load_data_from_db():
    try:
        conn = sqlite3.connect('tw50_strategy.db')
        df_price = pd.read_sql_query("SELECT * FROM daily_price", conn, parse_dates=['Date'])
        df_trades = pd.read_sql_query("SELECT * FROM backtest_trades", conn)
        conn.close()
        return df_price, df_trades
    except Exception as e:
        st.error(f"無法讀取資料庫，請確保 GitHub Actions 已成功生成資料庫。錯誤: {e}")
        st.stop()

df_price, df_trades = load_data_from_db()

# ==========================================================
# 3️⃣ 🧠 v02.6 網頁端即時評分引擎 (用於繪製動態圖表)
# ==========================================================
def compute_scores_for_app(df):
    df = df.sort_values('Date').reset_index(drop=True)
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['V_MA5'] = df['Volume'].rolling(5).mean()
    
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = ema12 - ema26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['DEA']
    
    t1 = (df['MACD_Hist'] > df['MACD_Hist'].shift(1)).astype(int) * 15 
    m1 = (df['Close'] > df['MA20']).astype(int) * 10
    m2 = ((df['MA20'] / df['MA20'].shift(5) - 1) > 0.01).astype(int) * 15 
    m3 = (df['MA20'] > df['MA60']).astype(int) * 10
    v1 = (df['Volume'] > df['V_MA5'] * 1.3).astype(int) * 10 
    
    df['Score'] = t1 + m1 + m2 + m3 + v1
    return df

# ==========================================================
# 4️⃣ 🎛️ 側邊欄控制面板 (版本與個股篩選)
# ==========================================================
st.sidebar.header("⚙️ 戰術設定")

available_versions = df_trades['version'].unique().tolist() if 'version' in df_trades.columns else ["v02.6"]
selected_version = st.sidebar.selectbox("📂 選擇策略版本", available_versions, index=len(available_versions)-1 if available_versions else 0)

ticker_list = sorted(df_price['ticker'].unique())
selected_ticker = st.sidebar.selectbox("🔍 選擇分析個股", ticker_list)

sub_price = df_price[df_price['ticker'] == selected_ticker].copy()
sub_price = compute_scores_for_app(sub_price)

if 'version' in df_trades.columns:
    sub_trades = df_trades[(df_trades['ticker'] == selected_ticker) & (df_trades['version'] == selected_version)].copy()
else:
    sub_trades = df_trades[df_trades['ticker'] == selected_ticker].copy()

# ==========================================================
# 5️⃣ 📊 主畫面 KPI 戰術看板
# ==========================================================
if len(sub_price) >= 2:
    latest_day = sub_price.iloc[-1]
    prev_day = sub_price.iloc[-2]
    current_score = int(latest_day['Score']) if pd.notna(latest_day['Score']) else 0
    delta_score = current_score - int(prev_day['Score']) if pd.notna(prev_day['Score']) else 0
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("v02.6 最新評分", f"{current_score} 分", delta=f"{delta_score} 分")
    with col2:
        ma20_status = "🟢 站上月線" if latest_day['Close'] >= latest_day['MA20'] else "🔴 跌破月線"
        st.metric("MA20 狀態", ma20_status)
    with col3:
        total_trades = len(sub_trades)
        total_wins = len(sub_trades[sub_trades['profit_pct'] > 0])
        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        st.metric("策略勝率", f"{win_rate:.1f} %", f"總交易 {total_trades} 次", delta_color="off")
    with col4:
        avg_profit = sub_trades['profit_pct'].mean() * 100 if total_trades > 0 else 0
        st.metric("平均單筆報酬", f"{avg_profit:.2f} %", delta_color="off")

# ==========================================================
# 6️⃣ 📈 雙軸互動圖表 (股價 + 策略分數)
# ==========================================================
st.subheader("📈 歷史走勢與策略動態觀測")

fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_trace(gr.Scatter(x=sub_price['Date'], y=sub_price['Close'], name="收盤價", line=dict(color='gray', width=1.5)), secondary_y=False)
fig.add_trace(gr.Scatter(x=sub_price['Date'], y=sub_price['MA20'], name="MA20 月線", line=dict(dash='dash')), secondary_y=False)
fig.add_trace(gr.Scatter(x=sub_price['Date'], y=sub_price['Score'], name="v02.6 分數", line=dict(color='orange', width=2)), secondary_y=True)

fig.add_shape(type="line", x0=sub_price['Date'].min(), y0=45, x1=sub_price['Date'].max(), y1=45, line=dict(color="red", dash="dot"), secondary_y=True)

fig.update_layout(title_text=f"{selected_ticker} 走勢與 v02.6 分數對照", hovermode="x unified", height=500)
fig.update_yaxes(title_text="<b>股價 (元)</b>", secondary_y=False)
fig.update_yaxes(title_text="<b>v02.6 策略分數</b>", range=[0, 65], secondary_y=True)

st.plotly_chart(fig, use_container_width=True)

# ==========================================================
# 7️⃣ 💼 歷史回測紀錄 (高階量化分析表)
# ==========================================================
st.subheader(f"💼 {selected_version} 策略實戰明細")

if not sub_trades.empty:
    sub_trades['profit_pct'] = (sub_trades['profit_pct'] * 100).round(2)
    mdd_col = 'trade_max_drawdown_pct' if 'trade_max_drawdown_pct' in sub_trades.columns else 'max_drawdown_pct'
    
    if mdd_col in sub_trades.columns and 'max_profit_pct' in sub_trades.columns:
        sub_trades['max_profit_pct'] = (sub_trades['max_profit_pct'] * 100).round(2)
        sub_trades[mdd_col] = (sub_trades[mdd_col] * 100).round(2)
        
        show_trades = sub_trades[['entry_date', 'exit_date', 'entry_price', 'exit_price', 'holding_bars', 'max_profit_pct', mdd_col, 'profit_pct']].rename(
            columns={
                'entry_date': '進場日期', 'exit_date': '出場日期', 
                'entry_price': '進場價', 'exit_price': '出場價', 
                'holding_bars': '持倉K棒數',
                'max_profit_pct': '最大利潤 (%)', mdd_col: '單筆MDD (%)',
                'profit_pct': '最終報酬 (%)'
            }
        ).sort_values('進場日期', ascending=False)
    else:
        show_trades = sub_trades[['entry_date', 'exit_date', 'entry_price', 'exit_price', 'profit_pct']].rename(
            columns={'entry_date': '進場日期', 'exit_date': '出場日期', 'entry_price': '進場價', 'exit_price': '出場價', 'profit_pct': '最終報酬 (%)'}
        ).sort_values('進場日期', ascending=False)
    
    st.dataframe(
        show_trades.style
        .format({
            '進場價': '{:.2f}', 
            '出場價': '{:.2f}',
            '最大利潤 (%)': '{:.2f}',
            '單筆MDD (%)': '{:.2f}',
            '最終報酬 (%)': '{:.2f}'
        })
        .background_gradient(subset=['最終報酬 (%)'], cmap='RdYlGn', vmin=-10, vmax=30), 
        use_container_width=True
    )
else:
    st.info(f"該標的在目前資料庫中，未觸發任何 {selected_version} 的完整交易訊號。")
