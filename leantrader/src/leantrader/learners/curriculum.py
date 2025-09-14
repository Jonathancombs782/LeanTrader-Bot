from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Skill:
    name: str
    enabled: bool = False
    threshold: float = 0.0


@dataclass
class Curriculum:
    skills: Dict[str, Skill] = field(
        default_factory=lambda: {
            "trend_follow": Skill("trend_follow", True, 0.0),
            "range_reversal": Skill("range_reversal", False, 0.1),
            "news_scalp": Skill("news_scalp", False, 0.15),
            "orderflow_fvg": Skill("orderflow_fvg", False, 0.2),
        }
    )

    def gate(self, metric_value: float):
        for s in self.skills.values():
            if not s.enabled and metric_value >= s.threshold:
                s.enabled = True

    def active(self):
        return [s.name for s in self.skills.values() if s.enabled]
