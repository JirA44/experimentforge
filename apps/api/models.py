from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Direction(str, Enum):
    GREATER = "greater"
    LESS = "less"
    DIFFERENT = "different"


class Verdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INSUFFICIENT = "INSUFFICIENT"


class ReplicationVerdict(str, Enum):
    REPLICATED = "REPLICATED"
    NOT_REPLICATED = "NOT_REPLICATED"
    INSUFFICIENT = "INSUFFICIENT"
    INCOMPATIBLE = "INCOMPATIBLE"


class SynthesisVerdict(str, Enum):
    CONSISTENT = "CONSISTENT"
    HETEROGENEOUS = "HETEROGENEOUS"
    INSUFFICIENT = "INSUFFICIENT"
    INCOMPATIBLE = "INCOMPATIBLE"


class InfluenceVerdict(str, Enum):
    ROBUST = "ROBUST"
    INFLUENTIAL = "INFLUENTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    INCOMPATIBLE = "INCOMPATIBLE"


class DeviationVerdict(str, Enum):
    ADHERENT = "ADHERENT"
    MINOR_DEVIATIONS = "MINOR_DEVIATIONS"
    MATERIAL_DEVIATIONS = "MATERIAL_DEVIATIONS"
    INSUFFICIENT = "INSUFFICIENT"
    INCOMPATIBLE = "INCOMPATIBLE"


class EffectStabilityQualification(str, Enum):
    STABLE = "STABLE"
    SHIFTED = "SHIFTED"
    INSUFFICIENT = "INSUFFICIENT"
    INCOMPATIBLE = "INCOMPATIBLE"


class ReplicationRobustnessQualification(str, Enum):
    ROBUST = "ROBUST"
    DIVERGENT = "DIVERGENT"
    INSUFFICIENT = "INSUFFICIENT"
    INCOMPATIBLE = "INCOMPATIBLE"


class ReplicationEvidenceCoverageQualification(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    INCOMPATIBLE = "INCOMPATIBLE"


class HypothesisSpec(StrictModel):
    statement: str = Field(min_length=3, max_length=2000)
    control_group: str = Field(min_length=1, max_length=80)
    treatment_group: str = Field(min_length=1, max_length=80)
    direction: Direction
    minimum_effect: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def distinct_groups(self):
        if self.control_group == self.treatment_group:
            raise ValueError("control_group and treatment_group must be distinct")
        return self


class ProtocolSpec(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    groups: list[str] = Field(min_length=2, max_length=8)
    metric_name: str = Field(min_length=1, max_length=160)
    metric_unit: str = Field(min_length=1, max_length=80)
    collection_method: str = Field(min_length=3, max_length=2000)
    seed: int = Field(ge=0, le=2**63 - 1)
    min_samples_per_group: int = Field(default=3, ge=3, le=1_000_000)
    analysis_method: str = Field(
        default="mean-difference-ci95-v1",
        pattern="^mean-difference-ci95-v1$",
    )
    collection_window_start: datetime | None = None
    collection_window_end: datetime | None = None
    allowed_exclusion_reasons: list[str] = Field(default_factory=list, max_length=100)
    max_exclusion_fraction: float = Field(default=0.10, ge=0.0, le=1.0)
    max_missing_fraction: float = Field(default=0.05, ge=0.0, le=1.0)
    analysis_parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_groups(self):
        if len(self.groups) != len(set(self.groups)):
            raise ValueError("groups must be unique")
        if any(not group for group in self.groups):
            raise ValueError("group names must not be empty")
        if (self.collection_window_start is None) != (self.collection_window_end is None):
            raise ValueError("collection window start and end must be declared together")
        if (
            self.collection_window_start is not None
            and self.collection_window_end <= self.collection_window_start
        ):
            raise ValueError("collection window end must be after start")
        if len(self.allowed_exclusion_reasons) != len(set(self.allowed_exclusion_reasons)):
            raise ValueError("allowed exclusion reasons must be unique")
        return self


class ExperimentCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    hypothesis: HypothesisSpec
    initial_protocol: ProtocolSpec

    @model_validator(mode="after")
    def protocol_covers_hypothesis(self):
        required = {self.hypothesis.control_group, self.hypothesis.treatment_group}
        if not required.issubset(set(self.initial_protocol.groups)):
            raise ValueError("protocol groups must include control_group and treatment_group")
        return self


class Experiment(StrictModel):
    id: str
    experiment_hash: str
    name: str
    description: str
    hypothesis: HypothesisSpec
    immutable: bool = True
    created_at: datetime


class ProtocolCreate(StrictModel):
    specification: ProtocolSpec


class ProtocolVersion(StrictModel):
    id: str
    experiment_id: str
    version: int
    protocol_hash: str
    specification: ProtocolSpec
    immutable: bool = True
    idempotent_replay: bool = False
    created_at: datetime


class ObservationCreate(StrictModel):
    idempotency_key: str = Field(min_length=8, max_length=200)
    protocol_version: int = Field(ge=1)
    group: str = Field(min_length=1, max_length=80)
    value: float
    observed_at: datetime
    source_ref: str = Field(min_length=1, max_length=2000)
    subject_ref: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Observation(StrictModel):
    id: str
    experiment_id: str
    protocol_version: int
    group: str
    value: float
    observed_at: datetime
    source_ref: str
    subject_ref: str | None = None
    metadata: dict[str, Any]
    observation_hash: str
    idempotent_replay: bool = False
    created_at: datetime


class EvaluationCreate(StrictModel):
    protocol_version: int = Field(ge=1)


class GroupAggregate(StrictModel):
    count: int
    mean: float
    sample_variance: float | None = None
    minimum: float
    maximum: float


class Interval95(StrictModel):
    lower: float | None = None
    upper: float | None = None


class Evaluation(StrictModel):
    id: str
    experiment_id: str
    protocol_version: int
    method: str
    verdict: Verdict
    aggregates: dict[str, GroupAggregate]
    treatment_minus_control: float | None = None
    standard_error: float | None = None
    interval95: Interval95
    experiment_hash: str
    protocol_hash: str
    observations_snapshot_hash: str
    evaluation_hash: str
    seed: int
    reproducible: bool = True
    idempotent_replay: bool = False
    created_at: datetime
    warning: str = (
        "Une expérience ne prouve pas une vérité universelle ; validité externe, "
        "causalité et biais doivent être évalués séparément."
    )


class ReplicationReportCreate(StrictModel):
    original_experiment_id: str = Field(min_length=1, max_length=200)
    original_protocol_version: int = Field(ge=1)
    replication_experiment_id: str = Field(min_length=1, max_length=200)
    replication_protocol_version: int = Field(ge=1)

    @model_validator(mode="after")
    def distinct_experiments(self):
        if self.original_experiment_id == self.replication_experiment_id:
            raise ValueError("original and replication experiments must be distinct")
        return self


class ReplicationCompatibility(StrictModel):
    hypothesis_statement: bool
    group_roles: bool
    direction: bool
    minimum_effect: bool
    metric_name: bool
    metric_unit: bool
    collection_method: bool
    analysis_method: bool
    minimum_sample_plan: bool

    @property
    def compatible(self) -> bool:
        return all(self.model_dump().values())


class ReplicationEvaluationSnapshot(StrictModel):
    evaluation_id: str
    verdict: Verdict
    treatment_minus_control: float | None = None
    interval95: Interval95
    experiment_hash: str
    protocol_hash: str
    observations_snapshot_hash: str
    evaluation_hash: str
    control_count: int
    treatment_count: int


class ReplicationReport(StrictModel):
    id: str
    original_experiment_id: str
    original_protocol_version: int
    replication_experiment_id: str
    replication_protocol_version: int
    verdict: ReplicationVerdict
    compatibility: ReplicationCompatibility
    original: ReplicationEvaluationSnapshot
    replication: ReplicationEvaluationSnapshot
    intervals_overlap: bool | None = None
    report_hash: str
    immutable: bool = True
    reproducible: bool = True
    idempotent_replay: bool = False
    created_at: datetime
    warning: str = (
        "Un rapport de réplication qualifie uniquement ces deux instantanés et leurs "
        "protocoles ; il ne généralise ni causalité ni vérité universelle."
    )


class SynthesisCreate(StrictModel):
    """Only immutable server-side evaluation identifiers are accepted."""

    evaluation_ids: list[str] = Field(min_length=2, max_length=100)

    @model_validator(mode="after")
    def unique_evaluations(self):
        if len(self.evaluation_ids) != len(set(self.evaluation_ids)):
            raise ValueError("evaluation_ids must be unique")
        return self


class SynthesisCompatibility(StrictModel):
    hypothesis_statement: bool
    group_roles: bool
    direction: bool
    minimum_effect: bool
    metric_name: bool
    metric_unit: bool
    analysis_method: bool

    @property
    def compatible(self) -> bool:
        return all(self.model_dump().values())


class SynthesisEvaluationSnapshot(StrictModel):
    evaluation_id: str
    experiment_id: str
    protocol_version: int
    evaluation_hash: str
    observations_snapshot_hash: str
    effect: float | None = None
    effect_variance: float | None = None
    interval95: Interval95
    weight: float | None = None
    source_verdict: Verdict


class SynthesisReport(StrictModel):
    id: str
    evaluation_ids: list[str]
    experiment_ids: list[str]
    verdict: SynthesisVerdict
    compatibility: SynthesisCompatibility
    evaluations: list[SynthesisEvaluationSnapshot]
    method: str = "fixed-effect-inverse-variance-v1"
    pooled_effect: float | None = None
    pooled_standard_error: float | None = None
    interval95: Interval95
    worst_effect: float | None = None
    worst_interval95: Interval95
    direction_consistent: bool | None = None
    cochran_q: float | None = None
    heterogeneity_i2_percent: float | None = None
    synthesis_hash: str
    immutable: bool = True
    reproducible: bool = True
    idempotent_replay: bool = False
    created_at: datetime
    warning: str = (
        "Cette synthèse qualifie uniquement les instantanés compatibles sélectionnés ; "
        "elle ne démontre ni causalité, ni validité externe, ni vérité universelle."
    )


class InfluenceReportCreate(StrictModel):
    synthesis_id: str = Field(min_length=1, max_length=200)


class LeaveOneOutResult(StrictModel):
    removed_experiment_id: str
    removed_evaluation_ids: list[str]
    remaining_evaluation_count: int
    pooled_effect: float | None = None
    pooled_effect_variance: float | None = None
    interval95: Interval95
    direction_consistent: bool | None = None
    cochran_q: float | None = None
    heterogeneity_i2_percent: float | None = None
    synthesis_qualification: SynthesisVerdict
    delta_pooled_effect: float | None = None
    relative_delta: float | None = None
    direction_changed: bool | None = None
    qualification_changed: bool | None = None
    influential: bool = False


class InfluenceReport(StrictModel):
    id: str
    synthesis_id: str
    source_synthesis_hash: str
    verdict: InfluenceVerdict
    method: str = "leave-one-experiment-out-fixed-effect-v1"
    full_synthesis_qualification: SynthesisVerdict
    full_pooled_effect: float | None = None
    full_pooled_effect_variance: float | None = None
    full_interval95: Interval95
    full_direction_consistent: bool | None = None
    full_cochran_q: float | None = None
    full_heterogeneity_i2_percent: float | None = None
    cases: list[LeaveOneOutResult]
    most_influential_experiment_id: str | None = None
    relative_delta_threshold: float = 0.10
    influence_hash: str
    immutable: bool = True
    reproducible: bool = True
    idempotent_replay: bool = False
    created_at: datetime
    warning: str = (
        "Ce diagnostic mesure la sensibilité de ces instantanés sélectionnés ; "
        "il ne démontre ni causalité, ni validité externe, ni vérité universelle."
    )


class DeviationReportCreate(StrictModel):
    experiment_id: str | None = Field(default=None, min_length=1, max_length=200)
    protocol_version: int | None = Field(default=None, ge=1)
    evaluation_id: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid_reference(self):
        direct = self.experiment_id is not None or self.protocol_version is not None
        if direct and (self.experiment_id is None or self.protocol_version is None):
            raise ValueError("experiment_id and protocol_version must be supplied together")
        if not direct and self.evaluation_id is None:
            raise ValueError("provide experiment/protocol or evaluation_id")
        return self


class DeviationFinding(StrictModel):
    category: str
    code: str
    material: bool
    observed: Any
    planned: Any
    detail: str


class ProtocolDeviationReport(StrictModel):
    id: str
    experiment_id: str
    protocol_version: int
    evaluation_id: str | None = None
    experiment_hash: str
    protocol_hash: str
    observations_snapshot_hash: str
    verdict: DeviationVerdict
    findings: list[DeviationFinding]
    planned_samples_per_required_group: int
    usable_samples_by_group: dict[str, int]
    total_observations: int
    excluded_observations: int
    missing_observations: int
    out_of_window_observations: int
    endpoint_mismatches: int
    parameter_mismatches: int
    sample_materiality_floor: float = 0.80
    out_of_window_material_fraction: float = 0.10
    report_hash: str
    immutable: bool = True
    reproducible: bool = True
    idempotent_replay: bool = False
    created_at: datetime
    warning: str = (
        "Ce dossier décrit des écarts aux artefacts persistés ; il ne constitue ni "
        "certification automatique, ni preuve de causalité ou de vérité universelle."
    )


class EffectStabilityDossierCreate(StrictModel):
    """Only persisted evaluation identifiers are accepted from the client."""

    evaluation_ids: list[str] = Field(min_length=2, max_length=50)

    @model_validator(mode="after")
    def unique_evaluations(self):
        if len(self.evaluation_ids) != len(set(self.evaluation_ids)):
            raise ValueError("evaluation_ids must be unique")
        return self


class EffectStabilityCompatibility(StrictModel):
    same_experiment: bool
    hypothesis_statement: bool
    metric_name: bool
    metric_unit: bool
    group_roles: bool
    direction: bool
    analysis_method: bool

    @property
    def compatible(self) -> bool:
        return all(self.model_dump().values())


class EffectStabilityEvaluationSnapshot(StrictModel):
    evaluation_id: str
    experiment_id: str
    protocol_version: int
    protocol_hash: str
    evaluation_hash: str
    observations_snapshot_hash: str
    effect: float | None = None
    interval95: Interval95


class EffectStabilityTransition(StrictModel):
    from_evaluation_id: str
    to_evaluation_id: str
    from_protocol_version: int
    to_protocol_version: int
    effect_delta: float
    relative_delta: float
    direction_changed: bool
    intervals_overlap: bool
    shifted: bool


class EffectStabilityDossier(StrictModel):
    id: str
    evaluation_ids: list[str]
    experiment_id: str | None = None
    qualification: EffectStabilityQualification
    compatibility: EffectStabilityCompatibility
    evaluations: list[EffectStabilityEvaluationSnapshot]
    transitions: list[EffectStabilityTransition]
    relative_range: float | None = None
    worst_transition: EffectStabilityTransition | None = None
    method: str = "protocol-version-effect-stability-v1"
    relative_delta_threshold: float = 0.10
    dossier_hash: str
    immutable: bool = True
    reproducible: bool = True
    idempotent_replay: bool = False
    created_at: datetime
    warning: str = (
        "Ce dossier décrit la stabilité des effets entre ces versions de protocole ; "
        "il ne certifie ni causalité, ni validité externe, ni vérité."
    )


class ReplicationRobustnessDossierCreate(StrictModel):
    """Only persisted evaluation identifiers are accepted."""

    evaluation_ids: list[str] = Field(min_length=2, max_length=100)

    @model_validator(mode="after")
    def unique_evaluations(self):
        if len(self.evaluation_ids) != len(set(self.evaluation_ids)):
            raise ValueError("evaluation_ids must be unique")
        return self


class ReplicationRobustnessSnapshot(StrictModel):
    evaluation_id: str
    experiment_id: str
    protocol_version: int
    protocol_hash: str
    evaluation_hash: str
    observations_snapshot_hash: str
    effect: float | None = None
    effect_variance: float | None = None
    interval95: Interval95
    source_verdict: Verdict
    deviation_qualification: DeviationVerdict
    deviation_report_hash: str
    sign: int | None = None
    supports_reference: bool | None = None
    contradicts_reference: bool | None = None
    interval_overlaps_reference: bool | None = None
    relative_delta_from_reference: float | None = None


class ReplicationRobustnessTransition(StrictModel):
    from_evaluation_id: str
    to_evaluation_id: str
    effect_delta: float
    relative_delta: float
    direction_changed: bool
    intervals_overlap: bool


class ReplicationRobustnessDossier(StrictModel):
    id: str
    evaluation_ids: list[str]
    qualification: ReplicationRobustnessQualification
    compatibility: SynthesisCompatibility
    reference_evaluation_id: str
    evaluations: list[ReplicationRobustnessSnapshot]
    transitions: list[ReplicationRobustnessTransition]
    supporting_replication_count: int
    contradicting_replication_count: int
    direction_consistent: bool | None = None
    mean_effect: float | None = None
    effect_range: float | None = None
    relative_effect_range: float | None = None
    effect_standard_deviation: float | None = None
    heterogeneity_i2_percent: float | None = None
    worst_replication: ReplicationRobustnessSnapshot | None = None
    worst_transition: ReplicationRobustnessTransition | None = None
    method: str = "multi-evaluation-replication-robustness-v1"
    relative_dispersion_threshold: float = 0.20
    heterogeneity_i2_threshold_percent: float = 50.0
    dossier_hash: str
    immutable: bool = True
    reproducible: bool = True
    idempotent_replay: bool = False
    created_at: datetime
    warning: str = (
        "Ce dossier qualifie uniquement la robustesse documentaire des évaluations "
        "sélectionnées ; il ne conclut ni causalité ni vérité universelle."
    )


class ReplicationEvidenceCoverageDossierCreate(StrictModel):
    """Only persisted evaluation identifiers are accepted."""

    evaluation_ids: list[str] = Field(min_length=2, max_length=100)

    @model_validator(mode="after")
    def unique_evaluations(self):
        if len(self.evaluation_ids) != len(set(self.evaluation_ids)):
            raise ValueError("evaluation_ids must be unique")
        return self


class ReplicationEvidenceCoverageSnapshot(StrictModel):
    evaluation_id: str
    experiment_id: str
    protocol_version: int
    protocol_hash: str
    evaluation_hash: str
    observations_snapshot_hash: str
    source_verdict: Verdict
    deviation_qualification: DeviationVerdict
    deviation_report_hash: str
    covered_checks: list[str]
    gap_codes: list[str]
    covered_check_count: int
    required_check_count: int
    coverage_ratio: float


class ReplicationEvidenceCoverageDossier(StrictModel):
    id: str
    evaluation_ids: list[str]
    experiment_ids: list[str]
    qualification: ReplicationEvidenceCoverageQualification
    compatibility: SynthesisCompatibility
    evaluations: list[ReplicationEvidenceCoverageSnapshot]
    required_checks: list[str]
    common_covered_checks: list[str]
    common_gap_codes: list[str]
    total_gap_count: int
    mean_coverage_ratio: float
    minimum_coverage_ratio: float
    worst_evaluation: ReplicationEvidenceCoverageSnapshot
    method: str = "replication-evidence-protocol-coverage-v1"
    dossier_hash: str
    immutable: bool = True
    reproducible: bool = True
    idempotent_replay: bool = False
    created_at: datetime
    warning: str = (
        "Ce dossier mesure la couverture documentaire des protocoles et instantanés "
        "sélectionnés ; il ne certifie ni réplication, ni causalité, ni vérité universelle."
    )


class AuditEvent(StrictModel):
    sequence: int
    event_type: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    previous_event_hash: str | None = None
    event_hash: str
    created_at: datetime
