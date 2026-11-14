"""The rescue code (SYNC-PLAN §2, legal 06.11.): a new one only in memory – never stored, never uploaded; what goes to
the server is the seed sealed with it (net/vault.rescue_put), and only after the user typed its last 5 characters.

    new_code()            -> "XXXXX XXXXX XXXXX XXXXX XXXXX" (25 characters, the last one a check character; blocks
                             with spaces since 0.9.8 – older ones with dashes stay valid)
    last5_ok(code, last5) -> the typed last 5 characters match (case, spaces and dashes don't matter)
"""
from net import pairing


def new_code():
    return pairing.new_rescue_code()


def last5_ok(code, last5):
    try:
        full = pairing.norm_rescue(code)
    except pairing.PairError:
        return False
    typed = "".join(str(last5 or "").upper().split()).replace("-", "")
    return len(typed) == 5 and full[-5:] == typed
