# ==============================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : TW50 Breakout Strategy
# 檔案名稱 : main.py
# 策略版本 : v02.11F
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

# ==============================
# 章節索引
# ==============================
# Prt.00 系統設定與套件匯入
# Prt.01 Telegram通知模組
# Prt.02 SQLite資料庫管理
# Prt.03 技術指標計算
# Prt.04 訊號評分系統
# Prt.05 Setup與進場邏輯
# Prt.06 持倉管理與出場邏輯
# Prt.07 資料同步模組
# Prt.08 回測主控引擎
# Prt.09 個股回測流程
# Prt.10 訊號判斷
# Prt.11 Trigger推播
# Prt.12 Watchlist推播
# Prt.13 回測結果寫入
# Prt.14 Telegram訊息組裝
# Prt.15 主程式入口
# ==============================

# ==============================
# Prt.00 系統全域設定與套件匯入
# ==============================
import pandas as pd
import numpy as np
import yfinance as yf
import sqlite3
import datetime
import os
import urllib.request
import json

# ==============================
# 台灣50成分股清單
# ==============================
# 資料來源：
# - Yahoo Finance
# 格式：
# - 股票代碼.TW
# 用途：
# - 回測與每日訊號掃描標的池
# ==============================

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
# Prt.01 Telegram 通知模組
# ==========================================================

def send_telegram_alert(message):
    
    """
    功能：
        發送 Telegram 推播通知
    參數：
        message : str
            HTML格式訊息內容
    注意：
        parse_mode固定使用HTML
        避免Markdown特殊字元造成推播失敗
    環境變數：
        TELEGRAM_TOKEN
        TELEGRAM_CHAT_ID
    """
    
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
        urllib.request.urlopen(req)
        print("✅ Telegram 推播成功！")
    except Exception as e:
        print(f"❌ Telegram 推播失敗: {e}")

# ==============================
# Prt.02 SQLite 資料庫管理
# ==============================

def init_db(db_name="tw50_strategy.db"):
    
    """
    功能：
        初始化SQLite資料庫
    建立資料表：
        daily_price
        backtest_trades
        alert_log
    升級方式：
        ALTER TABLE
    原則：
        禁止DROP TABLE
        確保歷史資料不遺失
    回傳：
        sqlite connection
    """
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    # ==============================
    # Prt.02.1 建立 daily_price 資料表
    # ==============================
    # Table : daily_price
    # ==============================
    # ticker    股票代號
    # Date      交易日期
    # Open      開盤價
    # High      最高價
    # Low       最低價
    # Close     收盤價
    # Volume    成交量
    # Primary Key：
    # - (ticker, Date)
    # ==============================
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_price (
            ticker TEXT, Date TEXT, Open REAL, High REAL, Low REAL, Close REAL, Volume INTEGER,
            PRIMARY KEY (ticker, Date)
        )
    ''')
    
    # ==============================
    # Prt.02.2 建立 backtest_trades 資料表
    # ==============================
    # Table : backtest_trades
    # ==============================
    # version
    # ticker
    # entry_date
    # exit_date
    # entry_price
    # exit_price
    # profit_pct
    # holding_bars
    # max_profit_pct
    # trade_max_drawdown_pct
    # entry_score
    # 用途：
    # - 儲存所有歷史回測交易紀錄
    # ================================
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backtest_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT, ticker TEXT, entry_date TEXT, exit_date TEXT, 
            entry_price REAL, exit_price REAL, profit_pct REAL,
            holding_bars INTEGER, max_profit_pct REAL, entry_score REAL
        )
    ''')

    # ==============================
    # Prt.02.3 建立 alert_log
    # ==============================
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alert_log (
            strategy_version TEXT,
            ticker TEXT,
            entry_date TEXT,
            PRIMARY KEY (
                strategy_version,
                ticker,
                entry_date
            )
        )
    ''')
    
    # ==============================
    # Prt.02.4 Schema Migration (ALTER TABLE 升級)
    # ==============================
    try:
        cursor.execute("ALTER TABLE backtest_trades ADD COLUMN trade_max_drawdown_pct REAL")
    except sqlite3.OperationalError:
        # 欄位若已存在則略過
        pass 
        
    conn.commit()
    return conn

# ==============================
# Prt.03 技術指標與評分系統
    # ==============================

def calculate_v0211F_and_backtest(df, ticker, strategy_version="v02.11F"):
    df = df.sort_values('Date').dropna().reset_index(drop=True)

    # ==========================================================
    # Prt.03.1 MA20
    # ==========================================================
    df['MA20'] = df['Close'].rolling(20).mean()
    
    # ==========================================================
    # Prt.03.2 MA60
    # ==========================================================   
    df['MA60'] = df['Close'].rolling(60).mean()
    
    # ==========================================================
    # Prt.03.3 V_MA5
    # ==========================================================  
    df['V_MA5'] = df['Volume'].rolling(5).mean()

    # ==========================================================
    # Prt.03.4 MACD
    # ==========================================================      
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = ema12 - ema26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['DEA']
    
    # ==========================================================
    # Prt.03.5 Score 評分系統
    # ==========================================================   
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
    
# ==========================================================
# Prt.04 Setup 與進場邏輯
# ==========================================================    
    setup_active = False
    signal_day_high = 0
    entry_score = 0

    for i in range(65, len(df)-1):

        yesterday = df.iloc[i-1]
        today = df.iloc[i]
        tomorrow = df.iloc[i+1]

        if not in_position:

            # ==========================================================
            # Prt.04.1 建立 Setup
            # ==========================================================  
            if (
                not setup_active
                and today['Score'] >= 45
                and yesterday['Score'] < 45
            ):
                setup_active = True
                signal_day_high = today['High']
                entry_score = today['Score']

            # ==========================================================
            # Prt.04.2 Setup 等待突破
            # ========================================================== 
            if setup_active:

                if today['Score'] < 45:
                    setup_active = False

            # ==========================================================
            # Prt.04.3 Buy Stop 突破進場
            # ========================================================== 
                elif tomorrow['High'] > signal_day_high:

                    in_position = True
                    setup_active = False

                    entry_price = max(
                        tomorrow['Open'],
                        signal_day_high
                    )

                    entry_date = tomorrow['Date']
                    entry_idx = i + 1
                    peak_price = entry_price
                    trade_max_drawdown = 0.0

# ==========================================================
# Prt.05 持倉管理系統
# ==========================================================      
        else:

            # ==========================================================
            # Prt.05.1 更新 Peak Price
            # ==========================================================
            peak_price = max(
                peak_price,
                tomorrow['High']
            )

            # ==========================================================
            # Prt.05.2 更新 MDD
            # ==========================================================
            trade_max_drawdown = min(
                trade_max_drawdown,
                (tomorrow['Low'] - peak_price) / peak_price
            )

            # ==========================================================
            # Prt.05.3 停損設定 8%
            # ==========================================================
            stop_loss_price = entry_price * 0.92

            # ==========================================================
            # Prt.05.4 停損檢查
            # ==========================================================
            if tomorrow['Low'] <= stop_loss_price:

                exit_price = min(
                    tomorrow['Open'],
                    stop_loss_price
                )

                exit_date = tomorrow['Date']
                profit_pct = (
                    exit_price - entry_price
                ) / entry_price

                holding_bars = (
                    i + 1
                ) - entry_idx

                max_p = (
                    peak_price - entry_price
                ) / entry_price

                trade_max_drawdown_pct = (
                    trade_max_drawdown * 100
                )
            # ==========================================================
            # Prt.05.5 停損出場紀錄
            # ==========================================================
                trades.append(
                    (
                        strategy_version,
                        ticker,
                        entry_date.strftime('%Y-%m-%d'),
                        exit_date.strftime('%Y-%m-%d'),
                        entry_price,
                        exit_price,
                        profit_pct,
                        holding_bars,
                        max_p,
                        trade_max_drawdown_pct,
                        entry_score
                    )
                )

                in_position = False

            # ==========================================================
            # Prt.05.6 月線跌破出場
            # ==========================================================
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
                    
                    trade_max_drawdown_pct = final_mdd * 100
                    trades.append(
                        (
                            strategy_version,
                            ticker,
                            entry_date.strftime('%Y-%m-%d'),
                            exit_date.strftime('%Y-%m-%d'),
                            entry_price,
                            exit_price,
                            profit_pct,
                            holding_bars,
                            max_p,
                            trade_max_drawdown_pct,
                            entry_score
                        )
                    )
                    in_position = False
                    
# ==========================================================
# Prt.06 回測期末強制平倉
# ==========================================================
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
        trades.append(
            (
                strategy_version,
                ticker,
                entry_date.strftime('%Y-%m-%d'),
                exit_date.strftime('%Y-%m-%d'),
                entry_price,
                exit_price,
                profit_pct,
                holding_bars,
                max_p,
                trade_max_drawdown_pct,
                entry_score
            )
        )
        
    return trades, df

# ==========================================================
# Prt.07 智能增量資料更新
# ==========================================================
def sync_daily_data(conn):
    cursor = conn.cursor()
    today = datetime.datetime.now(TAIPEI_TZ)
    
    cursor.execute("SELECT MAX(Date) FROM daily_price")
    last_date = cursor.fetchone()[0]
            
    # ==========================================================
    # Prt.07.1 判斷增量更新區間
    # ==========================================================    
    if last_date:
        start_date_obj = datetime.datetime.strptime(last_date, '%Y-%m-%d') - datetime.timedelta(days=2)
        start_date = start_date_obj.strftime('%Y-%m-%d')
        print(f"📊 增量更新，抓取區間: {start_date} 至今...")
    else:
        start_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
        print(f"⚠️ 初次下載，抓取區間: {start_date} 至今...")

    # ==========================================================
    # Prt.07.2 下載 Yahoo 資料
    # ==========================================================  
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

    # ==========================================================
    # Prt.07.3 寫入 SQLite
    # ==========================================================
        cursor.executemany('''
            INSERT OR REPLACE INTO daily_price (ticker, Date, Open, High, Low, Close, Volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', all_records)
        conn.commit()

    cutoff_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')

    # ==========================================================
    # Prt.07.4 清除五年前資料
    # ==========================================================
    cursor.execute("DELETE FROM daily_price WHERE Date < ?", (cutoff_date,))
    conn.commit()
    
    cursor.execute(
        '''

    # ==========================================================
    # Prt.07.5 Alert Log 保留五年
    # ==========================================================
        DELETE FROM alert_log
        WHERE entry_date < ?
        ''',
        (cutoff_date,)
    )
    conn.commit()
    
    # ==========================================================
    # Prt.07.6 SQLite VACUUM 月保養
    # ==========================================================
    if today.day == 1:

        # 確保不存在未完成交易
        conn.commit()

        # SQLite 官方建議：
        # VACUUM 必須於非 Transaction 狀態執行
        conn.execute("VACUUM")

        print(
            "🧹 每月 1 號例行保養："
            "已執行 VACUUM 釋放硬碟空間。"
        )

# ==========================================================
# Prt.08 回測主控引擎
# ==========================================================
def run_0050_batch(conn):
    strategy_version = "v02.11F"
    
    # ==========================================================
    # Prt.08.1 同步資料庫
    # ==========================================================
    sync_daily_data(conn)
    
    print(f"🚀 啟動 {strategy_version} 回測引擎...")
    
    all_trades = []
    alerts_setup = []
    alerts_trigger = []
    
    cursor = conn.cursor()

    alert_cursor = conn.cursor()
    
    # ==========================================================
    # Prt.08.2 清除本版回測資料
    # ==========================================================
    cursor.execute("DELETE FROM backtest_trades WHERE version = ?", (strategy_version,))
    conn.commit()

# ==========================================================
# Prt.09 個股回測流程
# ==========================================================    
    for ticker in tw50_tickers:
        try:

            # ==========================================================
            # Prt.09.1
            # ========================================================== 
            df_full = pd.read_sql_query(
                "SELECT Date, Open, High, Low, Close, Volume FROM daily_price WHERE ticker = ? ORDER BY Date", 
                conn, 
                params=(ticker,),
                parse_dates=['Date']
            )
            
            if len(df_full) < 65: continue
                
            # ==========================================================
            # Prt.09.2
            # ==========================================================     
            trades, df_updated = calculate_v0211F_and_backtest(df_full, ticker, strategy_version)
            all_trades.extend(trades)

            # ==========================================================
            # Prt.09.3
            # ========================================================== 
            latest_day = df_updated.iloc[-1]
            yesterday_day = df_updated.iloc[-2]
            
            score_today = latest_day['Score']
            score_yesterday = yesterday_day['Score']
            
            # 語意正名：精準使用 latest_trading_day 消滅時間錯覺
# ==========================================================
# Prt.10 訊號判斷
# ==========================================================             
            latest_trading_day = latest_day['Date'].strftime('%Y-%m-%d')
            
            # ==========================================================
            # Prt.10.1
            # ========================================================== 
            is_setup_ready = (pd.notna(score_today) and score_today >= 45 and pd.notna(score_yesterday) and score_yesterday < 45)
            
            # ==========================================================
            # Prt.10.2
            # ==========================================================
            entered_latest_day_trades = [
                t for t in trades
                if t[2] == latest_trading_day
            ]

# ==========================================================
# Prt.11 Trigger 推播
# ==========================================================
            # ==========================================================
            # Prt.11.1
            # ==========================================================
            if entered_latest_day_trades:

                actual_entry_price = entered_latest_day_trades[-1][4]

                entry_row = df_updated.loc[
                    df_updated['Date'] == latest_day['Date']
                ]

                entry_ma20 = (
                    entry_row.iloc[0]['MA20']
                    if not entry_row.empty
                    else latest_day['MA20']
                )
           
            # ==========================================================
            # Prt.11.2
            # ==========================================================
                alert_cursor.execute(
                    '''
                    SELECT 1
                    FROM alert_log
                    WHERE strategy_version = ?
                    AND ticker = ?
                    AND entry_date = ?
                    ''',
                    (
                        strategy_version,
                        ticker,
                        latest_trading_day
                    )
                )

                already_sent = alert_cursor.fetchone()

                if not already_sent:

            # ==========================================================
            # Prt.11.3
            # ==========================================================
                    alerts_trigger.append(
                        f"✅ <b>{ticker}</b> 今日突破進場\n"
                        f"成交價 <b>{actual_entry_price:.2f}</b>\n"
                        f"防守月線 <b>{entry_ma20:.2f}</b>"
                    )

            # ==========================================================
            # Prt.11.4
            # ==========================================================
                    alert_cursor.execute(
                        '''
                        INSERT OR IGNORE INTO alert_log
                        (
                            strategy_version,
                            ticker,
                            entry_date
                        )
                        VALUES (?, ?, ?)
                        ''',
                        (
                            strategy_version,
                            ticker,
                            latest_trading_day
                        )
                    )

                    conn.commit()

# ==========================================================
# Prt.12 Watchlist 預告推播
# ==========================================================
            elif is_setup_ready:

                alerts_setup.append(
                    f"🚀 <b>{ticker}</b> 首日達標\n"
                    f"Score = {int(score_today)}\n"
                    f"明日突破 <b>{latest_day['High']:.2f}</b> 買進"
                )
                
        except Exception as e:
            print(f"回測 {ticker} 錯誤: {e}")

# ==========================================================
# Prt.13 回測結果寫入 SQLite
# ==========================================================          
    if all_trades:
        cursor.executemany('''
            INSERT INTO backtest_trades 
            (version, ticker, entry_date, exit_date, entry_price, exit_price, profit_pct, holding_bars, max_profit_pct, trade_max_drawdown_pct, entry_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', all_trades)
        conn.commit()

# ==========================================================
# Prt.14 Telegram 戰情室訊息組裝
# ==========================================================    
    msg_parts = [f"📊 <b>{strategy_version} 台股 50 戰情室</b>"]

    # ==========================================================
    # Prt.14.1 Watchlist
    # ==========================================================
    if alerts_setup:
        msg_parts.append("================\n🎯 <b>潛力起漲預告 (Watchlist)</b>\n" + "\n\n".join(alerts_setup))

    # ==========================================================
    # Prt.14.2 Trigger
    # ========================================================== 
    if alerts_trigger:
        msg_parts.append("================\n🔥 <b>最新交易日執行回報</b>\n" + "\n\n".join(alerts_trigger))

    # ==========================================================
    # Prt.14.3 無訊號
    # ==========================================================   
    if not alerts_trigger and not alerts_setup:
        msg_parts.append("\n盤後無新增訊號。")
    
    # ==========================================================
    # Prt.14.4 送出 Telegram
    # ==========================================================         
    send_telegram_alert("\n\n".join(msg_parts))

if __name__ == "__main__":
    db_connection = init_db("tw50_strategy.db")
    run_0050_batch(db_connection)
    db_connection.close()
