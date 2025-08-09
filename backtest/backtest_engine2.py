import asyncio
import asyncpg
import pandas as pd
import os
import json
import traceback
from utils.logger import log
from utils.position_tracker import PositionTracker
from importlib import import_module
from datetime import datetime, timedelta, timezone
from utils.logger import log_level

class BacktestTranslator:
    def __init__(self, language='fr'):
        self.language = language
        self.translations = {}
        self.load_translations()
    
    def load_translations(self):
        """Charge les traductions depuis les fichiers JSON"""
        try:
            lang_file = f"locales/{self.language}.json"
            if os.path.exists(lang_file):
                with open(lang_file, 'r', encoding='utf-8') as f:
                    self.translations = json.load(f)
            else:
                # Fallback vers français si le fichier n'existe pas
                with open("locales/fr.json", 'r', encoding='utf-8') as f:
                    self.translations = json.load(f)
                print(f"Warning: {lang_file} not found, using French")
        except Exception as e:
            print(f"Error loading translations: {e}")
            # Traductions de fallback intégrées
            self.translations = self._get_fallback_translations()
    
    def _get_fallback_translations(self):
        """Traductions de secours si les fichiers JSON ne sont pas disponibles"""
        return {
            "backtest": {
                "no_ohlcv_data": "❌ Pas de données OHLCV en base pour backtest",
                "error_fetch_ohlcv": "❌ Erreur fetch OHLCV backtest: {}",
                "no_data": "❌ Pas de données OHLCV",
                "start": "✅ Début du backtest avec {} bougies",
                "end": "🔚 Backtest terminé",
                "stats_positions": "📊 Positions: {} | Gagnantes: {} | Perdantes: {}",
                "stats_pnl": "📈 PnL total: {:.2f}% | moyen: {:.2f}% | médian: {:.2f}% | taux de succès: {:.2f}%",
                "no_positions": "⚠️ Aucune position prise",
                "exception": "💥 Exception dans le backtest complet: {}"
            }
        }
    
    def t(self, category, key, *args, **kwargs):
        """Traduit une clé avec des paramètres optionnels"""
        try:
            text = self.translations.get(category, {}).get(key, f"[MISSING:{category}.{key}]")
            # Support pour les arguments positionnels et nommés
            if args:
                return text.format(*args)
            elif kwargs:
                return text.format(**kwargs)
            return text
        except Exception as e:
            return f"[TRANSLATION_ERROR:{category}.{key}]"
    
    def set_language(self, language):
        """Change la langue courante"""
        if language != self.language:
            self.language = language
            self.load_translations()

# Instance globale du traducteur
bt_translator = BacktestTranslator()

def set_backtest_language(language):
    """Configure la langue pour les messages de backtest"""
    bt_translator.set_language(language)

# Cette fonction charge dynamiquement la stratégie demandée
def get_signal_function(strategy_name):
    if strategy_name == "Trix":
        module = import_module("signals.trix_only_signal")
    elif strategy_name == "Combo":
        module = import_module("signals.macd_rsi_bo_trix")
    else:
        module = import_module("signals.macd_rsi_breakout")
    return module.get_combined_signal

async def fetch_ohlcv_from_db(pool, symbol):
    table_name = "ohlcv_" + "__".join(symbol.lower().split("_"))

    async with pool.acquire() as conn:
        try:
            query = f"""
                SELECT timestamp, open, high, low, close, volume
                FROM {table_name}
                WHERE interval_sec = 1
                ORDER BY timestamp ASC
            """
            rows = await conn.fetch(query)

            if not rows:
                log(f"[{symbol}] {bt_translator.t('backtest', 'no_ohlcv_data')}")
                return pd.DataFrame()

            df = pd.DataFrame([dict(row) for row in rows])
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            if df['timestamp'].dt.tz is None:
                df['timestamp'] = df['timestamp'].dt.tz_localize('Europe/Paris').dt.tz_convert('UTC')
            else:
                df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')

            df.set_index('timestamp', inplace=True)

            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            return df

        except Exception as e:
            log(f"[{symbol}] {bt_translator.t('backtest', 'error_fetch_ohlcv', str(e))}")
            traceback.print_exc()
            return pd.DataFrame()

async def run_backtest_async(symbol: str, interval, dsn: str, strategy_name: str, language: str = 'fr'):
    # Configure la langue pour ce backtest
    bt_translator.set_language(language)
    
    try:
        pool = await asyncpg.create_pool(dsn=dsn)
        df = await fetch_ohlcv_from_db(pool, symbol)
        await pool.close()

        if df.empty:
            log(f"[{symbol}] {bt_translator.t('backtest', 'no_data')}")
            return
        
        # --- Filtrage des données selon interval ---
        if isinstance(interval, (int, float)):
            # interval en heures, on prend les dernières interval heures
            end_time = df.index[-1]
            start_time = end_time - timedelta(hours=interval)
            df = df.loc[start_time:end_time]
            log(f"[{symbol}] {bt_translator.t('backtest', 'info_filter_duration', interval)}")
        elif isinstance(interval, tuple) and len(interval) == 2:
            start_time, end_time = interval
            # Assurer que start_time et end_time ont le bon timezone (UTC)
            # Si ce sont des datetime naïfs, on les localise en UTC
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            df = df.loc[start_time:end_time]
            log(f"[{symbol}] {bt_translator.t('backtest', 'info_filter_dates', start_time, end_time)}")

        if df.empty:
            log(f"[{symbol}] {bt_translator.t('backtest', 'no_data_after_filter')}")
            return

        log(f"[{symbol}] {bt_translator.t('backtest', 'start', len(df))}")

        tracker = PositionTracker(symbol)
        stats = {"total": 0, "win": 0, "loss": 0, "pnl": []}

        get_combined_signal = get_signal_function(strategy_name)

        for current_time in df.index:
            current_df = df.loc[:current_time]
            if len(current_df) < 100:
                continue

            result = get_combined_signal(current_df)
            if isinstance(result, tuple):
                signal, indicators = result
            else:
                signal = result
                indicators = {}
            if log_level.upper() == "DEBUG":
                debug_msg = (
                    f"[DEBUG] {symbol} | {current_time} | Signal={signal} "
                    f"| Prix={current_df.iloc[-1]['close']}"
                )
                if indicators:
                    debug_msg += " | " + " | ".join(f"{k}={v:.2f}" for k, v in indicators.items())
                log(debug_msg)



            current_price = current_df.iloc[-1]["close"]

            # Ouvre position si signal et aucune position
            if signal in ("BUY", "SELL") and not tracker.is_open():
                tracker.open(signal, current_price, current_time)

            # Met à jour trailing stop si position ouverte
            if tracker.is_open():
                tracker.update_trailing_stop(current_price, current_time)

                # Ferme si stop touché
                if tracker.should_close(current_price):
                    pnl = tracker.close(current_price, current_time)
                    stats["total"] += 1
                    stats["pnl"].append(pnl)
                    if pnl >= 0:
                        stats["win"] += 1
                    else:
                        stats["loss"] += 1

        log(f"[{symbol}] {bt_translator.t('backtest', 'end')}")
        
        if stats["total"] > 0:
            pnl_total = sum(stats["pnl"])
            pnl_moyen = pnl_total / stats["total"]
            pnl_median = pd.Series(stats["pnl"]).median()
            win_rate = stats["win"] / stats["total"] * 100
            
            log(f"[{symbol}] {bt_translator.t('backtest', 'stats_positions', stats['total'], stats['win'], stats['loss'])}")
            log(f"[{symbol}] {bt_translator.t('backtest', 'stats_pnl', pnl_total, pnl_moyen, pnl_median, win_rate)}")
        else:
            log(f"[{symbol}] {bt_translator.t('backtest', 'no_positions')}")

    except Exception as e:
        log(f"[{symbol}] {bt_translator.t('backtest', 'exception', str(e))}")
        traceback.print_exc()

# Appel principal depuis main.py
def run_backtest(symbol: str, interval: str, strategy_name: str, language: str = 'fr'):
    """
    Lance un backtest avec support multilingue
    
    Args:
        symbol: Symbole à analyser
        interval: Intervalle de temps
        strategy_name: Nom de la stratégie
        language: Langue des messages ('fr', 'en')
    """
    dsn = os.environ.get("PG_DSN")
    asyncio.run(run_backtest_async(symbol, interval, dsn, strategy_name, language))

# Fonction utilitaire pour obtenir les langues supportées
def get_supported_languages():
    """Retourne la liste des langues supportées en scannant le dossier locales/"""
    try:
        locales_dir = "locales"
        if os.path.exists(locales_dir):
            files = [f for f in os.listdir(locales_dir) if f.endswith('.json')]
            return [f.replace('.json', '') for f in files]
        return ['fr']  # Fallback
    except:
        return ['fr', 'en']