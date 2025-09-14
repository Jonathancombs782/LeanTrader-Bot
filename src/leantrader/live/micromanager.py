from typing import Dict, Literal

import pandas as pd

from ..learners.bandit import ContextBandit
from ..learners.replay import ReplayBuffer, TradeRecord
from ..sessions.manager import SessionBook, update_session_stats, which_session
from .signal_service import generate_signals


class MicroManager:
    def __init__(self, pair: str):
        self.pair = pair
        self.book = SessionBook(pair)
        self.bandit = ContextBandit()
        self.replay = ReplayBuffer()

    def step(self, frames: Dict[str, pd.DataFrame], regime: Literal["trend", "range", "news"] = "trend"):
        sigs = generate_signals(frames, self.pair)
        if len(sigs) == 0:
            return None
        last = sigs.iloc[-1]
        ts = sigs.index[-1]
        sess = which_session(pd.Timestamp(ts))
        # choose a policy (house_smc vs trader ensemble hook)
        pol = self.bandit.choose(sess, regime, policies=["house_smc", "trader_ensemble"])
        # reward proxy: +1 if signal exists and go==1, else 0
        reward = float(last.get("go", 0) > 0)
        self.bandit.learn(sess, regime, pol, reward)
        # Dummy replay record (replace with real outcome after trade is closed)
        self.replay.add(
            TradeRecord(
                ts=str(ts),
                pair=self.pair,
                session=sess,
                regime=regime,
                policy=pol,
                features={"adx_14": float(frames["M15"].get("adx_14", 0).iloc[-1]) if "M15" in frames else 0.0},
                outcome=0.0,
                costs=0.0,
            )
        )
        update_session_stats(self.book, sess, pnl=0.0, win=bool(reward))
        return {"ts": str(ts), "session": sess, "policy": pol, "reward": reward}
