import asyncio
from combined_indicators import fetch_api_fallback, calculate_rsi, RSI_PERIOD_MINUTES, log

async def test_api_fallback(symbol):
    df = await fetch_api_fallback(symbol)
    if df is None or df.empty:
        print(f"[{symbol}] Aucun donnée récupérée via API fallback")
        return
    print(f"[{symbol}] Données récupérées via API fallback : {len(df)} lignes")
    if len(df) < RSI_PERIOD_MINUTES:
        print(f"[{symbol}] ATTENTION: données récupérées insuffisantes pour RSI ({len(df)} < {RSI_PERIOD_MINUTES})")
    else:
        print(f"[{symbol}] OK pour calcul RSI (>= {RSI_PERIOD_MINUTES} lignes)")
    df = calculate_rsi(df, symbol=symbol)
    print(df[['timestamp','close','rsi']].tail(10))

if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTC_USDC_PERP"
    asyncio.run(test_api_fallback(symbol))
