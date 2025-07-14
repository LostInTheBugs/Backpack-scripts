import requests
import json

def get_symbols():
    url = "https://api.backpack.exchange/api/v1/markets"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        print(json.dumps(data, indent=2))  # 🔍 Ajoute cette ligne temporairement
        return []

    except requests.exceptions.RequestException as e:
        print("Erreur lors de la récupération des symboles :", e)
        return []

if __name__ == "__main__":
    get_symbols()
