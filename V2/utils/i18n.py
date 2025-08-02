import json
import os
from typing import Dict, Any

class I18n:
    def __init__(self, locale: str = "fr"):
        self.locale = locale
        self.translations = {}
        self.load_translations()
    
    def load_translations(self):
        """Charge les traductions depuis le fichier JSON"""
        try:
            locale_file = os.path.join("locales", f"{self.locale}.json")
            with open(locale_file, 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Fichier de traduction {self.locale}.json introuvable, utilisation du français par défaut")
            try:
                with open("locales/fr.json", 'r', encoding='utf-8') as f:
                    self.translations = json.load(f)
            except FileNotFoundError:
                self.translations = {}
    
    def get(self, key_path: str, *args, **kwargs) -> str:
        """
        Récupère une traduction avec formatage
        key_path: chemin vers la clé (ex: "symbols.update_auto")
        args: arguments pour format()
        """
        keys = key_path.split('.')
        value = self.translations
        
        try:
            for key in keys:
                value = value[key]
            
            # Formatage des arguments
            if args or kwargs:
                return value.format(*args, **kwargs)
            return value
        except (KeyError, TypeError):
            # Retourne la clé si traduction non trouvée
            return f"[MISSING: {key_path}]"
    
    def set_locale(self, locale: str):
        """Change la langue"""
        self.locale = locale
        self.load_translations()

# Instance globale
_i18n = I18n()

def t(key_path: str, *args, **kwargs) -> str:
    """Fonction raccourcie pour les traductions"""
    return _i18n.get(key_path, *args, **kwargs)

def set_locale(locale: str):
    """Change la langue globalement"""
    _i18n.set_locale(locale)

def get_available_locales() -> list:
    """Retourne la liste des langues disponibles"""
    try:
        files = os.listdir("locales")
        return [f.replace('.json', '') for f in files if f.endswith('.json')]
    except FileNotFoundError:
        return ['fr']