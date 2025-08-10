from utils.fetch_top_n_volatility_volume import fetch_top_n_volatility_volume

def get_top_symbols(top_n=10):
    """
    Retourne la liste des top_n symboles les plus volatils
    avec volume suffisant (≥ seuil défini dans fetch_top_n_volatility_volume).
    """
    try:
        symbols = fetch_top_n_volatility_volume(n=top_n)
        return symbols
    except Exception as e:
        print(f"❌ Erreur récupération des symboles : {e}")
        return []
