# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
#  檔名：main.py
#  版次：v02.6 (回測精確對齊與 DBA 強制升級版)
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
#  新增與優化：
#  1. [訊號A] Buy Stop 真實對齊：修正為 `> signal_day_high`，首日達標才算有效 Setup。
#  2. [訊號B] 價格預估精確化：推播加入 trigger_price 與 estimated_entry。
#  3. [資料庫C] Schema Migration：新增 DROP TABLE 機制強制升級結構，防舊欄位報錯。
#  4. [資料庫D] DBA 精簡化：移除冗餘的 ticker 複合索引。
#  5. [效能E] 移除未使用的 MA120，徹底釋放 CPU 運算資源。
# ==========================================================

# ==========================================================
# 1️⃣ 🚀 系統全域設定與套件匯入
# ==========================================================
import pandas as pd
import numpy as np
import yfinance as yf
import sqlite3
import datetime
import os
import urllib.request
import json

tw50_tickers = [
    '2330.TW', '2454.TW', '2303.TW', '3711.TW', '3034.TW', '2379.TW',
    '2317.TW', '2308.TW', '2382.TW', '3231.TW', '2324.TW', '2357.TW', 
    '2395.TW', '3008.TW', '3037.TW', '6669.TW', '3661.TW', '2345.TW', 
    '2301.TW', '2408.TW', '2412.TW', '3045.TW', '4904.TW', '2881.TW', 
    '2882.TW', '2891.TW', '2886.TW', '2884.TW', '2892.TW', '2885.TW', 
    '2880.TW', '2883.TW', '2887.TW', '2890.TW', '5880.TW', '5871.TW',
    '1301.TW', '1303.TW', '1326.TW', '6505.TW', '2603.TW', '2609.TW', 
    '2615.TW', '2002.TW', '1101.TW', '1216.TW', '2207.TW', '2912.TW', 
    '9904.TW', '1590.TW'
]

TAIPEI_TZ = datetime.timezone(datetime.timedelta(hours=8))

# ==========================================================
# 2️⃣ 📡 Telegram 警報推播模組
# ==========================================================
def send_telegram_alert(message):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("未設定 Telegram 金鑰，跳過推播。")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req)
        print("✅ Telegram 推播成功！")
    except Exception as e:
        print(f"❌ Telegram 推播失敗: {e}")

# ==========================================================
# 3️⃣ 🗄️ SQLite 資料庫建置與連線模組
# ==========================================================
def init_db(db_name="tw50_strategy.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_price (
            ticker TEXT, Date TEXT, Open REAL, High REAL, Low REAL, Close REAL, Volume INTEGER,
            PRIMARY KEY (ticker, Date)
        )
    ''')
    
    # 強制執行 Schema Migration 確保新欄位 trade_max_drawdown_pct 正確寫入
    cursor.execute("DROP TABLE IF EXISTS backtest_trades")
    cursor.execute('''
        CREATE TABLE backtest_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT, ticker TEXT, entry_date TEXT, exit_date TEXT, 
            entry_price REAL, exit_price REAL, profit_pct REAL,
            holding_bars INTEGER, max_profit_pct REAL, trade_max_drawdown_pct REAL, entry_score REAL
        )
    ''')
    conn.commit()
    return conn

# ==========================================================
# 4️⃣ 🧠 v02.6 核心評分與實戰回測引擎
# ==========================================================
def calculate_v026_and_backtest(df, ticker, strategy_version="v02.6"):
    df = df.sort_values('Date').dropna().reset_index(drop=True)
    
    # 移除無用的 MA120，釋放 CPU 效能
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
    
    trades = []
    in_position = False
    entry_price = signal_day_high = entry_score = 0
    entry_date = None
    
    peak_price = 0
    entry_idx = 0
    trade_max_drawdown = 0.0
    
    # MA最高到60，迴圈從 65 開始即可
    for i in range(65, len(df)-1):
        today = df.iloc[i]
        tomorrow = df.iloc[i+1]
        yesterday = df.iloc[i-1]
        
        if not in_position:
            # 嚴格化 Setup 條件：首日達標才算 (消滅連續洗版)
            if today['Score'] >= 45 and yesterday['Score'] < 45: 
                signal_day_high = today['High']
                entry_score = today['Score']
                
                # 買進觸發：隔日必須大於 (真突破) 訊號日高點
                if tomorrow['High'] > signal_day_high:
                    in_position = True
                    entry_price = max(tomorrow['Open'], signal_day_high)
                    entry_date = tomorrow['Date']
                    entry_idx = i + 1
                    peak_price = entry_price 
                    trade_max_drawdown = 0.0
        else:
            peak_price = max(peak_price, tomorrow['High'])
            current_drawdown = (tomorrow['Low'] - peak_price) / peak_price
            trade_max_drawdown = min(trade_max_drawdown, current_drawdown)
            
            stop_loss_price = entry_price * 0.92
            
            if tomorrow['Low'] <= stop_loss_price:
                exit_price = min(tomorrow['Open'], stop_loss_price)
                exit_date = tomorrow['Date']
                profit_pct = (exit_price - entry_price) / entry_price
                holding_bars = (i + 1) - entry_idx
                max_p = (peak_price - entry_price) / entry_price
                
                trades.append((strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'), entry_price, exit_price, profit_pct, holding_bars, max_p, trade_max_drawdown, entry_score))
                in_position = False
                
            elif tomorrow['Close'] < tomorrow['MA20']:
                if i+2 < len(df):
                    next_day = df.iloc[i+2]
                    exit_price = next_day['Open'] 
                    exit_date = next_day['Date']
                    profit_pct = (exit_price - entry_price) / entry_price
                    holding_bars = (i + 2) - entry_idx
                    
                    temp_peak = max(peak_price, next_day['High'])
                    temp_drawdown = (next_day['Low'] - temp_peak) / temp_peak
                    final_mdd = min(trade_max_drawdown, temp_drawdown)
                    max_p = (temp_peak - entry_price) / entry_price
                    
                    trades.append((strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'), entry_price, exit_price, profit_pct, holding_bars, max_p, final_mdd, entry_score))
                    in_position = False
                    
    if in_position:
        last_day = df.iloc[-1]
        exit_price = last_day['Close']
        exit_date = last_day['Date']
        profit_pct = (exit_price - entry_price) / entry_price
        holding_bars = (len(df) - 1) - entry_idx
        
        temp_peak = max(peak_price, last_day['High'])
        temp_drawdown = (last_day['Low'] - temp_peak) / temp_peak
        final_mdd = min(trade_max_drawdown, temp_drawdown)
        max_p = (temp_peak - entry_price) / entry_price
        
        trades.append((strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'), entry_price, exit_price, profit_pct, holding_bars, max_p, final_mdd, entry_score))
        
    return trades, df

# ==========================================================
# 5️⃣ 🏭 智能增量更新與主程式
# ==========================================================
def sync_daily_data(conn):
    cursor = conn.cursor()
    today = datetime.datetime.now(TAIPEI_TZ)
    
    cursor.execute("SELECT MAX(Date) FROM daily_price")
    last_date = cursor.fetchone()[0]
    
    if last_date:
        start_date_obj = datetime.datetime.strptime(last_date, '%Y-%m-%d') - datetime.timedelta(days=2)
        start_date = start_date_obj.strftime('%Y-%m-%d')
        print(f"📊 增量更新，抓取區間: {start_date} 至今...")
    else:
        start_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
        print(f"⚠️ 初次下載，抓取區間: {start_date} 至今...")

    end_date = (today + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    raw_data = yf.download(tw50_tickers, start=start_date, end=end_date, group_by='ticker', progress=False, threads=False)
    
    all_records = []
    for ticker in tw50_tickers:
        try:
            if ticker in raw_data:
                stock_data = raw_data[ticker].dropna(how='all').copy()
                if stock_data.empty: continue
                df = stock_data.reset_index()
                df_to_db = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
                df_to_db['Date'] = df_to_db['Date'].dt.strftime('%Y-%m-%d')
                df_to_db.insert(0, 'ticker', ticker)
                all_records.extend(df_to_db.values.tolist())
        except Exception as e:
            print(f"整理 {ticker} 錯誤: {e}")
            
    if all_records:
        cursor.executemany('''
            INSERT OR REPLACE INTO daily_price (ticker, Date, Open, High, Low, Close, Volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', all_records)
        conn.commit()

    cutoff_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
    cursor.execute("DELETE FROM daily_price WHERE Date < ?", (cutoff_date,))
    if cursor.rowcount > 0:
        conn.commit()
        # 僅在每月 1 號執行 VACUUM，節省 I/O 消耗
        if today.day == 1:
            conn.execute("VACUUM")
            print("🧹 每月 1 號例行保養：已執行 VACUUM 釋放硬碟空間。")

def run_0050_batch(conn):
    strategy_version = "v02.6"
    sync_daily_data(conn)
    
    print(f"🚀 啟動 {strategy_version} 回測引擎...")
    
    all_trades = []
    alerts_trigger = []
    alerts_watchlist = []
    cursor = conn.cursor()
    # Schema Migration 已刪除表格，此處直接新增即可
    
    for ticker in tw50_tickers:
        try:
            df_full = pd.read_sql_query(
                "SELECT Date, Open, High, Low, Close, Volume FROM daily_price WHERE ticker = ? ORDER BY Date", 
                conn, 
                params=(ticker,),
                parse_dates=['Date']
            )
            
            if len(df_full) < 65: continue
                
            trades, df_updated = calculate_v026_and_backtest(df_full, ticker, strategy_version)
            all_trades.extend(trades)
            
            latest_day = df_updated.iloc[-1]
            yesterday = df_updated.iloc[-2]
            day_before = df_updated.iloc[-3]
            
            score_today = latest_day['Score']
            score_yest = yesterday['Score']
            score_before = day_before['Score']
            
            # 1. 新增觀察 (Edge Trigger)：昨日未達標，今日首日達標
            is_new_setup = (pd.notna(score_today) and score_today >= 45) and (pd.notna(score_yest) and score_yest < 45)
            
            # 2. 突破進場 (Buy Stop)：昨日為首日達標，且今日發生真突破
            is_trigger = (pd.notna(score_yest) and score_yest >= 45) and \
                         (pd.notna(score_before) and score_before < 45) and \
                         (latest_day['High'] > yesterday['High'])
            
            if is_trigger:
                trigger_price = yesterday['High']
                estimated_entry = max(latest_day['Open'], trigger_price)
                alerts_trigger.append(
                    f"🚀 *{ticker}* 突破進場!\n"
                    f"突破價位: {trigger_price:.2f}\n"
                    f"預估成交: {estimated_entry:.2f}\n"
                    f"🛡️ 防守月線: {latest_day['MA20']:.2f}"
                )
            elif is_new_setup:
                alerts_watchlist.append(
                    f"👀 *{ticker}* 新增觀察\n"
                    f"評分: {int(score_today)} | 收盤: {latest_day['Close']:.2f}\n"
                    f"⚡ 待突破價位: {latest_day['High']:.2f}"
                )
        except Exception as e:
            print(f"回測 {ticker} 錯誤: {e}")
            
    if all_trades:
        cursor.executemany('''
            INSERT INTO backtest_trades 
            (version, ticker, entry_date, exit_date, entry_price, exit_price, profit_pct, holding_bars, max_profit_pct, trade_max_drawdown_pct, entry_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', all_trades)
        conn.commit()
    
    msg_parts = [f"📊 *{strategy_version} 台股 50 戰情室*"]
    if alerts_trigger:
        msg_parts.append("================\n🔥 **買進訊號觸發** 🔥\n" + "\n\n".join(alerts_trigger))
    if alerts_watchlist:
        msg_parts.append("================\n🎯 **潛力起漲觀察**\n" + "\n\n".join(alerts_watchlist))
        
    if not alerts_trigger and not alerts_watchlist:
        msg_parts.append("\n今日盤後無新增訊號。")
        
    send_telegram_alert("\n\n".join(msg_parts))

if __name__ == "__main__":
    db_connection = init_db("tw50_strategy.db")
    run_0050_batch(db_connection)
    db_connection.close()
