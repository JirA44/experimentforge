import hashlib
import json
import math
import statistics
from typing import Any

from .models import (
    Direction,
    Evaluation,
    GroupAggregate,
    HypothesisSpec,
    Interval95,
    ProtocolSpec,
    ReplicationCompatibility,
    ReplicationVerdict,
    SynthesisCompatibility,
    Verdict,
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def aggregate(values: list[float]) -> GroupAggregate:
    return GroupAggregate(
        count=len(values),
        mean=statistics.fmean(values),
        sample_variance=statistics.variance(values) if len(values) >= 2 else None,
        minimum=min(values),
        maximum=max(values),
    )


def decide(direction: Direction, minimum_effect: float, lower: float, upper: float) -> Verdict:
    if direction is Direction.GREATER:
        if lower >= minimum_effect:
            return Verdict.SUPPORTED
        if upper <= 0.0:
            return Verdict.REJECTED
        return Verdict.INCONCLUSIVE
    if direction is Direction.LESS:
        if upper <= -minimum_effect:
            return Verdict.SUPPORTED
        if lower >= 0.0:
            return Verdict.REJECTED
        return Verdict.INCONCLUSIVE
    if lower >= minimum_effect or upper <= -minimum_effect:
        return Verdict.SUPPORTED
    if lower >= -minimum_effect and upper <= minimum_effect:
        return Verdict.REJECTED
    return Verdict.INCONCLUSIVE


def compute_evaluation(
    hypothesis: HypothesisSpec,
    protocol: ProtocolSpec,
    observations_by_group: dict[str, list[float]],
) -> tuple[Verdict, dict[str, GroupAggregate], float | None, float | None, Interval95]:
    aggregates = {
        group: aggregate(values)
        for group, values in observations_by_group.items()
        if values
    }
    control = observations_by_group.get(hypothesis.control_group, [])
    treatment = observations_by_group.get(hypothesis.treatment_group, [])
    if (
        len(control) < protocol.min_samples_per_group
        or len(treatment) < protocol.min_samples_per_group
    ):
        return Verdict.INSUFFICIENT, aggregates, None, None, Interval95()

    control_mean = statistics.fmean(control)
    treatment_mean = statistics.fmean(treatment)
    contrast = treatment_mean - control_mean
    control_variance = statistics.variance(control)
    treatment_variance = statistics.variance(treatment)
    standard_error = math.sqrt(
        control_variance / len(control) + treatment_variance / len(treatment)
    )
    margin = 1.96 * standard_error
    lower = contrast - margin
    upper = contrast + margin
    verdict = decide(hypothesis.direction, hypothesis.minimum_effect, lower, upper)
    return verdict, aggregates, contrast, standard_error, Interval95(lower=lower, upper=upper)


def replication_compatibility(
    original_hypothesis: HypothesisSpec,
    original_protocol: ProtocolSpec,
    replication_hypothesis: HypothesisSpec,
    replication_protocol: ProtocolSpec,
) -> ReplicationCompatibility:
    """Compare the pre-declared analytical contract, never client verdicts."""
    return ReplicationCompatibility(
        hypothesis_statement=(
            original_hypothesis.statement.casefold()
            == replication_hypothesis.statement.casefold()
        ),
        group_roles=(
            original_hypothesis.control_group == replication_hypothesis.control_group
            and original_hypothesis.treatment_group == replication_hypothesis.treatment_group
            and set(original_protocol.groups) == set(replication_protocol.groups)
        ),
        direction=original_hypothesis.direction == replication_hypothesis.direction,
        minimum_effect=(
            original_hypothesis.minimum_effect == replication_hypothesis.minimum_effect
        ),
        metric_name=(
            original_protocol.metric_name.casefold()
            == replication_protocol.metric_name.casefold()
        ),
        metric_unit=(
            original_protocol.metric_unit.casefold()
            == replication_protocol.metric_unit.casefold()
        ),
        collection_method=(
            original_protocol.collection_method.casefold()
            == replication_protocol.collection_method.casefold()
        ),
        analysis_method=(
            original_protocol.analysis_method == replication_protocol.analysis_method
        ),
        minimum_sample_plan=(
            original_protocol.min_samples_per_group
            == replication_protocol.min_samples_per_group
        ),
    )


def intervals_overlap(original: Interval95, replication: Interval95) -> bool | None:
    if (
        original.lower is None
        or original.upper is None
        or replication.lower is None
        or replication.upper is None
    ):
        return None
    return max(original.lower, replication.lower) <= min(original.upper, replication.upper)


def qualify_replication(
    compatibility: ReplicationCompatibility,
    original: Evaluation,
    replication: Evaluation,
) -> tuple[ReplicationVerdict, bool | None]:
    """Apply a deliberately conservative deterministic replication rule."""
    overlap = intervals_overlap(original.interval95, replication.interval95)
    if not compatibility.compatible:
        return ReplicationVerdict.INCOMPATIBLE, overlap
    if original.verdict is not Verdict.SUPPORTED:
        return ReplicationVerdict.INSUFFICIENT, overlap
    if replication.verdict in {Verdict.INSUFFICIENT, Verdict.INCONCLUSIVE}:
        return ReplicationVerdict.INSUFFICIENT, overlap
    if replication.verdict is Verdict.SUPPORTED and overlap is True:
        return ReplicationVerdict.REPLICATED, overlap
    return ReplicationVerdict.NOT_REPLICATED, overlap


def synthesis_compatibility(
    contracts: list[tuple[HypothesisSpec, ProtocolSpec]],
) -> SynthesisCompatibility:
    """Compare the analytical contracts of every selected evaluation."""
    if not contracts:
        return SynthesisCompatibility(
            hypothesis_statement=False,
            group_roles=False,
            direction=False,
            minimum_effect=False,
            metric_name=False,
            metric_unit=False,
            analysis_method=False,
        )
    baseline_hypothesis, baseline_protocol = contracts[0]
    others = contracts[1:]
    return SynthesisCompatibility(
        hypothesis_statement=all(
            item[0].statement.casefold() == baseline_hypothesis.statement.casefold()
            for item in others
        ),
        group_roles=all(
            item[0].control_group == baseline_hypothesis.control_group
            and item[0].treatment_group == baseline_hypothesis.treatment_group
            and set(item[1].groups) == set(baseline_protocol.groups)
            for item in others
        ),
        direction=all(item[0].direction == baseline_hypothesis.direction for item in others),
        minimum_effect=all(
            item[0].minimum_effect == baseline_hypothesis.minimum_effect for item in others
        ),
        metric_name=all(
            item[1].metric_name.casefold() == baseline_protocol.metric_name.casefold()
            for item in others
        ),
        metric_unit=all(
            item[1].metric_unit.casefold() == baseline_protocol.metric_unit.casefold()
            for item in others
        ),
        analysis_method=all(
            item[1].analysis_method == baseline_protocol.analysis_method for item in others
        ),
    )


def direction_is_consistent(direction: Direction, effects: list[float]) -> bool:
    if direction is Direction.GREATER:
        return all(effect >= 0.0 for effect in effects)
    if direction is Direction.LESS:
        return all(effect <= 0.0 for effect in effects)
    nonzero_signs = {1 if effect > 0.0 else -1 if effect < 0.0 else 0 for effect in effects}
    return len(nonzero_signs) == 1 and 0 not in nonzero_signs


def worst_effect_index(direction: Direction, effects: list[float]) -> int:
    if direction is Direction.GREATER:
        return min(range(len(effects)), key=lambda index: (effects[index], index))
    if direction is Direction.LESS:
        return max(range(len(effects)), key=lambda index: (effects[index], -index))
    return min(range(len(effects)), key=lambda index: (abs(effects[index]), index))


def fixed_effect_synthesis(
    direction: Direction,
    effects: list[float],
    variances: list[float],
) -> dict[str, Any]:
    """Deterministic inverse-variance synthesis with an explicit variance floor."""
    if len(effects) != len(variances) or len(effects) < 2:
        raise ValueError("at least two effect/variance pairs are required")
    if any(variance < 0.0 or not math.isfinite(variance) for variance in variances):
        raise ValueError("effect variances must be finite and non-negative")
    variance_floor = 1e-12
    weights = [1.0 / max(variance, variance_floor) for variance in variances]
    weight_sum = math.fsum(weights)
    pooled_effect = math.fsum(
        weight * effect for weight, effect in zip(weights, effects, strict=True)
    ) / weight_sum
    pooled_standard_error = math.sqrt(1.0 / weight_sum)
    margin = 1.96 * pooled_standard_error
    cochran_q = math.fsum(
        weight * ((effect - pooled_effect) ** 2)
        for weight, effect in zip(weights, effects, strict=True)
    )
    degrees_of_freedom = len(effects) - 1
    i2 = (
        max(0.0, (cochran_q - degrees_of_freedom) / cochran_q) * 100.0
        if cochran_q > 0.0
        else 0.0
    )
    worst_index = worst_effect_index(direction, effects)
    return {
        "weights": weights,
        "pooled_effect": pooled_effect,
        "pooled_standard_error": pooled_standard_error,
        "interval95": Interval95(
            lower=pooled_effect - margin,
            upper=pooled_effect + margin,
        ),
        "direction_consistent": direction_is_consistent(direction, effects),
        "cochran_q": cochran_q,
        "heterogeneity_i2_percent": i2,
        "worst_index": worst_index,
    }
