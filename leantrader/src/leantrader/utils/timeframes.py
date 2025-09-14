from dataclasses import dataclass


@dataclass(frozen=True)
class TF:
    name: str
    minutes: int


D1 = TF("D1", 1440)
H4 = TF("H4", 240)
H1 = TF("H1", 60)
M15 = TF("M15", 15)
M5 = TF("M5", 5)
M1 = TF("M1", 1)

ALL = [D1, H4, H1, M15, M5, M1]
