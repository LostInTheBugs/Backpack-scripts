# utils/table_display.py - VERSION CORRIGÉE
import os
from datetime import datetime
from tabulate import tabulate
from utils.logger import log

class PositionTableDisplay:
    def __init__(self):
        self.positions_data = {}
        self.last_display_time = 0
        self.display_interval = 5  # Afficher le tableau toutes les 5 secondes
        
    def update_position(self, symbol, position_info):
        """Met à jour les données d'une position"""
        self.positions_data[symbol] = {
            'symbol': symbol,
            'side': position_info.get('side', 'N/A'),
            'entry_price': position_info.get('entry_price', 0.0),
            'mark_price': position_info.get('mark_price', 0.0),
            'pnl_pct': position_info.get('pnl_pct', 0.0),
            'pnl_usd': position_info.get('pnl_usd', 0.0),
            'amount': position_info.get('amount', 0.0),
            'duration': position_info.get('duration', '0h0m'),
            'trailing_stop': position_info.get('trailing_stop', None),  # ✅ None au lieu de 0.0
            'last_update': datetime.now()
        }
        
    def should_display(self):
        """Vérifie s'il faut afficher le tableau"""
        current_time = datetime.now().timestamp()
        if current_time - self.last_display_time >= self.display_interval:
            self.last_display_time = current_time
            return True
        return False
        
    def display_positions_table(self):
        """Affiche le tableau des positions"""
        if not self.positions_data:
            return
            
        # Préparer les données pour le tableau
        table_data = []
        total_pnl_usd = 0.0
        
        for pos in self.positions_data.values():
            # Formatage des données
            side_emoji = "🟢" if pos['side'] == "long" else "🔴" if pos['side'] == "short" else "⚪"
            pnl_emoji = "📈" if pos['pnl_pct'] > 0 else "📉" if pos['pnl_pct'] < 0 else "➡️"
            
            # ✅ CORRECTION: Affichage correct du trailing stop
            trailing_display = self._format_trailing_stop(pos['trailing_stop'], pos['pnl_pct'])
            
            table_data.append([
                f"{side_emoji} {pos['symbol']}",
                pos['side'].upper(),
                f"{pos['entry_price']:.6f}",
                f"{pos['mark_price']:.6f}",
                f"{pnl_emoji} {pos['pnl_pct']:+.2f}%",
                f"${pos['pnl_usd']:+.2f}",
                f"{pos['amount']:.4f}",
                pos['duration'],
                trailing_display
            ])
            
            total_pnl_usd += pos['pnl_usd']
        
        # Trier par PnL décroissant
        table_data.sort(key=lambda x: float(x[5].replace('$', '').replace('+', '')), reverse=True)
        
        # Afficher le tableau (vous pouvez personnaliser le format ici)
        # headers = ['Symbol', 'Side', 'Entry', 'Mark', 'PnL%', 'PnL$', 'Amount', 'Duration', 'Trailing']
        # print(tabulate(table_data, headers=headers, tablefmt='grid'))
        
    def _format_trailing_stop(self, trailing_value, pnl_pct):
        """
        ✅ CORRECTION: Formatage correct du trailing stop
        
        Args:
            trailing_value: Valeur du trailing stop (float) ou None
            pnl_pct: PnL actuel en %
            
        Returns:
            str: Texte formaté pour l'affichage
        """
        if trailing_value is not None:
            # Trailing stop ACTIF
            return f"+{trailing_value:.2f}% 🟢"
        else:
            # Trailing stop PAS ENCORE actif - stop-loss fixe
            return "-2.0% ⏸️"

# Instance globale
position_table = PositionTableDisplay()


# ========================================
# FONCTION CORRIGÉE POUR live_engine.py
# ========================================

async def handle_existing_position_with_table(symbol, real_run=True, dry_run=False):
    """
    ✅ VERSION CORRIGÉE: Gestion des positions avec tableau et trailing stop fonctionnel
    """
    try:
        from utils.position_utils import get_real_positions, safe_float
        from utils.table_display import position_table
        from datetime import datetime
        from config.settings import get_config
        from execute.close_position_percent import close_position_percent
        from bpx.public import Public
        import json
        import asyncio
        
        # ✅ CORRECTION: Import des fonctions du live_engine
        from live.live_engine import (
            get_position_trailing_stop, 
            should_close_position,
            get_position_hash,
            cleanup_trailing_stop,
            TRAILING_STOPS
        )
        
        config = get_config()
        
        # 1. Récupération des positions réelles
        raw_positions = await get_real_positions()
        
        # 2. Parse des positions
        parsed_positions = []
        for p in raw_positions:
            try:
                if isinstance(p, dict):
                    parsed_positions.append(p)
                elif isinstance(p, str) and p.strip():
                    parsed_pos = json.loads(p.strip())
                    if parsed_pos and isinstance(parsed_pos, dict):
                        parsed_positions.append(parsed_pos)
            except (json.JSONDecodeError, AttributeError) as e:
                log(f"[ERROR] parse_position failed: {e}", level="ERROR")
                continue

        pos = next((p for p in parsed_positions if p and p.get("symbol") == symbol), None)
        if not pos:
            # Retirer du tableau si plus de position
            if symbol in position_table.positions_data:
                del position_table.positions_data[symbol]
            return

        # 3. Extraction des données de position (SANS ARRONDIR)
        side = pos.get("side", "").lower()
        entry_price = float(pos.get("entry_price", 0))
        amount = float(pos.get("amount", 0))
        leverage = float(pos.get("leverage", 1))
        timestamp = float(pos.get("timestamp", datetime.utcnow().timestamp()))

        if entry_price <= 0 or amount <= 0:
            log(f"[{symbol}] Invalid position data: entry={entry_price}, amount={amount}", level="ERROR")
            return

        # 4. ✅ CORRECTION CRITIQUE: UN SEUL APPEL pour le prix actuel
        public = Public()
        try:
            ticker = await asyncio.to_thread(public.get_ticker, symbol)
            mark_price = float(ticker.get("lastPrice", entry_price))
        except Exception as e:
            log(f"[{symbol}] Failed to get ticker: {e}", level="ERROR")
            mark_price = entry_price

        # 5. ✅ CALCUL PNL UNE SEULE FOIS avec précision
        if side == "long":
            pnl_pct = ((mark_price - entry_price) / entry_price) * 100
            pnl_usdc = (mark_price - entry_price) * amount * leverage
        else:  # short
            pnl_pct = ((entry_price - mark_price) / entry_price) * 100
            pnl_usdc = (entry_price - mark_price) * amount * leverage

        # 6. Calcul de la durée
        duration_sec = datetime.utcnow().timestamp() - timestamp
        duration_str = f"{int(duration_sec // 3600)}h{int((duration_sec % 3600) // 60)}m"

        # 7. ✅ CORRECTION: Appel correct avec TOUS les paramètres
        trailing_stop = await get_position_trailing_stop(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            mark_price=mark_price,
            amount=amount,
            current_pnl_pct=pnl_pct  # ← Le PnL déjà calculé
        )

        # 8. Logs détaillés
        log(f"📊 [{symbol}] {side.upper()} | Entry: ${entry_price:.4f} | Mark: ${mark_price:.4f} | "
            f"PnL: {pnl_pct:+.2f}% (${pnl_usdc:+.2f}) | Trailing: {trailing_stop} | Duration: {duration_str}", 
            level="INFO")

        # 9. ✅ Mettre à jour le tableau avec les VRAIES données
        position_info = {
            'side': side,
            'entry_price': entry_price,
            'mark_price': mark_price,
            'pnl_pct': pnl_pct,
            'pnl_usd': pnl_usdc,
            'amount': amount,
            'duration': duration_str,
            'trailing_stop': trailing_stop  # ✅ None si pas actif, float si actif
        }
        
        position_table.update_position(symbol, position_info)
        
        # 10. Afficher le tableau si nécessaire
        if position_table.should_display():
            position_table.display_positions_table()

        # 11. ✅ VÉRIFICATION FERMETURE
        should_close = should_close_position(
            pnl_pct=pnl_pct,
            trailing_stop=trailing_stop,
            side=side,
            duration_sec=duration_sec,
            symbol=symbol,
            strategy=config.strategy.default_strategy
        )
        
        log(f"🔍 [{symbol}] Close decision | PnL: {pnl_pct:.4f}% | Trailing: {trailing_stop} | "
            f"ShouldClose: {should_close}", level="INFO")
        
        # 12. ✅ FERMETURE si nécessaire
        if should_close:
            close_reason = 'Trailing Stop' if trailing_stop is not None else 'Fixed Stop Loss'
            log(f"🚨 [{symbol}] CLOSING POSITION | Reason: {close_reason} | Final PnL: {pnl_pct:.2f}%", 
                level="WARNING")
            
            if real_run:
                try:
                    log(f"🔄 [{symbol}] Executing close_position_percent...", level="INFO")
                    result = await close_position_percent(symbol, 100)
                    log(f"✅ [{symbol}] Position closed successfully | Result: {result}", level="INFO")
                    
                    # Nettoyage avec le BON hash
                    cleanup_trailing_stop(symbol, side, entry_price, amount)
                    
                    # Retirer du tableau
                    if symbol in position_table.positions_data:
                        del position_table.positions_data[symbol]
                    
                except Exception as close_error:
                    log(f"❌ [{symbol}] CLOSE FAILED: {close_error}", level="ERROR")
                    import traceback
                    traceback.print_exc()
                    
            elif dry_run:
                log(f"🔄 [{symbol}] DRY RUN: Would close position", level="INFO")

    except Exception as e:
        log(f"❌ [{symbol}] Error in handle_existing_position_with_table: {e}", level="ERROR")
        import traceback
        traceback.print_exc()


# ========================================
# INSTRUCTIONS D'INTÉGRATION
# ========================================

def integration_guide():
    """
    📋 COMMENT INTÉGRER CE CODE:
    
    1. REMPLACER le contenu de utils/table_display.py par ce fichier
    
    2. Dans live/live_engine.py, MODIFIER la ligne qui appelle handle_existing_position:
    
       ❌ AVANT:
       await handle_existing_position(symbol, real_run, dry_run)
       
       ✅ APRÈS:
       from utils.table_display import handle_existing_position_with_table
       await handle_existing_position_with_table(symbol, real_run, dry_run)
    
    3. VÉRIFIER que live/live_engine.py expose bien ces fonctions:
       - get_position_trailing_stop
       - should_close_position
       - get_position_hash
       - cleanup_trailing_stop
       - TRAILING_STOPS (dict global)
    
    4. TESTER avec un symbole:
       - Attendre qu'une position atteigne +1.0% de PnL
       - Vérifier les logs: "🟢 TRAILING ACTIVATED!"
       - Le tableau doit afficher: "+0.5% 🟢" (ou la valeur calculée)
       - Avant +1.0%, le tableau doit afficher: "-2.0% ⏸️"
    
    5. LOGS À SURVEILLER:
       grep "TRAILING ACTIVATED" logs.txt  # Doit apparaître à +1.0%
       grep "Trailing not active" logs.txt  # Avant +1.0%
       grep "🔍.*Close decision" logs.txt   # Vérification à chaque cycle
    """
    pass
