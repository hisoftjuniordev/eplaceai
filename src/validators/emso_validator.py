"""EMŠO (Enotna matična številka občana) validator.

Format: DDMMYYYRSSS K
  DD   – dan rojstva (01-31)
  MM   – mesec rojstva (01-12)
  YYY  – zadnje 3 cifre leta (npr. 990 za 1990)
  R    – regijska koda (1-9)
  SSS  – zaporedna številka (000-999)
  K    – kontrolna cifra (mod 11)
"""


def validate_emso(emso: str) -> str:
    """Vrni EMŠO nespremenjen ali vrzi ValueError."""
    if len(emso) != 13 or not emso.isdigit():
        raise ValueError("EMŠO mora vsebovati natanko 13 številk")

    weights = [7, 6, 5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(emso[i]) * weights[i] for i in range(12))
    remainder = total % 11
    check = 0 if remainder == 0 else 11 - remainder

    if check == 10:
        raise ValueError("EMŠO ima neveljavno kontrolno cifro (rezultat 10)")
    if check != int(emso[12]):
        raise ValueError(
            f"EMŠO kontrolna cifra ni veljavna (pričakovano {check}, dobljeno {emso[12]})"
        )
    return emso
