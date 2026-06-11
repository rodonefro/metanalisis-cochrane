"""
Meta-analysis statistical engine.
Implements fixed-effects (inverse variance) and random-effects (DerSimonian-Laird)
models for binary (OR, RR, RD) and continuous (MD, SMD/Hedges' g) outcomes.
"""
import math
from typing import List, Optional
from dataclasses import dataclass, field
import numpy as np
from scipy import stats


@dataclass
class StudyEffect:
    study_label: str
    effect: float         # log scale for OR/RR
    variance: float
    weight_fe: float = 0.0
    weight_re: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    year: Optional[int] = None


@dataclass
class MetaResult:
    studies: List[StudyEffect]
    pooled_effect: float
    pooled_lower: float
    pooled_upper: float
    pooled_se: float
    # Heterogeneity
    Q: float
    Q_df: int
    Q_pvalue: float
    I2: float
    tau2: float
    tau: float
    # Model
    model: str          # "fixed" | "random"
    effect_measure: str # "OR" | "RR" | "RD" | "MD" | "SMD"
    k: int              # number of studies
    total_n: int = 0
    # Prediction interval (random effects)
    pi_lower: Optional[float] = None
    pi_upper: Optional[float] = None


# ── Effect size calculators ────────────────────────────────────────────────────

def _safe_log(x: float) -> float:
    return math.log(max(x, 1e-10))


def compute_log_or(a: int, b: int, c: int, d: int):
    """log(OR) and variance using Woolf correction when cell = 0."""
    # Haldane-Anscombe correction if any cell is zero
    if a == 0 or b == 0 or c == 0 or d == 0:
        a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    log_or = _safe_log((a * d) / (b * c))
    var = 1 / a + 1 / b + 1 / c + 1 / d
    return log_or, var


def compute_log_rr(a: int, n1: int, c: int, n2: int):
    """log(RR) and variance."""
    if a == 0 or c == 0:
        a = a + 0.5; c = c + 0.5; n1 = n1 + 0.5; n2 = n2 + 0.5
    p1 = a / n1; p2 = c / n2
    log_rr = _safe_log(p1 / p2)
    var = (1 - p1) / (n1 * p1) + (1 - p2) / (n2 * p2)
    return log_rr, var


def compute_rd(a: int, n1: int, c: int, n2: int):
    """Risk Difference and variance."""
    p1 = a / n1; p2 = c / n2
    rd = p1 - p2
    var = p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2
    return rd, var


def compute_md(mean1: float, sd1: float, n1: int,
               mean2: float, sd2: float, n2: int):
    """Mean Difference and variance."""
    md = mean1 - mean2
    var = sd1 ** 2 / n1 + sd2 ** 2 / n2
    return md, var


def compute_smd_hedges_g(mean1: float, sd1: float, n1: int,
                          mean2: float, sd2: float, n2: int):
    """Hedges' g (bias-corrected SMD) and variance."""
    sp = math.sqrt(((n1 - 1) * sd1 ** 2 + (n2 - 1) * sd2 ** 2) / (n1 + n2 - 2))
    if sp == 0:
        return 0.0, 1.0
    d = (mean1 - mean2) / sp
    # Correction factor J
    df = n1 + n2 - 2
    j = 1 - 3 / (4 * df - 1)
    g = j * d
    var = (n1 + n2) / (n1 * n2) + g ** 2 / (2 * (n1 + n2))
    return g, var


# ── Pooling ────────────────────────────────────────────────────────────────────

def _inverse_variance_fixed(effects: List[float], variances: List[float]):
    weights = [1.0 / v for v in variances]
    pooled = sum(w * e for w, e in zip(weights, effects)) / sum(weights)
    pooled_var = 1.0 / sum(weights)
    return pooled, pooled_var, weights


def _cochran_q(effects: List[float], variances: List[float],
               pooled_fe: float):
    weights = [1.0 / v for v in variances]
    Q = sum(w * (e - pooled_fe) ** 2 for w, e in zip(weights, effects))
    return Q, weights


def _tau2_dl(Q: float, k: int, weights: List[float]) -> float:
    """DerSimonian-Laird estimator of between-study variance."""
    df = k - 1
    C = sum(weights) - sum(w ** 2 for w in weights) / sum(weights)
    tau2 = max(0.0, (Q - df) / C)
    return tau2


def run_meta_analysis(study_data: list, effect_measure: str,
                      model: str = "random") -> MetaResult:
    """
    study_data: list of dicts with keys matching Study model fields.
    effect_measure: "OR" | "RR" | "RD" | "MD" | "SMD"
    model: "fixed" | "random"
    """
    study_effects: List[StudyEffect] = []
    total_n = 0

    for s in study_data:
        label = s.get("study_label", f"{s.get('authors','?')} {s.get('year','')}")
        try:
            if effect_measure in ("OR", "RR", "RD"):
                a = int(s.get("events_intervention") or 0)
                n1 = int(s.get("total_intervention") or 0)
                c = int(s.get("events_control") or 0)
                n2 = int(s.get("total_control") or 0)
                if n1 == 0 or n2 == 0:
                    continue
                total_n += n1 + n2
                if effect_measure == "OR":
                    b, d = n1 - a, n2 - c
                    eff, var = compute_log_or(a, b, c, d)
                elif effect_measure == "RR":
                    eff, var = compute_log_rr(a, n1, c, n2)
                else:
                    eff, var = compute_rd(a, n1, c, n2)

            elif effect_measure in ("MD", "SMD"):
                m1 = s.get("mean_intervention"); sd1 = s.get("sd_intervention")
                n1 = s.get("n_intervention"); m2 = s.get("mean_control")
                sd2 = s.get("sd_control"); n2 = s.get("n_control")
                if any(v is None for v in [m1, sd1, n1, m2, sd2, n2]):
                    continue
                n1, n2 = int(n1), int(n2)
                total_n += n1 + n2
                if effect_measure == "MD":
                    eff, var = compute_md(float(m1), float(sd1), n1,
                                         float(m2), float(sd2), n2)
                else:
                    eff, var = compute_smd_hedges_g(float(m1), float(sd1), n1,
                                                    float(m2), float(sd2), n2)

            elif effect_measure == "PRECALCULATED":
                eff = float(s.get("effect_size") or 0)
                lo = float(s.get("effect_size_lower") or (eff - 1))
                hi = float(s.get("effect_size_upper") or (eff + 1))
                se = (hi - lo) / (2 * 1.96)
                var = se ** 2
            else:
                continue

            if var <= 0 or math.isnan(eff) or math.isinf(eff):
                continue

            study_effects.append(StudyEffect(
                study_label=label,
                effect=eff,
                variance=var,
                year=s.get("year"),
            ))

        except (TypeError, ValueError, ZeroDivisionError):
            continue

    k = len(study_effects)
    if k == 0:
        raise ValueError("No hay estudios con datos suficientes para el análisis.")

    effects = [s.effect for s in study_effects]
    variances = [s.variance for s in study_effects]

    # Fixed effects
    pooled_fe, var_fe, weights_fe = _inverse_variance_fixed(effects, variances)
    Q, _ = _cochran_q(effects, variances, pooled_fe)
    Q_df = k - 1
    Q_pvalue = float(1 - stats.chi2.cdf(Q, df=Q_df)) if Q_df > 0 else 1.0
    I2 = max(0.0, (Q - Q_df) / Q * 100) if Q > 0 else 0.0
    tau2 = _tau2_dl(Q, k, weights_fe) if model == "random" else 0.0
    tau = math.sqrt(tau2)

    # Random effects weights
    weights_re = [1.0 / (v + tau2) for v in variances]
    pooled_re = sum(w * e for w, e in zip(weights_re, effects)) / sum(weights_re)
    var_re = 1.0 / sum(weights_re)

    pooled = pooled_re if model == "random" else pooled_fe
    pooled_var = var_re if model == "random" else var_fe
    pooled_se = math.sqrt(pooled_var)
    z = stats.norm.ppf(0.975)

    pooled_lower = pooled - z * pooled_se
    pooled_upper = pooled + z * pooled_se

    # Prediction interval (random effects only)
    pi_lower = pi_upper = None
    if model == "random" and k >= 3:
        t_val = stats.t.ppf(0.975, df=max(k - 2, 1))
        pi_lower = pooled - t_val * math.sqrt(pooled_var + tau2)
        pi_upper = pooled + t_val * math.sqrt(pooled_var + tau2)

    # Per-study CIs and weights
    for i, se_obj in enumerate(study_effects):
        se_i = math.sqrt(variances[i])
        se_obj.ci_lower = effects[i] - z * se_i
        se_obj.ci_upper = effects[i] + z * se_i
        se_obj.weight_fe = weights_fe[i] / sum(weights_fe) * 100
        se_obj.weight_re = weights_re[i] / sum(weights_re) * 100

    return MetaResult(
        studies=study_effects,
        pooled_effect=pooled,
        pooled_lower=pooled_lower,
        pooled_upper=pooled_upper,
        pooled_se=pooled_se,
        Q=Q,
        Q_df=Q_df,
        Q_pvalue=Q_pvalue,
        I2=I2,
        tau2=tau2,
        tau=tau,
        model=model,
        effect_measure=effect_measure,
        k=k,
        total_n=total_n,
        pi_lower=pi_lower,
        pi_upper=pi_upper,
    )


def back_transform(value: float, effect_measure: str) -> float:
    """Convert log-scale back to original scale for OR/RR."""
    if effect_measure in ("OR", "RR"):
        return math.exp(value)
    return value


def result_to_dict(result: MetaResult) -> dict:
    """Serialize MetaResult to JSON-compatible dict (back-transformed)."""
    bt = lambda v: back_transform(v, result.effect_measure)
    is_log = result.effect_measure in ("OR", "RR")

    studies_out = []
    for s in result.studies:
        studies_out.append({
            "label": s.study_label,
            "effect": bt(s.effect),
            "ci_lower": bt(s.ci_lower),
            "ci_upper": bt(s.ci_upper),
            "weight_fe": round(s.weight_fe, 1),
            "weight_re": round(s.weight_re, 1),
            "year": s.year,
        })

    return {
        "studies": studies_out,
        "pooled": {
            "effect": bt(result.pooled_effect),
            "ci_lower": bt(result.pooled_lower),
            "ci_upper": bt(result.pooled_upper),
            "se": result.pooled_se,
        },
        "heterogeneity": {
            "Q": round(result.Q, 2),
            "Q_df": result.Q_df,
            "Q_pvalue": round(result.Q_pvalue, 4),
            "I2": round(result.I2, 1),
            "tau2": round(result.tau2, 4),
            "tau": round(result.tau, 4),
        },
        "model": result.model,
        "effect_measure": result.effect_measure,
        "k": result.k,
        "total_n": result.total_n,
        "prediction_interval": {
            "lower": bt(result.pi_lower) if result.pi_lower is not None else None,
            "upper": bt(result.pi_upper) if result.pi_upper is not None else None,
        },
    }
