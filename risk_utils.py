def calculate_position_size(entry, stop, account_size, risk_pct):
    if not entry or not stop:
        return 0

    risk_amount = account_size * risk_pct
    risk_per_share = abs(entry - stop)

    if risk_per_share == 0:
        return 0

    qty = risk_amount / risk_per_share
    return int(qty)
