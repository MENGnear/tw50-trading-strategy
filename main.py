# ==============================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : TW50 Breakout Strategy
# 檔案名稱 : main.py
# 策略版本 : v02.12
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
# Prt.04 Setup與進場邏輯
# Prt.05 持倉管理與出場邏輯
# Prt.06 歷史資料同步
# Prt.07 回測主控引擎
# Prt.08 個股回測流程
# Prt.09 訊號判斷
# Prt.10 Trigger推播
# Prt.11 Watchlist推播
# Prt.12 回測結果寫入
# Prt.13 Telegram訊息組裝
# Prt.14 發送Telegram
# Prt.15 主程式入口
# ==============================

# ==============================
# Prt.00 系統全域設定與套件匯入
# ==============================
#
# 載入程式執行所需套件
# 設定 Telegram Token
# 設定資料庫名稱
# 設定策略版本
# 建立台灣50股票清單
#
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
#
# 負責將訊息推送到 Telegram
#
# 用途：
# 當產生交易訊號時
# 將結果即時通知使用者
#
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
        urllib.request.urlopen(
            req,
            timeout=15
        )
        print("✅ Telegram 推播成功！")
    except Exception as e:
        print(f"❌ Telegram 推播失敗: {e}")

# ==============================
# Prt.02 SQLite 資料庫管理
# ==============================
#
# 建立資料庫
# 建立資料表
# 執行資料庫升級
#
# ==============================

def init_db(db_name="tw50_strategy.db"):
    
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    # ==============================
    # Prt.02.1 daily_price 資料表
    # ==============================
    #
    # 儲存股票歷史價格
    #
    # 包含：
    # 開盤價
    # 最高價
    # 最低價
    # 收盤價
    # 成交量
    #
    # ==============================
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_price (
            ticker TEXT, Date TEXT, Open REAL, High REAL, Low REAL, Close REAL, Volume INTEGER,
            PRIMARY KEY (ticker, Date)
        )
    ''')
    
    # ==============================
    # Prt.02.2 backtest_trades 資料表
    # ==============================
    #
    # 儲存回測交易紀錄
    #
    # 包含：
    # 進場日期
    # 出場日期
    # 進場價格
    # 出場價格
    # 報酬率
    #
    # ==============================
    
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

    # ==============================
    # Prt.02.3 alert_log 資料表
    # ==============================
    #
    # 記錄已推播訊號
    #
    # 避免同一天重複通知
    #
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
    # Prt.02.4 Schema Migration
    # ==============================
    
    try:
        cursor.execute(
            "ALTER TABLE backtest_trades "
            "ADD COLUMN trade_max_drawdown_pct REAL"
        )
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    return conn

# ==============================
# Prt.03 技術指標計算
# ==============================
#
# 計算策略所需技術指標
#
# 包含：
# MA20
# MA60
# MACD
# Score
#
# ==============================

def calculate_v0212_and_backtest(df, ticker, strategy_version="v02.12"):  
    df = df.sort_values('Date').dropna().reset_index(drop=True)

    # ==============================
    # Prt.03.1 MA20
    # ==============================
    #
    # 計算20日均線
    #
    # 觀察短期趨勢方向
    #
    # ==============================
    df['MA20'] = df['Close'].rolling(20).mean()
    
    # ==============================
    # Prt.03.2 MA60
    # ==============================
    #
    # 計算60日均線
    #
    # 觀察中期趨勢方向
    #
    # ==============================
    df['MA60'] = df['Close'].rolling(60).mean()
    
    # ==============================
    # Prt.03.3 V_MA5
    # ==============================
    df['V_MA5'] = df['Volume'].rolling(5).mean()

    # ==============================
    # Prt.03.4 MACD
    # ==============================
    #
    # 計算 MACD 指標
    #
    # 判斷市場動能是否增強
    #
    # ==============================
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = ema12 - ema26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['DEA']
    
    # ==============================
    # Prt.03.5 Score 評分系統
    # ==============================
    #
    # 將多項條件加總成分數
    #
    # 分數越高
    # 代表股票越符合策略條件
    #
    # ==============================

    # MACD 柱體持續放大
    # 代表短期動能增強
    t1 = (df['MACD_Hist'] > df['MACD_Hist'].shift(1)).astype(int) * 15 
    
    # 股價站上 MA20
    # 代表短期趨勢偏多 
    m1 = (df['Close'] > df['MA20']).astype(int) * 10                    
    
    # MA20 五日斜率大於 1%
    # 代表均線開始向上
    m2 = ((df['MA20'] / df['MA20'].shift(5) - 1) > 0.01).astype(int) * 15 
    
    # MA20 位於 MA60 之上
    # 代表中期趨勢偏多
    m3 = (df['MA20'] > df['MA60']).astype(int) * 10                      
    
    # 成交量高於平均量
    # 代表市場開始關注
    v1 = (df['Volume'] > df['V_MA5'] * 1.3).astype(int) * 10            
    
    # Score Range : 0 ~ 60
    df['Score'] = t1 + m1 + m2 + m3 + v1
    
    trades = []
    in_position = False
    
    entry_price = signal_day_high = entry_score = 0
    entry_date = None
    peak_price = 0
    entry_idx = 0
    trade_max_drawdown = 0.0
    
# ==============================
# Prt.04 Setup 與進場邏輯
# ==============================
#
# 找出符合條件的股票
#
# 當 Score 首次達標
# 建立 Setup
#
# 等待後續突破進場
#
# ==============================
    setup_active = False
    signal_day_high = 0
    entry_score = 0

    for i in range(65, len(df)-1):

        yesterday = df.iloc[i-1]
        today = df.iloc[i]
        tomorrow = df.iloc[i+1]

        if not in_position:

            # ==============================
            # Prt.04.1 建立 Setup
            # ==============================
            #
            # 當分數首次達到門檻
            #
            # 記錄：
            # Setup 日期
            # Setup 高點
            #
            # ==============================
            if (
                not setup_active
                and today['Score'] >= 45
                and yesterday['Score'] < 45
            ):
                setup_active = True
                signal_day_high = today['High']
                entry_score = today['Score']

            # ==============================
            # Prt.04.2 Setup 等待突破
            # ==============================
            #
            # Setup 建立後
            # 持續觀察是否突破 Setup 高點
            #
            # 若分數跌回門檻以下
            # 取消本次 Setup
            #
            # ==============================
            
            if setup_active:

                if today['Score'] < 45:
                    setup_active = False

            # ==============================
            # Prt.04.3 Buy Stop 突破進場
            # ==============================
            #
            # 使用突破高點方式進場
            #
            # 當後續價格突破 Setup 高點
            # 視為正式買進
            #
            # ============================== 
                
                elif tomorrow['High'] > signal_day_high:
                    in_position = True
                    setup_active = False

            # ==============================
            # Buy Stop 成交模型
            # ==============================
            #
            # 跳空開高：
            # 使用開盤價成交
            #
            # 一般突破：
            # 使用 Setup 當天高點成交
            # ==============================
                    
                    entry_price = max(
                        tomorrow['Open'],
                        signal_day_high
                    )

                    entry_date = tomorrow['Date']
                    entry_idx = i + 1
                    peak_price = entry_price
                    trade_max_drawdown = 0.0

# ==============================
# Prt.05 持倉管理與出場邏輯
# ==============================
#
# 買進後開始追蹤持倉狀態
#
# 包含：
# 停損
# MDD
# 均線出場
#
# ==============================
      
        else:

            # ==============================
            # Prt.05.1 更新持倉最高價
            # ==============================
            #
            # 記錄買進後曾經出現過的最高價格
            #
            # 後續計算 MDD 會使用
            #
            # ==============================

            peak_price = max(
                peak_price,
                tomorrow['High']
            )

            # ==============================
            # Prt.05.2 計算交易期間最大跌幅
            # ==============================
            #
            # 記錄買進後
            # 從最高點曾經跌下來多少
            #
            # 用來觀察這筆交易過程中的風險
            #
            # ==============================

            trade_max_drawdown = min(
                trade_max_drawdown,
                (tomorrow['Low'] - peak_price) / peak_price
            )

            # ==============================
            # Prt.05.3 停損設定 8%
            # ==============================
            stop_loss_price = entry_price * 0.92

            # ==============================
            # Prt.05.4 停損檢查
            # ==============================
            #
            # 跌破停損價格
            # 強制出場
            #
            # 避免虧損持續擴大
            # 
            # ==============================
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
            # ==============================
            # Prt.05.5 停損出場紀錄
            # ==============================
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

            # ==============================
            # Prt.05.6 月線跌破出場
            # ==============================
            #
            # 收盤跌破 MA20
            #
            # 視為趨勢轉弱
            # 執行出場
            #
            # ==============================

            elif tomorrow['Close'] < tomorrow['MA20']:
            
                if i + 2 < len(df):
            
                    next_day = df.iloc[i + 2]
            
                    exit_price = next_day['Open']
                    exit_date = next_day['Date']
                    profit_pct = (
                        exit_price - entry_price
                    ) / entry_price
            
                    holding_bars = (
                        i + 2
                    ) - entry_idx
            
                    temp_peak = max(
                        peak_price,
                        next_day['High']
                    )
            
                    temp_drawdown = (
                        next_day['Low'] - temp_peak
                    ) / temp_peak
            
                    final_mdd = min(
                        trade_max_drawdown,
                        temp_drawdown
                    )
            
                    max_p = (
                        temp_peak - entry_price
                    ) / entry_price
            
                else:
                    # 回測最後一天沒有下一根K棒
                    # 使用最後收盤價出場
            
                    last_day = df.iloc[-1]
            
                    exit_price = last_day['Close']
                    exit_date = last_day['Date']
            
                    profit_pct = (
                        exit_price - entry_price
                    ) / entry_price
            
                    holding_bars = (
                        len(df) - 1
                    ) - entry_idx
            
                    temp_peak = max(
                        peak_price,
                        last_day['High']
                    )
            
                    temp_drawdown = (
                        last_day['Low'] - temp_peak
                    ) / temp_peak
            
                    final_mdd = min(
                        trade_max_drawdown,
                        temp_drawdown
                    )
            
                    max_p = (
                        temp_peak - entry_price
                    ) / entry_price
            
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
                    
            # ==============================
            # Prt.05.7 回測期末強制平倉
            # ==============================
            #
            # 若最後一天仍持有股票
            #
            # 使用最後收盤價平倉
            #
            # ==============================
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

# ==============================
# Prt.06 歷史資料同步
# ==============================
#
# Prt.06 歷史資料同步
#
# 從 Yahoo Finance 下載最新股價資料
#
# 寫入 SQLite 資料庫
#
# 並清除五年前的舊資料
#
# ==============================

def sync_daily_data(conn):
    
    cursor = conn.cursor()
    today = datetime.datetime.now(TAIPEI_TZ)
    
    cursor.execute("SELECT MAX(Date) FROM daily_price")
    last_date = cursor.fetchone()[0]
            
    # ==============================
    # Prt.06.1 判斷更新區間
    # ==============================
    #
    # 找出資料庫最後日期
    #
    # 僅下載缺少資料
    #
    # ==============================

    if last_date:
        start_date_obj = datetime.datetime.strptime(last_date, '%Y-%m-%d') - datetime.timedelta(days=2)
        start_date = start_date_obj.strftime('%Y-%m-%d')
        print(f"📊 增量更新，抓取區間: {start_date} 至今...")
    else:
        start_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
        print(f"⚠️ 初次下載，抓取區間: {start_date} 至今...")

    # ==============================
    # Prt.06.2 下載 Yahoo 資料
    # ==============================
    end_date = (today + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    raw_data = yf.download(tw50_tickers, start=start_date, end=end_date, group_by='ticker', progress=False, threads=False)
    
    all_records = []
    for ticker in tw50_tickers:
        try:
            if ticker in raw_data:
                stock_data = raw_data[ticker].dropna(how='all').copy()
                if stock_data.empty: 
                    print(f"⚠️ {ticker} 資料為空，跳過。")
                    continue
                
                df = stock_data.reset_index()
                # 這裡檢查一下欄位名稱是否正確
                print(f"✅ {ticker} 抓取成功，共有 {len(df)} 筆資料。")
                
                df_to_db = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
                df_to_db.insert(0, 'ticker', ticker)
                all_records.extend(df_to_db.values.tolist())
            else:
                print(f"❌ {ticker} 不在 raw_data 中。")
        except Exception as e:
            print(f"❌ 整理 {ticker} 錯誤: {e}")
    
    if not all_records:
        print("⚠️ 警告：all_records 為空，嘗試手動轉存 raw_data...")
        # 這裡簡單備份一份原始下載資料，確保你有檔案可以測試
        raw_data.to_csv("temp_data.csv") 
    else:
        final_df = pd.DataFrame(all_records, columns=['ticker', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
        final_df.to_csv("temp_data.csv", index=False)
        print("✅ 數據已成功導出至 temp_data.csv")
    
    # 原本的資料庫操作維持你的 try-except 保護
    try:
        # db.insert_many(...)
        pass
    except Exception as e:
        print(f"⚠️ 資料庫寫入警告 (已忽略): {e}")

# === 確保資料處理完畢後，強制導出 CSV ===
    if all_records:
        final_df = pd.DataFrame(all_records, columns=['ticker', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
        final_df.to_csv("temp_data.csv", index=False)
        print("✅ 數據已強制導出至 temp_data.csv，準備執行狀態機。")
    else:
        print("❌ 錯誤：all_records 為空，未抓取到任何資料。請檢查 tw50_tickers 下載是否成功。")

    # === 將資料庫寫入邏輯完全隔離，使其無法中斷程式 ===
    print("--- 執行資料庫寫入嘗試 ---")
    try:
        # 這裡放入你原本的資料庫寫入邏輯
        # 如果這裡崩潰，程式會跳到 except，但不會影響上面已經存好的 CSV
        pass 
    except Exception as e:
        print(f"⚠️ 資料庫寫入警告 (已忽略): {e}")

    # === 最後印出結果 ===
    print("--- 讀取回測績效前 5 名的交易 ---")
    # (保持你原本後續的輸出邏輯)
            
    # ==============================
    # Prt.06.3 寫入 SQLite
    # ==============================
    #
    # 將下載結果存入 daily_price
    #
    # ==============================
        cursor.executemany('''
            INSERT OR REPLACE INTO daily_price (ticker, Date, Open, High, Low, Close, Volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', all_records)
        conn.commit()

    cutoff_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')

    # ==============================
    # Prt.06.4 清除五年前資料
    # ==============================
    cursor.execute("DELETE FROM daily_price WHERE Date < ?", (cutoff_date,))
    conn.commit()

    # ==============================
    # Prt.06.5 Alert Log 保留五年
    # ==============================
    cursor.execute(
        '''
        DELETE FROM alert_log
        WHERE entry_date < ?
        ''',
        (cutoff_date,)
    )
    conn.commit()
    
    # ==============================
    # Prt.06.6 SQLite VACUUM 月保養
    # ==============================
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

# ==============================
# Prt.07 回測主控引擎
# ==============================
#
# 執行整個策略流程
#
# ==============================

def run_0050_batch(conn):

    strategy_version = "v02.12"

    print("=" * 60)
    print(f"Strategy Version : {strategy_version}")
    print(f"Backtest Start   : {datetime.datetime.now(TAIPEI_TZ)}")
    print("=" * 60)
    
    # ==============================
    # Prt.07.1 同步資料庫
    # ==============================
    sync_daily_data(conn)
    
    print(f"🚀 啟動 {strategy_version} 回測引擎...")
    
    all_trades = []
    alerts_setup = []
    alerts_trigger = []
    
    cursor = conn.cursor()

    alert_cursor = conn.cursor()
    
    # ==============================
    # Prt.07.2 清除本版回測資料
    # ==============================
    cursor.execute("DELETE FROM backtest_trades WHERE version = ?", (strategy_version,))
    conn.commit()

# ==============================
# Prt.08 個股回測流程
# ==============================
#
# 逐一處理台灣50股票
#
# ==============================

    for ticker in tw50_tickers:
        try:

            # ==============================
            # Prt.08.1 讀取歷史資料
            # ==============================
            
            df_full = pd.read_sql_query(
                "SELECT Date, Open, High, Low, Close, Volume FROM daily_price WHERE ticker = ? ORDER BY Date", 
                conn, 
                params=(ticker,),
                parse_dates=['Date']
            )
            
            if len(df_full) < 65: continue
                
            # ==============================
            # Prt.08.2 執行策略回測
            # ==============================
            trades, df_updated = calculate_v0211F_and_backtest(df_full, ticker, strategy_version)
            all_trades.extend(trades)

            # ==============================
            # Prt.08.3 取得最新交易日結果
            # ==============================
            latest_day = df_updated.iloc[-1]
            yesterday_day = df_updated.iloc[-2]
            
            score_today = latest_day['Score']
            score_yesterday = yesterday_day['Score']
            
# ==============================
# Prt.09 訊號判斷
# ==============================
#
# 判斷今天是否產生新訊號
#       
# ==============================

            latest_trading_day = (
                df_updated['Date']
                .max()
                .strftime('%Y-%m-%d')
            )
            
            # ==============================
            # Prt.09.1 Setup 首次成立
            # ==============================
            is_setup_ready = (pd.notna(score_today) and score_today >= 45 and pd.notna(score_yesterday) and score_yesterday < 45)
            
            # ==============================
            # Prt.09.2 最新交易日成功進場
            # ==============================
            entered_latest_day_trades = [
                t for t in trades
                if t[2] == latest_trading_day
            ]

# ==============================
# Prt.10 Trigger 推播
# ==============================
#
# 當股票已經正式進場
#
# 建立買進通知內容
#
# 準備送往 Telegram
#
# ==============================
            
            # ==============================
            # Prt.10.1 計算實際進場價格
            # ==============================
            if entered_latest_day_trades:

                actual_entry_price = entered_latest_day_trades[-1][4]

                entry_trade_date = pd.to_datetime(
                    entered_latest_day_trades[-1][2]
                )
                
                entry_row = df_updated.loc[
                    df_updated['Date'] == entry_trade_date
                ]
                entry_ma20 = (
                    entry_row.iloc[0]['MA20']
                    if not entry_row.empty
                    else latest_day['MA20']
                )
           
            # ==============================
            # Prt.10.2 檢查是否已推播
            # ==============================
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

            # ==============================
            # Prt.10.3 建立 Trigger 訊息
            # ==============================
                    alerts_trigger.append(
                        f"✅ <b>{ticker}</b> 今日突破進場\n"
                        f"成交價 <b>{actual_entry_price:.2f}</b>\n"
                        f"防守月線 <b>{entry_ma20:.2f}</b>"
                    )

            # ==============================
            # Prt.10.4 寫入 Alert Log
            # ==============================
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

# ==============================
# Prt.11 Watchlist 推播
# ==============================
#
# 將符合 Setup 條件
# 但尚未突破進場的股票整理成觀察名單
#
# ==============================

            elif is_setup_ready:

                alerts_setup.append(
                    f"🚀 <b>{ticker}</b> 首日達標\n"
                    f"Score = {int(score_today)}\n"
                    f"明日突破 <b>{latest_day['High']:.2f}</b> 買進"
                )
                
        except Exception as e:
            print(f"回測 {ticker} 錯誤: {e}")

        # ==============================
        # Commit Alert Log
        # ==============================
        
        if conn.in_transaction:
            conn.commit()
            
# ==============================
# Prt.12 回測結果寫入資料庫
# ==============================
#
# 將所有交易紀錄存入資料庫
#
# ==============================
    
    if all_trades:
        cursor.executemany('''
            INSERT INTO backtest_trades 
            (version, ticker, entry_date, exit_date, entry_price, exit_price, profit_pct, holding_bars, max_profit_pct, trade_max_drawdown_pct, entry_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', all_trades)
        conn.commit()

# ==============================
# Prt.13 Telegram 訊息組裝
# ==============================
#
# 整理 Trigger 與 Watchlist
#
# 合併成最終通知內容
#
# ==============================
    
    msg_parts = [f"📊 <b>{strategy_version} 台股 50 戰情室</b>"]

    # ==============================
    # Prt.13.1 Watchlist
    # ==============================
    if alerts_setup:
        msg_parts.append("================\n🎯 <b>潛力起漲預告 (Watchlist)</b>\n" + "\n\n".join(alerts_setup))

    # ==============================
    # Prt.13.2 Trigger
    # ==============================
    if alerts_trigger:
        msg_parts.append("================\n🔥 <b>最新交易日執行回報</b>\n" + "\n\n".join(alerts_trigger))

    # ==============================
    # Prt.13.3 無訊號
    # ==============================
    if not alerts_trigger and not alerts_setup:
        msg_parts.append("\n盤後無新增訊號。")
    
# ==============================
# Prt.14 發送 Telegram
# ==============================
#
# 將整理完成訊息送出
#    
# ==============================
    
    send_telegram_alert("\n\n".join(msg_parts))
    
# ==============================
# Prt.15 主程式入口
# ==============================
#
# 執行順序：
#
# 1. 初始化資料庫
# 2. 更新歷史資料
# 3. 執行回測
# 4. 判斷交易訊號
# 5. 發送 Telegram
#
# ==============================

if __name__ == "__main__":
    db_connection = init_db("tw50_strategy.db")
    run_0050_batch(db_connection)
    db_connection.close()




