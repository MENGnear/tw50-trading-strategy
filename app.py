# ==========================================
# 這是全新的 app_v02_10.py (控制器模式)
# 不修改 main.py 的前提下，擷取其運算結果
# ==========================================
import pandas as pd

# 1. 匯入正式系統 (這會讓 main.py 自動載入並執行它那 15 個段落)
# 備註：請確保 main.py 和此腳本放在同一個資料夾下
import main 

def run_poc_state_machine():
    print("🚀 啟動 v02.10 POC 狀態機攔截與二次運算...")
    
    # 2. 從 main.py 的記憶體中，直接提取它算好的「技術指標與歷史資料」
    # 注意：請將 main.stock_data 替換成你 main.py 實際存放 DataFrame 的變數名稱
    # 例如可能是 main.df_history 或 main.all_data
    if hasattr(main, 'stock_data'):
        df = main.stock_data
    else:
        print("❌ 找不到 main.py 的資料變數，請確認變數名稱")
        return

    # 3. 植入 app_v02_10.py 核心：Setup 狀態機
    setup_active = False
    signal_day_high = 0.0
    entry_score = 0.0
    
    alerts_setup = []
    alerts_trigger = []
    in_position = False

    # 4. 開始跑我們的 POC 獨立邏輯
    for index, row in df.iterrows():
        today_score = row['Score']
        today_high = row['High']
        
        # 建立 Setup
        if not setup_active and not in_position and today_score >= 45:
            setup_active = True
            signal_day_high = today_high
            entry_score = today_score
            alerts_setup.append(f"🎯 Setup 觸發！分數 {entry_score} (突破點: {signal_day_high})")
            continue
            
        # 等待突破
        if setup_active:
            if today_high > signal_day_high:
                in_position = True
                setup_active = False
                alerts_trigger.append(f"🔥 突破進場！成交價高於 {signal_day_high}")
                # 這裡可以繼續寫你的平倉邏輯
    
    # 5. 輸出或推播結果
    print("\n".join(alerts_setup))
    print("\n".join(alerts_trigger))

    # 如果需要發送 Telegram，可以直接呼叫 main 裡面的發送函數，但傳入我們的資料
    # main.send_telegram_alert("\n".join(alerts_setup + alerts_trigger))

# 執行狀態機
if __name__ == "__main__":
    run_poc_state_machine()
