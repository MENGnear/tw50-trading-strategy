# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
#  版次 v02.3 (智能增量更新與核心回測引擎版)
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
#  新增與優化：
#  ... [回測與策略邏輯與上一版相同] ...
#  8. [資料H] 導入智能「增量更新 (Incremental Update)」：每天只下載最新 K 線，不再重複下載 5 年歷史。
#  9. [資料I] 導入滾動視窗：每日自動清除超過 5 年之老舊資料庫紀錄，維持資料庫輕量化。
# 10. [架構J] 運算解耦：回測引擎改為「先讀取本地 DB 完整資料」再計算，徹底解決 Yahoo API 封鎖問題。
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
            version TEXT, ticker TEXT, entry_date TEXT, exit_date TEXT, 
            entry_price REAL, exit_price REAL, profit_pct REAL,
            holding_bars INTEGER, max_profit_pct REAL, max_drawdown_pct REAL, entry_score REAL
        )
    ''')
    conn.commit()
    return conn

def calculate_v023_and_backtest(df, ticker, strategy_version="V02.3"):
    """V02.3 核心邏輯 (與上一版相同)"""
    df = df.sort_values('Date').dropna().reset_index(drop=True)
    
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['MA120'] = df['Close'].rolling(120).mean()
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
    
    peak_price = lowest_price = 0
    entry_idx = 0
    max_drawdown = 0.0
    
    for i in range(120, len(df)-1):
        today = df.iloc[i]
        tomorrow = df.iloc[i+1]
        
        if not in_position:
            if today['Score'] >= 45: 
                signal_day_high = today['High']
                entry_score = today['Score']
                
                if tomorrow['High'] >= signal_day_high:
                    in_position = True
                    entry_price = max(tomorrow['Open'], signal_day_high)
                    entry_date = tomorrow['Date']
                    entry_idx = i + 1
                    peak_price = lowest_price = entry_price 
                    max_drawdown = 0.0
        else:
            peak_price = max(peak_price, tomorrow['High'])
            lowest_price = min(lowest_price, tomorrow['Low'])
            
            current_drawdown = (tomorrow['Low'] - peak_price) / peak_price
            max_drawdown = min(max_drawdown, current_drawdown)
            
            stop_loss_price = entry_price * 0.92
            
            if tomorrow['Low'] <= stop_loss_price:
                exit_price = min(tomorrow['Open'], stop_loss_price)
                exit_date = tomorrow['Date']
                profit_pct = (exit_price - entry_price) / entry_price
                holding_bars = (i + 1) - entry_idx
                max_p = (peak_price - entry_price) / entry_price
                
                trades.append((strategy_version, ticker, entry_date, exit_date, entry_price, exit_price, profit_pct, holding_bars, max_p, max_drawdown, entry_score))
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
                    final_mdd = min(max_drawdown, temp_drawdown)
                    max_p = (temp_peak - entry_price) / entry_price
                    
                    trades.append((strategy_version, ticker, entry_date, exit_date, entry_price, exit_price, profit_pct, holding_bars, max_p, final_mdd, entry_score))
                    in_position = False
                    
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
        
        trades.append((strategy_version, ticker, entry_date, exit_date, entry_price, exit_price, profit_pct, holding_bars, max_p, final_mdd, entry_score))
        
    return trades, df

def sync_daily_data(conn):
    """【新功能】智能增量更新：判斷資料庫狀態，決定下載區間"""
    cursor = conn.cursor()
    today = datetime.datetime.now()
    
    # 檢查資料庫最新日期
    cursor.execute("SELECT MAX(Date) FROM daily_price")
    last_date = cursor.fetchone()[0]
    
    if last_date:
        # 如果有資料：為了防止 Yahoo 盤後微調數據，從最後日期的前兩天開始抓取重疊覆蓋
        start_date_obj = datetime.datetime.strptime(last_date, '%Y-%m-%d') - datetime.timedelta(days=2)
        start_date = start_date_obj.strftime('%Y-%m-%d')
        print(f"📊 偵測到既有資料庫 (最新資料: {last_date})。啟動增量更新，抓取區間: {start_date} 至今...")
    else:
        # 如果是空的：首次執行，抓取 5 年資料
        start_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
        print(f"⚠️ 資料庫為空！啟動初次歷史資料大撒網下載，抓取區間: {start_date} 至今...")

    # yfinance 的 end 參數是不包含當天的，所以要加 1 天
    end_date = (today + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    
    # 執行下載 (設定 threads=False 避免多執行緒被 Yahoo 封鎖)
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
            print(f"整理 {ticker} 下載資料時發生錯誤: {e}")
            
    if all_records:
        cursor.executemany('''
            INSERT OR REPLACE INTO daily_price (ticker, Date, Open, High, Low, Close, Volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', all_records)
        conn.commit()
        print(f"✅ 成功將 {len(all_records)} 筆最新 K 線寫入資料庫！")

    # 【新功能】資料庫滾動瘦身：刪除 5 年前（超過第 6 年）的老舊資料
    cutoff_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
    cursor.execute("DELETE FROM daily_price WHERE Date < ?", (cutoff_date,))
    deleted_rows = cursor.rowcount
    if deleted_rows > 0:
        conn.commit()
        print(f"🧹 資料庫滾動瘦身：已自動清除 {cutoff_date} 之前的舊資料共 {deleted_rows} 筆。")

def run_0050_batch(conn):
    strategy_version = "v02.3"
    
    # 第一階段：智能同步最新價格資料到 SQLite
    sync_daily_data(conn)
    
    # 第二階段：從本地端資料庫讀取完整的 5 年歷史，進行回測與計算
    print(f"🚀 啟動 {strategy_version} 核心回測引擎 (讀取本地資料庫)...")
    
    all_trades = []
    daily_alerts = []
    cursor = conn.cursor()
    
    # 每次回測前，清除該版本的舊紀錄避免重複
    cursor.execute("DELETE FROM backtest_trades WHERE version = ?", (strategy_version,))
    conn.commit()
    
    for ticker in tw50_tickers:
        try:
            # 直接從資料庫撈出這檔股票所有的歷史資料
            df_full = pd.read_sql_query("SELECT Date, Open, High, Low, Close, Volume FROM daily_price WHERE ticker = ? ORDER BY Date", conn)
            
            if len(df_full) < 120:
                continue # 資料不足以計算 MA120，跳過
                
            trades, df_updated = calculate_v023_and_backtest(df_full, ticker, strategy_version)
            all_trades.extend(trades)
            
            # 檢查今日訊號
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
            print(f"執行 {ticker} 回測時發生錯誤: {e}")
            
    if all_trades:
        cursor.executemany('''
            INSERT INTO backtest_trades 
            (version, ticker, entry_date, exit_date, entry_price, exit_price, profit_pct, holding_bars, max_profit_pct, max_drawdown_pct, entry_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', all_trades)
        conn.commit()
        print(f"✅ 回測完成，共寫入 {len(all_trades)} 筆實戰紀錄。")
    
    if daily_alerts:
        msg = f"🚀 *{strategy_version} 台股 50 強勢雷達* 🚀\n(已啟用增量更新模組)\n\n" + "\n\n".join(daily_alerts)
    else:
        msg = f"📊 *{strategy_version} 台股 50 雷達*\n今日無符合 >= 45 分的標的。"
    send_telegram_alert(msg)

if __name__ == "__main__":
    db_connection = init_db("tw50_strategy.db")
    run_0050_batch(db_connection)
    db_connection.close()
