import re
from typing import Callable, Dict

import pandas as pd
import yaml

from .schema import StrategySpec


def build_feature_registry() -> Dict[str, Callable[[pd.DataFrame], pd.Series]]:
    reg: Dict[str, Callable] = {}

    reg["ema_close_50"] = lambda df: df["close"].ewm(span=50, adjust=False).mean()
    reg["ema_close_200"] = lambda df: df["close"].ewm(span=200, adjust=False).mean()
    reg["adx_14"] = lambda df: df["adx_14"]
    reg["fvg_score"] = lambda df: df["fvg_score"]
    reg["rsi_14"] = lambda df: df["rsi_14"]
    reg["structure_hh_hl"] = lambda df: (df["ms_state"] == "bull").astype(int)
    reg["structure_ll_lh"] = lambda df: (df["ms_state"] == "bear").astype(int)
    reg["rsi_14_div_bull"] = lambda df: (df.get("rsi_div", 0) > 0).astype(int)
    reg["rsi_14_div_bear"] = lambda df: (df.get("rsi_div", 0) < 0).astype(int)
    return reg


def parse_expr(expr: str):
    m = re.match(r"\s*(\w+)\s*([<>]=?|==)\s*([\w\.]+)\s*", expr)
    if not m:
        raise ValueError(f"Bad feature expression: {expr}")
    return m.group(1), m.group(2), m.group(3)


def eval_condition(expr: str, df: pd.DataFrame, reg):
    left, op, right = parse_expr(expr)
    left_val = reg[left](df) if left in reg else df[left]
    try:
        right_val = reg[right](df) if right in reg else float(right)
    except Exception:
        right_val = df[right]
    if op == ">":
        return (left_val > right_val).astype(int)
    if op == "<":
        return (left_val < right_val).astype(int)
    if op == ">=":
        return (left_val >= right_val).astype(int)
    if op == "<=":
        return (left_val <= right_val).astype(int)
    if op == "==":
        return (left_val == right_val).astype(int)
    raise ValueError(op)


def load_strategy(path: str) -> StrategySpec:
    spec = StrategySpec(**yaml.safe_load(open(path)))
    return spec


def compile_strategy(spec: StrategySpec):
    reg = build_feature_registry()

    def strategy_fn(frames):
        base_tf = spec.timeframes[-1]
        df = frames[base_tf]
        outs = []
        for rule in spec.signals:
            entry_hits = [
                eval_condition(c.feature, frames[c.timeframe], reg).reindex(df.index, method="ffill").fillna(0)
                for c in rule.entry
            ]
            entry_ok = (sum(entry_hits) == len(rule.entry)).astype(int)
            confirm_ok = None
            if rule.confirm_any:
                conf_hits = [
                    eval_condition(c.feature, frames[c.timeframe], reg).reindex(df.index, method="ffill").fillna(0)
                    for c in rule.confirm_any
                ]
                confirm_ok = (sum(conf_hits) >= 1).astype(int)
            final = entry_ok if confirm_ok is None else (entry_ok & confirm_ok)
            outs.append(pd.DataFrame({"signal": rule.name, "side": rule.side, "go": final}, index=df.index))
        res = (
            pd.concat(outs, axis=0)
            .groupby(level=0)
            .apply(
                lambda x: (
                    x.loc[x["go"].idxmax()]
                    if (x["go"].max() > 0)
                    else pd.Series({"signal": None, "side": None, "go": 0})
                )
            )
        )
        return res

    return strategy_fn
