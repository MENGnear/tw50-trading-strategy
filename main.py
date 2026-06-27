# ==============================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : TW50 Breakout Strategy
# 檔案名稱 : main.py
# 策略版本 : v02.18 (核心策略回測模組重構：指標/訊號/交易/統計 解耦)
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 功能說明：
# 1. 台股50成分股歷史資料同步
# 2. 技術指標計算 (MA、MACD、ATR)
# 3. Breakout Strategy 回測
# 4. SQLite 資料儲存與管理
# 5. Telegram 即時訊號與「策略總體績效」通知
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 主要策略：
# - Score >= 45 建立 Setup
# - Buy Stop 突破進場
# - 動態停損 (Entry - 2*ATR20)
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
# Prt.03 核心策略模組拆解 (v02.18)
# ==============================

def calculate_indicator(df):
    """階段一：計算所有底層技術指標"""
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['V_MA5'] = df['Volume'].rolling(5).mean()

    # MACD
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = ema12 - ema26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['DEA']
    
    # ATR20
    df['Prev_Close'] = df['Close'].shift(1)
    df['TR'] = np.maximum(
        df['High'] - df['Low'],
        np.maximum(
            abs(df['High'] - df['Prev_Close']),
            abs(df['Low'] - df['Prev_Close'])
        )
    )
    df['ATR20'] = df['TR'].rolling(window=20).mean()
    return df

def generate_signal(df):
    """階段二：依據指標計算策略訊號與評分"""
    t1 = (df['MACD_Hist'] > df['MACD_Hist'].shift(1)).astype(int) * 15 
    m1 = (df['Close'] > df['MA20']).astype(int) * 10                    
    m2 = ((df['MA20'] / df['MA20'].shift(5) - 1) > 0.01).astype(int) * 15 
    m3 = (df['MA20'] > df['MA60']).astype(int) * 10                      
    v1 = (df['Volume'] > df['V_MA5'] * 1.3).astype(int) * 10            
    df['Score'] = t1 + m1 + m2 + m3 + v1
    return df

def trade_statistics(entry_price, exit_price, entry_idx, exit_idx, peak_price, trade_max_drawdown):
    """階段三：計算單筆交易的績效統計數據"""
    profit_pct = (exit_price - entry_price) / entry_price
    holding_bars = exit_idx - entry_idx
    max_p = (peak_price - entry_price) / entry_price
    trade_max_drawdown_pct = trade_max_drawdown * 100
    return profit_pct, holding_bars, max_p, trade_max_drawdown_pct

def simulate_trade(df, ticker, strategy_version):
    """階段四：執行交易狀態機，進行歷史回測"""
    trades = []
    in_position = False
    entry_price = signal_day_high = entry_score = 0
    entry_date = None
    peak_price = 0
    entry_idx = 0
    trade_max_drawdown = 0.0
    setup_active = False
    stop_loss_price = 0.0

    for i in range(65, len(df)-1):
        yesterday = df.iloc[i-1]
        today = df.iloc[i]
        tomorrow = df.iloc[i+1]

        if not in_position:
            # Setup 條件：今日 >= 45 且昨日 < 45
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
                    
                    # 鎖定進場當日的動態停損點
                    stop_loss_price = entry_price - (2 * today['ATR20'])
        else:
            # 倉位監控與更新最大回撤
            peak_price = max(peak_price, tomorrow['High'])
            trade_max_drawdown = min(trade_max_drawdown, (tomorrow['Low'] - peak_price) / peak_price)

            # 離場條件 1: 觸發動態停損
            if tomorrow['Low'] <= stop_loss_price:
                exit_price = min(tomorrow['Open'], stop_loss_price)
                exit_date = tomorrow['Date']
                exit_idx = i + 1
                
                p, h, m, d = trade_statistics(entry_price, exit_price, entry_idx, exit_idx, peak_price, trade_max_drawdown)
                
                trades.append((
                    strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'),
                    entry_price, exit_price, p, h, m, d, entry_score
                ))
                in_position = False

            # 離場條件 2: 跌破 MA20
            elif tomorrow['Close'] < tomorrow['MA20']:
                if i + 2 < len(df):
                    next_day = df.iloc[i + 2]
                    exit_price = next_day['Open']
                    exit_date = next_day['Date']
                    exit_idx = i + 2
                    
                    temp_peak = max(peak_price, next_day['High'])
                    temp_drawdown = (next_day['Low'] - temp_peak) / temp_peak
                    final_mdd = min(trade_max_drawdown, temp_drawdown)
                    
                    p, h, m, d = trade_statistics(entry_price, exit_price, entry_idx, exit_idx, temp_peak, final_mdd)
                else:
                    last_day = df.iloc[-1]
                    exit_price = last_day['Close']
                    exit_date = last_day['Date']
                    exit_idx = len(df) - 1
                    
                    temp_peak = max(peak_price, last_day['High'])
                    temp_drawdown = (last_day['Low'] - temp_peak) / temp_peak
                    final_mdd = min(trade_max_drawdown, temp_drawdown)
                    
                    p, h, m, d = trade_statistics(entry_price, exit_price, entry_idx, exit_idx, temp_peak, final_mdd)
            
                trades.append((
                    strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'),
                    entry_price, exit_price, p, h, m, d, entry_score
                ))
                in_position = False
                    
    # 回測結束，強制平倉未結算的倉位
    if in_position:
        last_day = df.iloc[-1]
        exit_price = last_day['Close']
        exit_date = last_day['Date']
        exit_idx = len(df) - 1
        
        temp_peak = max(peak_price, last_day['High'])
        temp_drawdown = (last_day['Low'] - temp_peak) / temp_peak
        final_mdd = min(trade_max_drawdown, temp_drawdown)
        
        p, h, m, d = trade_statistics(entry_price, exit_price, entry_idx, exit_idx, temp_peak, final_mdd)
        
        trades.append((
            strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'),
            entry_price, exit_price, p, h, m, d, entry_score
        ))
        
    return trades

def calculate_strategy(df, ticker, strategy_version="v02.18"):  
    """總指揮官：依序呼叫指標、訊號、交易模擬模組"""
    df = df.sort_values('Date').dropna().reset_index(drop=True)
    
    df = calculate_indicator(df)
    df = generate_signal(df)
    trades = simulate_trade(df, ticker, strategy_version)
    
    return trades, df

# ==============================
# Prt.04 歷史資料同步
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
        cursor.executemany('''
            INSERT OR REPLACE INTO daily_price (ticker, Date, Open, High, Low, Close, Volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', all_records)
        conn.commit()
        print("✅ 最新數據已成功寫入 SQLite 資料庫。")

    try:
        full_df = pd.read_sql_query("SELECT * FROM daily_price ORDER BY ticker, Date ASC", conn)
        full_df.to_csv("temp_data.csv", index=False)
        print(f"✅ 完整 5 年最新數據已成功同步匯出至 temp_data.csv (共 {len(full_df)} 筆記錄)")
    except Exception as csv_e:
        print(f"❌ 匯出完整 CSV 失敗: {csv_e}")

    cutoff_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
    cursor.execute("DELETE FROM daily_price WHERE Date < ?", (cutoff_date,))
    cursor.execute("DELETE FROM alert_log WHERE entry_date < ?", (cutoff_date,))
    conn.commit()
    
    if today.day == 1:
        conn.commit()
        conn.execute("VACUUM")
        print("🧹 每月 1 號例行保養：已執行 VACUUM 釋放硬碟空間。")

# ==============================
# Prt.05 總體績效結算模組 (Portfolio Equity 演算法)
# ==============================
def generate_performance_report(conn, version):
    try:
        df = pd.read_sql_query(
            "SELECT entry_date, exit_date, profit_pct FROM backtest_trades WHERE version = ? ORDER BY exit_date ASC", 
            conn, params=(version,)
        )
        if df.empty:
            return "================\n📈 <b>策略績效健檢</b>\n目前無足夠歷史交易資料可供統計。"
            
        total_trades = len(df)
        win_trades = df[df['profit_pct'] > 0]
        loss_trades = df[df['profit_pct'] <= 0]
        
        win_rate = (len(win_trades) / total_trades) * 100 if total_trades > 0 else 0
        
        gross_profit = win_trades['profit_pct'].sum()
        gross_loss = abs(loss_trades['profit_pct'].sum())
        profit_factor = (gross_profit / gross_loss) if gross_loss != 0 else float('inf')
        
        avg_win = win_trades['profit_pct'].mean() if not win_trades.empty else 0
        avg_loss = loss_trades['profit_pct'].mean() if not loss_trades.empty else 0
        expectancy = (avg_win * (len(win_trades) / total_trades)) + (avg_loss * (len(loss_trades) / total_trades))
        
        # --- 🎯 資金組合曲線 (Portfolio Equity Curve) 模擬 ---
        weight_per_trade = 0.10
        
        df['entry_date'] = pd.to_datetime(df['entry_date'])
        df['exit_date'] = pd.to_datetime(df['exit_date'])
        
        daily_records = []
        
        for _, row in df.iterrows():
            dr = pd.date_range(start=row['entry_date'], end=row['exit_date'], freq='D')
            hold_days = len(dr) - 1
            if hold_days > 0:
                daily_pnl = (row['profit_pct'] * weight_per_trade) / hold_days
                for d in dr[1:]:
                    daily_records.append({'date': d, 'pnl': daily_pnl})
            else:
                daily_records.append({'date': row['exit_date'], 'pnl': row['profit_pct'] * weight_per_trade})
                
        if daily_records:
            daily_df = pd.DataFrame(daily_records)
            port_daily = daily_df.groupby('date')['pnl'].sum().reset_index()
            port_daily = port_daily.sort_values('date')
            
            port_daily['equity'] = 1.0 + port_daily['pnl'].cumsum()
            port_daily['peak'] = port_daily['equity'].cummax()
            port_daily['drawdown'] = (port_daily['equity'] - port_daily['peak']) / port_daily['peak']
            
            sys_mdd = port_daily['drawdown'].min() * 100
            
            days = (port_daily['date'].max() - port_daily['date'].min()).days
            final_equity = port_daily['equity'].iloc[-1]
            if days > 0 and final_equity > 0:
                cagr = ((final_equity ** (365.25 / days)) - 1) * 100
            else:
                cagr = (final_equity - 1) * 100 
        else:
            sys_mdd = 0
            cagr = 0
        
        report = (
            f"================\n"
            f"📈 <b>策略歷史績效健檢 (System Metrics)</b>\n"
            f"• 總交易筆數: {total_trades} 筆\n"
            f"• 勝率 (Win Rate): {win_rate:.1f}%\n"
            f"• 獲利因子 (Profit Factor): {profit_factor:.2f}\n"
            f"• 期望值 (Expectancy): {expectancy*100:.2f}%\n"
            f"• 年化報酬 (CAGR): {cagr:.1f}%\n"
            f"• 系統最大回撤 (Max DD): {sys_mdd:.1f}%\n"
            f"<i>*註: CAGR與MDD採固定10%資金平鋪持倉進行每日淨值模擬</i>"
        )
        return report
    except Exception as e:
        return f"================\n⚠️ 績效統計發生錯誤: {e}"

# ==============================
# Prt.06 回測主控引擎
# ==============================
def run_0050_batch(conn):
    print("啟動 TW50 掃描與回測...")

    strategy_version = "v02.18"
    tickers = tw50_tickers
    alerts_setup = []
    alerts_trigger = []

    try:
        conn.execute("BEGIN TRANSACTION")
        
        # 回測前先清空當前版本的舊紀錄，避免重複累積失真
        conn.execute("DELETE FROM backtest_trades WHERE version = ?", (strategy_version,))

        for ticker in tickers:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT Date, Open, High, Low, Close, Volume FROM daily_price WHERE ticker = ? ORDER BY Date ASC", 
                    (ticker,)
                )
                rows = cursor.fetchall()
                if not rows:
                    continue
                
                df_ticker = pd.DataFrame(rows, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
                df_ticker['Date'] = pd.to_datetime(df_ticker['Date'])
                
                all_trades, df_processed = calculate_strategy(df_ticker, ticker, strategy_version)
                
                if not df_processed.empty:
                    last_row = df_processed.iloc[-1]
                    if last_row['Score'] >= 45:
                        entry_target = last_row['High']
                        atr20 = last_row['ATR20']
                        stop_target = entry_target - (2 * atr20)
                        risk_pct = (entry_target - stop_target) / entry_target * 100 if entry_target > 0 else 0
                        
                        alerts_setup.append(f"• {ticker} (Score: {int(last_row['Score'])}, 明日突破 {entry_target:.2f} 買進, 防守 {stop_target:.2f} [-{risk_pct:.1f}%])")
                
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

        conn.commit()
        print(f"✅ {strategy_version} 效能優化：TW50 全數標的已完成大批次寫入！")

    except Exception as main_e:
        conn.rollback()
        error_message = f"❌ 系統嚴重崩潰，資料庫已安全回滾！原因: {main_e}"
        print(error_message)
        alerts_trigger.append(f"⚠️ <b>資料庫寫入失敗</b>\n{error_message}")

    now_str = datetime.datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d %I.%M.%S %p")
    
    msg_parts = [
        f"📊 <b>{strategy_version} 台股 50 戰情室 (自動盤後更新)</b>",
        f"🕒 {now_str} 回測"
    ]

    if alerts_setup:
        try:
            alerts_setup_sorted = sorted(alerts_setup, key=lambda x: int(x.split('Score: ')[1].split(',')[0]), reverse=True)
        except Exception:
            alerts_setup_sorted = alerts_setup 

        msg_parts.append("================\n🎯 <b>滿足潛力起漲 (Score >= 45)</b>\n" + "\n".join(alerts_setup_sorted))

    if alerts_trigger:
        msg_parts.append("================\n🔥 <b>最新交易日執行回報</b>\n" + "\n".join(alerts_trigger))

    if not alerts_trigger and not alerts_setup:
        msg_parts.append("================\n盤後無新增訊號。")
        
    performance_report = generate_performance_report(conn, strategy_version)
    msg_parts.append(performance_report)

    msg_parts.append("================\n✅ 系統目前正常運作中")

    send_telegram_alert("\n".join(msg_parts))

if __name__ == "__main__":
    db_connection = init_db("tw50_strategy.db")
    sync_daily_data(db_connection)
    run_0050_batch(db_connection)
    db_connection.close()
