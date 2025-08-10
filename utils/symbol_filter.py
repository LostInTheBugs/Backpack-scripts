from config.settings import config

def filter_symbols(symbols: list[str], include: list[str] | None, exclude: list[str] | None) -> list[str]:
    filtered = symbols
    if include:
        # Ne garder que ceux dans include
        include_set = set(include)
        filtered = [s for s in filtered if s in include_set]
    if exclude:
        exclude_set = set(exclude)
        filtered = [s for s in filtered if s not in exclude_set]
    return filtered

def filter_symbols_by_config(symbols: list) -> list:
    """
    Filtre les symboles en fonction du settings.yaml :
    - symbols.include : ajoute ou garde uniquement certains symboles
    - symbols.exclude : retire définitivement certains symboles
    """
    include_list = getattr(config.symbols, "include", [])
    exclude_list = getattr(config.symbols, "exclude", [])

    # On normalise en majuscule
    include_list = [s.upper() for s in include_list]
    exclude_list = [s.upper() for s in exclude_list]

    # Si "include" est défini → on garde uniquement ceux listés + on ajoute ceux absents du top N
    if include_list:
        filtered = [s for s in symbols if s.upper() in include_list]
        for s in include_list:
            if s not in filtered:
                filtered.append(s)
    else:
        filtered = symbols.copy()

    # Retire ceux en "exclude"
    filtered = [s for s in filtered if s.upper() not in exclude_list]

    return filtered