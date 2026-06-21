# =============================================================================
# 檔名：app_v02_10.py
# 版次：v02.10
# 備註：
# 1. 修正狀態鎖定，導入 setup_active 邊緣觸發機制 (Edge Trigger)。
# 2. 修正 Buy Stop 邏輯為大於 (>) 而非大於等於 (>=)。
# 3. 推播文字同步，區分「候選 Setup」與「實際 Trigger」。
# 4. 使用 next(generator, None) 安全抓取 latest_trading_day 資料。
# 5. 資料庫升級採用 PRAGMA table_info 進行防呆 Schema Migration。
# 6. Drawdown 欄位更名並直接儲存百分比數值 (trade_max_drawdown_pct)。
# 7. 全面落實 Prt.01 ~ Prt.09 規範。
# =============================================================================

import sqlite3
import datetime
import requests
import pandas as pd
import yfinance as yf
import numpy as np

# ====== 1. 系統全域設定 ======
APP_VERSION = "v02.10"
TG_BOT_TOKEN = "YOUR_TG_BOT_TOKEN"
TG_CHAT_ID = "YOUR_TG_CHAT_ID"

# ====== 2. 推播模組 (Prt.02 Telegram HTML 格式) ======
def send_telegram_message(message: str):
    """
    發送 Telegram 推播，嚴格採用 HTML 解析模式，避免特殊符號導致錯誤
    """
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"推播失敗: {e}")

# ====== 3. 資料庫架構與遷移模組 (Prt.01 Schema Migration) ======
def init_db():
    conn = sqlite3.connect('backtest_v02.db')
    cursor = conn.cursor()
    
    # 建立主表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backtest_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id TEXT,
            entry_date TEXT,
            entry_price REAL,
            signal_day_high REAL,
            entry_score REAL,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # 欄位擴充檢查 (Schema Migration)
    cursor.execute("PRAGMA table_info(backtest_trades)")
    existing_columns = [col[1] for col in cursor.fetchall()]
    
    # Prt.06 Drawdown 儲存格式修正
    if 'trade_max_drawdown_pct' not in existing_columns:
        cursor.execute("ALTER TABLE backtest_trades ADD COLUMN trade_max_drawdown_pct REAL")
    
    if 'exit_date' not in existing_columns:
        cursor.execute("ALTER TABLE backtest_trades ADD COLUMN exit_date TEXT")
        
    if 'exit_price' not in existing_columns:
        cursor.execute("ALTER TABLE backtest_trades ADD COLUMN exit_price REAL")
        
    conn.commit()
    return conn, cursor

# ====== 4. 資料獲取與指標運算模組 ======
def fetch_and_calculate(stock_id: str):
    df = yf.Ticker(stock_id).history(period="1y")
    if df.empty or len(df) < 65:
        return None
    
    df = df.reset_index()
    df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
    
    # 模擬分數計算 (以 RSI 壓縮或自訂邏輯替代)
    # 此處保留您原本的 Score 概念，隨機生成作為架構演示
    np.random.seed(42) # 測試用
    df['Score'] = np.random.uniform(20, 80, size=len(df))
    df['MA20'] = df['Close'].rolling(window=20).mean()
    
    return df

# ====== 5. 核心回測引擎 (Prt.07, Prt.08, Prt.05, Prt.06) ======
def run_backtest_engine(stock_id: str, df: pd.DataFrame, conn, cursor):
    in_position = False
    setup_active = False
    signal_day_high = 0.0
    entry_score = 0.0
    entry_price = 0.0
    peak_price = 0.0
    trade_max_drawdown = 0.0
    
    # 清理該檔股票舊回測紀錄
    cursor.execute("DELETE FROM backtest_trades WHERE stock_id = ?", (stock_id,))
    
    # Prt.04 命名規範：使用 latest_trading_day
    latest_trading_day = df.iloc[-1]['Date']
    
    for i in range(65, len(df)-1):
        yesterday = df.iloc[i-1]
        today = df.iloc[i]
        tomorrow = df.iloc[i+1]
        
        # 尚未持有部位
        if not in_position:
            
            # Prt.07 Edge Trigger 機制：建立 Setup (只觸發一次)
            if (
                not setup_active 
                and today['Score'] >= 45 
                and yesterday['Score'] < 45
            ):
                setup_active = True
                signal_day_high = today['High']
                entry_score = today['Score']
                
                # 若今天剛好是最新交易日，準備推播第一層
                if today['Date'] == latest_trading_day:
                    msg = (
                        f"<b>【候選 Setup】</b>\n"
                        f"🚀 {stock_id}\n"
                        f"首日達標\n"
                        f"Score = {entry_score:.1f}\n"
                        f"明日突破 {signal_day_high:.2f} 買進"
                    )
                    send_telegram_message(msg)

            # 持續等待突破
            if setup_active:
                
                # Prt.08 Buy Stop 定義：必須「大於」前高，不是碰觸(>=)
                if tomorrow['High'] > signal_day_high:
                    in_position = True
                    setup_active = False  # 任務完成，關閉 Setup 狀態
                    
                    # Prt.05 真實成交價模型 (跳空開高以開盤價成交)
                    entry_price = max(tomorrow['Open'], signal_day_high)
                    entry_date = tomorrow['Date']
                    
                    peak_price = entry_price
                    trade_max_drawdown = 0.0
                    
                    # 寫入資料庫
                    cursor.execute('''
                        INSERT INTO backtest_trades 
                        (stock_id, entry_date, entry_price, signal_day_high, entry_score, is_active)
                        VALUES (?, ?, ?, ?, ?, 1)
                    ''', (stock_id, entry_date, entry_price, signal_day_high, entry_score))
                    
                # 這裡保留未來擴充：Setup 失效機制 (例如 today['Score'] < 20 則 setup_active = False)
        
        # 已經持有部位，計算 Drawdown 與出場
        else:
            current_low = today['Low']
            current_high = today['High']
            
            if current_high > peak_price:
                peak_price = current_high
                
            dd = (current_low - peak_price) / peak_price
            if dd < trade_max_drawdown:
                trade_max_drawdown = dd
                
            # 假設出場條件 (例如跌破 20MA)
            if today['Close'] < today['MA20']:
                in_position = False
                
                # Prt.06 Drawdown 百分比真實儲存 (-0.135 -> -13.5)
                trade_max_drawdown_pct = trade_max_drawdown * 100
                exit_price = today['Close']
                exit_date = today['Date']
                
                cursor.execute('''
                    UPDATE backtest_trades
                    SET exit_date = ?, exit_price = ?, trade_max_drawdown_pct = ?, is_active = 0
                    WHERE stock_id = ? AND is_active = 1
                ''', (exit_date, exit_price, trade_max_drawdown_pct, stock_id))
                
    conn.commit()

# ====== 6. 每日執行與推播模組 ======
def daily_job():
    conn, cursor = init_db()
    
    # 範例監控清單
    watch_list = ["2330.TW", "2454.TW", "2317.TW"]
    
    for stock_id in watch_list:
        df = fetch_and_calculate(stock_id)
        if df is not None:
            # 執行回測與最新日判斷
            run_backtest_engine(stock_id, df, conn, cursor)
            
            # Prt.04 取得最新交易日
            latest_trading_day = df.iloc[-1]['Date']
            
            # Prt.09 抓取最新一日的進場紀錄 (Trigger 推播)
            cursor.execute('''
                SELECT entry_price FROM backtest_trades 
                WHERE stock_id = ? AND entry_date = ?
            ''', (stock_id, latest_trading_day))
            trades = cursor.fetchall()
            
            # 問題四修正：使用 next(generator, None) 安全抓取
            entered_trade = next(
                (t for t in trades), 
                None
            )
            
            if entered_trade:
                real_entry_price = entered_trade[0]
                ma20_defense = df.iloc[-1]['MA20']
                
                msg = (
                    f"<b>【正式 Trigger】</b>\n"
                    f"✅ {stock_id}\n"
                    f"今日突破進場\n"
                    f"成交價 {real_entry_price:.2f}\n"
                    f"防守月線 {ma20_defense:.2f}"
                )
                send_telegram_message(msg)

    # Prt.03 每月 1 號固定保養資料庫 (VACUUM)
    today_date = datetime.datetime.now()
    if today_date.day == 1:
        print("🧹 執行每月資料庫 VACUUM 保養...")
        conn.execute("VACUUM")
        
    conn.close()

# ====== 程式進入點 ======
if __name__ == "__main__":
    daily_job()
