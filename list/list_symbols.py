import requests

def get_symbols():
    url = "https://api.backpack.exchange/api/v1/markets"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        symbols = [market['name'] for market in data]
        return symbols

    except requests.exceptions.RequestException as e:
        print("Error :", e)
        return []

if __name__ == "__main__":
    symbols = get_symbols()
    print(f"🔍 {len(symbols)} symboles :\n")
    for symbol in symbols:
        print(symbol)