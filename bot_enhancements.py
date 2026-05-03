from adaptive_scoring import get_weight, update_weights, load_weights, save_weights
from market_regime import regime_adjustment


_ORIGINAL_BUILD_CANDIDATE_ATTR = "_original_build_candidate_before_enhancements"


def apply_enhancements(bot_cls):
    """Patch StockTechnicalAIBot with adaptive/regime ranking enhancements.

    This keeps bot.py stable while allowing main.py to launch the enhanced runtime.
    The wrapper adjusts candidate ranking after the normal engine accepts a setup.
    """
    if hasattr(bot_cls, _ORIGINAL_BUILD_CANDIDATE_ATTR):
        return bot_cls

    original_build_candidate = bot_cls.build_candidate
    setattr(bot_cls, _ORIGINAL_BUILD_CANDIDATE_ATTR, original_build_candidate)

    async def enhanced_build_candidate(self, ticker):
        candidate = await original_build_candidate(self, ticker)
        if not candidate:
            return None

        entry_mode = candidate.get("entry_mode") or candidate.get("setup", {}).get("entry_mode", "STANDARD")
        market = self.get_market_bias()

        reg_adj = regime_adjustment(entry_mode, market)
        adaptive_bonus = get_weight(entry_mode)

        candidate["market_regime"] = reg_adj.regime
        candidate["regime_reason"] = reg_adj.reason
        candidate["regime_score_adjustment"] = reg_adj.score_adjustment
        candidate["adaptive_score_adjustment"] = adaptive_bonus
        candidate["ranking_score"] = (
            float(candidate.get("ranking_score", 0))
            + float(reg_adj.score_adjustment)
            + float(adaptive_bonus)
        )

        print(
            f"{ticker}: regime={reg_adj.regime} adj={reg_adj.score_adjustment} | "
            f"adaptive={adaptive_bonus} | final_rank={candidate['ranking_score']:.1f}"
        )
        return candidate

    bot_cls.build_candidate = enhanced_build_candidate
    return bot_cls


def learn_from_outcomes(outcomes):
    """Update adaptive weights from outcome rows that include entry_mode/result.

    Safe to call from replay/dashboard tools. Rows without entry_mode or final result are ignored.
    """
    weights = load_weights()

    for row in outcomes:
        entry_mode = row.get("entry_mode")
        result = row.get("result")
        if not entry_mode or result not in {"WIN", "LOSS"}:
            continue
        weights = update_weights(entry_mode, result)

    return weights
