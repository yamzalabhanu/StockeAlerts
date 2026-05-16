from __future__ import annotations

from typing import Any, Dict, List

from bot_utils import safe_float

ELITE = "ELITE"
HIGH = "HIGH"
GOOD = "GOOD"
SKIP = "SKIP"

DEFAULT_PENALTIES = {
    "execution_bad": -12,
    "execution_warning": -4,
    "setup_reject": -12,
    "setup_warning": -4,
    "mtf_mixed": -5,
    "mtf_poor": -20,
    "vision_poor": -12,
}


def classify_score(score: float) -> str:
    """Convert a 0-100 probabilistic score into alert quality bands."""
    score = safe_float(score, 0) or 0
    if score >= 90:
        return ELITE
    if score >= 80:
        return HIGH
    if score >= 70:
        return GOOD
    return SKIP


def probabilistic_penalty_profile(
    *,
    execution: Dict[str, Any] | None = None,
    setup_quality: Dict[str, Any] | None = None,
    mtf: Dict[str, Any] | None = None,
    vision: Dict[str, Any] | None = None,
    penalties: Dict[str, int] | None = None,
) -> Dict[str, Any]:
    """Translate former hard-reject states into additive score penalties.

    The alert pipeline can still skip low-scoring or high no-trade-risk setups,
    but this profile keeps imperfect early movers in the scoring universe rather
    than rejecting them before ensemble/learning components have a vote.
    """
    execution = execution or {}
    setup_quality = setup_quality or {}
    mtf = mtf or {}
    vision = vision or {}
    penalties = {**DEFAULT_PENALTIES, **(penalties or {})}

    total = 0
    reasons: List[str] = []

    ex_quality = str(execution.get("quality") or "").upper()
    if ex_quality == "BAD":
        total += penalties["execution_bad"]
        reasons.append(f"execution BAD {penalties['execution_bad']:+d}")
    elif ex_quality == "WARNING":
        total += penalties["execution_warning"]
        reasons.append(f"execution WARNING {penalties['execution_warning']:+d}")

    setup_status = str(setup_quality.get("status") or "").upper()
    if setup_status == "REJECT":
        total += penalties["setup_reject"]
        reasons.append(f"setup filter REJECT {penalties['setup_reject']:+d}")
    elif setup_status == "WARNING":
        total += penalties["setup_warning"]
        reasons.append(f"setup filter WARNING {penalties['setup_warning']:+d}")

    mtf_structure = str(mtf.get("structure") or "").upper()
    if mtf_structure == "MIXED_ALIGNMENT":
        total += penalties["mtf_mixed"]
        reasons.append(f"MTF MIXED_ALIGNMENT {penalties['mtf_mixed']:+d}")
    elif mtf_structure and mtf_structure not in {"GOOD_ALIGNMENT", "STRONG_ALIGNMENT"}:
        total += penalties["mtf_poor"]
        reasons.append(f"MTF {mtf_structure} {penalties['mtf_poor']:+d}")

    vision_quality = str(vision.get("quality") or "").upper()
    if vision_quality == "POOR":
        total += penalties["vision_poor"]
        reasons.append(f"vision POOR {penalties['vision_poor']:+d}")

    return {
        "penalty": int(total),
        "confidence_adjustment": int(round(total * 0.65)),
        "reasons": reasons,
        "hard_reject": False,
    }
