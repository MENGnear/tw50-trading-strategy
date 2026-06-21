import pandas as pd
import sys

# 嘗試靜態載入 main
try:
    import main
except ImportError:
    print("❌ 無法載入 main.py，請確認檔案名稱是否正確且位於同一路徑")
    sys.exit(1)

def run_poc_state_machine():
    print("🚀 啟動 v02.10 攔截運算...")
    
    # 檢查目標變數，如果 main.py 內部變數是區域變數，請在 main.py 底部增加：
    # global stock_data 
    # stock_data = your_dataframe_name
    
    target_df = getattr(main, 'stock_data', None)
    
    if target_df is None:
        print("❌ 錯誤：在 main.py 中找不到 'stock_data' 變數。")
        print(f"現有屬性: {dir(main)}") # 除錯用：顯示 main 中所有的變數名稱
        return

    # ... 後續邏輯 ...
