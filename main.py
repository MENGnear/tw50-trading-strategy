# ==============================
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 專案名稱 : TW50 Breakout Strategy
# 檔案名稱 : main.py
# 策略版本 : v02.22 (企業級重構：Context Manager, Enum, Logging, SRP 訊息抽離)
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
# 功能說明：
# 1. 台股50成分股歷史資料同步
# 2. 技術指標計算 (MA、MACD、ATR)
# 3. Breakout Strategy 回測
# 4. SQLite 資料儲存與管理
# 5. Telegram 即時訊號與「策略已實現績效」通知
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐

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

# ==============================
# Prt.00 全域常數與設定 (Single Source of Truth)
# ==============================
STRATEGY_VERSION = "v02.22"
DB_NAME = "tw50_strategy.db"
TAIPEI_TZ = datetime.timezone(datetime.timedelta(hours=8))

# 日誌系統設定
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

# 狀態機列舉 (取代 Magic Strings/Booleans)
class TradeState(Enum):
    IDLE = 0
    SETUP = 1
    IN_POSITION = 2

# ==============================
# Prt.01 Telegram 通知與排版抽離
# ==============================
def send_telegram_alert(message):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        logging.warning("未設定 Telegram 金鑰，跳過推播。")
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
        logging.info("✅ Telegram 推播成功！")
    except urllib.error.URLError as net_e:
        logging.error(f"❌ Telegram 網路請求失敗: {net_e}")
    except Exception as e:
        logging.error(f"❌ Telegram 推播發生未預期錯誤: {e}")

def build_telegram_report(version, alerts_setup, alerts_trigger, perf_report):
    """SRP: 專責組裝 Telegram 訊息格式"""
    now_str = datetime.datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d %I.%M.%S %p")
    msg_parts = [
        f"📊 <b>{version} 台股 50 戰情室 (自動盤後更新)</b>",
        f"🕒 {now_str} 回測"
    ]

    if alerts_setup:
        try:
            alerts_setup_sorted = sorted(alerts_setup, key=lambda x: int(x.split('Score: ')[1].split(',')[0]), reverse=True)
        except Exception:
            alerts_setup_sorted = alerts_setup 
        msg_parts.append("================\n🎯 <b>滿足潛力起漲 (近期 Setup 有效)</b>\n" + "\n".join(alerts_setup_sorted))

    if alerts_trigger:
        msg_parts.append("================\n🔥 <b>最新交易日執行回報</b>\n" + "\n".join(alerts_trigger))

    if not alerts_trigger and not alerts_setup:
        msg_parts.append("================\n盤後無新增訊號。")
        
    msg_parts.append(perf_report)
    msg_parts.append("================\n✅ 系統目前正常運作中")
    
    return "\n".join(msg_parts)

# ==============================
# Prt.02 SQLite 資料庫管理 (導入 Context Manager)
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
            
            try:
                cursor.execute("ALTER TABLE backtest_trades ADD COLUMN trade_max_drawdown_pct REAL")
            except sqlite3.OperationalError:
                pass
                
    except sqlite3.Error as db_e:
        logging.error(f"資料庫初始化失敗: {db_e}")

# ==============================
# Prt.03 核心策略模組 (v02.22)
# ==============================
def calculate_indicator(df):
    """階段一：計算所有底層技術指標"""
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['V_MA5'] = df['Volume'].rolling(5).mean()

    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = ema12 - ema26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['DEA']
    
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
    """階段二：依據指標計算策略訊號與評分 (語意化重構)"""
    score_macd_trend = (df['MACD_Hist'] > df['MACD_Hist'].shift(1)).astype(int) * 15 
    score_ma20_cross = (df['Close'] > df['MA20']).astype(int) * 10                    
    score_ma20_slope = ((df['MA20'] / df['MA20'].shift(5) - 1) > 0.01).astype(int) * 15 
    score_ma60_trend = (df['MA20'] > df['MA60']).astype(int) * 10                      
    score_volume_burst = (df['Volume'] > df['V_MA5'] * 1.3).astype(int) * 10            
    
    df['Score'] = sum([
        score_macd_trend,
        score_ma20_cross,
        score_ma20_slope,
        score_ma60_trend,
        score_volume_burst
    ])
    return df

def trade_statistics(entry_price, exit_price, entry_idx, exit_idx, peak_price, trade_max_drawdown):
    """階段三：計算單筆交易的績效統計數據"""
    profit_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0
    holding_bars = exit_idx - entry_idx
    max_p = (peak_price - entry_price) / entry_price if entry_price > 0 else 0
    trade_max_drawdown_pct = trade_max_drawdown * 100
    return profit_pct, holding_bars, max_p, trade_max_drawdown_pct

def simulate_trade(df, ticker, strategy_version):
    """階段四：無未來函數之事件驅動狀態機 (導入 Enum)"""
    trades = []
    
    # 狀態機變數初始化
    state = TradeState.IDLE
    setup_high = 0.0
    setup_low = 0.0
    setup_age = 0
    entry_score = 0
    
    entry_price = 0.0
    entry_date = None
    entry_idx = 0
    peak_price = 0.0
    trade_max_drawdown = 0.0
    stop_loss_price = 0.0
    pending_exit = False 

    for i in range(65, len(df)):
        curr_bar = df.iloc[i]
        prev_bar = df.iloc[i-1]
        
        if pd.isna(curr_bar['ATR20']):
            continue
            
        if state == TradeState.IN_POSITION:
            # 1. 執行跨日預定出場
            if pending_exit:
                exit_price = curr_bar['Open']
                exit_date = curr_bar['Date']
                p, h, m, d = trade_statistics(entry_price, exit_price, entry_idx, i, peak_price, trade_max_drawdown)
                trades.append((strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'), entry_price, exit_price, p, h, m, d, entry_score))
                state = TradeState.IDLE
                pending_exit = False
                continue
                
            # 2. 更新持倉指標
            peak_price = max(peak_price, curr_bar['High'])
            trade_max_drawdown = min(trade_max_drawdown, (curr_bar['Low'] - peak_price) / peak_price)
            
            # 3. 盤中觸發動態停損
            if curr_bar['Low'] <= stop_loss_price:
                exit_price = min(curr_bar['Open'], stop_loss_price)
                exit_date = curr_bar['Date']
                p, h, m, d = trade_statistics(entry_price, exit_price, entry_idx, i, peak_price, trade_max_drawdown)
                trades.append((strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'), entry_price, exit_price, p, h, m, d, entry_score))
                state = TradeState.IDLE
                continue
                
            # 4. 盤後檢查出場條件
            if curr_bar['Close'] < curr_bar['MA20']:
                pending_exit = True
                
        else:
            # 尚未進場，處理 Setup 與進場邏輯
            if state == TradeState.SETUP and curr_bar['High'] > setup_high:
                # 突破觸發進場
                state = TradeState.IN_POSITION
                entry_price = max(curr_bar['Open'], setup_high)
                entry_date = curr_bar['Date']
                entry_idx = i
                peak_price = max(entry_price, curr_bar['High'])
                trade_max_drawdown = min(0.0, (curr_bar['Low'] - peak_price) / peak_price)
                stop_loss_price = entry_price - (2 * prev_bar['ATR20'])
                
                if curr_bar['Low'] <= stop_loss_price:
                    exit_price = stop_loss_price
                    exit_date = curr_bar['Date']
                    p, h, m, d = trade_statistics(entry_price, exit_price, entry_idx, i, peak_price, trade_max_drawdown)
                    trades.append((strategy_version, ticker, entry_date.strftime('%Y-%m-%d'), exit_date.strftime('%Y-%m-%d'), entry_price, exit_price, p, h, m, d, entry_score))
                    state = TradeState.IDLE
                    continue
                    
                if curr_bar['Close'] < curr_bar['MA20']:
                    pending_exit = True
            else:
                # 處理 Setup 狀態流轉
                if state == TradeState.SETUP:
                    setup_age += 1
                    if curr_bar['Low'] < setup_low:
                        state = TradeState.IDLE
                    elif setup_age > 5:
                        state = TradeState.IDLE
                    elif curr_bar['Score'] >= 45:
                        setup_high = max(setup_high, curr_bar['High'])
                            
                # 產生新 Setup
                if state == TradeState.IDLE and curr_bar['Score'] >= 45 and prev_bar['Score'] < 45:
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
        
    active_setup_info = None
    if state == TradeState.SETUP:
        last_bar = df.iloc[-1]
        atr20 = last_bar['ATR20']
        stop_target = setup_high - (2 * atr20)
        risk_pct = (setup_high - stop_target) / setup_high * 100 if setup_high > 0 else 0
        active_setup_info = {
            'ticker': ticker,
            'score': int(last_bar['Score']),
            'entry_target': setup_high,
            'stop_target': stop_target,
            'risk_pct': risk_pct
        }
        
    return trades, df, active_setup_info

def calculate_strategy(df, ticker, strategy_version=STRATEGY_VERSION):  
    """總指揮官：依序呼叫指標、訊號、交易模擬模組"""
    df = df.sort_values('Date').dropna().reset_index(drop=True)
    df = calculate_indicator(df)
    df = generate_signal(df)
    trades, df, active_setup_info = simulate_trade(df, ticker, strategy_version)
    return trades, df, active_setup_info

# ==============================
# Prt.04 歷史資料同步
# ==============================
def sync_daily_data(db_name=DB_NAME):
    today = datetime.datetime.now(TAIPEI_TZ)
    force_reset = os.environ.get('FORCE_RESET', 'false').lower() == 'true'
    
    try:
        with sqlite3.connect(db_name) as conn:
            cursor = conn.cursor()
            
            if force_reset:
                logging.warning("⚠️ 觸發強制重設：清空 daily_price 表格，準備重抓 5 年資料！")
                cursor.execute("DELETE FROM daily_price")
                last_date = None
            else:
                cursor.execute("SELECT MAX(Date) FROM daily_price")
                last_date = cursor.fetchone()[0]

            if last_date:
                start_date_obj = datetime.datetime.strptime(last_date, '%Y-%m-%d') - datetime.timedelta(days=2)
                start_date = start_date_obj.strftime('%Y-%m-%d')
                logging.info(f"📊 增量更新，抓取區間: {start_date} 至今...")
            else:
                start_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
                logging.warning(f"⚠️ 初次下載/強制重置，抓取區間: {start_date} 至今...")

            end_date = (today + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            
            # yfinance 取資料
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
                    logging.error(f"❌ 整理 {ticker} 錯誤: {e}")

            if all_records:
                cursor.executemany('''
                    INSERT OR REPLACE INTO daily_price (ticker, Date, Open, High, Low, Close, Volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', all_records)
                logging.info("✅ 最新數據已成功寫入 SQLite 資料庫。")

            try:
                full_df = pd.read_sql_query("SELECT * FROM daily_price ORDER BY ticker, Date ASC", conn)
                full_df.to_csv("temp_data.csv", index=False)
                logging.info(f"✅ 完整 5 年最新數據已成功同步匯出至 temp_data.csv (共 {len(full_df)} 筆記錄)")
            except Exception as csv_e:
                logging.error(f"❌ 匯出完整 CSV 失敗: {csv_e}")

            cutoff_date = (today - datetime.timedelta(days=1825)).strftime('%Y-%m-%d')
            cursor.execute("DELETE FROM daily_price WHERE Date < ?", (cutoff_date,))
            
            if today.day == 1:
                conn.execute("VACUUM")
                logging.info("🧹 每月 1 號例行保養：已執行 VACUUM 釋放硬碟空間。")
                
    except sqlite3.Error as db_e:
        logging.error(f"資料庫同步操作失敗: {db_e}")

# ==============================
# Prt.05 總體績效結算模組
# ==============================
def generate_performance_report(version, db_name=DB_NAME):
    try:
        with sqlite3.connect(db_name) as conn:
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
        
        # --- 🎯 已實現交易淨值 (Sequential Trade Equity) ---
        weight_per_trade = 0.10
        
        df['exit_date'] = pd.to_datetime(df['exit_date'])
        df['realized_pnl'] = df['profit_pct'] * weight_per_trade
        df['equity'] = 1.0 + df['realized_pnl'].cumsum()
        
        df['peak'] = df['equity'].cummax()
        df['drawdown'] = (df['equity'] - df['peak']) / df['peak']
        
        sys_mdd = df['drawdown'].min() * 100 if not df.empty else 0
        
        days = (df['exit_date'].max() - df['exit_date'].min()).days if not df.empty else 0
        final_equity = df['equity'].iloc[-1] if not df.empty else 1.0
        
        if days > 0 and final_equity > 0:
            cagr = ((final_equity ** (365.25 / days)) - 1) * 100
        else:
            cagr = (final_equity - 1) * 100 
        
        report = (
            f"================\n"
            f"📈 <b>策略已實現績效 (Trade-Based Metrics)</b>\n"
            f"• 總交易筆數: {total_trades} 筆\n"
            f"• 勝率 (Win Rate): {win_rate:.1f}%\n"
            f"• 獲利因子 (Profit Factor): {profit_factor:.2f}\n"
            f"• 期望值 (Expectancy): {expectancy*100:.2f}%\n"
            f"• 年化報酬 (CAGR): {cagr:.1f}%\n"
            f"• 系統最大回撤 (Max DD): {sys_mdd:.1f}%\n"
            f"<i>*註: 採用 Sequential Trade Equity 算法，假設每筆訊號固定投入 10% 資金，依出場日結算已實現損益。</i>"
        )
        return report
    except sqlite3.Error as db_e:
        return f"================\n⚠️ 績效統計資料庫錯誤: {db_e}"
    except Exception as e:
        return f"================\n⚠️ 績效統計發生未預期錯誤: {e}"

# ==============================
# Prt.06 回測主控引擎
# ==============================
def run_0050_batch(db_name=DB_NAME, version=STRATEGY_VERSION):
    logging.info("啟動 TW50 掃描與回測...")

    alerts_setup = []
    alerts_trigger = []

    try:
        with sqlite3.connect(db_name) as conn:
            cursor = conn.cursor()
            # 確保交易單一來源與防止重複寫入
            cursor.execute("DELETE FROM backtest_trades WHERE version = ?", (version,))

            for ticker in tw50_tickers:
                try:
                    cursor.execute(
                        "SELECT Date, Open, High, Low, Close, Volume FROM daily_price WHERE ticker = ? ORDER BY Date ASC", 
                        (ticker,)
                    )
                    rows = cursor.fetchall()
                    if not rows:
                        continue
                    
                    df_ticker = pd.DataFrame(rows, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
                    df_ticker['Date'] = pd.to_datetime(df_ticker['Date'])
                    
                    all_trades, df_processed, active_setup_info = calculate_strategy(df_ticker, ticker, version)
                    
                    if active_setup_info:
                        alerts_setup.append(
                            f"• {active_setup_info['ticker']} (Score: {active_setup_info['score']}, 明日突破 {active_setup_info['entry_target']:.2f} 買進, 防守 {active_setup_info['stop_target']:.2f} [-{active_setup_info['risk_pct']:.1f}%])"
                        )
                    
                    if all_trades:
                        cursor.executemany('''
                            INSERT INTO backtest_trades (
                                version, ticker, entry_date, exit_date, entry_price, exit_price, 
                                profit_pct, holding_bars, max_profit_pct, trade_max_drawdown_pct, entry_score
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', all_trades)              
                   
                except Exception as inner_e:
                    logging.warning(f"⚠️ {ticker} 處理異常，已跳過: {inner_e}")
                    continue

            logging.info(f"✅ {version} 效能優化：TW50 全數標的已完成大批次寫入！")

    except sqlite3.Error as db_e:
        error_message = f"❌ 系統嚴重崩潰，資料庫寫入失敗！原因: {db_e}"
        logging.error(error_message)
        alerts_trigger.append(f"⚠️ <b>資料庫寫入失敗</b>\n{error_message}")
    except Exception as main_e:
        error_message = f"❌ 系統發生未預期嚴重錯誤！原因: {main_e}"
        logging.error(error_message)
        alerts_trigger.append(f"⚠️ <b>系統嚴重錯誤</b>\n{error_message}")

    # 組裝與發送 Telegram 報告
    perf_report = generate_performance_report(version, db_name)
    final_message = build_telegram_report(version, alerts_setup, alerts_trigger, perf_report)
    send_telegram_alert(final_message)

if __name__ == "__main__":
    init_db(DB_NAME)
    sync_daily_data(DB_NAME)
    run_0050_batch(DB_NAME, STRATEGY_VERSION)
