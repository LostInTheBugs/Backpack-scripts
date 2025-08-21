# utils/table_display.py
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
            'trailing_stop': position_info.get('trailing_stop', 0.0),
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
            
            table_data.append([
                f"{side_emoji} {pos['symbol']}",
                pos['side'].upper(),
                f"{pos['entry_price']:.6f}",
                f"{pos['mark_price']:.6f}",
                f"{pnl_emoji} {pos['pnl_pct']:+.2f}%",
                f"${pos['pnl_usd']:+.2f}",
                f"{pos['amount']:.4f}",
                pos['duration'],
                f"{pos['trailing_stop']:+.2f}%"
            ])
            
            total_pnl_usd += pos['pnl_usd']
        
        # Trier par PnL décroissant
        table_data.sort(key=lambda x: float(x[5].replace('$', '').replace('+', '')), reverse=True)

# Instance globale
position_table = PositionTableDisplay()

# live/live_engine.py - Version modifiée de handle_existing_position
async def handle_existing_position_with_table(symbol, real_run=True, dry_run=False):
    """Version modifiée qui met à jour le tableau au lieu de logger individuellement"""
    try:
        from utils.position_utils import get_real_positions, safe_float, get_real_pnl
        from utils.table_display import position_table
        from datetime import datetime
        from config.settings import get_config
        from execute.async_wrappers import close_position_percent_async
        
        # ✅ NOUVEAU: Import de la logique de stop loss
        from live.live_engine import get_position_trailing_stop, should_close_position
        
        config = get_config()
        
        # Récupération des positions réelles
        raw_positions = await get_real_positions()
        
        # Parse des positions (en utilisant votre fonction parse_position existante)
        parsed_positions = []
        for p in raw_positions:
            if isinstance(p, dict):
                parsed_positions.append(p)
            elif isinstance(p, str):
                try:
                    import json
                    parsed_pos = json.loads(p.strip()) if p.strip() else None
                    if parsed_pos:
                        parsed_positions.append(parsed_pos)
                except:
                    continue

        pos = next((p for p in parsed_positions if p and p.get("symbol") == symbol), None)
        if not pos:
            # Retirer le symbole du tableau s'il n'y a plus de position
            if symbol in position_table.positions_data:
                del position_table.positions_data[symbol]
            return

        # Conversion sécurisée des valeurs
        side = pos.get("side")
        entry_price = safe_float(pos.get("entry_price"), 0.0)
        amount = safe_float(pos.get("amount"), 0.0)
        leverage = safe_float(pos.get("leverage", 1), 1.0)
        ts = safe_float(pos.get("timestamp", datetime.utcnow().timestamp()), datetime.utcnow().timestamp())

        # Calcul du PnL réel
        pnl_data = await get_real_pnl(symbol, side, entry_price, amount, leverage)
        
        if isinstance(pnl_data, dict):
            pnl_usdc = safe_float(pnl_data.get("pnl_usd", 0), 0.0)
            pnl_percent = safe_float(pnl_data.get("pnl_percent", 0), 0.0)
            mark_price = safe_float(pnl_data.get("mark_price", entry_price), entry_price)
        else:
            pnl_usdc = 0.0
            pnl_percent = 0.0
            mark_price = entry_price

        # Calcul de la durée
        duration_sec = datetime.utcnow().timestamp() - ts
        duration_str = f"{int(duration_sec // 3600)}h{int((duration_sec % 3600) // 60)}m"

        # ✅ NOUVEAU: Mise à jour du trailing stop via la fonction du live_engine
        trailing_stop = await get_position_trailing_stop(symbol, side, entry_price, mark_price)

        # Mettre à jour les données du tableau
        position_info = {
            'side': side,
            'entry_price': entry_price,
            'mark_price': mark_price,
            'pnl_pct': pnl_percent,
            'pnl_usd': pnl_usdc,
            'amount': amount,
            'duration': duration_str,
            'trailing_stop': trailing_stop if trailing_stop else 0.0
        }
        
        position_table.update_position(symbol, position_info)
        
        # Afficher le tableau si nécessaire
        if position_table.should_display():
            position_table.display_positions_table()

        # ✅ NOUVEAU: Logique de fermeture de position avec stop loss
        should_close = should_close_position(pnl_percent, trailing_stop, side, duration_sec, strategy=config.strategy.default_strategy)
        
        # ✅ DEBUG: Log détaillé pour débugger
        log(f"[{symbol}] CLOSE CHECK: PnL={pnl_percent:.2f}%, Trailing={trailing_stop}, Duration={duration_sec}s, ShouldClose={should_close}", level="INFO")
        
        if should_close:
            if real_run:
                try:
                    log(f"[{symbol}] 🎯 Closing position due to stop loss/trailing stop trigger", level="INFO")
                    # ✅ CORRECTION: Utiliser la bonne fonction de fermeture
                    try:
                        await close_position_percent_async(symbol, 100)  # Essayer avec pourcentage
                    except TypeError:
                        # Si ça ne marche pas, essayer sans pourcentage
                        from execute.async_wrappers import close_position_async
                        await close_position_async(symbol)
                    
                    # Nettoyer le trailing stop de la mémoire
                    from live.live_engine import TRAILING_STOPS
                    key = f"{symbol}_{side}_{entry_price}"
                    if key in TRAILING_STOPS:
                        del TRAILING_STOPS[key]
                        log(f"[{symbol}] 🧹 Trailing stop cleaned from memory", level="DEBUG")
                    
                    # Retirer du tableau
                    if symbol in position_table.positions_data:
                        del position_table.positions_data[symbol]
                    
                    log(f"[{symbol}] ✅ Position closed successfully", level="INFO")
                except Exception as e:
                    log(f"[{symbol}] ❌ Error closing position: {e}", level="ERROR")
            elif dry_run:
                log(f"[{symbol}] 🧪 DRY-RUN: Would close position due to stop loss/trailing stop", level="DEBUG")

    except Exception as e:
        log(f"[{symbol}] ❌ Error in handle_existing_position_with_table: {e}", level="ERROR")
        import traceback
        traceback.print_exc()


# Fonction utilitaire pour l'intégration
def integrate_table_display():
    """
    Instructions pour intégrer l'affichage en tableau dans votre code existant:
    
    1. Créer le fichier utils/table_display.py avec le contenu ci-dessus
    
    2. Dans live/live_engine.py, remplacer l'appel à handle_existing_position par:
       await handle_existing_position_with_table(symbol, real_run, dry_run)
    
    3. Optionnel: Ajouter un affichage périodique dans votre boucle principale:
       from utils.table_display import position_table
       # Dans votre boucle principale, ajouter:
       if position_table.should_display():
           position_table.display_positions_table()
    """
    pass