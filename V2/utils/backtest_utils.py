import pandas as pd

def analyze_results(df):
    total = len(df)
    winners = df[df['pnl'] > 0]
    losers = df[df['pnl'] <= 0]

    print(f"📊 Nombre de trades : {total}")
    print(f"✅ Gagnants : {len(winners)}")
    print(f"❌ Perdants : {len(losers)}")
    print(f"💰 PnL total : {df['pnl'].sum():.4f}")
    print(f"📈 PnL moyen : {df['pnl'].mean():.4f}")
    print(f"📉 PnL médian : {df['pnl'].median():.4f}")
