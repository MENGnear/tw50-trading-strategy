# ==============================
# Prt.04 技術指標與 v02.12 安全評分 (v03.06.1 修正版)
# ==============================
def calculate_v0212_score(df_stock):
    # 確保資料依照時間排序，並移除沒有收盤價的無效天數
    df = df_stock.dropna(subset=['Close']).sort_values('Date').copy()
    
    # 🚨 第一道防線：如果資料連 2 天都沒有，根本無法計算趨勢，直接放棄
    if len(df) < 2: return None

    # 基礎指標 (補0以防爆開)
    df['MA20'] = df['Close'].rolling(window=min(20, len(df))).mean().fillna(0)
    df['MA60'] = df['Close'].rolling(window=min(60, len(df))).mean().fillna(0)
    df['V_MA5'] = df['Volume'].rolling(window=min(5, len(df))).mean().fillna(0)
    
    # MACD 結構計算
    if len(df) >= 26:
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = ema12 - ema26
        df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = (df['DIF'] - df['DEA']).fillna(0)
    else:
        df['MACD_Hist'] = 0.0

    # 取得最新與昨天的資料行
    today = df.iloc[-1]
    yest = df.iloc[-2] if len(df) > 1 else today

    # 提取安全數值，避免 KeyError 
    today_close = today.get('Close', 0)
    today_vol = today.get('Volume', 0)
    today_macd = today.get('MACD_Hist', 0)
    yest_macd = yest.get('MACD_Hist', 0)
    today_ma20 = today.get('MA20', 0)
    today_ma60 = today.get('MA60', 0)
    today_vma5 = today.get('V_MA5', 0)

    # --- 五大評分邏輯 ---
    # 1. MACD 翻揚
    t1 = 15 if (today_macd > yest_macd) else 0
    
    # 2. 站上月線
    m1 = 10 if (today_ma20 > 0 and today_close > today_ma20) else 0
    
    # 3. 月線斜率 (🚨 第二道防線：嚴格檢查長度是否大於等於 6，避免 iloc[-6] 崩潰)
    m2 = 0
    if len(df) >= 6:
        ma20_past = df['MA20'].iloc[-6]
        if ma20_past > 0 and ((today_ma20 / ma20_past) - 1) > 0.01:
            m2 = 15
            
    # 4. 多頭排列
    m3 = 10 if (today_ma60 > 0 and today_ma20 > today_ma60) else 0
    
    # 5. 爆量突破
    v1 = 10 if (today_vma5 > 0 and today_vol > (today_vma5 * 1.3)) else 0
    
    total_score = int(t1 + m1 + m2 + m3 + v1)

    # RSI 計算
    df['RSI_6'], df['RSI_14'], df['RSI_24'] = 50.0, 50.0, 50.0
    if len(df) >= 24:
        delta = df['Close'].diff()
        up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
        for p in [6, 14, 24]:
            ema_up = up.ewm(com=p-1, adjust=False).mean()
            ema_down = down.ewm(com=p-1, adjust=False).mean()
            df[f'RSI_{p}'] = 100 - (100 / (1 + ema_up / ema_down.replace(0, 1e-9)))
    
    res = {
        'Date': today.get('Date', pd.Timestamp.now()),
        'Close': today_close,
        'High': today.get('High', 0),
        'Score': total_score,
        's1': t1, 's2': m1, 's3': m2, 's4': m3, 's5': v1,
        'RSI_6': df['RSI_6'].iloc[-1], 
        'RSI_14': df['RSI_14'].iloc[-1], 
        'RSI_24': df['RSI_24'].iloc[-1]
    }
    return res
