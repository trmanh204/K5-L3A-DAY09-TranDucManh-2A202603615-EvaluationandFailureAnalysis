"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
import numpy as np
from scipy.stats import bootstrap

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    tp = fp = fn = tn = 0
    for h, j in zip(human, judge):
        h_pos = (h == POS)
        j_pos = (j == POS)
        if j_pos and h_pos:
            tp += 1
        elif j_pos and not h_pos:
            fp += 1
        elif not j_pos and h_pos:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    """precision = tp/(tp+fp), recall = tp/(tp+fn); return 0.0 when denominator is 0."""
    cm = confusion(human, judge)
    tp, fp, fn = cm["tp"], cm["fp"], cm["fn"]
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    n = len(human)
    if n == 0:
        raise ValueError("empty input")
    cm = confusion(human, judge)
    tp, fp, fn, tn = cm["tp"], cm["fp"], cm["fn"], cm["tn"]

    p_o = (tp + tn) / n
    h_pos, h_neg = tp + fn, fp + tn
    j_pos, j_neg = tp + fp, fn + tn
    p_e = (h_pos * j_pos + h_neg * j_neg) / (n * n)

    if p_e >= 1.0 or abs(1.0 - p_e) < 1e-12:
        raise ValueError("p_e == 1: constant judge has no signal")

    return (p_o - p_e) / (1.0 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1.0
    if abs(denom) < 1e-12:
        return 0.0
    val = (observed_rate + specificity - 1.0) / denom
    return float(np.clip(val, 0.0, 1.0))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    if all(x == y for x, y in zip(a, b)):
        return (0.0, 0.0, 0.0)

    arr_a = np.array(a, dtype=float)
    arr_b = np.array(b, dtype=float)
    diff = float(np.mean(arr_a) - np.mean(arr_b))

    res = bootstrap(
        (arr_a, arr_b),
        statistic=lambda x, y: np.mean(x) - np.mean(y),
        paired=True,
        n_resamples=n_resamples,
        random_state=np.random.default_rng(rng),
        confidence_level=confidence,
        method="percentile",
    )
    lo = float(res.confidence_interval.low)
    hi = float(res.confidence_interval.high)
    return (diff, lo, hi)


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes."""
    if k > n or k <= 0 or c < 0 or c > n:
        raise ValueError("invalid arguments")
    return float(1.0 - math.comb(n - c, k) / math.comb(n, k))


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass."""
    if k > n or k <= 0 or c < 0 or c > n:
        raise ValueError("invalid arguments")
    return float(math.comb(c, k) / math.comb(n, k))