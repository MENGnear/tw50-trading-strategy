# ==========================================================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : TW50 Breakout Strategy
# 檔案名稱 : Tw50_main_v2.24.py
# 策略版本 : v02.24 (導入 SSOT 單一資料源架構，寫入 dashboard_signals 表)
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# ==========================================================

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
STRATEGY_VERSION = "v02.24"
DB_NAME = "tw50_strategy.db"
TAIPEI_TZ = datetime.timezone(datetime.timedelta(hours=8))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

tw50_tickers = [
    '2330.TW', '2454.TW', '2303.TW', '3711.TW', '2308.TW', '2382.TW', '2881.TW', '2891.TW', '2317.TW', '2886.TW',
    '2882.TW', '2884.TW', '1216.TW', '2002.TW', '2885.TW', '2892.TW', '2880.TW', '2883.TW', '2887.TW', '2890.TW',
    '2888.TW', '2912.TW', '2412.TW', '3045.TW', '4904.TW', '5880.TW', '2801.TW', '2889.TW', '2395.TW', '3008.TW',
    '2301.TW', '2324.TW', '2345.TW', '2356.TW', '2379.TW', '2385.TW', '2395.TW', '2408.TW', '2603.TW', '2609.TW',
    '2615.TW', '2809.TW', '3034.TW', '3231.TW', '3661.TW', '4938.TW', '5871.TW', '6669.TW', '8454.TW', '9904.TW'
]

# ==============================
# Prt.01 參數物件化 (StrategyConfig)
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
# Prt.02 SQLite 初始化與結構建立 (含 SSOT 新表)
# ==============================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # 歷史回測紀錄表 (保留 Unique Index 防重複)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backtest_trades (
            version TEXT,
            ticker TEXT,
            entry_date TEXT,
            exit_date TEXT,
            entry_price REAL,
            exit_price REAL,
            profit_pct REAL,
            UNIQUE(version, ticker, entry_date)
        )
    ''')
    # 🎯 新增：前端儀表板單一資料源專用表 (SSOT)
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
    conn.commit()
    conn.close()

# ==============================
# Prt.03 核心技術指標與動能評分引擎
# ==============================
def clean_dataframe(df):
    if df.empty: return df
    df = df.reset_index()
    if 'Datetime' in df.columns: df = df.rename(columns={'Datetime': 'Date'})
    df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
    return df

def calculate_indicators(df, config):
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

def get_latest_score_and_data(df, config):
    if len(df) < 6: return None
    today = df.iloc[-1]
    yest = df.iloc[-2]
    ma_fast_past = df['MA_Fast'].iloc[-6]

    s1 = 15 if (today['MACD_Hist'] > yest['MACD_Hist']) else 0
    s2 = 10 if (today['MA_Fast'] > 0 and today['Close'] > today['MA_Fast']) else 0
    s3 = 15 if (ma_fast_past > 0 and ((today['MA_Fast'] / ma_fast_past) - 1) > 0.01) else 0
    s4 = 10 if (today['MA_Slow'] > 0 and today['MA_Fast'] > today['MA_Slow']) else 0
    s5 = 10 if (today['V_MA'] > 0 and today['Volume'] > (today['V_MA'] * config.vol_ratio)) else 0
    
    total_score = s1 + s2 + s3 + s4 + s5
    
    return {
        'Date': today['Date'],
        'Close': today['Close'],
        'High': today['High'],
        'Score': total_score,
        's1': s1, 's2': s2, 's3': s3, 's4': s4, 's5': s5,
        'RSI_6': today['RSI_6'], 'RSI_14': today['RSI_14'], 'RSI_24': today['RSI_24'],
        'ATR': today['ATR']
    }

# ==============================
# Prt.04 Telegram 通報與結算模組
# ==============================
def send_telegram_alert(message):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id: 
        logging.warning("⚠️ 找不到 Telegram 憑證，跳過發送。")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": str(chat_id), "text": message, "parse_mode": "HTML"}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try: 
        urllib.request.urlopen(req)
        logging.info("✅ Telegram 推播發送成功！")
    except Exception as e: 
        logging.error(f"❌ Telegram 發送失敗: {e}")

def generate_performance_report(version):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            df = pd.read_sql_query("SELECT profit_pct FROM backtest_trades WHERE version = ?", conn, params=(version,))
        if df.empty: return "目前無歷史交易資料。"
        total_trades = len(df)
        win_trades = df[df['profit_pct'] > 0]
        win_rate = (len(win_trades) / total_trades) * 100 if total_trades > 0 else 0
        return f"總交易: {total_trades} 筆 | 勝率: {win_rate:.1f}%"
    except Exception as e:
        return f"績效統計錯誤: {e}"

# ==============================
# Prt.05 主控台回測與 SSOT 寫入引擎
# ==============================
def main():
    logging.info(f"🚀 啟動 TW50 掃描與回測引擎 ({STRATEGY_VERSION})...")
    init_db()
    
    all_trades = []
    dashboard_records = []
    alerts_setup = []
    
    update_time_str = datetime.datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d %H:%M:%S")

    for ticker in tw50_tickers:
        try:
            stock = yf.Ticker(ticker)
            df_raw = stock.history(period="1y")
            if df_raw.empty: continue
            
            df = clean_dataframe(df_raw)
            df = calculate_indicators(df, config)
            
            # 歷史回測狀態機 (簡化版示意，確保資料寫入與過去邏輯銜接)
            state = TradeState.IDLE
            entry_price = 0
            entry_date = None
            
            for i in range(20, len(df)):
                row = df.iloc[i]
                prev = df.iloc[i-1]
                
                if state == TradeState.IDLE:
                    # 模擬進場邏輯
                    if row['Close'] > row['MA_Fast'] and prev['MACD_Hist'] < row['MACD_Hist']:
                        state = TradeState.SETUP
                
                elif state == TradeState.SETUP:
                    entry_price = row['Close']
                    entry_date = row['Date']
                    state = TradeState.IN_POSITION
                
                elif state == TradeState.IN_POSITION:
                    # 模擬出場邏輯 (停損 8% 或 均線跌破)
                    if row['Close'] < row['MA_Fast'] or (row['Close'] - entry_price)/entry_price < -0.08:
                        profit_pct = (row['Close'] - entry_price) / entry_price * 100
                        all_trades.append((
                            STRATEGY_VERSION, ticker, str(entry_date), str(row['Date']), 
                            entry_price, row['Close'], profit_pct
                        ))
                        state = TradeState.IDLE

            # 🎯 取得今日最新狀態並寫入 SSOT Dashboard
            latest_data = get_latest_score_and_data(df, config)
            if latest_data:
                score = latest_data['Score']
                high = latest_data['High']
                atr = latest_data['ATR']
                
                stop_tgt = high - (config.atr_multiplier * atr)
                risk_pct = ((high - stop_tgt) / high * 100) if high > 0 else 0
                
                # 準備寫入 Dashboard Signals
                dashboard_records.append((
                    ticker, update_time_str, latest_data['Close'], high, score,
                    latest_data['s1'], latest_data['s2'], latest_data['s3'], latest_data['s4'], latest_data['s5'],
                    latest_data['RSI_6'], latest_data['RSI_14'], latest_data['RSI_24'], 
                    atr, stop_tgt, risk_pct
                ))
                
                # 如果分數達標，加入 TG 警報
                if score >= config.setup_score_threshold:
                    alerts_setup.append(f"🔥 <b>{ticker}</b> | 評分: {score} | 突破買進: {high:.2f} | 停損: {stop_tgt:.2f} (-{risk_pct:.1f}%)")

        except Exception as e:
            logging.warning(f"⚠️ {ticker} 處理異常: {e}")
            continue

    # ==============================
    # Prt.06 資料庫大批次寫入 (SSOT)
    # ==============================
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            
            # 1. 寫入歷史回測交易
            if all_trades:
                cursor.executemany('''
                    INSERT OR IGNORE INTO backtest_trades (
                        version, ticker, entry_date, exit_date, entry_price, exit_price, profit_pct
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', all_trades)
            
            # 2. 🎯 寫入儀表板最新訊號 (INSERT OR REPLACE 更新)
            if dashboard_records:
                cursor.executemany('''
                    INSERT OR REPLACE INTO dashboard_signals (
                        ticker, update_time, close, high, score,
                        s1, s2, s3, s4, s5, rsi_6, rsi_14, rsi_24, atr, stop_tgt, risk_pct
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', dashboard_records)
                
            logging.info(f"✅ {STRATEGY_VERSION} 資料庫更新完畢：已同步歷史交易與儀表板 SSOT 資料！")
            
    except sqlite3.Error as db_e:
        logging.error(f"❌ 資料庫寫入失敗: {db_e}")

    # ==============================
    # Prt.07 彙整發送 Telegram 通報
    # ==============================
    perf_report = generate_performance_report(STRATEGY_VERSION)
    
    msg_parts = [
        f"📊 <b>{STRATEGY_VERSION} 台股戰情室回報</b>",
        f"🕒 {update_time_str}\n================"
    ]
    
    if alerts_setup:
        msg_parts.append("🎯 <b>潛力突破 SETUP 標的</b>")
        msg_parts.extend(alerts_setup)
    else:
        msg_parts.append("🎯 今日盤面無達標突破標的。")
        
    msg_parts.append("================")
    msg_parts.append(f"📈 <b>系統已實現績效</b>\n{perf_report}")
    
    final_message = "\n".join(msg_parts)
    send_telegram_alert(final_message)

if __name__ == "__main__":
    main()
