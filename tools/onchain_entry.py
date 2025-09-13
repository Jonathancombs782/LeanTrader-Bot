from __future__ import annotations

from typing import Any


def build_tx(slippage_bps: int) -> Any:
    # Replace with real encoder for your DEX
    return {"slippage_bps": int(slippage_bps)}


def send_public(tx: Any) -> Any:
    # Replace with JSON-RPC/mempool submission
    return None  # simulate that public path is not used by default


def send_private(tx: Any) -> Any:
    # Replace with Flashbots/MEV-Share submission
    return {"ok": True, "tx": tx}

