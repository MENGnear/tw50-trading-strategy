# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
#  版次 v02.3 (核心回測引擎與架構優化版)
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
#  新增與優化：
#  1. [回測A] 導入 Buy Stop 觸價單邏輯，隔日高點突破才進場，消除「偷看未來」的收盤滑價作弊。
#  2. [回測B] 新增硬性停損防線 (-8%)，嚴格控管極端黑天鵝風險，保護本金。
#  3. [回測C] 最大回撤 (MDD) 計算公式重構，精準測量從波段最高點回落之真實幅度。
#  4. [策略D] V02.2/02.3 評分系統大改版：新增 MA20 5日斜率濾網 (>1%)，過濾盤整假突破。
#  5. [效能E] 捨棄迴圈抓資料，改用 yfinance group_by 批次下載，執行時間從 8 分鐘縮減至 1 分鐘內。
#  6. [資料F] SQLite 導入 INSERT OR REPLACE 容錯機制與 Version 欄位，支援多版本策略共存與效能提升。
#  7. [架構G] 程式碼全面模組化，新增各功能區段之高可讀性註解排版。
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

# 0050 成分股代碼清單 (固定 50 檔)
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

# ==========================================================
# 2️⃣ 📡 Telegram 警報推播模組
# ==========================================================
def send_telegram_alert(message):
    """讀取 GitHub Secrets 並發送 Telegram 推播"""
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
    """初始化資料庫與資料表結構 (支援版本共存)"""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    # 日線價格表 (使用 ticker 與 Date 作為主鍵防呆)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_price (
            ticker TEXT, Date TEXT, Open REAL, High REAL, Low REAL, Close REAL, Volume INTEGER,
            PRIMARY KEY (ticker, Date)
        )
    ''')
    
    # 策略回測表 (新增 version 與高階統計欄位)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backtest_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT,
            ticker TEXT, entry_date TEXT, exit_date TEXT, 
            entry_price REAL, exit_price REAL, profit_pct REAL,
            holding_bars INTEGER, max_profit_pct REAL, max_drawdown_pct REAL, entry_score REAL
        )
    ''')
    conn.commit()
    return conn

# ==========================================================
# 4️⃣ 🧠 v02.3 核心評分與實戰回測引擎
# ==========================================================
def calculate_v023_and_backtest(df, ticker, strategy_version="V02.3"):
    """執行指標計算、濾網篩選與 Buy Stop 回測邏輯"""
    df = df.sort_values('Date').dropna().reset_index(drop=True)
    
    # ─── 指標計算 ───
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['MA120'] = df['Close'].rolling(120).mean()
    df['V_MA5'] = df['Volume'].rolling(5).mean()
    
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = ema12 - ema26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['DEA']
    
    # ─── v02.3 評分系統 (滿分 60 分) ───
    t1 = (df['MACD_Hist'] > df['MACD_Hist'].shift(1)).astype(int) * 15  # 動能增強
    m1 = (df['Close'] > df['MA20']).astype(int) * 10                    # 站上月線
    m2 = ((df['MA20'] / df['MA20'].shift(5) - 1) > 0.01).astype(int) * 15 # MA20 五日斜率 > 1% (過濾盤整)
    m3 = (df['MA20'] > df['MA60']).astype(int) * 10                     # 多頭排列
    v1 = (df['Volume'] > df['V_MA5'] * 1.3).astype(int) * 10            # 溫和出量起漲
    
    df['Score'] = t1 + m1 + m2 + m3 + v1
    
    # ─── 實戰回測變數初始化 ───
    trades = []
    in_position = False
    entry_price = signal_day_high = entry_score = 0
    entry_date = None
    
    peak_price = lowest_price = 0
    entry_idx = 0
    max_drawdown = 0.0
    
    # ─── K棒逐日回測迴圈 (Buy Stop 邏輯) ───
    for i in range(120, len(df)-1):
        today = df.iloc[i]
        tomorrow = df.iloc[i+1]
        
        # 狀態：空手尋找進場點
        if not in_position:
            if today['Score'] >= 45: # 門檻設定為 45 分
                signal_day_high = today['High']
                entry_score = today['Score']
                
                # 隔日高點必須突破訊號日高點才成交 (Buy Stop)
                if tomorrow['High'] >= signal_day_high:
                    in_position = True
                    entry_price = max(tomorrow['Open'], signal_day_high)
                    entry_date = tomorrow['Date']
                    entry_idx = i + 1
                    
                    peak_price = entry_price 
                    lowest_price = entry_price
                    max_drawdown = 0.0
        
        # 狀態：持倉中尋找部位平倉點
        else:
            # 更新最高點，計算精準 MDD
            peak_price = max(peak_price, tomorrow['High'])
            lowest_price = min(lowest_price, tomorrow['Low'])
            
            current_drawdown = (tomorrow['Low'] - peak_price) / peak_price
            max_drawdown = min(max_drawdown, current_drawdown)
            
            # 防線一：硬性停損 -8%
            stop_loss_price = entry_price * 0.92
            
            if tomorrow['Low'] <= stop_loss_price:
                exit_price = min(tomorrow['Open'], stop_loss_price)
                exit_date = tomorrow['Date']
                profit_pct = (exit_price - entry_price) / entry_price
                holding_bars = (i + 1) - entry_idx
                max_p = (peak_price - entry_price) / entry_price
                
                trades.append((
                    strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'),
                    entry_price, exit_price, profit_pct, holding_bars, max_p, max_drawdown, entry_score
                ))
                in_position = False
                
            # 防線二：跌破 MA20 停利/出場
            elif tomorrow['Close'] < tomorrow['MA20']:
                if i+2 < len(df):
                    next_day = df.iloc[i+2]
                    exit_price = next_day['Open'] # 隔日開盤市價結算
                    exit_date = next_day['Date']
                    profit_pct = (exit_price - entry_price) / entry_price
                    holding_bars = (i + 2) - entry_idx
                    
                    temp_peak = max(peak_price, next_day['High'])
                    temp_drawdown = (next_day['Low'] - temp_peak) / temp_peak
                    final_mdd = min(max_drawdown, temp_drawdown)
                    max_p = (temp_peak - entry_price) / entry_price
                    
                    trades.append((
                        strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'),
                        entry_price, exit_price, profit_pct, holding_bars, max_p, final_mdd, entry_score
                    ))
                    in_position = False
                    
    # 迴圈結束若仍持倉，強制以最後一日收盤價結算
    if in_position:
        last_day = df.iloc[-1]
        exit_price = last_day['Close']
        exit_date = last_day['Date']
        profit_pct = (exit_price - entry_price) / entry_price
        holding_bars = (len(df) - 1) - entry_idx
        
        temp_peak = max(peak_price, last_day['High'])
        temp_drawdown = (last_day['Low'] - temp_peak) / temp_peak
        final_mdd = min(max_drawdown, temp_drawdown)
        max_p = (temp_peak - entry_price) / entry_price
        
        trades.append((
            strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'),
            entry_price, exit_price, profit_pct, holding_bars, max_p, final_mdd, entry_score
        ))
        
    return trades, df

# ==========================================================
# 5️⃣ 🏭 批次調度與主程式執行
# ==========================================================
def run_0050_batch(conn):
    """執行資料抓取、更新資料庫與推播調度"""
    # 回測區間：5年 (減輕存活者偏差)
    start_date = (datetime.datetime.now() - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    strategy_version = "v02.3"
    
    print("🚀 啟動 yfinance 批次下載 (大幅提速中)...")
    raw_data = yf.download(tw50_tickers, start=start_date, end=end_date, group_by='ticker', progress=False)
    
    all_trades = []
    daily_alerts = []
    cursor = conn.cursor()
    
    for ticker in tw50_tickers:
        try:
            stock_data = raw_data[ticker].dropna(how='all').copy()
            if stock_data.empty: continue
            
            df = stock_data.reset_index()
            
            # 整理並寫入歷史 K 線資料表 (使用 executemany 提升效能)
            df_to_db = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
            df_to_db['Date'] = df_to_db['Date'].dt.strftime('%Y-%m-%d')
            df_to_db.insert(0, 'ticker', ticker)
            
            records = df_to_db.values.tolist()
            cursor.executemany('''
                INSERT OR REPLACE INTO daily_price (ticker, Date, Open, High, Low, Close, Volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', records)
            
            # 呼叫核心回測引擎
            trades, df_updated = calculate_v023_and_backtest(df, ticker, strategy_version)
            all_trades.extend(trades)
            
            # 檢查是否觸發今日推播訊號
            if len(df_updated) >= 2:
                latest_day = df_updated.iloc[-1]
                yesterday = df_updated.iloc[-2]
                score = latest_day['Score']
                score_delta = score - yesterday['Score']
                
                if pd.notna(score) and score >= 45:
                    daily_alerts.append(
                        f"🎯 *{ticker}*\n"
                        f"版號: {strategy_version}\n"
                        f"評分: {int(score)} (變動: {int(score_delta):+d})\n"
                        f"收盤: {latest_day['Close']:.2f} | 🛡️ MA20防守: {latest_day['MA20']:.2f}\n"
                        f"⚡ 觸發價 (明日突破此價進場): {latest_day['High']:.2f}"
                    )
        except Exception as e:
            print(f"處理 {ticker} 時發生錯誤: {e}")
            
    # 寫入回測交易紀錄 (帶入版本號，允許不同策略紀錄共存)
    if all_trades:
        cursor.executemany('''
            INSERT INTO backtest_trades 
            (version, ticker, entry_date, exit_date, entry_price, exit_price, profit_pct, holding_bars, max_profit_pct, max_drawdown_pct, entry_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', all_trades)
        conn.commit()
        print(f"✅ {strategy_version} 回測完成，共寫入 {len(all_trades)} 筆實戰紀錄。")
    
    # 彙整並發布 Telegram 警報
    if daily_alerts:
        msg = f"🚀 *{strategy_version} 台股 50 強勢雷達* 🚀\n(已啟用斜率與提速濾網)\n\n" + "\n\n".join(daily_alerts)
    else:
        msg = f"📊 *{strategy_version} 台股 50 雷達*\n今日無符合 >= 45 分的標的。"
    send_telegram_alert(msg)

if __name__ == "__main__":
    db_connection = init_db("tw50_strategy.db")
    run_0050_batch(db_connection)
    db_connection.close()
