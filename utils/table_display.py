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
        
        # Effacer l'écran et afficher le tableau
        os.system('clear' if os.name == 'posix' else 'cls')
        
        print("=" * 120)
        print(f"🚀 POSITIONS OUVERTES - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"💰 PnL Total: ${total_pnl_usd:+.2f}")
        print("=" * 120)
        
        if table_data:
            headers = [
                "Symbol", "Side", "Entry", "Mark", "PnL %", "PnL $", 
                "Amount", "Duration", "Trailing"
            ]
            
            print(tabulate(
                table_data,
                headers=headers,
                tablefmt="fancy_grid",
                floatfmt=".6f"
            ))
        else:
            print("📭 Aucune position ouverte")
            
        print("=" * 120)
        print()

# Instance globale
position_table = PositionTableDisplay()

# live/live_engine.py - Version modifiée de handle_existing_position
async def handle_existing_position_with_table(symbol, real_run=True, dry_run=False):
    """Version modifiée qui met à jour le tableau au lieu de logger individuellement"""
    try:
        from utils.position_utils import get_real_positions, safe_float, get_real_pnl
        from utils.table_display import position_table
        from datetime import datetime
        
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
        trailing_stop = safe_float(pos.get("trailing_stop", 0), 0.0)

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

        # Mise à jour du trailing stop
        if side == "long":
            new_trailing_stop = max(trailing_stop, pnl_percent - 1.0)
        else:
            new_trailing_stop = min(trailing_stop, pnl_percent + 1.0)

        # Mettre à jour les données du tableau
        position_info = {
            'side': side,
            'entry_price': entry_price,
            'mark_price': mark_price,
            'pnl_pct': pnl_percent,
            'pnl_usd': pnl_usdc,
            'amount': amount,
            'duration': duration_str,
            'trailing_stop': new_trailing_stop
        }
        
        position_table.update_position(symbol, position_info)
        
        # Afficher le tableau si nécessaire
        if position_table.should_display():
            position_table.display_positions_table()

        # Logique de fermeture de position (si nécessaire)
        # ... (votre code existant pour should_close_position)

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