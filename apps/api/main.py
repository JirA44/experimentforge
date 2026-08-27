import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from .models import (
    AuditEvent,
    DeviationReportCreate,
    EffectStabilityDossier,
    EffectStabilityDossierCreate,
    Evaluation,
    EvaluationCreate,
    Experiment,
    ExperimentCreate,
    InfluenceReport,
    InfluenceReportCreate,
    Observation,
    ObservationCreate,
    ProtocolCreate,
    ProtocolDeviationReport,
    ProtocolVersion,
    ReplicationReport,
    ReplicationReportCreate,
    ReplicationRobustnessDossier,
    ReplicationRobustnessDossierCreate,
    ReplicationEvidenceCoverageDossier,
    ReplicationEvidenceCoverageDossierCreate,
    SynthesisCreate,
    SynthesisReport,
)
from .repository import Repository


app = FastAPI(
    title="ExperimentForge API",
    version="1.0.7",
    description=(
        "Registre d'expériences reproductibles : hypothèses et protocoles immuables, "
        "observations brutes append-only, évaluations, réplications et synthèses "
        "multi-expériences, diagnostics d'influence, écarts au protocole, stabilité d'effet "
        "et couverture des preuves de réplication."
    ),
)
DB_PATH = os.getenv(
    "EXPERIMENTFORGE_DB",
    str(Path(__file__).resolve().parents[2] / "experimentforge.db"),
)
repo = Repository(DB_PATH)


def translate_error(exc: Exception):
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=exc.args[0]) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/health")
def health():
    return {"status": "ok", "service": "experimentforge", "version": "1.0.7"}


@app.get("/info")
def info():
    return {
        "service": "experimentforge",
        "version": "1.0.7",
        "replication_method": "replication-direction-and-ci-overlap-v1",
        "synthesis_method": "fixed-effect-inverse-variance-v1",
        "influence_method": "leave-one-experiment-out-fixed-effect-v1",
        "influence_relative_delta_threshold": 0.10,
        "deviation_method": "protocol-execution-deviation-v1",
        "deviation_sample_materiality_floor": 0.80,
        "deviation_out_of_window_material_fraction": 0.10,
        "effect_stability_method": "protocol-version-effect-stability-v1",
        "effect_stability_relative_delta_threshold": 0.10,
        "replication_robustness_method": "multi-evaluation-replication-robustness-v1",
        "replication_robustness_relative_dispersion_threshold": 0.20,
        "replication_robustness_heterogeneity_i2_threshold_percent": 50.0,
        "replication_evidence_coverage_method": "replication-evidence-protocol-coverage-v1",
        "replication_evidence_coverage_required_check_count": 8,
    }


@app.post("/v1/experiments", response_model=Experiment, status_code=201)
def create_experiment(data: ExperimentCreate):
    return repo.create_experiment(data)


@app.get("/v1/experiments", response_model=list[Experiment])
def list_experiments():
    return repo.list_experiments()


@app.get("/v1/experiments/{experiment_id}", response_model=Experiment)
def get_experiment(experiment_id: str):
    try:
        return repo.get_experiment(experiment_id)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.post(
    "/v1/experiments/{experiment_id}/protocols",
    response_model=ProtocolVersion,
    status_code=201,
)
def add_protocol(experiment_id: str, data: ProtocolCreate):
    try:
        return repo.add_protocol(experiment_id, data)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.get(
    "/v1/experiments/{experiment_id}/protocols",
    response_model=list[ProtocolVersion],
)
def list_protocols(experiment_id: str):
    try:
        return repo.list_protocols(experiment_id)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.post(
    "/v1/experiments/{experiment_id}/observations",
    response_model=Observation,
    status_code=201,
)
def add_observation(experiment_id: str, data: ObservationCreate):
    try:
        return repo.add_observation(experiment_id, data)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.get(
    "/v1/experiments/{experiment_id}/observations",
    response_model=list[Observation],
)
def list_observations(
    experiment_id: str,
    protocol_version: int = Query(ge=1),
):
    try:
        return repo.list_observations(experiment_id, protocol_version)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.post(
    "/v1/experiments/{experiment_id}/evaluations",
    response_model=Evaluation,
    status_code=201,
)
def evaluate(experiment_id: str, data: EvaluationCreate):
    try:
        return repo.evaluate(experiment_id, data)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.get(
    "/v1/experiments/{experiment_id}/evaluations",
    response_model=list[Evaluation],
)
def list_evaluations(experiment_id: str):
    try:
        return repo.list_evaluations(experiment_id)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.post(
    "/v1/replication-reports",
    response_model=ReplicationReport,
    status_code=201,
)
def create_replication_report(data: ReplicationReportCreate):
    try:
        return repo.create_replication_report(data)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.get("/v1/replication-reports", response_model=list[ReplicationReport])
def list_replication_reports():
    return repo.list_replication_reports()


@app.get(
    "/v1/replication-reports/{report_id}", response_model=ReplicationReport
)
def get_replication_report(report_id: str):
    try:
        return repo.get_replication_report(report_id)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.post("/v1/syntheses", response_model=SynthesisReport, status_code=201)
def create_synthesis(data: SynthesisCreate):
    try:
        return repo.create_synthesis(data)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.get("/v1/syntheses", response_model=list[SynthesisReport])
def list_syntheses():
    return repo.list_syntheses()


@app.get("/v1/syntheses/{synthesis_id}", response_model=SynthesisReport)
def get_synthesis(synthesis_id: str):
    try:
        return repo.get_synthesis(synthesis_id)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.post(
    "/v1/influence-reports", response_model=InfluenceReport, status_code=201
)
def create_influence_report(data: InfluenceReportCreate):
    try:
        return repo.create_influence_report(data)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.get("/v1/influence-reports", response_model=list[InfluenceReport])
def list_influence_reports():
    return repo.list_influence_reports()


@app.get(
    "/v1/influence-reports/{report_id}", response_model=InfluenceReport
)
def get_influence_report(report_id: str):
    try:
        return repo.get_influence_report(report_id)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.post(
    "/v1/deviation-reports", response_model=ProtocolDeviationReport, status_code=201
)
def create_deviation_report(data: DeviationReportCreate):
    try:
        return repo.create_deviation_report(data)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.get("/v1/deviation-reports", response_model=list[ProtocolDeviationReport])
def list_deviation_reports():
    return repo.list_deviation_reports()


@app.get(
    "/v1/deviation-reports/{report_id}", response_model=ProtocolDeviationReport
)
def get_deviation_report(report_id: str):
    try:
        return repo.get_deviation_report(report_id)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.post(
    "/v1/effect-stability-dossiers",
    response_model=EffectStabilityDossier,
    status_code=201,
)
def create_effect_stability_dossier(data: EffectStabilityDossierCreate):
    try:
        return repo.create_effect_stability_dossier(data)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.get(
    "/v1/effect-stability-dossiers", response_model=list[EffectStabilityDossier]
)
def list_effect_stability_dossiers():
    return repo.list_effect_stability_dossiers()


@app.get(
    "/v1/effect-stability-dossiers/{dossier_id}",
    response_model=EffectStabilityDossier,
)
def get_effect_stability_dossier(dossier_id: str):
    try:
        return repo.get_effect_stability_dossier(dossier_id)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.post(
    "/v1/replication-robustness-dossiers",
    response_model=ReplicationRobustnessDossier,
    status_code=201,
)
def create_replication_robustness_dossier(data: ReplicationRobustnessDossierCreate):
    try:
        return repo.create_replication_robustness_dossier(data)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.get(
    "/v1/replication-robustness-dossiers",
    response_model=list[ReplicationRobustnessDossier],
)
def list_replication_robustness_dossiers():
    return repo.list_replication_robustness_dossiers()


@app.get(
    "/v1/replication-robustness-dossiers/{dossier_id}",
    response_model=ReplicationRobustnessDossier,
)
def get_replication_robustness_dossier(dossier_id: str):
    try:
        return repo.get_replication_robustness_dossier(dossier_id)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.post(
    "/v1/replication-evidence-coverage-dossiers",
    response_model=ReplicationEvidenceCoverageDossier,
    status_code=201,
)
def create_replication_evidence_coverage_dossier(
    data: ReplicationEvidenceCoverageDossierCreate,
):
    try:
        return repo.create_replication_evidence_coverage_dossier(data)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.get(
    "/v1/replication-evidence-coverage-dossiers",
    response_model=list[ReplicationEvidenceCoverageDossier],
)
def list_replication_evidence_coverage_dossiers():
    return repo.list_replication_evidence_coverage_dossiers()


@app.get(
    "/v1/replication-evidence-coverage-dossiers/{dossier_id}",
    response_model=ReplicationEvidenceCoverageDossier,
)
def get_replication_evidence_coverage_dossier(dossier_id: str):
    try:
        return repo.get_replication_evidence_coverage_dossier(dossier_id)
    except (KeyError, ValueError) as exc:
        translate_error(exc)


@app.get(
    "/v1/experiments/{experiment_id}/audit",
    response_model=list[AuditEvent],
)
def list_audit(experiment_id: str):
    try:
        return repo.list_audit(experiment_id)
    except (KeyError, ValueError) as exc:
        translate_error(exc)
