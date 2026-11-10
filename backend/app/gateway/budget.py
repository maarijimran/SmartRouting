from dataclasses import dataclass


@dataclass
class Budget:
    cap_usd: float
    reserved_usd: float = 0.0
    spent_usd: float = 0.0

    def reserve(self, estimate_usd: float) -> bool:
        if estimate_usd < 0:
            raise ValueError("Budget estimate cannot be negative")
        if self.spent_usd + self.reserved_usd + estimate_usd > self.cap_usd:
            return False
        self.reserved_usd += estimate_usd
        return True

    def settle(self, estimate_usd: float, measured_usd: float) -> None:
        if measured_usd < 0:
            raise ValueError("Measured cost cannot be negative")
        if estimate_usd < 0 or estimate_usd > self.reserved_usd:
            raise ValueError("Unknown budget reservation")
        self.reserved_usd -= estimate_usd
        self.spent_usd += measured_usd
