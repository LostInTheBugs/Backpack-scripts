

async def handle_live_symbol(symbol: str, pool, real_run: bool, dry_run: bool):
    try:
        log(f"[{symbol}] 📈 Chargement OHLCV pour {INTERVAL}")

        if not await check_table_and_fresh_data(pool, symbol, max_age_seconds=60):
            log(f"[{symbol}] Ignoré : pas de données récentes")
            return

        if INTERVAL == "1s":
            end_ts = datetime.now(timezone.utc)
            start_ts = end_ts - timedelta(seconds=60)
            df = await fetch_ohlcv_1s(symbol, start_ts, end_ts)
        else:
            data = get_ohlcv(symbol, INTERVAL)
            if not data:
                log(f"[{symbol}] ❌ Données OHLCV vides")
                return
            df = get_ohlcv_df(symbol, INTERVAL)

        if df.empty:
            log(f"[{symbol}] ❌ DataFrame OHLCV vide après conversion")
            return
        if len(df) < 2:
            log(f"[{symbol}] ⚠️ Pas assez de données (moins de 2 lignes) pour calculer le signal")
            return

        # Correction des timestamps
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        df.set_index('timestamp', inplace=True)

        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        signal = get_combined_signal(df)
        log(f"[{symbol}] 🎯 Signal détecté : {signal}")

        if signal in ["BUY", "SELL"]:
            if position_already_open(symbol):
                log(f"[{symbol}] ⚠️ Position déjà ouverte — Ignorée")
                return
            direction = "long" if signal == "BUY" else "short"

            if dry_run:
                log(f"[{symbol}] 🧪 DRY-RUN: Simulation d'ouverture position {direction.upper()}")
            elif real_run:
                log(f"[{symbol}] ✅ OUVERTURE position réelle : {direction.upper()}")
                open_position(symbol, POSITION_AMOUNT_USDC, direction)
            else:
                log(f"[{symbol}] ❌ Ni --real-run ni --dry-run spécifié : aucune action")
    except Exception as e:
        log(f"[{symbol}] 💥 Erreur: {e}")
        traceback.print_exc()