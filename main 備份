# ==============================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : TW50 Breakout Strategy
# 檔案名稱 : main.py
# 策略版本 : v02.13
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 功能說明：
# 1. 台股50成分股歷史資料同步
# 2. 技術指標計算 (MA、MACD)
# 3. Breakout Strategy 回測
# 4. SQLite 資料儲存與管理
# 5. Telegram 即時訊號通知
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 主要策略：
# - Score >= 45 建立 Setup
# - Buy Stop 突破進場
# - 固定停損 8%
# - 跌破 MA20 出場
# - 回測結束強制平倉
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# ==============================

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

# ==============================
# Prt.01 Telegram 通知功能
# ==============================
def send_telegram_alert(message):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("未設定 Telegram 金鑰，跳過推播。")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    data = json.dumps({
        "chat_id": chat_id, 
        "text": message, 
        "parse_mode": "HTML"
    }).encode('utf-8')
    
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=15)
        print("✅ Telegram 推播成功！")
    except Exception as e:
        print(f"❌ Telegram 推播失敗: {e}")

# ==============================
# Prt.02 SQLite 資料庫管理
# ==============================
def init_db(db_name="tw50_strategy.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_price (
            ticker TEXT, Date TEXT, Open REAL, High REAL, Low REAL, Close REAL, Volume INTEGER,
            PRIMARY KEY (ticker, Date)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backtest_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT,
            ticker TEXT,
            entry_date TEXT,
            exit_date TEXT,
            entry_price REAL,
            exit_price REAL,
            profit_pct REAL,
            holding_bars INTEGER,
            max_profit_pct REAL,
            trade_max_drawdown_pct REAL,
            entry_score REAL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alert_log (
            strategy_version TEXT,
            ticker TEXT,
            entry_date TEXT,
            PRIMARY KEY (strategy_version, ticker, entry_date)
        )
    ''')
    
    try:
        cursor.execute("ALTER TABLE backtest_trades ADD COLUMN trade_max_drawdown_pct REAL")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    return conn

# ==============================
# Prt.03 技術指標計算與回測
# ==============================
def calculate_v0212_and_backtest(df, ticker, strategy_version="v02.12"):  
    df = df.sort_values('Date').dropna().reset_index(drop=True)

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
    setup_active = False

    for i in range(65, len(df)-1):
        yesterday = df.iloc[i-1]
        today = df.iloc[i]
        tomorrow = df.iloc[i+1]

        if not in_position:
            if not setup_active and today['Score'] >= 45 and yesterday['Score'] < 45:
                setup_active = True
                signal_day_high = today['High']
                entry_score = today['Score']

            if setup_active:
                if today['Score'] < 45:
                    setup_active = False
                elif tomorrow['High'] > signal_day_high:
                    in_position = True
                    setup_active = False
                    entry_price = max(tomorrow['Open'], signal_day_high)
                    entry_date = tomorrow['Date']
                    entry_idx = i + 1
                    peak_price = entry_price
                    trade_max_drawdown = 0.0
        else:
            peak_price = max(peak_price, tomorrow['High'])
            trade_max_drawdown = min(trade_max_drawdown, (tomorrow['Low'] - peak_price) / peak_price)
            stop_loss_price = entry_price * 0.92

            if tomorrow['Low'] <= stop_loss_price:
                exit_price = min(tomorrow['Open'], stop_loss_price)
                exit_date = tomorrow['Date']
                profit_pct = (exit_price - entry_price) / entry_price
                holding_bars = (i + 1) - entry_idx
                max_p = (peak_price - entry_price) / entry_price
                trade_max_drawdown_pct = (trade_max_drawdown * 100)
                
                trades.append((
                    strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'),
                    entry_price, exit_price, profit_pct, holding_bars, max_p, trade_max_drawdown_pct, entry_score
                ))
                in_position = False

            elif tomorrow['Close'] < tomorrow['MA20']:
                if i + 2 < len(df):
                    next_day = df.iloc[i + 2]
                    exit_price = next_day['Open']
                    exit_date = next_day['Date']
                    profit_pct = (exit_price - entry_price) / entry_price
                    holding_bars = (i + 2) - entry_idx
                    temp_peak = max(peak_price, next_day['High'])
                    temp_drawdown = (next_day['Low'] - temp_peak) / temp_peak
                    final_mdd = min(trade_max_drawdown, temp_drawdown)
                    max_p = (temp_peak - entry_price) / entry_price
                else:
                    last_day = df.iloc[-1]
                    exit_price = last_day['Close']
                    exit_date = last_day['Date']
                    profit_pct = (exit_price - entry_price) / entry_price
                    holding_bars = (len(df) - 1) - entry_idx
                    temp_peak = max(peak_price, last_day['High'])
                    temp_drawdown = (last_day['Low'] - temp_peak) / temp_peak
                    final_mdd = min(trade_max_drawdown, temp_drawdown)
                    max_p = (temp_peak - entry_price) / entry_price
            
                trade_max_drawdown_pct = final_mdd * 100
                trades.append((
                    strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'),
                    entry_price, exit_price, profit_pct, holding_bars, max_p, trade_max_drawdown_pct, entry_score
                ))
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
        trade_max_drawdown_pct = final_mdd * 100
        trades.append((
            strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'),
            entry_price, exit_price, profit_pct, holding_bars, max_p, trade_max_drawdown_pct, entry_score
        ))
        
    return trades, df

# ==============================
# Prt.06 歷史資料同步
# ==============================
def sync_daily_data(conn):
    cursor = conn.cursor()
    today = datetime.datetime.now(TAIPEI_TZ)
    force_reset = os.environ.get('FORCE_RESET', 'false').lower() == 'true'
    
    if force_reset:
        print("⚠️ 觸發強制重設：清空 daily_price 表格，準備重抓 5 年資料！")
        cursor.execute("DELETE FROM daily_price")
        conn.commit()
        last_date = None
    else:
        cursor.execute("SELECT MAX(Date) FROM daily_price")
        last_date = cursor.fetchone()[0]

    if last_date:
        start_date_obj = datetime.datetime.strptime(last_date, '%Y-%m-%d') - datetime.timedelta(days=2)
        start_date = start_date_obj.strftime('%Y-%m-%d')
        print(f"📊 增量更新，抓取區間: {start_date} 至今...")
    else:
        start_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
        print(f"⚠️ 初次下載/強制重置，抓取區間: {start_date} 至今...")

    end_date = (today + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    raw_data = yf.download(tw50_tickers, start=start_date, end=end_date, group_by='ticker', progress=False, threads=False)

    all_records = []
    for ticker in tw50_tickers:
        try:
            if ticker in raw_data:
                stock_data = raw_data[ticker].dropna(how='all').copy()
                if stock_data.empty: 
                    continue
                df = stock_data.reset_index()
                df_to_db = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
                df_to_db['Date'] = pd.to_datetime(df_to_db['Date']).dt.strftime('%Y-%m-%d')
                df_to_db.insert(0, 'ticker', ticker)
                all_records.extend(df_to_db.values.tolist())
        except Exception as e:
            print(f"❌ 整理 {ticker} 錯誤: {e}")

    if all_records:
        # 1. 先將最新下載的增量數據寫入（或更新）資料庫
        cursor.executemany('''
            INSERT OR REPLACE INTO daily_price (ticker, Date, Open, High, Low, Close, Volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', all_records)
        conn.commit()
        print("✅ 最新數據已成功寫入 SQLite 資料庫。")

    # 🚀 【關鍵修復】：不論是初次還是增量，都從資料庫倒出「最完整」的歷史資料覆蓋成 CSV
    # 這樣 temp_data.csv 就不會被閹割，永遠維持最新的完整5年資料！
    try:
        full_df = pd.read_sql_query("SELECT * FROM daily_price ORDER BY ticker, Date ASC", conn)
        full_df.to_csv("temp_data.csv", index=False)
        print(f"✅ 完整 5 年最新數據已成功同步匯出至 temp_data.csv (共 {len(full_df)} 筆記錄)")
    except Exception as csv_e:
        print(f"❌ 匯出完整 CSV 失敗: {csv_e}")

    # 刪除過期資料
    cutoff_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
    cursor.execute("DELETE FROM daily_price WHERE Date < ?", (cutoff_date,))
    cursor.execute("DELETE FROM alert_log WHERE entry_date < ?", (cutoff_date,))
    conn.commit()
    
    if today.day == 1:
        conn.commit()
        conn.execute("VACUUM")
        print("🧹 每月 1 號例行保養：已執行 VACUUM 釋放硬碟空間。")

# ==============================
# Prt.07 回測主控引擎 (封裝成標準函式)
# ==============================
def run_0050_batch(conn):
    print("啟動 TW50 掃描與回測...")

    strategy_version = "v02.12"
    tickers = tw50_tickers
    alerts_setup = []
    alerts_trigger = []

    # 🚀 v02.13 新增：開啟大批次交易防護 (Try-Except-Rollback)
    try:
        # 宣告開始批次交易，讓 SQLite 將接下來的寫入全數暫存在記憶體中
        conn.execute("BEGIN TRANSACTION")

        # ==============================
        # Prt.08 個股回測流程
        # ==============================
        for ticker in tickers:
            try:
                # 從資料庫中讀取該個股的歷史價格資料
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT Date, Open, High, Low, Close, Volume FROM daily_price WHERE ticker = ? ORDER BY Date ASC", 
                    (ticker,)
                )
                rows = cursor.fetchall()
                if not rows:
                    continue
                
                # 將資料轉換回 DataFrame
                df_ticker = pd.DataFrame(rows, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
                df_ticker['Date'] = pd.to_datetime(df_ticker['Date'])
                
                # 執行技術指標計算與策略回測
                all_trades, df_processed = calculate_v0212_and_backtest(df_ticker, ticker, strategy_version)
                
                # 🎯 訊號監控：判斷最新交易日是否符合 Watchlist 條件 (Score >= 45)
                if not df_processed.empty:
                    last_row = df_processed.iloc[-1]
                    if last_row['Score'] >= 45:
                        alerts_setup.append(f"• {ticker} (Score: {int(last_row['Score'])}, 明日突破 {last_row['High']:.2f} 買進)")
                
                # ==============================
                # Prt.12 回測結果寫入 (對齊資料表：backtest_trades)
                # ==============================
                if all_trades:
                    conn.executemany('''
                        INSERT INTO backtest_trades (
                            version, ticker, entry_date, exit_date, entry_price, exit_price, 
                            profit_pct, holding_bars, max_profit_pct, trade_max_drawdown_pct, entry_score
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', all_trades)              
               
            except Exception as inner_e:
                print(f"⚠️ {ticker} 處理異常，已跳過: {inner_e}")
                continue

        # ==============================
        # 🎯 迴圈結束：執行大批次落盤 (Batch Commit)
        # ==============================
        conn.commit()
        print("✅ v02.13 效能優化：TW50 全數標的已完成大批次寫入！")

    except Exception as main_e:
        # ==============================
        # 🚨 全局異常防護：資料庫回滾 (Rollback)
        # ==============================
        conn.rollback()
        error_message = f"❌ 系統嚴重崩潰，資料庫已安全回滾！原因: {main_e}"
        print(error_message)
        alerts_trigger.append(f"⚠️ <b>資料庫寫入失敗</b>\n{error_message}")

    # ==============================
    # Prt.13 Telegram 訊息組裝与發送
    # ==============================
    # 抓取台北時間
    now_str = datetime.datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d %I.%M.%S %p")
    
    # 初始化訊息陣列 (加入標題與時間)
    msg_parts = [
        f"📊 <b>{strategy_version} 台股 50 戰情室 (自動盤後更新)</b>",
        f"🕒 {now_str} 回測"
    ]

    # ==============================
    # Prt.13.1 Watchlist (對齊手動格式)
    # ==============================
    if alerts_setup:
        # 為了跟手動版本一樣由分數高到低排序，我們先依照分數對字串進行排序
        # (這裡利用字串中包含的 "Score: XX" 數字來降冪排序)
        try:
            alerts_setup_sorted = sorted(alerts_setup, key=lambda x: int(x.split('Score: ')[1].split(',')[0]), reverse=True)
        except Exception:
            alerts_setup_sorted = alerts_setup # 若解析失敗則維持原排序

        msg_parts.append("================\n🎯 <b>滿足潛力起漲 (Score >= 45)</b>\n" + "\n".join(alerts_setup_sorted))

    # ==============================
    # Prt.13.2 Trigger (若有觸發進出場訊號)
    # ==============================
    if alerts_trigger:
        msg_parts.append("================\n🔥 <b>最新交易日執行回報</b>\n" + "\n".join(alerts_trigger))

    # ==============================
    # Prt.13.3 無訊號
    # ==============================
    if not alerts_trigger and not alerts_setup:
        msg_parts.append("================\n盤後無新增訊號。")
        
    # ==============================
    # Prt.13.4 系統狀態結尾
    # ==============================
    msg_parts.append("================\n✅ 系統目前正常運作中")

    # ==============================
    # Prt.14 發送 Telegram
    # ==============================
    # 注意：將原本的 "\n\n".join() 改成 "\n".join() 讓整體排版更緊湊
    send_telegram_alert("\n".join(msg_parts))

# ==============================
# Prt.15 主程式入口
# ==============================
if __name__ == "__main__":
    db_connection = init_db("tw50_strategy.db")
    
    # 1. 必須先同步每日最新的歷史資料，否則資料庫內永遠是舊資料
    sync_daily_data(db_connection)
    
    # 2. 執行台股 50 大批次掃描與訊號推播
    run_0050_batch(db_connection)
    
    db_connection.close()
