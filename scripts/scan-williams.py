import ccxt
import pandas as pd
import numpy as np
import json
import os
import requests
from datetime import datetime, timezone

# ========== KONFIGURASI ==========
TIMEFRAME = '5m'
LIMIT = 30  # Cukup untuk Williams %R (14 period + buffer crossing)
WILLIAMS_LENGTH = 14
CROSSING_THRESHOLD = -50

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram(message):
    """Kirim notifikasi ke Telegram"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram config missing")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Telegram sent: {response.status_code}")
    except Exception as e:
        print(f"Telegram error: {e}")

def calculate_williams_r(df, length=14):
    """Hitung Williams %R"""
    if len(df) < length + 2:
        return None
    
    high = df['high'].rolling(window=length).max()
    low = df['low'].rolling(window=length).min()
    close = df['close']
    
    wr = -100 * (high - close) / (high - low)
    return wr

def check_crossing(wr_series):
    """
    Cek crossing di -50
    Returns: 'CROSS_UP', 'CROSS_DOWN', atau None
    """
    if len(wr_series) < 2:
        return None
    
    prev = wr_series.iloc[-2]
    curr = wr_series.iloc[-1]
    
    # Crossing up: dari bawah -50 ke atas -50
    if prev < CROSSING_THRESHOLD and curr > CROSSING_THRESHOLD:
        return 'CROSS_UP'
    
    # Crossing down: dari atas -50 ke bawah -50  
    elif prev > CROSSING_THRESHOLD and curr < CROSSING_THRESHOLD:
        return 'CROSS_DOWN'
    
    return None

def fetch_ohlcv(exchange, symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=LIMIT)
        if not ohlcv or len(ohlcv) < WILLIAMS_LENGTH + 2:
            return None
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except Exception as e:
        print(f"Error fetch {symbol}: {e}")
        return None

def main():
    print(f"[{datetime.now(timezone.utc)}] Checking Williams %R triggers...")
    
    # Baca watchlist
    try:
        with open('watchlist.json', 'r') as f:
            watchlist = json.load(f)
    except Exception as e:
        print(f"Error read watchlist: {e}")
        return
    
    coins = watchlist.get('coins', [])
    if not coins:
        print("Watchlist kosong")
        return
    
    print(f"Scanning {len(coins)} coins from watchlist...")
    
    exchange = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY', ''),
        'secret': os.getenv('BINANCE_SECRET', ''),
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
    
    triggered = []
    
    for coin in coins:
        symbol = coin['symbol']
        # Format symbol untuk CCXT (tambah /USDT)
        ccxt_symbol = f"{symbol.replace('USDT', '')}/USDT:USDT" if 'USDT' in symbol else f"{symbol}/USDT:USDT"
        
        df = fetch_ohlcv(exchange, ccxt_symbol)
        if df is None:
            continue
        
        wr = calculate_williams_r(df, WILLIAMS_LENGTH)
        if wr is None:
            continue
        
        signal = check_crossing(wr)
        
        if signal:
            current_wr = wr.iloc[-1]
            current_price = df['close'].iloc[-1]
            
            arrow = "🟢" if signal == 'CROSS_UP' else "🔴"
            direction = "UP" if signal == 'CROSS_UP' else "DOWN"
            
            msg = (
                f"{arrow} <b>WILLIAMS %R TRIGGER</b> {arrow}\n\n"
                f"<b>Coin:</b> <code>{symbol}</code>\n"
                f"<b>Signal:</b> Crossing {direction} -50\n"
                f"<b>WR Value:</b> {current_wr:.2f}\n"
                f"<b>Price:</b> ${current_price:,.4f}\n"
                f"<b>SMP:</b> SH={coin.get('sh', 'N/A')} | SL={coin.get('sl', 'N/A')}\n"
                f"<b>Time:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
            )
            
            send_telegram(msg)
            triggered.append({
                'symbol': symbol,
                'signal': signal,
                'wr': float(current_wr),
                'price': float(current_price),
                'time': datetime.now(timezone.utc).isoformat()
            })
            
            print(f"🚨 {symbol}: {signal} at WR={current_wr:.2f}")
    
    if triggered:
        print(f"\nTotal triggers: {len(triggered)}")
        # Optional: Simpan log triggers
        with open('triggers_log.json', 'a') as f:
            for t in triggered:
                f.write(json.dumps(t) + '\n')
    else:
        print("No triggers found")

if __name__ == "__main__":
    main()
