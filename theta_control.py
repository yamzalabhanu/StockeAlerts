def theta_risk_control(option):
    """Simple theta decay protection rules."""
    dte = option.get("dte", 0)
    theta = option.get("theta")

    if dte <= 3:
        return "EXIT", "Too close to expiry (theta risk high)"

    if theta and abs(theta) > 0.5:
        return "TRIM", "High theta decay"

    return "HOLD", "Theta acceptable"
