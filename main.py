import pandas as pd
import numpy as np
import yfinance as yf
import sqlite3
import datetime
import os
import urllib.request
import json

# 0050 成分股代碼清單
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
    # 建立日線價格表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_price (
            ticker TEXT, Date TEXT, Open REAL, High REAL, Low REAL, Close REAL, Volume INTEGER,
            PRIMARY KEY (ticker, Date)
        )
    ''')
    # V02.2 升級：增加進階統計欄位
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backtest_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT, entry_date TEXT, exit_date TEXT, 
            entry_price REAL, exit_price REAL, profit_pct REAL,
            holding_days INTEGER, max_profit_pct REAL, max_drawdown_pct REAL, entry_score REAL
        )
    ''')
    conn.commit()
    return conn

def calculate_v022_and_backtest(df, ticker):
    df = df.sort_values('Date').dropna().reset_index(drop=True)
    
    # 基礎指標
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['MA120'] = df['Close'].rolling(120).mean()
    df['V_MA5'] = df['Volume'].rolling(5).mean()
    
    # MACD
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = ema12 - ema26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['DEA']
    
    # V02.2 評分邏輯優化 (減少多重共線性，加入斜率)
    t1 = (df['MACD_Hist'] > df['MACD_Hist'].shift(1)).astype(int) * 15 # 動能增強
    
    m1 = (df['Close'] > df['MA20']).astype(int) * 10
    # 新增：MA20 斜率濾網 (過濾盤整)
    m2 = (df['MA20'] > df['MA20'].shift(5)).astype(int) * 15
    m3 = (df['MA20'] > df['MA60']).astype(int) * 10
    
    v1 = (df['Volume'] > df['V_MA5'] * 1.5).astype(int) * 10 # 爆量起漲
    
    df['Score'] = t1 + m1 + m2 + m3 + v1 # 總分調整，降低虛胖分數
    
    trades = []
    in_position = False
    entry_price = signal_day_high = entry_score = 0
    entry_date = None
    
    # 用於計算最大回撤與最大利潤
    highest_price = lowest_price = entry_idx = 0
    
    for i in range(120, len(df)-1):
        today = df.iloc[i]
        tomorrow = df.iloc[i+1]
        
        if not in_position:
            # 條件 1: 今日分數達標 (這裡門檻配合新計分系統稍微下修至 50 分作為訊號)
            if today['Score'] >= 50:
                signal_day_high = today['High']
                entry_score = today['Score']
                
                # 條件 2: Buy Stop 邏輯，隔日最高價必須突破訊號日最高價
                if tomorrow['High'] >= signal_day_high:
                    in_position = True
                    # 如果跳空開高，成交在開盤價；否則成交在突破點
                    entry_price = max(tomorrow['Open'], signal_day_high)
                    entry_date = tomorrow['Date']
                    entry_idx = i + 1
                    highest_price = entry_price
                    lowest_price = entry_price
        else:
            highest_price = max(highest_price, tomorrow['High'])
            lowest_price = min(lowest_price, tomorrow['Low'])
            
            # 停損邏輯：固定 -8% (嚴格執行，如果開盤就跌破，則以開盤價停損)
            stop_loss_price = entry_price * 0.92
            
            # 判斷是否觸發停損
            if tomorrow['Low'] <= stop_loss_price:
                exit_price = min(tomorrow['Open'], stop_loss_price)
                exit_date = tomorrow['Date']
                profit_pct = (exit_price - entry_price) / entry_price
                holding_days = (exit_date - entry_date).days
                max_p = (highest_price - entry_price) / entry_price
                max_d = (lowest_price - entry_price) / entry_price
                
                trades.append((
                    ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'),
                    entry_price, exit_price, profit_pct, holding_days, max_p, max_d, entry_score
                ))
                in_position = False
                
            # 停利邏輯：跌破 MA20 出場 (如果沒被停損洗掉)
            elif tomorrow['Close'] < tomorrow['MA20']:
                if i+2 < len(df):
                    next_day = df.iloc[i+2]
                    exit_price = next_day['Open'] # 隔日開盤市價出
                    exit_date = next_day['Date']
                    profit_pct = (exit_price - entry_price) / entry_price
                    holding_days = (exit_date - entry_date).days
                    max_p = (highest_price - entry_price) / entry_price
                    max_d = (lowest_price - entry_price) / entry_price
                    
                    trades.append((
                        ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'),
                        entry_price, exit_price, profit_pct, holding_days, max_p, max_d, entry_score
                    ))
                    in_position = False
                    
    # 如果迴圈結束還在場內，強制結算
    if in_position:
        last_day = df.iloc[-1]
        exit_price = last_day['Close']
        exit_date = last_day['Date']
        profit_pct = (exit_price - entry_price) / entry_price
        holding_days = (exit_date - entry_date).days
        max_p = (highest_price - entry_price) / entry_price
        max_d = (lowest_price - entry_price) / entry_price
        
        trades.append((
            ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'),
            entry_price, exit_price, profit_pct, holding_days, max_p, max_d, entry_score
        ))
        
    return trades, df

def run_0050_batch(conn):
    # 為減輕存活者偏差，預設回測改為 5 年
    start_date = (datetime.datetime.now() - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    print("🚀 啟動 yfinance 批次下載 (大幅提速)...")
    # 批次下載
    raw_data = yf.download(tw50_tickers, start=start_date, end=end_date, group_by='ticker', progress=False)
    
    all_trades = []
    daily_alerts = []
    cursor = conn.cursor()
    
    # 每次回測前清空舊的交易紀錄表，避免重複寫入
    cursor.execute("DELETE FROM backtest_trades")
    conn.commit()
    
    for ticker in tw50_tickers:
        try:
            # 從批次資料中提取單一個股
            stock_data = raw_data[ticker].dropna(how='all').copy()
            if stock_data.empty: continue
            
            df = stock_data.reset_index()
            
            # --- 處理資料庫重複累積問題 (INSERT OR REPLACE) ---
            df_to_db = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
            df_to_db['Date'] = df_to_db['Date'].dt.strftime('%Y-%m-%d')
            df_to_db.insert(0, 'ticker', ticker)
            
            # 寫入暫存表
            df_to_db.to_sql('temp_price', conn, if_exists='replace', index=False)
            # 使用 SQL 語法進行合併更新
            cursor.execute('''
                INSERT OR REPLACE INTO daily_price (ticker, Date, Open, High, Low, Close, Volume)
                SELECT ticker, Date, Open, High, Low, Close, Volume FROM temp_price
            ''')
            conn.commit()
            
            # --- 執行 V02.2 回測 ---
            trades, df_updated = calculate_v022_and_backtest(df, ticker)
            all_trades.extend(trades)
            
            # --- Telegram 推播邏輯 ---
            if len(df_updated) >= 2:
                latest_day = df_updated.iloc[-1]
                yesterday = df_updated.iloc[-2]
                score = latest_day['Score']
                score_delta = score - yesterday['Score']
                
                # 新版 V02.2 滿分為 60 分，這裡設定 >= 50 作為強勢起漲推播門檻
                if pd.notna(score) and score >= 50:
                    daily_alerts.append(
                        f"🎯 *{ticker}*\n評分: {int(score)} (變動: {int(score_delta):+d})\n"
                        f"收盤: {latest_day['Close']:.2f} | 🛡️ MA20防守: {latest_day['MA20']:.2f}\n"
                        f"⚡ 訊號觸發價 (明日突破此價位進場): {latest_day['High']:.2f}"
                    )
        except Exception as e:
            print(f"處理 {ticker} 時發生錯誤: {e}")
            
    if all_trades:
        cursor.executemany('''
            INSERT INTO backtest_trades 
            (ticker, entry_date, exit_date, entry_price, exit_price, profit_pct, holding_days, max_profit_pct, max_drawdown_pct, entry_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', all_trades)
        conn.commit()
        print(f"✅ V02.2 升級版回測完成，共寫入 {len(all_trades)} 筆實戰紀錄。")
    
    if daily_alerts:
        msg = "🚀 *V02.2 台股 50 強勢起漲雷達* 🚀\n(已加上 MA20 斜率濾網)\n\n" + "\n\n".join(daily_alerts)
    else:
        msg = "📊 *V02.2 台股 50 雷達*\n今日掃描完畢，無符合 >= 50 分的起漲標的。"
    send_telegram_alert(msg)

if __name__ == "__main__":
    db_connection = init_db("tw50_strategy.db")
    run_0050_batch(db_connection)
    db_connection.close()
