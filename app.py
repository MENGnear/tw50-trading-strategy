import pandas as pd
import os

def run_poc_state_machine():
    print("🚀 啟動 v02.10 POC 狀態機...")
    
    file_path = "temp_data.csv"
    if not os.path.exists(file_path):
        print(f"❌ 錯誤：找不到 {file_path}，請先執行 main.py")
        return

    # 讀取資料
    df = pd.read_csv(file_path)
    print(f"✅ 成功讀取資料。現有欄位: {list(df.columns)}")

    # --- 狀態機邏輯 ---
    # 如果資料內沒有 Score，我們用 Close 價做簡單模擬
    # 如果有特定演算法計算 Score，請在這裡補上
    if 'Score' not in df.columns:
        print("⚠️ CSV 中未找到 'Score' 欄位，將使用 'Close' 進行初步邏輯測試")
        df['Score'] = df['Close'] / df['Close'].mean() * 50 # 簡單比例模擬

    setup_active = False
    signal_day_high = 0.0
    entry_score = 0.0
    alerts_setup = []
    alerts_trigger = []
    in_position = False

    for index, row in df.iterrows():
        today_score = row.get('Score', 0)
        today_high = row.get('High', 0)
        
        # 建立 Setup (這裡預設以 45 為門檻，你可以隨時修改)
        if not setup_active and not in_position and today_score >= 45:
            setup_active = True
            signal_day_high = today_high
            entry_score = today_score
            alerts_setup.append(f"🎯 Setup 觸發！分數 {entry_score:.2f} (突破點: {signal_day_high})")
            continue
            
        # 等待突破
        if setup_active:
            if today_high > signal_day_high:
                in_position = True
                setup_active = False
                alerts_trigger.append(f"🔥 突破進場！成交價高於 {signal_day_high}")

    # 輸出結果
    if alerts_setup or alerts_trigger:
        print("\n--- 運算結果 ---")
        for log in alerts_setup + alerts_trigger:
            print(log)
    else:
        print("ℹ️ 檢查完畢：無觸發訊號。")

if __name__ == "__main__":
    run_poc_state_machine()
