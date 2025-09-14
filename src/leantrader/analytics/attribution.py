def attribute_trade(entry_px, exit_px, sl_px, tp_px, costs, side: str) -> dict:
    # Simple components: entry edge, exit edge, risk (SL/TP), and costs
    if side == "long":
        gross = exit_px - entry_px
    else:
        gross = entry_px - exit_px
    return {
        "gross": gross,
        "costs": costs,
        "net": gross - costs,
        "entry_edge": 0.5 * gross,  # placeholders for demo
        "exit_edge": 0.5 * gross,
    }
