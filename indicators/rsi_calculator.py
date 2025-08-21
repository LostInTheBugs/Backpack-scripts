# indicators/rsi_calculator.py
import os
import pandas as pd
import asyncio
from datetime import datetime, timezone
from utils.logger import log
from bpx.public import Public

public = Public()

# Configuration RSI
RSI_PERIOD = 14  # Période standard du RSI
MIN_DATA_POINTS = RSI_PERIOD * 3  # Minimum de points pour un calcul fiable

async def fetch_rsi_data(symbol: str, interval: str = "5m") -> pd.DataFrame:
    """
    Récupère les données nécessaires pour le calcul du RSI via l'API Backpack.
    Utilise la limite de 6 jours de l'API.
    """
    try:
        # Calcul des timestamps (API attend des secondes Unix)
        end_time = int(datetime.now(timezone.utc).timestamp())
        # 6 jours maximum selon la limite API
        start_time = end_time - (6 * 24 * 3600)
        
        log(f"[{symbol}] Récupération données RSI via API Backpack ({interval}) sur 6 jours", level="DEBUG")
        
        # Appel API
        data = await asyncio.to_thread(
            public.get_klines,
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time
        )
        
        if not data:
            log(f"[{symbol}] Aucune donnée reçue de l'API Backpack", level="WARNING")
            return pd.DataFrame()
        
        # Conversion en DataFrame
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
        ])
        
        # Nettoyage et conversion
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # Tri par timestamp
        df = df.sort_values("timestamp").reset_index(drop=True)
        
        log(f"[{symbol}] ✅ {len(df)} bougies récupérées pour RSI", level="DEBUG")
        return df
        
    except Exception as e:
        log(f"[{symbol}] Erreur lors de la récupération des données RSI: {e}", level="ERROR")
        return pd.DataFrame()

def calculate_rsi_optimized(df: pd.DataFrame, period: int = RSI_PERIOD, symbol: str = "UNKNOWN") -> pd.DataFrame:
    """
    Calcule le RSI de manière optimisée avec gestion des cas limites.
    """
    if len(df) < period:
        log(f"[{symbol}] Données insuffisantes pour RSI: {len(df)} < {period}", level="WARNING")
        df['rsi'] = 50.0  # Valeur neutre par défaut
        return df
    
    try:
        # Calcul des variations de prix
        delta = df['close'].diff()
        
        # Séparation gains/pertes
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        
        # Calcul des moyennes mobiles exponentielles
        alpha = 1.0 / period
        avg_gain = gain.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
        
        # Calcul RS et RSI
        rs = avg_gain / (avg_loss + 1e-10)  # Éviter division par zéro
        rsi = 100 - (100 / (1 + rs))
        
        # Gestion des valeurs NaN initiales
        rsi = rsi.fillna(50.0)  # Valeur neutre pour les premières valeurs
        
        df['rsi'] = rsi
        
        # Validation des résultats
        valid_rsi = df['rsi'].dropna()
        if len(valid_rsi) > 0:
            current_rsi = valid_rsi.iloc[-1]
            log(f"[{symbol}] ✅ RSI calculé: {current_rsi:.2f} (sur {len(valid_rsi)} points valides)", level="DEBUG")
        else:
            log(f"[{symbol}] ⚠️ RSI calculé mais toutes valeurs NaN", level="WARNING")
            
        return df
        
    except Exception as e:
        log(f"[{symbol}] Erreur calcul RSI: {e}", level="ERROR")
        df['rsi'] = 50.0  # Valeur de sécurité
        return df

async def get_current_rsi(symbol: str, interval: str = "5m") -> float:
    """
    Récupère le RSI actuel pour un symbole donné.
    Retourne une valeur entre 0 et 100.
    """
    try:
        # Récupération des données
        df = await fetch_rsi_data(symbol, interval)
        
        if df.empty:
            log(f"[{symbol}] Pas de données pour RSI, retour valeur neutre (50)", level="WARNING")
            return 50.0
        
        # Calcul du RSI
        df = calculate_rsi_optimized(df, symbol=symbol)
        
        # Récupération de la dernière valeur
        current_rsi = df['rsi'].iloc[-1]
        
        # Validation de la valeur
        if pd.isna(current_rsi) or not (0 <= current_rsi <= 100):
            log(f"[{symbol}] RSI invalide ({current_rsi}), retour valeur neutre", level="WARNING")
            return 50.0
            
        return float(current_rsi)
        
    except Exception as e:
        log(f"[{symbol}] Erreur get_current_rsi: {e}", level="ERROR")
        return 50.0

# Cache pour éviter trop d'appels API
_rsi_cache = {}
_cache_duration = 300  # 5 minutes

async def get_cached_rsi(symbol: str, interval: str = "5m") -> float:
    """
    Version avec cache du RSI pour éviter trop d'appels API.
    """
    cache_key = f"{symbol}_{interval}"
    current_time = datetime.now(timezone.utc).timestamp()
    
    # Vérifier le cache
    if cache_key in _rsi_cache:
        cached_time, cached_rsi = _rsi_cache[cache_key]
        if current_time - cached_time < _cache_duration:
            log(f"[{symbol}] RSI depuis cache: {cached_rsi:.2f}", level="DEBUG")
            return cached_rsi
    
    # Calculer nouveau RSI
    rsi = await get_current_rsi(symbol, interval)
    _rsi_cache[cache_key] = (current_time, rsi)
    
    return rsi