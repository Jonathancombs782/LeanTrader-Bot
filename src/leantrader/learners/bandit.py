import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass
class BetaArm:
    alpha: float = 1.0
    beta: float = 1.0

    def sample(self) -> float:
        # naive sampler (replace with numpy.random.beta for more realism)
        import random

        # simple approximation: alpha/(alpha+beta) + noise
        mean = self.alpha / (self.alpha + self.beta)
        return max(0.0, min(1.0, mean + random.uniform(-0.05, 0.05)))

    def update(self, reward: float):
        # treat reward>0 as success
        if reward > 0:
            self.alpha += 1.0
        else:
            self.beta += 1.0


@dataclass
class ContextBandit:
    # context key: (session, regime)
    arms: Dict[Tuple[str, str], Dict[str, BetaArm]] = field(default_factory=lambda: defaultdict(dict))

    def choose(self, session: str, regime: str, policies) -> str:
        key = (session, regime)
        if key not in self.arms:
            self.arms[key] = {p: BetaArm() for p in policies}
            return random.choice(policies)
        draws = {p: arm.sample() for p, arm in self.arms[key].items()}
        return max(draws.items(), key=lambda kv: kv[1])[0]

    def learn(self, session: str, regime: str, policy: str, reward: float):
        key = (session, regime)
        if key not in self.arms or policy not in self.arms[key]:
            self.arms.setdefault(key, {})[policy] = BetaArm()
        self.arms[key][policy].update(reward)
