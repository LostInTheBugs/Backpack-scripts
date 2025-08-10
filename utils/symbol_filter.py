from config.settings import get_config

config = get_config()

def filter_symbols(symbols: list[str], include: list[str] | None, exclude: list[str] | None) -> list[str]:
    filtered = symbols
    if include:
        include_set = set(s.upper() for s in include)
        filtered = [s for s in filtered if s.upper() in include_set]
    if exclude:
        exclude_set = set(s.upper() for s in exclude)
        filtered = [s for s in filtered if s.upper() not in exclude_set]
    return filtered

def filter_symbols_by_config(symbols: list[str]) -> list[str]:
    """
    Filtre les symboles en fonction du settings.yaml :
    - config.symbols.include : garde uniquement ces symboles + les ajoute si manquants
    - config.symbols.exclude : retire définitivement certains symboles
    """
    include_list = getattr(config.symbols, "include", [])
    exclude_list = getattr(config.symbols, "exclude", [])

    # Normaliser en majuscule
    include_list = [s.upper() for s in include_list]
    exclude_list = [s.upper() for s in exclude_list]

    if include_list:
        # Garde uniquement les symboles dans include
        filtered = [s for s in symbols if s.upper() in include_list]
        # Ajoute ceux qui sont dans include mais absents de symbols (pour s'assurer qu'ils soient inclus)
        for s in include_list:
            if s not in filtered:
                filtered.append(s)
    else:
        filtered = symbols.copy()

    # Retirer ceux présents dans exclude
    filtered = [s for s in filtered if s.upper() not in exclude_list]

    return filtered
