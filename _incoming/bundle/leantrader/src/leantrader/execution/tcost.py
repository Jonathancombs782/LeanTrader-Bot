def expected_cost(spread_pts: float) -> float:
    return max(0.0001, spread_pts * 0.2)
