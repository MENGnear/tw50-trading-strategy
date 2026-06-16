import pandas as pd
import numpy as np
import yfinance as yf
import sqlite3
import datetime

# ==========================================
# 步驟 1: SQLite 資料庫架設與初始化
# ==========================================
def init_db(db_name="tw50_strategy.db"):
    """初始化 SQLite 資料庫，建立歷史價格與回測結果表"""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    # 建立歷史數據表 (若不存在)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_price (
            ticker TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            PRIMARY KEY (ticker, date)
        )
    ''')
    
    # 建立回測交易紀錄表
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

# ==========================================
# 步驟 2: V02.1 演算法與回測邏輯 (不含推播)
# ==========================================
def calculate_v021_and_backtest(df, ticker):
    """計算 V02.1 指標並執行 MA20 停利回測"""
    # 確保資料依照時間排序並清理空值
    df = df.sort_values('Date').dropna().reset_index(drop=True)
    
    # --- 計算基礎技術指標 ---
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
    
    # RSI (標準 EMA 算法)
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
    
    # --- V02.1 狀態型評分系統 ---
    # Trend (30分)
    t1 = (df['DIF'] > df['DEA']).astype(int) * 15
    t2 = (df['DIF'] > 0).astype(int) * 5
    t3 = (df['MACD_Hist'] > df['Prev_Hist']).astype(int) * 10
    score_t = t1 + t2 + t3
    
    # MA (25分)
    m1 = (df['Close'] > df['MA20']).astype(int) * 5
    m2 = (df['MA20'] > df['MA60']).astype(int) * 10
    m3 = (df['MA60'] > df['MA120']).astype(int) * 10
    score_m = m1 + m2 + m3
    
    # Momentum (20分)
    r1 = (df['RSI'] > 50).astype(int) * 5
    r2 = (df['RSI'] > 60).astype(int) * 5
    r3 = (df['K'] > df['D']).astype(int) * 10
    score_r = r1 + r2 + r3
    
    # Volume (15分)
    v1 = (df['Volume'] > df['V_MA5']).astype(int) * 5
    v2 = (df['Volume'] > df['V_MA10']).astype(int) * 5
    v3 = (df['Volume'] > df['V_MA5'] * 1.5).astype(int) * 5
    score_v = v1 + v2 + v3
    
    df['Score'] = score_t + score_m + score_r + score_v
    
    # --- 執行回測：分數 >= 75 進場，跌破 MA20 出場 ---
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
                # 隔日突破訊號日高點進場
                if tomorrow['High'] > signal_day_high:
                    in_position = True
                    entry_price = max(tomorrow['Open'], signal_day_high)
                    entry_date = tomorrow['Date'].strftime('%Y-%m-%d')
        else:
            # 跌破 MA20 停利/停損
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
                    
    # 強制平倉最後一筆
    if in_position:
        last_day = df.iloc[-1]
        exit_price = last_day['Close']
        profit_pct = (exit_price - entry_price) / entry_price
        trades.append((
            ticker, entry_date, last_day['Date'].strftime('%Y-%m-%d'),
            entry_price, exit_price, profit_pct
        ))
        
    return trades

# ==========================================
# 步驟 3: 抓取 0050 成分股資料並寫入 DB
# ==========================================
def run_0050_batch(conn):
    # 台灣 50 成分股代碼 (此處列舉部分作為範例，實戰可補齊 50 檔)
    tw50_tickers = [
        '2330.TW', '2317.TW', '2454.TW', '2308.TW', '2382.TW', 
        '2881.TW', '2882.TW', '2891.TW', '2412.TW', '3231.TW'
    ]
    
    start_date = (datetime.datetime.now() - datetime.timedelta(days=3650)).strftime('%Y-%m-%d')
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    all_trades = []
    
    for ticker in tw50_tickers:
        print(f"正在處理: {ticker}...")
        try:
            # 從 yfinance 下載 10 年資料
            stock_data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if stock_data.empty:
                continue
                
            # 重設 index 讓 Date 變成欄位，並過濾欄位
            df = stock_data.reset_index()
            # 寫入 SQLite (日線資料)
            df_to_db = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
            df_to_db['Date'] = df_to_db['Date'].dt.strftime('%Y-%m-%d')
            df_to_db.insert(0, 'ticker', ticker)
            
            # 使用 pandas 內建功能快速匯入資料庫
            df_to_db.to_sql('daily_price', conn, if_exists='append', index=False, 
                            method='multi', chunksize=1000)
            
            # 執行回測邏輯
            trades = calculate_v021_and_backtest(df, ticker)
            all_trades.extend(trades)
            
        except Exception as e:
            print(f"處理 {ticker} 時發生錯誤: {e}")
            
    # 將回測結果寫入資料庫
    if all_trades:
        cursor = conn.cursor()
        cursor.executemany('''
            INSERT INTO backtest_trades (ticker, entry_date, exit_date, entry_price, exit_price, profit_pct)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', all_trades)
        conn.commit()
        print(f"\n✅ 成功完成回測，共產生 {len(all_trades)} 筆交易紀錄已存入資料庫。")

# --- 執行主程式 ---
if __name__ == "__main__":
    db_connection = init_db("tw50_strategy.db")
    run_0050_batch(db_connection)
    
    # 驗證資料庫查詢
    print("\n--- 讀取回測績效前 5 名的交易 ---")
    top_trades = pd.read_sql_query('''
        SELECT ticker, entry_date, exit_date, round(profit_pct*100, 2) as profit_pct
        FROM backtest_trades 
        ORDER BY profit_pct DESC LIMIT 5
    ''', db_connection)
    print(top_trades)
    
    db_connection.close()