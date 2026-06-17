import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import plotly.graph_objects as gr
from plotly.subplots import make_subplots

# 1. 網頁基本設定
st.set_page_config(page_title="V02.1 台股50戰情室", page_icon="🚀", layout="wide")
st.title("🚀 V02.1 台股 50 視覺化數據中心")
st.markdown("本網頁直接讀取雲端回測資料庫 `tw50_strategy.db` 的即時數據進行分析。")

# 2. 連結資料庫
@st.cache_data
def load_data_from_db():
    conn = sqlite3.connect('tw50_strategy.db')
    # 讀取價格與交易紀錄
    df_price = pd.read_sql_query("SELECT * FROM daily_price", conn)
    df_trades = pd.read_sql_query("SELECT * FROM backtest_trades", conn)
    conn.close()
    
    # 轉換日期格式
    df_price['Date'] = pd.to_datetime(df_price['Date'])
    return df_price, df_trades

try:
    df_price, df_trades = load_data_from_db()
except Exception as e:
    st.error(f"無法讀取資料庫，請確保 'tw50_strategy.db' 檔案已放在正確的資料夾中。錯誤: {e}")
    st.stop()

# 3. 在網頁端動態重算 V02.1 分數趨勢 (確保圖表資料完整)
def compute_scores_for_app(df):
    df = df.sort_values('Date').reset_index(drop=True)
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['MA120'] = df['Close'].rolling(120).mean()
    df['V_MA5'] = df['Volume'].rolling(5).mean()
    df['V_MA10'] = df['Volume'].rolling(10).mean()
    
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = ema12 - ema26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['DEA']
    df['Prev_Hist'] = df['MACD_Hist'].shift(1)
    
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=13, adjust=False).mean()
    ema_down = down.ewm(com=13, adjust=False).mean()
    df['RSI'] = 100 - (100 / (1 + (ema_up / ema_down)))
    
    low_min = df['Low'].rolling(9).min()
    high_max = df['High'].rolling(9).max()
    df['RSV'] = 100 * (df['Close'] - low_min) / (high_max - low_min)
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    t1 = (df['DIF'] > df['DEA']).astype(int) * 15
    t2 = (df['DIF'] > 0).astype(int) * 5
    t3 = (df['MACD_Hist'] > df['Prev_Hist']).astype(int) * 10
    
    m1 = (df['Close'] > df['MA20']).astype(int) * 5
    m2 = (df['MA20'] > df['MA60']).astype(int) * 10
    m3 = (df['MA60'] > df['MA120']).astype(int) * 10
    
    r1 = (df['RSI'] > 50).astype(int) * 5
    r2 = (df['RSI'] > 60).astype(int) * 5
    r3 = (df['K'] > df['D']).astype(int) * 10
    
    v1 = (df['Volume'] > df['V_MA5']).astype(int) * 5
    v2 = (df['Volume'] > df['V_MA10']).astype(int) * 5
    v3 = (df['Volume'] > df['V_MA5'] * 1.5).astype(int) * 5
    
    df['Score'] = t1 + t2 + t3 + m1 + m2 + m3 + r1 + r2 + r3 + v1 + v2 + v3
    return df

# 4. 側邊欄：選擇個股
ticker_list = sorted(df_price['ticker'].unique())
selected_ticker = st.sidebar.selectbox("🔍 選擇分析個股", ticker_list)

# 篩選特定個股資料
sub_price = df_price[df_price['ticker'] == selected_ticker].copy()
sub_price = compute_scores_for_app(sub_price)
sub_trades = df_trades[df_trades['ticker'] == selected_ticker].copy()

# 5. 主畫面 KPI 看板
latest_day = sub_price.iloc[-1]
prev_day = sub_price.iloc[-2]
current_score = int(latest_day['Score'])
delta_score = current_score - int(prev_day['Score'])

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("V02.1 最新評分", f"{current_score} 分", delta=f"{delta_score} 分")
with col2:
    ma20_status = "站上 MA20 偏多" if latest_day['Close'] >= latest_day['MA20'] else "跌破 MA20 偏空"
    st.metric("均線結構 (月線位階)", ma20_status)
with col3:
    total_wins = len(sub_trades[sub_trades['profit_pct'] > 0])
    win_rate = (total_wins / len(sub_trades) * 100) if len(sub_trades) > 0 else 0
    st.metric("10年策略回測勝率", f"{win_rate:.1f} %", f"總交易 {len(sub_trades)} 次")

# 6. 繪製雙軸互動圖表 (股價 + V02.1 分數走勢)
st.subheader("📊 歷史走勢與策略動態觀測")

fig = make_subplots(specs=[[{"secondary_y": True}]])
# 畫股價
fig.add_trace(gr.Scatter(x=sub_price['Date'], y=sub_price['Close'], name="收盤價", line=dict(color='gray', width=1.5)), secondary_y=False)
fig.add_trace(gr.Scatter(x=sub_price['Date'], y=sub_price['MA20'], name="MA20 月線", line=dict(dash='dash')), secondary_y=False)
# 畫分數
fig.add_trace(gr.Scatter(x=sub_price['Date'], y=sub_price['Score'], name="V02.1 分數", line=dict(color='orange', width=2)), secondary_y=True)

# 加上 75 分進場門檻參考線
fig.add_shape(type="line", x0=sub_price['Date'].min(), y0=75, x1=sub_price['Date'].max(), y1=75, line=dict(color="red", dash="dot"), secondary_y=True)

fig.update_layout(title_text=f"{selected_ticker} 10年股價與策略分數對照圖", hovermode="x unified")
fig.update_yaxes(title_text="<b>股價 (元)</b>", secondary_y=False)
fig.update_yaxes(title_text="<b>V02.1 策略分數</b>", range=[0, 105], secondary_y=True)

st.plotly_chart(fig, use_container_width=True)

# 7. 顯示歷史交易明細
st.subheader("💼 10 年策略模擬進出場明細")
if not sub_trades.empty:
    sub_trades['profit_pct'] = (sub_trades['profit_pct'] * 100).round(2)
    # 欄位中文化優化
    show_trades = sub_trades[['entry_date', 'exit_date', 'entry_price', 'exit_price', 'profit_pct']].rename(
        columns={'entry_date': '進場日期', 'exit_date': '出場日期', 'entry_price': '進場價', 'exit_price': '出場價', 'profit_pct': '報酬率 (%)'}
    ).sort_values('進場日期', ascending=False)
    
    st.dataframe(show_trades, use_container_width=True)
else:
    st.info("該標的在過去 10 年內未觸發任何完整交易訊號。")
