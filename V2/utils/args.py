import argparse

parser = argparse.ArgumentParser(description="Bot de trading Backpack")

parser.add_argument("symbols", nargs="?", default="", help="Liste des symboles (ex: BTC_USDC_PERP,SOL_USDC_PERP)")
parser.add_argument("--auto-select", action="store_true", help="Sélection automatique des symboles les plus volatils")
parser.add_argument('--real-run', action='store_true', help='Lancer en mode réel')
parser.add_argument('--dry-run', action='store_true', help='Lancer en mode simulation')
parser.add_argument('--backtest', action='store_true', help='Activer le mode backtest')
parser.add_argument('--strategie', type=str, default="Default", help='Stratégie à utiliser : Default, Trix, Combo')

args = parser.parse_args()
