import pandas as pd
import sys
import main  # 這會觸發 main.py 的初始化

def run_poc_state_machine():
    print("🚀 啟動 v02.10 POC 狀態機...")
    
    # --- 1. 自動尋找目標數據集 ---
    # 如果變數是全域的，直接取用；如果是函數內部的，可能需要調整 main.py
    # 這裡我們嘗試尋找常見的命名
    target_df = None
    possible_names = ['stock_data', 'df_history', 'all_data', 'df']
    
    for name in possible_names:
        if hasattr(main, name):
            target_df = getattr(main, name)
            print(f"✅ 成功找到數據變數: {name}")
            break
            
    if target_df is None:
        print("❌ 錯誤：無法在 main.py 中找到資料變數。")
        print(f"當前可用變數: {[attr for attr in dir(main) if not attr.startswith('__')]}")
        return

    # --- 2. 狀態機核心邏輯 ---
    setup_active = False
    signal_day_high = 0.0
    entry_score = 0.0
    alerts = []
    in_position = False

    for index, row in target_df.iterrows():
        # 確保 DataFrame 欄位名稱與此處一致
        today_score = row.get('Score', 0)
        today_high = row.get('High', 0)
        
        # Setup 偵測
        if not setup_active and not in_position and today_score >= 45:
            setup_active = True
            signal_day_high = today_high
            entry_score = today_score
            alerts.append(f"🎯 [Setup] 觸發：分數 {entry_score:.2f} (突破點: {signal_day_high})")
            continue
            
        # Trigger 偵測
        if setup_active and today_high > signal_day_high:
            in_position = True
            setup_active = False
            alerts.append(f"🔥 [Trigger] 突破進場：成交價 {today_high} > 突破點 {signal_day_high}")

    # --- 3. 輸出結果 ---
    print("\n--- 運算結果摘要 ---")
    if not alerts:
        print("沒有觸發任何訊號。")
    else:
        for alert in alerts:
            print(alert)

if __name__ == "__main__":
    run_poc_state_machine()
