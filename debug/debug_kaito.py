from utils.position_utils import get_raw_positions, safe_float
from utils.logger import log

async def debug_kaito_position():
    """
    Debug spécifique de la position KAITO pour identifier le problème
    """
    symbol = "KAITO_USDC_PERP"
    
    try:
        # 1. Récupérer les données brutes de l'API
        raw_positions = await get_raw_positions()
        kaito_raw = next((p for p in raw_positions if p.get("symbol") == symbol), None)
        
        if not kaito_raw:
            log("[DEBUG KAITO] Position not found", level="INFO")
            return
        
        log("=" * 80, level="INFO")
        log("[DEBUG KAITO] RAW DATA:", level="INFO")
        for key, value in kaito_raw.items():
            log(f"  {key}: {value}", level="INFO")
        
        # 2. Données extraites
        entry_price = safe_float(kaito_raw.get("entryPrice"), 0.0)
        mark_price = safe_float(kaito_raw.get("markPrice"), 0.0)
        net_qty = safe_float(kaito_raw.get("netQuantity"), 0.0)
        pnl_unrealized = safe_float(kaito_raw.get("pnlUnrealized"), 0.0)
        
        log(f"[DEBUG KAITO] EXTRACTED:", level="INFO")
        log(f"  Entry: {entry_price:.6f}", level="INFO")
        log(f"  Mark: {mark_price:.6f}", level="INFO")
        log(f"  NetQty: {net_qty:.6f}", level="INFO")
        log(f"  PnL_API: {pnl_unrealized:.6f}", level="INFO")
        
        # 3. Calculs manuels
        side = "long" if net_qty > 0 else "short"
        amount = abs(net_qty)
        
        log(f"[DEBUG KAITO] CALCULATED:", level="INFO")
        log(f"  Side: {side}", level="INFO")
        log(f"  Amount: {amount:.6f}", level="INFO")
        
        # 4. Calcul PnL manuel
        if side == "short":
            manual_pnl_usd = (entry_price - mark_price) * amount
            manual_pnl_pct = (entry_price - mark_price) / entry_price * 100
        else:
            manual_pnl_usd = (mark_price - entry_price) * amount
            manual_pnl_pct = (mark_price - entry_price) / entry_price * 100
        
        log(f"[DEBUG KAITO] MANUAL CALC:", level="INFO")
        log(f"  PnL USD: {manual_pnl_usd:.6f}", level="INFO")
        log(f"  PnL %: {manual_pnl_pct:.4f}%", level="INFO")
        
        # 5. Comparaison avec API
        log(f"[DEBUG KAITO] COMPARISON:", level="INFO")
        log(f"  API PnL: {pnl_unrealized:.6f}", level="INFO")
        log(f"  Manual PnL: {manual_pnl_usd:.6f}", level="INFO")
        log(f"  Difference: {abs(pnl_unrealized - manual_pnl_usd):.6f}", level="INFO")
        log(f"  Ratio API/Manual: {pnl_unrealized/manual_pnl_usd if manual_pnl_usd != 0 else 'N/A'}", level="INFO")
        
        # 6. Vérification avec données Exchange (valeurs observées)
        exchange_pnl_usd = 3.65  
        exchange_pnl_pct = 7.90  
        
        log(f"[DEBUG KAITO] EXCHANGE COMPARISON:", level="INFO")
        log(f"  Exchange PnL USD: ${exchange_pnl_usd:.2f}", level="INFO")
        log(f"  Exchange PnL %: {exchange_pnl_pct:.2f}%", level="INFO")
        log(f"  Ratio API/Exchange USD: {pnl_unrealized/exchange_pnl_usd:.4f}", level="INFO")
        log(f"  Ratio Manual/Exchange USD: {manual_pnl_usd/exchange_pnl_usd:.4f}", level="INFO")
        
        log("=" * 80, level="INFO")
        
    except Exception as e:
        log(f"[ERROR] Debug KAITO failed: {e}", level="ERROR")
        import traceback
        traceback.print_exc()