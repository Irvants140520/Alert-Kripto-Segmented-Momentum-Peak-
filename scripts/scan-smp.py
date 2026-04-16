import ccxt
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timezone

# ========== KONFIGURASI ==========
TIMEFRAME = '5m'
LIMIT = 150  # Cukup untuk SMP + buffer
SENSITIVITY = 1.2
LENGTH_ROC = 1
SEGMENT_WINDOW = 10
LOOKBACK_HORIZON = 10

# Threshold SMP
SH_THRESHOLD = 2.0
SL_THRESHOLD = -2.0

def calculate_roc(close, length=1):
    return ((close - close.shift(length)) / close.shift(length)) * 100

def calculate_smp(df):
    """Hitung SMP (Segmented Momentum Peak)"""
    if len(df) < 50:
        return None, None
    
    roc = calculate_roc(df['close'], LENGTH_ROC)
    hhv = roc.rolling(window=SEGMENT_WINDOW).max()
    llv = roc.rolling(window=SEGMENT_WINDOW).min()
    
    sum_hhv = 0.0
    sum_llv = 0.0
    
    required_offset = 1 + ((LOOKBACK_HORIZON - 1) * SEGMENT_WINDOW)
    if len(hhv) < required_offset + 1:
        return None, None
    
    for i in range(LOOKBACK_HORIZON):
        offset = 1 + (i * SEGMENT_WINDOW)
        sum_hhv += hhv.iloc[-offset]
        sum_llv += llv.iloc[-offset]
    
    smp_high = sum_hhv / LOOKBACK_HORIZON
    smp_low = sum_llv / LOOKBACK_HORIZON
    
    sh = smp_high / SENSITIVITY
    sl = smp_low / SENSITIVITY
    
    return sh, sl

def fetch_ohlcv(exchange, symbol):
    """Fetch data dengan retry"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=LIMIT)
        if not ohlcv or len(ohlcv) < 50:
            return None
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except Exception as e:
        print(f"Error fetch {symbol}: {e}")
        return None

def get_perpetual_symbols(exchange):
    """Ambil semua USDT Perpetual"""
    try:
        markets = exchange.load_markets()
        symbols = []
        for s, m in markets.items():
            if (m.get('quote') == 'USDT' and 
                m.get('type') == 'swap' and 
                m.get('linear') == True):
                symbols.append(s)
        return sorted(symbols)
    except Exception as e:
        print(f"Error load markets: {e}")
        return []

def main():
    print(f"[{datetime.now(timezone.utc)}] Starting SMP Scan...")
    
    exchange = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY', ''),
        'secret': os.getenv('BINANCE_SECRET', ''),
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
    
    symbols = get_perpetual_symbols(exchange)
    print(f"Total coins: {len(symbols)}")
    
    watchlist = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "coins": []
    }
    
    count = 0
    for symbol in symbols:
        count += 1
        if count % 20 == 0:
            print(f"Progress: {count}/{len(symbols)}")
        
        df = fetch_ohlcv(exchange, symbol)
        if df is None:
            continue
        
        sh, sl = calculate_smp(df)
        if sh is None or sl is None:
            continue
        
        # Kriteria: sh > 2.0 dan sl < -2.0
        if sh > SH_THRESHOLD and sl < SL_THRESHOLD:
            current_price = df['close'].iloc[-1]
            coin_data = {
                "symbol": symbol.replace('/', ''),
                "sh": round(float(sh), 2),
                "sl": round(float(sl), 2),
                "price": round(float(current_price), 4),
                "added_at": datetime.now(timezone.utc).isoformat()
            }
            watchlist["coins"].append(coin_data)
            print(f"✅ {symbol}: SH={sh:.2f}, SL={sl:.2f}")
    
    # Simpan ke watchlist.json
    with open('watchlist.json', 'w') as f:
        json.dump(watchlist, f, indent=2)
    
    print(f"\nWatchlist updated: {len(watchlist['coins'])} coins")
    print(f"Saved to watchlist.json")

if __name__ == "__main__":
    main()
