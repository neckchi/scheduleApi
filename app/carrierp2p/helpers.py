from functools import cache
import csv

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

@cache
def check_loop(file_path,scac:str,loop_code:str = None,loop_name:str = None):
    """
    Check if the loop code/loop name exists in SCT
    """
    with open(file_path, mode="r") as loop:
        reader = csv.reader(loop)
        for row in reader:
            if (loop_code and scac == row[0] and loop_code == row[1]) or (loop_name and scac == row[0] and loop_name == row[2]):
                return True
    return False