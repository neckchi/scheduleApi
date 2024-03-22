

def deepget(dct: dict, *keys):
    """
    Use function to check the json properties
    """
    for key in keys:
        try:
            dct = dct[key]
        except (TypeError, KeyError):
            return None
    return dct


