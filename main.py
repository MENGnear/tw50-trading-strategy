# ==============================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : TW50 Breakout Strategy
# 檔案名稱 : Tw50_main_v02.26.py
# 策略版本 : v02.26 (自動推播雙重排序機制與格式淨化)
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# ==============================

import pandas as pd
import numpy as np
import yfinance as yf
import sqlite3
import datetime
import os
import urllib.request
import urllib.error
import json
import logging
from enum import Enum
from dataclasses import dataclass

# ==============================
# Prt.00 全域常數與設定
# ==============================
STRATEGY_VERSION = "v02.26"
DB_NAME = "tw50_strategy.db"
TAIPEI_TZ = datetime.timezone(datetime.timedelta(hours=8))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

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

# ==============================
# Prt.01 策略參數配置物件
# ==============================
@dataclass
class StrategyConfig:
    ma_fast: int = 20
    ma_slow: int = 60
    vma_period: int = 5
    vol_ratio: float = 1.3
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 20
    atr_multiplier: float = 2.0
    setup_score_threshold: int = 45
    max_setup_days: int = 5
    capital_weight_per_trade: float = 0.10

config = StrategyConfig()

class TradeState(Enum):
    IDLE = 0
    SETUP = 1
    IN_POSITION = 2

# ==============================
# Prt.02 SQLite 資料庫管理 (含 11 維度回測表 & SSOT 表)
# ==============================
def init_db(db_name=DB_NAME):
    try:
        with sqlite3.connect(db_name) as conn:
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
            cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_uniq ON backtest_trades(version, ticker, entry_date)')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dashboard_signals (
                    ticker TEXT PRIMARY KEY,
                    update_time TEXT,
                    close REAL,
                    high REAL,
                    score INTEGER,
                    s1 INTEGER,
                    s2 INTEGER,
                    s3 INTEGER,
                    s4 INTEGER,
                    s5 INTEGER,
                    rsi_6 REAL,
                    rsi_14 REAL,
                    rsi_24 REAL,
                    atr REAL,
                    stop_tgt REAL,
                    risk_pct REAL
                )
            ''')
    except sqlite3.Error as db_e:
        logging.error(f"資料庫初始化失敗: {db_e}")

# ==============================
# Prt.03 核心策略模組與指標計算
# ==============================
def calculate_indicator(df, config: StrategyConfig):
    df['MA_Fast'] = df['Close'].rolling(config.ma_fast).mean().fillna(0)
    df['MA_Slow'] = df['Close'].rolling(config.ma_slow).mean().fillna(0)
    df['V_MA'] = df['Volume'].rolling(config.vma_period).mean().fillna(0)

    ema_fast = df['Close'].ewm(span=config.macd_fast, adjust=False).mean()
    ema_slow = df['Close'].ewm(span=config.macd_slow, adjust=False).mean()
    df['DIF'] = ema_fast - ema_slow
    df['DEA'] = df['DIF'].ewm(span=config.macd_signal, adjust=False).mean()
    df['MACD_Hist'] = (df['DIF'] - df['DEA']).fillna(0)
    
    df['Prev_Close'] = df['Close'].shift(1).fillna(df['Close'])
    df['TR'] = np.maximum(
        df['High'] - df['Low'],
        np.maximum(abs(df['High'] - df['Prev_Close']), abs(df['Low'] - df['Prev_Close']))
    )
    df['ATR'] = df['TR'].rolling(window=config.atr_period).mean().fillna(0)

    df['RSI_6'], df['RSI_14'], df['RSI_24'] = 50.0, 50.0, 50.0
    if len(df) >= 24:
        delta = df['Close'].diff()
        up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
        for p in [6, 14, 24]:
            ema_up = up.ewm(com=p-1, adjust=False).mean()
            ema_down = down.ewm(com=p-1, adjust=False).mean()
            df[f'RSI_{p}'] = 100 - (100 / (1 + ema_up / ema_down.replace(0, 1e-9)))
            
    return df

def generate_signal(df, config: StrategyConfig):
    s1 = (df['MACD_Hist'] > df['MACD_Hist'].shift(1)).astype(int) * 15 
    s2 = (df['Close'] > df['MA_Fast']).astype(int) * 10                    
    s3 = ((df['MA_Fast'] / df['MA_Fast'].shift(5) - 1) > 0.01).astype(int) * 15 
    s4 = (df['MA_Fast'] > df['MA_Slow']).astype(int) * 10                      
    s5 = (df['Volume'] > df['V_MA'] * config.vol_ratio).astype(int) * 10            
    
    df['Score'] = s1 + s2 + s3 + s4 + s5
    df['s1'], df['s2'], df['s3'], df['s4'], df['s5'] = s1, s2, s3, s4, s5
    return df

def trade_statistics(entry_price, exit_price, entry_idx, exit_idx, peak_price, trade_max_drawdown):
    profit_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0
    holding_bars = exit_idx - entry_idx
    max_p = (peak_price - entry_price) / entry_price if entry_price > 0 else 0
    trade_max_drawdown_pct = trade_max_drawdown * 100
    return profit_pct, holding_bars, max_p, trade_max_drawdown_pct

def simulate_trade(df, ticker, config: StrategyConfig, strategy_version):
    trades = []
    state = TradeState.IDLE
    setup_high, setup_low, setup_age, entry_score = 0.0, 0.0, 0, 0
    entry_price, entry_idx, peak_price, trade_max_drawdown, stop_loss_price = 0.0, 0, 0.0, 0.0, 0.0
    entry_date = None
    pending_exit = False 

    for i in range(65, len(df)):
        curr_bar = df.iloc[i]
        prev_bar = df.iloc[i-1]
        
        if pd.isna(curr_bar['ATR']): continue
            
        if state == TradeState.IN_POSITION:
            if pending_exit:
                exit_price = curr_bar['Open']
                exit_date = curr_bar['Date']
                p, h, m, d = trade_statistics(entry_price, exit_price, entry_idx, i, peak_price, trade_max_drawdown)
                trades.append((strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'), entry_price, exit_price, p, h, m, d, entry_score))
                state = TradeState.IDLE
                pending_exit = False
                continue
                
            peak_price = max(peak_price, curr_bar['High'])
            trade_max_drawdown = min(trade_max_drawdown, (curr_bar['Low'] - peak_price) / peak_price)
            
            if curr_bar['Low'] <= stop_loss_price:
                exit_price = min(curr_bar['Open'], stop_loss_price)
                exit_date = curr_bar['Date']
                p, h, m, d = trade_statistics(entry_price, exit_price, entry_idx, i, peak_price, trade_max_drawdown)
                trades.append((strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'), entry_price, exit_price, p, h, m, d, entry_score))
                state = TradeState.IDLE
                continue
                
            if curr_bar['Close'] < curr_bar['MA_Fast']:
                pending_exit = True
                
        else:
            if state == TradeState.SETUP and curr_bar['High'] > setup_high:
                state = TradeState.IN_POSITION
                entry_price = max(curr_bar['Open'], setup_high)
                entry_date = curr_bar['Date']
                entry_idx = i
                peak_price = max(entry_price, curr_bar['High'])
                trade_max_drawdown = min(0.0, (curr_bar['Low'] - peak_price) / peak_price)
                stop_loss_price = entry_price - (config.atr_multiplier * prev_bar['ATR'])
                
                if curr_bar['Low'] <= stop_loss_price:
                    exit_price = stop_loss_price
                    exit_date = curr_bar['Date']
                    p, h, m, d = trade_statistics(entry_price, exit_price, entry_idx, i, peak_price, trade_max_drawdown)
                    trades.append((strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'), entry_price, exit_price, p, h, m, d, entry_score))
                    state = TradeState.IDLE
                    continue
                    
                if curr_bar['Close'] < curr_bar['MA_Fast']: pending_exit = True
            else:
                if state == TradeState.SETUP:
                    setup_age += 1
                    if curr_bar['Low'] < setup_low or setup_age > config.max_setup_days:
                        state = TradeState.IDLE
                    elif curr_bar['Score'] >= config.setup_score_threshold:
                        setup_high = max(setup_high, curr_bar['High'])
                            
                if state == TradeState.IDLE and curr_bar['Score'] >= config.setup_score_threshold and prev_bar['Score'] < config.setup_score_threshold:
                    state = TradeState.SETUP
                    setup_high = curr_bar['High']
                    setup_low = curr_bar['Low']
                    setup_age = 0 
                    entry_score = curr_bar['Score']
                    
    if state == TradeState.IN_POSITION:
        last_bar = df.iloc[-1]
        exit_price = last_bar['Close']
        exit_date = last_bar['Date']
        p, h, m, d = trade_statistics(entry_price, exit_price, entry_idx, len(df)-1, peak_price, trade_max_drawdown)
        trades.append((strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'), entry_price, exit_price, p, h, m, d, entry_score))
        
    return trades, df

def calculate_strategy(df, ticker, config: StrategyConfig, strategy_version=STRATEGY_VERSION):  
    df = df.sort_values('Date').dropna().reset_index(drop=True)
    df = calculate_indicator(df, config)
    df = generate_signal(df, config)
    trades, df = simulate_trade(df, ticker, config, strategy_version)
    return trades, df

# ==============================
# Prt.04 歷史資料同步
# ==============================
def sync_daily_data(db_name=DB_NAME):
    today = datetime.datetime.now(TAIPEI_TZ)
    try:
        with sqlite3.connect(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(Date) FROM daily_price")
            last_date = cursor.fetchone()[0]

            if last_date:
                start_date = (datetime.datetime.strptime(last_date, '%Y-%m-%d') - datetime.timedelta(days=2)).strftime('%Y-%m-%d')
            else:
                start_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')

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
                        df_to_db['Date'] = pd.to_datetime(df_to_db['Date']).dt.strftime('%Y-%m-%d')
                        df_to_db.insert(0, 'ticker', ticker)
                        all_records.extend(df_to_db.values.tolist())
                except: pass

            if all_records:
                cursor.executemany('''
                    INSERT OR REPLACE INTO daily_price (ticker, Date, Open, High, Low, Close, Volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', all_records)
                
            cutoff_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
            cursor.execute("DELETE FROM daily_price WHERE Date < ?", (cutoff_date,))
            
    except sqlite3.Error as db_e:
        logging.error(f"資料庫同步操作失敗: {db_e}")

# ==============================
# Prt.05 Telegram 發送引擎 
# ==============================
def send_telegram_alert(message):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id: return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try: urllib.request.urlopen(req, timeout=15)
    except: pass

def build_telegram_report(version, alerts_setup):
    now_str = datetime.datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d %H:%M:%S")
    msg_parts = [
        f"📊 <b>{version} 台股戰情室回報</b>",
        f"🕒 {now_str}"
    ]

    if alerts_setup:
        msg_parts.append("================")
        msg_parts.append("🎯 <b>潛力突破 SETUP 標的</b>")
        msg_parts.append("\n".join(alerts_setup))
    else:
        msg_parts.append("================\n🎯 盤面無達標突破標的。")

    msg_parts.append("================")
    msg_parts.append("✅ 系統監控中")
    return "\n".join(msg_parts)

# ==============================
# Prt.06 回測主控與 SSOT 寫入引擎
# ==============================
def run_0050_batch(db_name=DB_NAME, version=STRATEGY_VERSION):
    logging.info("啟動 TW50 掃描與回測...")
    config = StrategyConfig()
    
    raw_alerts = [] # 用於雙重排序的中繼字典陣列
    dashboard_records = []
    update_time_str = datetime.datetime.now(TAIPEI_TZ).strftime("%H:%M:%S %m/%d/%Y")

    try:
        with sqlite3.connect(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM backtest_trades WHERE version = ?", (version,))

            for ticker in tw50_tickers:
                try:
                    cursor.execute(
                        "SELECT Date, Open, High, Low, Close, Volume FROM daily_price WHERE ticker = ? ORDER BY Date ASC", 
                        (ticker,)
                    )
                    rows = cursor.fetchall()
                    if not rows: continue
                    
                    df_ticker = pd.DataFrame(rows, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
                    df_ticker['Date'] = pd.to_datetime(df_ticker['Date'])
                    
                    all_trades, df_processed = calculate_strategy(df_ticker, ticker, config, version)
                    
                    last_bar = df_processed.iloc[-1]
                    score = int(last_bar.get('Score', 0))
                    price = last_bar.get('Close', 0.0)
                    high = last_bar.get('High', 0.0)
                    atr = last_bar.get('ATR', 0.0)
                    stop_target = high - (config.atr_multiplier * atr)
                    risk_pct = ((high - stop_target) / high * 100) if high > 0 else 0

                    dashboard_records.append((
                        ticker, update_time_str, price, high, score,
                        int(last_bar.get('s1', 0)), int(last_bar.get('s2', 0)), int(last_bar.get('s3', 0)), int(last_bar.get('s4', 0)), int(last_bar.get('s5', 0)),
                        last_bar.get('RSI_6', 50), last_bar.get('RSI_14', 50), last_bar.get('RSI_24', 50),
                        atr, stop_target, risk_pct
                    ))

                    if score >= config.setup_score_threshold:
                        # 🎯 放入字典等待雙重排序
                        raw_alerts.append({
                            'ticker': ticker, 'score': score, 'close': price,
                            'high': high, 'stop_target': stop_target, 'risk_pct': risk_pct
                        })
                    
                    if all_trades:
                        cursor.executemany('''
                            INSERT OR REPLACE INTO backtest_trades (
                                version, ticker, entry_date, exit_date, entry_price, exit_price, 
                                profit_pct, holding_bars, max_profit_pct, trade_max_drawdown_pct, entry_score
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', all_trades)              
                   
                except Exception as inner_e: continue

            if dashboard_records:
                cursor.executemany('''
                    INSERT OR REPLACE INTO dashboard_signals (
                        ticker, update_time, close, high, score,
                        s1, s2, s3, s4, s5, rsi_6, rsi_14, rsi_24, atr, stop_tgt, risk_pct
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', dashboard_records)

    except Exception as main_e:
        logging.error(f"系統錯誤: {main_e}")

    # 🎯 實作雙重排序與淨化 TG 字串
    alerts_setup = []
    if raw_alerts:
        # 依分數與收盤價降冪排序
        raw_alerts.sort(key=lambda x: (x['score'], x['close']), reverse=True)
        for a in raw_alerts:
            tk_clean = a['ticker'].split(".")[0]
            rp_abs = abs(a['risk_pct'])
            alerts_setup.append(f"{tk_clean} |📊{a['score']} | 🟢{a['high']:.2f} | 🔴{a['stop_target']:.2f} ({rp_abs:.1f}%)")

    final_message = build_telegram_report(version, alerts_setup)
    send_telegram_alert(final_message)

if __name__ == "__main__":
    init_db(DB_NAME)
    sync_daily_data(DB_NAME)
    run_0050_batch(DB_NAME, STRATEGY_VERSION)
