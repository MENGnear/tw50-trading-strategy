import pandas as pd
import numpy as np
import yfinance as yf
import sqlite3
import datetime

# 0050 成分股代碼清單 (完整 50 檔)
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

def init_db(db_name="tw50_strategy.db"):
    """初始化 SQLite 資料庫"""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_price (
            ticker TEXT,
            Date TEXT,
            Open REAL,
            High REAL,
            Low REAL,
            Close REAL,
            Volume INTEGER,
            PRIMARY KEY (ticker, Date)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backtest_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            entry_date TEXT,
            exit_date TEXT,
            entry_price REAL,
            exit_price REAL,
            profit_pct REAL
        )
    ''')
    conn.commit()
    return conn

def calculate_v021_and_backtest(df, ticker):
    """計算 V02.1 指標並執行 MA20 停利回測"""
    df = df.sort_values('Date').dropna().reset_index(drop=True)
    
    # 基礎指標
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['MA120'] = df['Close'].rolling(120).mean()
    df['V_MA5'] = df['Volume'].rolling(5).mean()
    df['V_MA10'] = df['Volume'].rolling(10).mean()
    
    # MACD
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = ema12 - ema26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['DEA']
    df['Prev_Hist'] = df['MACD_Hist'].shift(1)
    
    # RSI
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=13, adjust=False).mean()
    ema_down = down.ewm(com=13, adjust=False).mean()
    rs = ema_up / ema_down
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # KD
    low_min = df['Low'].rolling(9).min()
    high_max = df['High'].rolling(9).max()
    df['RSV'] = 100 * (df['Close'] - low_min) / (high_max - low_min)
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    # V02.1 評分計算
    t1 = (df['DIF'] > df['DEA']).astype(int) * 15
    t2 = (df['DIF'] > 0).astype(int) * 5
    t3 = (df['MACD_Hist'] > df['Prev_Hist']).astype(int) * 10
    score_t = t1 + t2 + t3
    
    m1 = (df['Close'] > df['MA20']).astype(int) * 5
    m2 = (df['MA20'] > df['MA60']).astype(int) * 10
    m3 = (df['MA60'] > df['MA120']).astype(int) * 10
    score_m = m1 + m2 + m3
    
    r1 = (df['RSI'] > 50).astype(int) * 5
    r2 = (df['RSI'] > 60).astype(int) * 5
    r3 = (df['K'] > df['D']).astype(int) * 10
    score_r = r1 + r2 + r3
    
    v1 = (df['Volume'] > df['V_MA5']).astype(int) * 5
    v2 = (df['Volume'] > df['V_MA10']).astype(int) * 5
    v3 = (df['Volume'] > df['V_MA5'] * 1.5).astype(int) * 5
    score_v = v1 + v2 + v3
    
    df['Score'] = score_t + score_m + score_r + score_v
    
    # 執行回測
    trades = []
    in_position = False
    entry_price = 0
    signal_day_high = 0
    entry_date = None
    
    for i in range(120, len(df)-1):
        today = df.iloc[i]
        tomorrow = df.iloc[i+1]
        
        if not in_position:
            if today['Score'] >= 75:
                signal_day_high = today['High']
                if tomorrow['High'] > signal_day_high:
                    in_position = True
                    entry_price = max(tomorrow['Open'], signal_day_high)
                    entry_date = tomorrow['Date'].strftime('%Y-%m-%d')
        else:
            if tomorrow['Close'] < tomorrow['MA20']:
                if i+2 < len(df):
                    next_day = df.iloc[i+2]
                    exit_price = next_day['Open']
                    profit_pct = (exit_price - entry_price) / entry_price
                    trades.append((
                        ticker, entry_date, next_day['Date'].strftime('%Y-%m-%d'),
                        entry_price, exit_price, profit_pct
                    ))
                    in_position = False
                    
    if in_position:
        last_day = df.iloc[-1]
        exit_price = last_day['Close']
        profit_pct = (exit_price - entry_price) / entry_price
        trades.append((
            ticker, entry_date, last_day['Date'].strftime('%Y-%m-%d'),
            entry_price, exit_price, profit_pct
        ))
        
    return trades

def run_0050_batch(conn):
    start_date = (datetime.datetime.now() - datetime.timedelta(days=3650)).strftime('%Y-%m-%d')
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    all_trades = []
    
    for ticker in tw50_tickers:
        print(f"正在處理: {ticker}...")
        try:
            # 抓取資料
            stock_data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if stock_data.empty:
                continue
                
            # 【關鍵修復】: 將新版 yfinance 的雙層 MultiIndex 欄位壓平為單層
            if isinstance(stock_data.columns, pd.MultiIndex):
                stock_data.columns = stock_data.columns.get_level_values(0)
                
            # 準備寫入資料庫的格式
            df = stock_data.reset_index()
            df_to_db = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
            df_to_db['Date'] = df_to_db['Date'].dt.strftime('%Y-%m-%d')
            df_to_db.insert(0, 'ticker', ticker)
            
            # 寫入 SQLite
            df_to_db.to_sql('daily_price', conn, if_exists='append', index=False, 
                            method='multi', chunksize=1000)
            
            # 回測運算
            trades = calculate_v021_and_backtest(df, ticker)
            all_trades.extend(trades)
            
        except Exception as e:
            print(f"處理 {ticker} 時發生錯誤: {e}")
            
    if all_trades:
        cursor = conn.cursor()
        cursor.executemany('''
            INSERT INTO backtest_trades (ticker, entry_date, exit_date, entry_price, exit_price, profit_pct)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', all_trades)
        conn.commit()
        print(f"\n✅ 成功完成回測，共存入 {len(all_trades)} 筆交易紀錄。")

if __name__ == "__main__":
    db_connection = init_db("tw50_strategy.db")
    run_0050_batch(db_connection)
    
    print("\n--- 讀取回測績效前 5 名的交易 ---")
    top_trades = pd.read_sql_query('''
        SELECT ticker, entry_date, exit_date, round(profit_pct*100, 2) as profit_pct
        FROM backtest_trades 
        ORDER BY profit_pct DESC LIMIT 5
    ''', db_connection)
    print(top_trades)
    
    db_connection.close()
