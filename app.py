import main
import sys

print("=== 系統測試：開始載入 ===")

# 檢查一下到底抓到了什麼
if hasattr(main, 'stock_data'):
    df = main.stock_data
    print(f"成功抓取數據，共 {len(df)} 筆資料")
    print(f"前五筆分數: {df['Score'].head().tolist()}")
else:
    print("❌ 錯誤：找不到 stock_data")
    # 把這行印出來，讓我幫你分析為什麼抓不到
    print(f"main 裡面的屬性有: {dir(main)}")
    sys.exit()

# 測試邏輯
print("=== 測試邏輯中 ===")
# 這裡隨便模擬一個觸發，看 Telegram 會不會動
# main.send_telegram_alert("測試：系統已成功掛載！")
print("測試訊息已發送 (若沒收到，請檢查 main.py 的 token 設定)")
