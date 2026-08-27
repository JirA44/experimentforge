from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.main import app
from apps.api.models import (
    EvaluationCreate,
    DeviationReportCreate,
    EffectStabilityDossierCreate,
    ExperimentCreate,
    HypothesisSpec,
    InfluenceReportCreate,
    ObservationCreate,
    ProtocolCreate,
    ProtocolSpec,
    ReplicationReportCreate,
    ReplicationRobustnessDossierCreate,
    ReplicationEvidenceCoverageDossierCreate,
    SynthesisCreate,
)
from apps.api.repository import Repository


def experiment_data(
    direction="greater",
    minimum_effect=0.5,
    min_samples=3,
    name="Effet du traitement",
    metric_name="score",
    collection_method="Mesure instrumentale en aveugle",
):
    return ExperimentCreate(
        name=name,
        description="Plan reproductible de démonstration",
        hypothesis=HypothesisSpec(
            statement="Le traitement améliore la métrique",
            control_group="control",
            treatment_group="treatment",
            direction=direction,
            minimum_effect=minimum_effect,
        ),
        initial_protocol=ProtocolSpec(
            name="Protocole principal",
            groups=["control", "treatment"],
            metric_name=metric_name,
            metric_unit="point",
            collection_method=collection_method,
            seed=20260822,
            min_samples_per_group=min_samples,
        ),
    )


def add_values(repo, experiment_id, group, values):
    for index, value in enumerate(values):
        repo.add_observation(
            experiment_id,
            ObservationCreate(
                idempotency_key=f"{group}-sample-{index:03d}",
                protocol_version=1,
                group=group,
                value=value,
                observed_at=datetime(2026, 8, 22, index, tzinfo=timezone.utc),
                source_ref=f"instrument://run/{group}/{index}",
                subject_ref=f"subject-{group}-{index}",
                metadata={"operator": "automated"},
            ),
        )


def test_minimum_sample_guard_and_idempotent_evaluation():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment = repo.create_experiment(experiment_data())
        add_values(repo, experiment.id, "control", [1.0, 1.1])
        add_values(repo, experiment.id, "treatment", [3.0, 3.1])
        first = repo.evaluate(experiment.id, EvaluationCreate(protocol_version=1))
        second = repo.evaluate(experiment.id, EvaluationCreate(protocol_version=1))
        assert first.verdict.value == "INSUFFICIENT"
        assert first.treatment_minus_control is None
        assert second.id == first.id
        assert second.evaluation_hash == first.evaluation_hash
        assert second.idempotent_replay is True


@pytest.mark.parametrize(
    "control,treatment,expected",
    [
        ([0.9, 1.0, 1.1], [2.9, 3.0, 3.1], "SUPPORTED"),
        ([2.9, 3.0, 3.1], [0.9, 1.0, 1.1], "REJECTED"),
        ([1.0, 2.0, 3.0], [1.1, 2.1, 3.1], "INCONCLUSIVE"),
    ],
)
def test_server_computes_conservative_verdicts(control, treatment, expected):
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment = repo.create_experiment(experiment_data())
        add_values(repo, experiment.id, "control", control)
        add_values(repo, experiment.id, "treatment", treatment)
        result = repo.evaluate(experiment.id, EvaluationCreate(protocol_version=1))
        assert result.verdict.value == expected
        assert result.aggregates["control"].count == 3
        assert result.aggregates["treatment"].count == 3
        assert result.protocol_hash and result.observations_snapshot_hash
        assert result.seed == 20260822


def test_protocol_versions_and_observation_idempotence_are_immutable():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment = repo.create_experiment(experiment_data())
        changed = ProtocolCreate(
            specification=ProtocolSpec(
                name="Protocole réplication",
                groups=["control", "treatment"],
                metric_name="score",
                metric_unit="point",
                collection_method="Réplication indépendante en aveugle",
                seed=99,
                min_samples_per_group=5,
            )
        )
        second = repo.add_protocol(experiment.id, changed)
        replay = repo.add_protocol(experiment.id, changed)
        assert second.version == 2
        assert replay.id == second.id and replay.idempotent_replay is True
        assert [item.version for item in repo.list_protocols(experiment.id)] == [1, 2]

        observation = ObservationCreate(
            idempotency_key="stable-key-0001",
            protocol_version=1,
            group="control",
            value=4.0,
            observed_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
            source_ref="instrument://stable/1",
        )
        first = repo.add_observation(experiment.id, observation)
        same = repo.add_observation(experiment.id, observation)
        assert same.id == first.id and same.idempotent_replay is True

        changed_observation = observation.model_copy(update={"value": 5.0})
        with pytest.raises(ValueError, match="already used"):
            repo.add_observation(experiment.id, changed_observation)


def test_client_cannot_supply_verdict_and_unknown_group_is_rejected():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvaluationCreate(protocol_version=1, verdict="SUPPORTED")
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment = repo.create_experiment(experiment_data())
        with pytest.raises(ValueError, match="not declared"):
            repo.add_observation(
                experiment.id,
                ObservationCreate(
                    idempotency_key="unknown-group-001",
                    protocol_version=1,
                    group="undeclared",
                    value=1.0,
                    observed_at=datetime.now(timezone.utc),
                    source_ref="instrument://unknown",
                ),
            )


def test_audit_is_hash_chained_and_append_only():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment = repo.create_experiment(experiment_data())
        events = repo.list_audit(experiment.id)
        assert len(events) == 2
        assert events[0].previous_event_hash is None
        assert events[1].previous_event_hash == events[0].event_hash
        with repo.connect() as connection:
            with pytest.raises(Exception, match="append-only"):
                connection.execute("DELETE FROM audit_events")


def make_replication_pair(repo, replication_overrides=None):
    replication_overrides = replication_overrides or {}
    original = repo.create_experiment(experiment_data())
    replication = repo.create_experiment(
        experiment_data(name="Réplication indépendante", **replication_overrides)
    )
    return original, replication


def replication_request(original_id, replication_id):
    return ReplicationReportCreate(
        original_experiment_id=original_id,
        original_protocol_version=1,
        replication_experiment_id=replication_id,
        replication_protocol_version=1,
    )


def test_replication_report_is_computed_idempotent_and_immutable():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        original, replication = make_replication_pair(repo)
        add_values(repo, original.id, "control", [0.9, 1.0, 1.1])
        add_values(repo, original.id, "treatment", [2.9, 3.0, 3.1])
        add_values(repo, replication.id, "control", [1.0, 1.1, 1.2])
        add_values(repo, replication.id, "treatment", [2.8, 2.9, 3.0])

        request = replication_request(original.id, replication.id)
        first = repo.create_replication_report(request)
        replay = repo.create_replication_report(request)

        assert first.verdict.value == "REPLICATED"
        assert first.compatibility.compatible is True
        assert first.intervals_overlap is True
        assert first.original.treatment_minus_control == pytest.approx(2.0)
        assert first.replication.treatment_minus_control == pytest.approx(1.8)
        assert first.original.observations_snapshot_hash
        assert first.replication.observations_snapshot_hash
        assert replay.id == first.id
        assert replay.report_hash == first.report_hash
        assert replay.idempotent_replay is True
        assert repo.get_replication_report(first.id).report_hash == first.report_hash
        assert len(repo.list_replication_reports()) == 1

        with repo.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                connection.execute(
                    "UPDATE replication_reports SET verdict='NOT_REPLICATED' WHERE id=?",
                    (first.id,),
                )

        events = repo.list_audit(original.id)
        report_events = [event for event in events if event.event_type == "REPLICATION_REPORT_FROZEN"]
        assert len(report_events) == 1
        assert report_events[0].payload["report_hash"] == first.report_hash


def test_replication_report_detects_non_replication():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        original, replication = make_replication_pair(repo)
        add_values(repo, original.id, "control", [0.9, 1.0, 1.1])
        add_values(repo, original.id, "treatment", [2.9, 3.0, 3.1])
        add_values(repo, replication.id, "control", [3.0, 3.1, 3.2])
        add_values(repo, replication.id, "treatment", [1.0, 1.1, 1.2])
        report = repo.create_replication_report(
            replication_request(original.id, replication.id)
        )
        assert report.verdict.value == "NOT_REPLICATED"
        assert report.replication.verdict.value == "REJECTED"
        assert report.intervals_overlap is False


def test_replication_report_is_insufficient_when_replication_is_underpowered():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        original, replication = make_replication_pair(repo)
        add_values(repo, original.id, "control", [0.9, 1.0, 1.1])
        add_values(repo, original.id, "treatment", [2.9, 3.0, 3.1])
        add_values(repo, replication.id, "control", [1.0, 1.1])
        add_values(repo, replication.id, "treatment", [3.0, 3.1])
        report = repo.create_replication_report(
            replication_request(original.id, replication.id)
        )
        assert report.verdict.value == "INSUFFICIENT"
        assert report.replication.verdict.value == "INSUFFICIENT"
        assert report.intervals_overlap is None


def test_replication_report_rejects_incompatible_metric_contract():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        original, replication = make_replication_pair(
            repo, {"metric_name": "latence"}
        )
        for experiment in (original, replication):
            add_values(repo, experiment.id, "control", [0.9, 1.0, 1.1])
            add_values(repo, experiment.id, "treatment", [2.9, 3.0, 3.1])
        report = repo.create_replication_report(
            replication_request(original.id, replication.id)
        )
        assert report.verdict.value == "INCOMPATIBLE"
        assert report.compatibility.metric_name is False
        assert report.original.evaluation_hash
        assert report.replication.evaluation_hash


def test_replication_input_forbids_client_verdict_and_same_experiment():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReplicationReportCreate(
            original_experiment_id="original",
            original_protocol_version=1,
            replication_experiment_id="replication",
            replication_protocol_version=1,
            verdict="REPLICATED",
        )
    with pytest.raises(ValidationError, match="must be distinct"):
        replication_request("same", "same")


def test_health_and_static_runtime_openapi_contracts():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "experimentforge",
        "version": "1.0.7",
    }
    info_response = client.get("/info")
    assert info_response.status_code == 200
    assert info_response.json()["version"] == "1.0.7"
    assert info_response.json()["synthesis_method"] == "fixed-effect-inverse-variance-v1"
    assert info_response.json()["influence_method"] == "leave-one-experiment-out-fixed-effect-v1"
    assert info_response.json()["influence_relative_delta_threshold"] == 0.10
    assert info_response.json()["deviation_method"] == "protocol-execution-deviation-v1"
    assert info_response.json()["deviation_sample_materiality_floor"] == 0.80
    runtime = app.openapi()
    static_path = Path(__file__).parents[1] / "packages" / "contracts" / "openapi.yaml"
    static = yaml.safe_load(static_path.read_text(encoding="utf-8"))
    assert static["openapi"] == "3.1.0"
    assert static["info"]["title"] == runtime["info"]["title"]
    assert static["info"]["version"] == runtime["info"]["version"] == "1.0.7"
    assert set(static["paths"]) == set(runtime["paths"])
    assert static == runtime


def evaluated_experiment(repo, name, control, treatment, **overrides):
    experiment = repo.create_experiment(experiment_data(name=name, **overrides))
    add_values(repo, experiment.id, "control", control)
    add_values(repo, experiment.id, "treatment", treatment)
    evaluation = repo.evaluate(experiment.id, EvaluationCreate(protocol_version=1))
    return experiment, evaluation


def test_synthesis_consistent_recalculates_effects_and_fixed_weights():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        first_experiment, first = evaluated_experiment(
            repo, "Étude A", [0.0, 1.0, 2.0], [2.0, 3.0, 4.0]
        )
        second_experiment, second = evaluated_experiment(
            repo, "Étude B", [1.0, 2.0, 3.0], [3.0, 4.0, 5.0]
        )
        report = repo.create_synthesis(
            SynthesisCreate(evaluation_ids=[first.id, second.id])
        )
        assert report.verdict.value == "CONSISTENT"
        assert report.experiment_ids == sorted([first_experiment.id, second_experiment.id])
        assert report.pooled_effect == pytest.approx(2.0)
        assert report.worst_effect == pytest.approx(2.0)
        assert report.direction_consistent is True
        assert report.cochran_q == pytest.approx(0.0)
        assert report.heterogeneity_i2_percent == pytest.approx(0.0)
        assert report.interval95.lower < 2.0 < report.interval95.upper
        assert all(snapshot.effect_variance == pytest.approx(2.0 / 3.0) for snapshot in report.evaluations)
        assert all(snapshot.weight == pytest.approx(1.5) for snapshot in report.evaluations)
        assert "vérité universelle" in report.warning


def test_synthesis_opposite_effects_are_heterogeneous():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, first = evaluated_experiment(
            repo, "Étude positive", [0.9, 1.0, 1.1], [2.9, 3.0, 3.1]
        )
        _, second = evaluated_experiment(
            repo, "Étude opposée", [2.9, 3.0, 3.1], [0.9, 1.0, 1.1]
        )
        report = repo.create_synthesis(
            SynthesisCreate(evaluation_ids=[first.id, second.id])
        )
        assert report.verdict.value == "HETEROGENEOUS"
        assert report.direction_consistent is False
        assert report.heterogeneity_i2_percent > 99.0
        assert report.worst_effect == pytest.approx(-2.0)
        assert report.worst_interval95.upper < 0.0


def test_synthesis_is_insufficient_for_underpowered_evaluation():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, complete = evaluated_experiment(
            repo, "Étude complète", [0.9, 1.0, 1.1], [2.9, 3.0, 3.1]
        )
        _, underpowered = evaluated_experiment(
            repo, "Étude courte", [1.0, 1.1], [3.0, 3.1]
        )
        report = repo.create_synthesis(
            SynthesisCreate(evaluation_ids=[complete.id, underpowered.id])
        )
        assert report.verdict.value == "INSUFFICIENT"
        assert report.pooled_effect is None
        assert report.cochran_q is None
        assert report.evaluations[1].effect is None or report.evaluations[0].effect is None


def test_synthesis_rejects_incompatible_metric_and_unit_contract():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, first = evaluated_experiment(
            repo, "Score", [0.9, 1.0, 1.1], [2.9, 3.0, 3.1]
        )
        _, second = evaluated_experiment(
            repo,
            "Latence",
            [0.9, 1.0, 1.1],
            [2.9, 3.0, 3.1],
            metric_name="latence",
        )
        report = repo.create_synthesis(
            SynthesisCreate(evaluation_ids=[first.id, second.id])
        )
        assert report.verdict.value == "INCOMPATIBLE"
        assert report.compatibility.metric_name is False
        assert report.pooled_effect is None


def test_synthesis_is_idempotent_order_independent_audited_and_immutable():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        first_experiment, first = evaluated_experiment(
            repo, "Étude A", [0.0, 1.0, 2.0], [2.0, 3.0, 4.0]
        )
        _, second = evaluated_experiment(
            repo, "Étude B", [1.0, 2.0, 3.0], [3.0, 4.0, 5.0]
        )
        initial = repo.create_synthesis(
            SynthesisCreate(evaluation_ids=[first.id, second.id])
        )
        replay = repo.create_synthesis(
            SynthesisCreate(evaluation_ids=[second.id, first.id])
        )
        assert replay.id == initial.id
        assert replay.synthesis_hash == initial.synthesis_hash
        assert replay.idempotent_replay is True
        assert repo.get_synthesis(initial.id).synthesis_hash == initial.synthesis_hash
        assert len(repo.list_syntheses()) == 1
        events = repo.list_audit(first_experiment.id)
        frozen = [event for event in events if event.event_type == "SYNTHESIS_FROZEN"]
        assert len(frozen) == 1
        assert frozen[0].payload["synthesis_hash"] == initial.synthesis_hash
        with repo.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                connection.execute(
                    "UPDATE synthesis_reports SET verdict='INSUFFICIENT' WHERE id=?",
                    (initial.id,),
                )


def test_synthesis_input_is_ids_only_strict_and_requires_two_unique_ids():
    with pytest.raises(ValidationError, match="at least 2 items"):
        SynthesisCreate(evaluation_ids=["one"])
    with pytest.raises(ValidationError, match="must be unique"):
        SynthesisCreate(evaluation_ids=["same", "same"])
    for forbidden in ("effects", "metrics", "verdict"):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            SynthesisCreate(
                evaluation_ids=["first", "second"],
                **{forbidden: [1.0, 2.0]},
            )


def test_synthesis_refuses_stale_evaluation_snapshot():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        first_experiment, first = evaluated_experiment(
            repo, "Étude A", [0.0, 1.0, 2.0], [2.0, 3.0, 4.0]
        )
        _, second = evaluated_experiment(
            repo, "Étude B", [1.0, 2.0, 3.0], [3.0, 4.0, 5.0]
        )
        repo.add_observation(
            first_experiment.id,
            ObservationCreate(
                idempotency_key="late-control-0001",
                protocol_version=1,
                group="control",
                value=1.5,
                observed_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
                source_ref="instrument://late/1",
            ),
        )
        with pytest.raises(ValueError, match="not current"):
            repo.create_synthesis(
                SynthesisCreate(evaluation_ids=[first.id, second.id])
            )


def test_synthesis_api_returns_created_and_not_found_contracts():
    client = TestClient(app)
    response = client.post(
        "/v1/syntheses", json={"evaluation_ids": ["missing-a", "missing-b"]}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "evaluation not found"
    assert client.get("/v1/syntheses/missing").status_code == 404


def synthesis_from_effects(repo, effects):
    experiments = []
    evaluations = []
    for index, effect in enumerate(effects):
        experiment, evaluation = evaluated_experiment(
            repo,
            f"Étude influence {index}",
            [0.9, 1.0, 1.1],
            [0.9 + effect, 1.0 + effect, 1.1 + effect],
        )
        experiments.append(experiment)
        evaluations.append(evaluation)
    synthesis = repo.create_synthesis(
        SynthesisCreate(evaluation_ids=[item.id for item in evaluations])
    )
    return experiments, evaluations, synthesis


def test_influence_report_is_robust_for_stable_experiments():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiments, evaluations, synthesis = synthesis_from_effects(
            repo, [2.0, 2.0, 2.0]
        )
        report = repo.create_influence_report(
            InfluenceReportCreate(synthesis_id=synthesis.id)
        )
        assert report.verdict.value == "ROBUST"
        assert report.source_synthesis_hash == synthesis.synthesis_hash
        assert report.full_pooled_effect == pytest.approx(synthesis.pooled_effect)
        assert report.full_pooled_effect_variance == pytest.approx(
            synthesis.pooled_standard_error**2
        )
        assert len(report.cases) == 3
        assert {item.removed_experiment_id for item in report.cases} == {
            item.id for item in experiments
        }
        assert all(item.remaining_evaluation_count == 2 for item in report.cases)
        assert all(item.relative_delta == pytest.approx(0.0) for item in report.cases)
        assert all(item.influential is False for item in report.cases)
        assert report.most_influential_experiment_id in {item.id for item in experiments}
        assert report.relative_delta_threshold == 0.10
        assert "vérité universelle" in report.warning


def test_influence_report_detects_opposite_outlier_and_direction_change():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiments, _, synthesis = synthesis_from_effects(repo, [2.0, 2.0, -4.0])
        report = repo.create_influence_report(
            InfluenceReportCreate(synthesis_id=synthesis.id)
        )
        assert report.verdict.value == "INFLUENTIAL"
        assert report.full_synthesis_qualification.value == "HETEROGENEOUS"
        assert report.most_influential_experiment_id == experiments[2].id
        outlier_case = next(
            item
            for item in report.cases
            if item.removed_experiment_id == experiments[2].id
        )
        assert outlier_case.pooled_effect == pytest.approx(2.0)
        assert outlier_case.direction_changed is True
        assert outlier_case.qualification_changed is True
        assert outlier_case.synthesis_qualification.value == "CONSISTENT"
        assert outlier_case.influential is True


def test_influence_report_requires_three_evaluations_and_experiments():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, _, synthesis = synthesis_from_effects(repo, [2.0, 2.0])
        report = repo.create_influence_report(
            InfluenceReportCreate(synthesis_id=synthesis.id)
        )
        assert report.verdict.value == "INSUFFICIENT"
        assert report.cases == []
        assert report.most_influential_experiment_id is None


def test_influence_report_revalidates_incompatible_contracts():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        evaluations = []
        for index, metric in enumerate(["score", "score", "latence"]):
            _, evaluation = evaluated_experiment(
                repo,
                f"Contrat {index}",
                [0.9, 1.0, 1.1],
                [2.9, 3.0, 3.1],
                metric_name=metric,
            )
            evaluations.append(evaluation)
        synthesis = repo.create_synthesis(
            SynthesisCreate(evaluation_ids=[item.id for item in evaluations])
        )
        assert synthesis.verdict.value == "INCOMPATIBLE"
        report = repo.create_influence_report(
            InfluenceReportCreate(synthesis_id=synthesis.id)
        )
        assert report.verdict.value == "INCOMPATIBLE"
        assert report.full_synthesis_qualification.value == "INCOMPATIBLE"
        assert report.cases == []


def test_influence_report_is_idempotent_immutable_and_audited():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiments, _, synthesis = synthesis_from_effects(repo, [2.0, 2.0, 2.0])
        request = InfluenceReportCreate(synthesis_id=synthesis.id)
        first = repo.create_influence_report(request)
        replay = repo.create_influence_report(request)
        assert replay.id == first.id
        assert replay.influence_hash == first.influence_hash
        assert replay.idempotent_replay is True
        assert repo.get_influence_report(first.id).influence_hash == first.influence_hash
        assert len(repo.list_influence_reports()) == 1
        events = repo.list_audit(experiments[0].id)
        frozen = [item for item in events if item.event_type == "INFLUENCE_REPORT_FROZEN"]
        assert len(frozen) == 1
        assert frozen[0].payload["influence_hash"] == first.influence_hash
        with repo.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                connection.execute(
                    "UPDATE influence_reports SET verdict='INSUFFICIENT' WHERE id=?",
                    (first.id,),
                )


def test_influence_input_accepts_only_synthesis_id():
    for forbidden in ("effects", "score", "verdict", "evaluation_ids"):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            InfluenceReportCreate(
                synthesis_id="persisted-synthesis",
                **{forbidden: [1.0]},
            )
    with pytest.raises(ValidationError):
        InfluenceReportCreate(synthesis_id="")


def test_influence_recalculation_refuses_stale_evaluation():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiments, _, synthesis = synthesis_from_effects(repo, [2.0, 2.0, 2.0])
        repo.add_observation(
            experiments[0].id,
            ObservationCreate(
                idempotency_key="late-influence-001",
                protocol_version=1,
                group="control",
                value=1.5,
                observed_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
                source_ref="instrument://late/influence",
            ),
        )
        with pytest.raises(ValueError, match="not current"):
            repo.create_influence_report(
                InfluenceReportCreate(synthesis_id=synthesis.id)
            )


def test_influence_api_missing_source_and_report_contracts():
    client = TestClient(app)
    response = client.post(
        "/v1/influence-reports", json={"synthesis_id": "missing"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "synthesis report not found"
    assert client.get("/v1/influence-reports/missing").status_code == 404


def deviation_experiment(repo, min_samples=3, **protocol_updates):
    data = experiment_data(min_samples=min_samples)
    data = data.model_copy(
        update={
            "initial_protocol": data.initial_protocol.model_copy(update=protocol_updates)
        }
    )
    return repo.create_experiment(data)


def add_execution(repo, experiment_id, group, count, metadata=None, start_day=22):
    for index in range(count):
        repo.add_observation(
            experiment_id,
            ObservationCreate(
                idempotency_key=f"exec-{experiment_id}-{group}-{start_day}-{index}",
                protocol_version=1,
                group=group,
                value=float(index + 1),
                observed_at=datetime(2026, 8, start_day, index, tzinfo=timezone.utc),
                source_ref=f"execution://{group}/{index}",
                metadata=dict(metadata or {}),
            ),
        )


def test_deviation_report_adherent_and_hash_verified():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment = deviation_experiment(repo)
        add_execution(repo, experiment.id, "control", 3)
        add_execution(repo, experiment.id, "treatment", 3)
        evaluation = repo.evaluate(experiment.id, EvaluationCreate(protocol_version=1))
        report = repo.create_deviation_report(
            DeviationReportCreate(evaluation_id=evaluation.id)
        )
        assert report.verdict.value == "ADHERENT"
        assert report.findings == []
        assert report.experiment_hash == experiment.experiment_hash
        assert report.protocol_hash and report.observations_snapshot_hash
        assert report.usable_samples_by_group["control"] == 3
        assert "certification automatique" in report.warning


def test_deviation_report_minor_sample_shortfall_at_materiality_floor():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment = deviation_experiment(repo, min_samples=5)
        add_execution(repo, experiment.id, "control", 4)
        add_execution(repo, experiment.id, "treatment", 4)
        report = repo.create_deviation_report(
            DeviationReportCreate(experiment_id=experiment.id, protocol_version=1)
        )
        assert report.verdict.value == "MINOR_DEVIATIONS"
        assert len(report.findings) == 2
        assert all(item.material is False for item in report.findings)


def test_deviation_report_material_sample_shortfall():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment = deviation_experiment(repo, min_samples=5)
        add_execution(repo, experiment.id, "control", 3)
        add_execution(repo, experiment.id, "treatment", 3)
        report = repo.create_deviation_report(
            DeviationReportCreate(experiment_id=experiment.id, protocol_version=1)
        )
        assert report.verdict.value == "MATERIAL_DEVIATIONS"
        assert any(item.code == "SAMPLE_BELOW_PLAN" and item.material for item in report.findings)


def test_deviation_report_detects_endpoint_and_parameter_mismatch():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment = deviation_experiment(repo)
        metadata = {"metric_name": "latence", "metric_unit": "ms", "analysis_method": "changed"}
        add_execution(repo, experiment.id, "control", 3, metadata)
        add_execution(repo, experiment.id, "treatment", 3, metadata)
        report = repo.create_deviation_report(
            DeviationReportCreate(experiment_id=experiment.id, protocol_version=1)
        )
        assert report.verdict.value == "MATERIAL_DEVIATIONS"
        assert report.endpoint_mismatches == 6
        assert report.parameter_mismatches == 6


def test_deviation_report_checks_window_exclusions_and_missing_data():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment = deviation_experiment(
            repo,
            collection_window_start=datetime(2026, 8, 22, tzinfo=timezone.utc),
            collection_window_end=datetime(2026, 8, 23, tzinfo=timezone.utc),
            allowed_exclusion_reasons=["sensor-failure"],
            max_exclusion_fraction=0.10,
            max_missing_fraction=0.05,
        )
        add_execution(repo, experiment.id, "control", 3)
        add_execution(repo, experiment.id, "treatment", 3)
        add_execution(repo, experiment.id, "control", 1, {"excluded": True, "exclusion_reason": "invented"}, 24)
        add_execution(repo, experiment.id, "treatment", 1, {"missing": True}, 24)
        report = repo.create_deviation_report(
            DeviationReportCreate(experiment_id=experiment.id, protocol_version=1)
        )
        assert report.verdict.value == "MATERIAL_DEVIATIONS"
        assert report.excluded_observations == 1
        assert report.missing_observations == 1
        assert report.out_of_window_observations == 2
        assert any(item.code == "UNDOCUMENTED_EXCLUSION" for item in report.findings)


def test_deviation_report_insufficient_without_required_execution_data():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment = deviation_experiment(repo)
        report = repo.create_deviation_report(
            DeviationReportCreate(experiment_id=experiment.id, protocol_version=1)
        )
        assert report.verdict.value == "INSUFFICIENT"
        assert report.total_observations == 0


def test_deviation_report_marks_cross_references_incompatible():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        first = deviation_experiment(repo)
        second = repo.create_experiment(experiment_data(name="Autre exécution"))
        for item in (first, second):
            add_execution(repo, item.id, "control", 3)
            add_execution(repo, item.id, "treatment", 3)
        evaluation = repo.evaluate(second.id, EvaluationCreate(protocol_version=1))
        report = repo.create_deviation_report(
            DeviationReportCreate(
                experiment_id=first.id, protocol_version=1, evaluation_id=evaluation.id
            )
        )
        assert report.verdict.value == "INCOMPATIBLE"
        assert report.findings[0].code == "INCOMPATIBLE_EVALUATION_REFERENCE"


def test_deviation_report_idempotent_immutable_audited_and_strict():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment = deviation_experiment(repo)
        add_execution(repo, experiment.id, "control", 3)
        add_execution(repo, experiment.id, "treatment", 3)
        request = DeviationReportCreate(experiment_id=experiment.id, protocol_version=1)
        first = repo.create_deviation_report(request)
        replay = repo.create_deviation_report(request)
        assert replay.id == first.id and replay.idempotent_replay is True
        assert repo.get_deviation_report(first.id).report_hash == first.report_hash
        assert len(repo.list_deviation_reports()) == 1
        assert any(item.event_type == "DEVIATION_REPORT_FROZEN" for item in repo.list_audit(experiment.id))
        with repo.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                connection.execute("UPDATE deviation_reports SET verdict='INSUFFICIENT' WHERE id=?", (first.id,))
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DeviationReportCreate(experiment_id="x", protocol_version=1, verdict="ADHERENT")
    with pytest.raises(ValidationError, match="provide"):
        DeviationReportCreate()


def test_deviation_api_missing_reference_and_report():
    client = TestClient(app)
    response = client.post(
        "/v1/deviation-reports", json={"experiment_id": "missing", "protocol_version": 1}
    )
    assert response.status_code == 404
    assert client.get("/v1/deviation-reports/missing").status_code == 404


def stability_evaluations(repo, effects, *, metric_names=None, samples=3, name="Stabilité"):
    experiment = repo.create_experiment(experiment_data(min_samples=3, name=name))
    evaluations = []
    metric_names = metric_names or ["score"] * len(effects)
    for version, (effect, metric_name) in enumerate(zip(effects, metric_names), start=1):
        if version > 1:
            protocol = ProtocolSpec(
                name=f"Protocole {version}",
                groups=["control", "treatment"],
                metric_name=metric_name,
                metric_unit="point",
                collection_method=f"Mesure version {version}",
                seed=20260822 + version,
                min_samples_per_group=3,
            )
            repo.add_protocol(experiment.id, ProtocolCreate(specification=protocol))
        for group, center in (("control", 1.0), ("treatment", 1.0 + effect)):
            for index in range(samples):
                repo.add_observation(
                    experiment.id,
                    ObservationCreate(
                        idempotency_key=f"v{version}-{group}-{index:03d}",
                        protocol_version=version,
                        group=group,
                        value=center + (index - 1) * 0.1,
                        observed_at=datetime(2026, 8, 22, version, index, tzinfo=timezone.utc),
                        source_ref=f"instrument://v{version}/{group}/{index}",
                    ),
                )
        evaluations.append(repo.evaluate(experiment.id, EvaluationCreate(protocol_version=version)))
    return experiment, evaluations


def test_effect_stability_is_stable_and_orders_protocol_versions():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment, evaluations = stability_evaluations(repo, [2.0, 2.05, 2.1])
        dossier = repo.create_effect_stability_dossier(
            EffectStabilityDossierCreate(evaluation_ids=[item.id for item in reversed(evaluations)])
        )
        assert dossier.qualification.value == "STABLE"
        assert dossier.experiment_id == experiment.id
        assert [item.protocol_version for item in dossier.evaluations] == [1, 2, 3]
        assert dossier.relative_range == pytest.approx(0.1 / 2.1)
        assert all(not item.shifted for item in dossier.transitions)


def test_effect_stability_detects_relative_shift_at_ten_percent():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = stability_evaluations(repo, [2.0, 2.3])
        dossier = repo.create_effect_stability_dossier(
            EffectStabilityDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )
        assert dossier.qualification.value == "SHIFTED"
        assert dossier.transitions[0].relative_delta >= 0.10
        assert dossier.worst_transition.shifted is True


def test_effect_stability_detects_direction_change_and_nonoverlap():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = stability_evaluations(repo, [1.0, -1.0])
        dossier = repo.create_effect_stability_dossier(
            EffectStabilityDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )
        transition = dossier.transitions[0]
        assert dossier.qualification.value == "SHIFTED"
        assert transition.direction_changed is True
        assert transition.intervals_overlap is False


def test_effect_stability_is_insufficient_without_effects():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = stability_evaluations(repo, [2.0, 2.0], samples=2)
        dossier = repo.create_effect_stability_dossier(
            EffectStabilityDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )
        assert dossier.qualification.value == "INSUFFICIENT"
        assert dossier.transitions == [] and dossier.relative_range is None


def test_effect_stability_rejects_cross_experiment_as_incompatible():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, first = stability_evaluations(repo, [2.0, 2.05])
        _, second = stability_evaluations(repo, [2.0, 2.05], name="Autre stabilité")
        dossier = repo.create_effect_stability_dossier(
            EffectStabilityDossierCreate(evaluation_ids=[first[0].id, second[0].id])
        )
        assert dossier.qualification.value == "INCOMPATIBLE"
        assert dossier.compatibility.same_experiment is False


def test_effect_stability_detects_metric_incompatibility():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = stability_evaluations(repo, [2.0, 2.05], metric_names=["score", "latence"])
        dossier = repo.create_effect_stability_dossier(
            EffectStabilityDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )
        assert dossier.qualification.value == "INCOMPATIBLE"
        assert dossier.compatibility.metric_name is False


def test_effect_stability_is_order_independent_and_idempotent():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = stability_evaluations(repo, [2.0, 2.05])
        first = repo.create_effect_stability_dossier(
            EffectStabilityDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )
        replay = repo.create_effect_stability_dossier(
            EffectStabilityDossierCreate(evaluation_ids=[item.id for item in reversed(evaluations)])
        )
        assert replay.id == first.id and replay.dossier_hash == first.dossier_hash
        assert replay.idempotent_replay is True


def test_effect_stability_is_immutable_audited_gettable_and_listable():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment, evaluations = stability_evaluations(repo, [2.0, 2.05])
        dossier = repo.create_effect_stability_dossier(
            EffectStabilityDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )
        assert repo.get_effect_stability_dossier(dossier.id).dossier_hash == dossier.dossier_hash
        assert [item.id for item in repo.list_effect_stability_dossiers()] == [dossier.id]
        assert any(
            item.event_type == "EFFECT_STABILITY_DOSSIER_FROZEN"
            for item in repo.list_audit(experiment.id)
        )
        with repo.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                connection.execute(
                    "UPDATE effect_stability_dossiers SET qualification='SHIFTED' WHERE id=?",
                    (dossier.id,),
                )


def test_effect_stability_input_is_strict_unique_and_bounded():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EffectStabilityDossierCreate(evaluation_ids=["a", "b"], qualification="STABLE")
    with pytest.raises(ValidationError, match="must be unique"):
        EffectStabilityDossierCreate(evaluation_ids=["same", "same"])
    with pytest.raises(ValidationError):
        EffectStabilityDossierCreate(evaluation_ids=["one"])
    with pytest.raises(ValidationError):
        EffectStabilityDossierCreate(evaluation_ids=[str(index) for index in range(51)])


def test_effect_stability_api_missing_and_info_contract():
    client = TestClient(app)
    assert client.post(
        "/v1/effect-stability-dossiers", json={"evaluation_ids": ["a", "b"]}
    ).status_code == 404
    assert client.get("/v1/effect-stability-dossiers/missing").status_code == 404
    info = client.get("/info").json()
    assert info["effect_stability_method"] == "protocol-version-effect-stability-v1"
    assert info["effect_stability_relative_delta_threshold"] == 0.10


def robustness_evaluations(repo, effects, *, metric_names=None, samples=3):
    evaluations = []
    experiments = []
    metric_names = metric_names or ["score"] * len(effects)
    for index, (effect, metric_name) in enumerate(zip(effects, metric_names), start=1):
        experiment = repo.create_experiment(
            experiment_data(name=f"Réplication robustesse {index}", metric_name=metric_name)
        )
        experiments.append(experiment)
        control = [1.0 + offset for offset in (-0.1, 0.0, 0.1)][:samples]
        treatment = [1.0 + effect + offset for offset in (-0.1, 0.0, 0.1)][:samples]
        add_values(repo, experiment.id, "control", control)
        add_values(repo, experiment.id, "treatment", treatment)
        evaluations.append(repo.evaluate(experiment.id, EvaluationCreate(protocol_version=1)))
    return experiments, evaluations


def test_replication_robustness_is_robust_and_server_ordered():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiments, evaluations = robustness_evaluations(repo, [2.0, 1.95, 2.05])
        dossier = repo.create_replication_robustness_dossier(
            ReplicationRobustnessDossierCreate(
                evaluation_ids=[item.id for item in reversed(evaluations)]
            )
        )
        assert dossier.qualification.value == "ROBUST"
        assert dossier.reference_evaluation_id == evaluations[0].id
        assert dossier.supporting_replication_count == 2
        assert dossier.contradicting_replication_count == 0
        assert dossier.direction_consistent is True
        assert dossier.relative_effect_range < 0.20
        assert all(item.deviation_qualification.value == "ADHERENT" for item in dossier.evaluations)
        assert {item.experiment_id for item in dossier.evaluations} == {item.id for item in experiments}


def test_replication_robustness_detects_opposite_sign_and_worst_replication():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = robustness_evaluations(repo, [2.0, -2.0, 1.9])
        dossier = repo.create_replication_robustness_dossier(
            ReplicationRobustnessDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )
        assert dossier.qualification.value == "DIVERGENT"
        assert dossier.direction_consistent is False
        assert dossier.contradicting_replication_count >= 1
        assert dossier.worst_replication.evaluation_id == evaluations[1].id
        assert any(item.direction_changed for item in dossier.transitions)


def test_replication_robustness_detects_dispersion_nonoverlap_and_heterogeneity():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = robustness_evaluations(repo, [1.0, 2.0, 3.0])
        dossier = repo.create_replication_robustness_dossier(
            ReplicationRobustnessDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )
        assert dossier.qualification.value == "DIVERGENT"
        assert dossier.relative_effect_range >= 0.20
        assert dossier.heterogeneity_i2_percent >= 50.0
        assert dossier.worst_transition.intervals_overlap is False


def test_replication_robustness_is_insufficient_when_proof_is_missing():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = robustness_evaluations(repo, [2.0, 2.0], samples=2)
        dossier = repo.create_replication_robustness_dossier(
            ReplicationRobustnessDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )
        assert dossier.qualification.value == "INSUFFICIENT"
        assert dossier.mean_effect is None
        assert all(item.effect is None and item.effect_variance is None for item in dossier.evaluations)


def test_replication_robustness_rejects_incompatible_metric_contract():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = robustness_evaluations(
            repo, [2.0, 2.0], metric_names=["score", "latence"]
        )
        dossier = repo.create_replication_robustness_dossier(
            ReplicationRobustnessDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )
        assert dossier.qualification.value == "INCOMPATIBLE"
        assert dossier.compatibility.metric_name is False


def test_replication_robustness_is_order_independent_and_idempotent():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = robustness_evaluations(repo, [2.0, 2.05])
        first = repo.create_replication_robustness_dossier(
            ReplicationRobustnessDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )
        replay = repo.create_replication_robustness_dossier(
            ReplicationRobustnessDossierCreate(evaluation_ids=[item.id for item in reversed(evaluations)])
        )
        assert replay.id == first.id and replay.dossier_hash == first.dossier_hash
        assert replay.idempotent_replay is True


def test_replication_robustness_is_immutable_audited_gettable_and_listable():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiments, evaluations = robustness_evaluations(repo, [2.0, 2.05])
        dossier = repo.create_replication_robustness_dossier(
            ReplicationRobustnessDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )
        assert repo.get_replication_robustness_dossier(dossier.id).dossier_hash == dossier.dossier_hash
        assert [item.id for item in repo.list_replication_robustness_dossiers()] == [dossier.id]
        assert any(
            item.event_type == "REPLICATION_ROBUSTNESS_DOSSIER_FROZEN"
            for item in repo.list_audit(experiments[0].id)
        )
        with repo.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                connection.execute(
                    "UPDATE replication_robustness_dossiers SET qualification='DIVERGENT' WHERE id=?",
                    (dossier.id,),
                )


def test_replication_robustness_recalculates_and_rejects_tampered_hash():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = robustness_evaluations(repo, [2.0, 2.05])
        with repo.connect() as connection:
            connection.execute("DROP TRIGGER evaluations_no_update")
            connection.execute(
                "UPDATE evaluations SET evaluation_hash=? WHERE id=?",
                ("0" * 64, evaluations[1].id),
            )
        with pytest.raises(ValueError, match="evaluation hash"):
            repo.create_replication_robustness_dossier(
                ReplicationRobustnessDossierCreate(evaluation_ids=[item.id for item in evaluations])
            )


def test_replication_robustness_input_is_strict_unique_bounded_and_missing_safe():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReplicationRobustnessDossierCreate(
            evaluation_ids=["a", "b"], qualification="ROBUST"
        )
    with pytest.raises(ValidationError, match="must be unique"):
        ReplicationRobustnessDossierCreate(evaluation_ids=["same", "same"])
    with pytest.raises(ValidationError):
        ReplicationRobustnessDossierCreate(evaluation_ids=["one"])
    with pytest.raises(ValidationError):
        ReplicationRobustnessDossierCreate(evaluation_ids=[str(index) for index in range(101)])
    client = TestClient(app)
    assert client.post(
        "/v1/replication-robustness-dossiers", json={"evaluation_ids": ["a", "b"]}
    ).status_code == 404
    assert client.get("/v1/replication-robustness-dossiers/missing").status_code == 404


def test_replication_robustness_info_contract():
    info = TestClient(app).get("/info").json()
    assert info["replication_robustness_method"] == "multi-evaluation-replication-robustness-v1"
    assert info["replication_robustness_relative_dispersion_threshold"] == 0.20
    assert info["replication_robustness_heterogeneity_i2_threshold_percent"] == 50.0


def test_replication_evidence_coverage_is_complete_and_server_ordered():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiments, evaluations = robustness_evaluations(repo, [2.0, 2.05, 1.95])
        dossier = repo.create_replication_evidence_coverage_dossier(
            ReplicationEvidenceCoverageDossierCreate(
                evaluation_ids=[item.id for item in reversed(evaluations)]
            )
        )
        assert dossier.qualification.value == "COMPLETE"
        assert dossier.evaluation_ids == [item.id for item in evaluations]
        assert dossier.total_gap_count == 0
        assert dossier.mean_coverage_ratio == 1.0
        assert dossier.minimum_coverage_ratio == 1.0
        assert len(dossier.common_covered_checks) == 8
        assert {item.experiment_id for item in dossier.evaluations} == {
            item.id for item in experiments
        }


def test_replication_evidence_coverage_is_partial_without_subject_traceability():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = robustness_evaluations(repo, [2.0, 2.05])
        with repo.connect() as connection:
            connection.execute("DROP TRIGGER observations_no_update")
            row = connection.execute(
                "SELECT * FROM observations WHERE experiment_id=? LIMIT 1",
                (evaluations[1].experiment_id,),
            ).fetchone()
            normalized = ObservationCreate(
                idempotency_key=row["idempotency_key"], protocol_version=1,
                group=row["group_name"], value=row["value"], observed_at=row["observed_at"],
                source_ref=row["source_ref"], subject_ref=None,
                metadata=yaml.safe_load(row["metadata_json"]),
            ).model_dump(mode="json", exclude={"idempotency_key"})
            from apps.api.analysis import canonical_hash
            observation_hash = canonical_hash({
                "experiment_id": evaluations[1].experiment_id, "observation": normalized
            })
            connection.execute(
                "UPDATE observations SET subject_ref=NULL,observation_hash=? WHERE id=?",
                (observation_hash, row["id"]),
            )
            hashes = [item["observation_hash"] for item in connection.execute(
                "SELECT observation_hash FROM observations WHERE experiment_id=? ORDER BY observation_hash",
                (evaluations[1].experiment_id,),
            ).fetchall()]
            snapshot_hash = canonical_hash(hashes)
            connection.execute("DROP TRIGGER evaluations_no_update")
            evaluation_row = connection.execute(
                "SELECT * FROM evaluations WHERE id=?", (evaluations[1].id,)
            ).fetchone()
            # Preserve semantic data while updating the snapshot/evaluation hashes consistently.
            protocol = connection.execute(
                "SELECT * FROM protocols WHERE id=?", (evaluation_row["protocol_id"],)
            ).fetchone()
            aggregates = yaml.safe_load(evaluation_row["aggregates_json"])
            interval = yaml.safe_load(evaluation_row["interval_json"])
            evaluation_hash = canonical_hash({
                "experiment_hash": repo.get_experiment(evaluations[1].experiment_id).experiment_hash,
                "protocol_hash": protocol["protocol_hash"],
                "observations_snapshot_hash": snapshot_hash,
                "method": evaluation_row["method"], "verdict": evaluation_row["verdict"],
                "aggregates": aggregates, "treatment_minus_control": evaluation_row["contrast"],
                "standard_error": evaluation_row["standard_error"], "interval95": interval,
                "seed": yaml.safe_load(protocol["specification_json"])["seed"],
            })
            connection.execute(
                "UPDATE evaluations SET observations_snapshot_hash=?,evaluation_hash=? WHERE id=?",
                (snapshot_hash, evaluation_hash, evaluations[1].id),
            )
        dossier = repo.create_replication_evidence_coverage_dossier(
            ReplicationEvidenceCoverageDossierCreate(
                evaluation_ids=[item.id for item in evaluations]
            )
        )
        assert dossier.qualification.value == "PARTIAL"
        assert "SUBJECT_PROVENANCE_PRESENT" in dossier.worst_evaluation.gap_codes


def test_replication_evidence_coverage_is_insufficient_for_missing_effect():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = robustness_evaluations(repo, [2.0, 2.0], samples=2)
        dossier = repo.create_replication_evidence_coverage_dossier(
            ReplicationEvidenceCoverageDossierCreate(
                evaluation_ids=[item.id for item in evaluations]
            )
        )
        assert dossier.qualification.value == "INSUFFICIENT"
        assert "MINIMUM_SAMPLE_PLAN_MET" in dossier.common_gap_codes
        assert "ANALYTIC_RESULT_AVAILABLE" in dossier.common_gap_codes


def test_replication_evidence_coverage_is_incompatible_for_metric_change():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = robustness_evaluations(
            repo, [2.0, 2.0], metric_names=["score", "latence"]
        )
        dossier = repo.create_replication_evidence_coverage_dossier(
            ReplicationEvidenceCoverageDossierCreate(
                evaluation_ids=[item.id for item in evaluations]
            )
        )
        assert dossier.qualification.value == "INCOMPATIBLE"
        assert dossier.compatibility.metric_name is False


def test_replication_evidence_coverage_same_experiment_is_insufficient():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiment = repo.create_experiment(experiment_data())
        add_values(repo, experiment.id, "control", [0.9, 1.0, 1.1])
        add_values(repo, experiment.id, "treatment", [2.9, 3.0, 3.1])
        first = repo.evaluate(experiment.id, EvaluationCreate(protocol_version=1))
        changed = repo.add_protocol(experiment.id, ProtocolCreate(
            specification=experiment_data().initial_protocol.model_copy(update={"seed": 7})
        ))
        for group, values in (("control", [1.0, 1.1, 1.2]), ("treatment", [3.0, 3.1, 3.2])):
            for index, value in enumerate(values):
                repo.add_observation(experiment.id, ObservationCreate(
                    idempotency_key=f"v2-{group}-{index}", protocol_version=changed.version,
                    group=group, value=value,
                    observed_at=datetime(2026, 8, 23, index, tzinfo=timezone.utc),
                    source_ref=f"instrument://v2/{group}/{index}",
                    subject_ref=f"v2-{group}-{index}",
                ))
        second = repo.evaluate(experiment.id, EvaluationCreate(protocol_version=2))
        dossier = repo.create_replication_evidence_coverage_dossier(
            ReplicationEvidenceCoverageDossierCreate(evaluation_ids=[first.id, second.id])
        )
        assert dossier.qualification.value == "INSUFFICIENT"


def test_replication_evidence_coverage_is_order_independent_and_idempotent():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = robustness_evaluations(repo, [2.0, 2.05])
        first = repo.create_replication_evidence_coverage_dossier(
            ReplicationEvidenceCoverageDossierCreate(
                evaluation_ids=[item.id for item in evaluations]
            )
        )
        replay = repo.create_replication_evidence_coverage_dossier(
            ReplicationEvidenceCoverageDossierCreate(
                evaluation_ids=[item.id for item in reversed(evaluations)]
            )
        )
        assert replay.id == first.id and replay.dossier_hash == first.dossier_hash
        assert replay.idempotent_replay is True


def test_replication_evidence_coverage_is_immutable_audited_gettable_and_listable():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        experiments, evaluations = robustness_evaluations(repo, [2.0, 2.05])
        dossier = repo.create_replication_evidence_coverage_dossier(
            ReplicationEvidenceCoverageDossierCreate(
                evaluation_ids=[item.id for item in evaluations]
            )
        )
        assert repo.get_replication_evidence_coverage_dossier(dossier.id).dossier_hash == dossier.dossier_hash
        assert [item.id for item in repo.list_replication_evidence_coverage_dossiers()] == [dossier.id]
        assert any(
            item.event_type == "REPLICATION_EVIDENCE_COVERAGE_DOSSIER_FROZEN"
            for item in repo.list_audit(experiments[0].id)
        )
        with repo.connect() as connection:
            with pytest.raises(Exception, match="immutable"):
                connection.execute(
                    "UPDATE replication_evidence_coverage_dossiers SET qualification='PARTIAL' WHERE id=?",
                    (dossier.id,),
                )


def test_replication_evidence_coverage_rejects_tampered_evaluation_hash():
    with TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "experiment.db")
        _, evaluations = robustness_evaluations(repo, [2.0, 2.05])
        with repo.connect() as connection:
            connection.execute("DROP TRIGGER evaluations_no_update")
            connection.execute(
                "UPDATE evaluations SET evaluation_hash=? WHERE id=?",
                ("0" * 64, evaluations[1].id),
            )
        with pytest.raises(ValueError, match="evaluation hash"):
            repo.create_replication_evidence_coverage_dossier(
                ReplicationEvidenceCoverageDossierCreate(
                    evaluation_ids=[item.id for item in evaluations]
                )
            )


def test_replication_evidence_coverage_input_is_strict_unique_bounded_and_missing_safe():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReplicationEvidenceCoverageDossierCreate(
            evaluation_ids=["a", "b"], qualification="COMPLETE"
        )
    with pytest.raises(ValidationError, match="must be unique"):
        ReplicationEvidenceCoverageDossierCreate(evaluation_ids=["same", "same"])
    with pytest.raises(ValidationError):
        ReplicationEvidenceCoverageDossierCreate(evaluation_ids=["one"])
    with pytest.raises(ValidationError):
        ReplicationEvidenceCoverageDossierCreate(
            evaluation_ids=[str(index) for index in range(101)]
        )
    client = TestClient(app)
    assert client.post(
        "/v1/replication-evidence-coverage-dossiers",
        json={"evaluation_ids": ["a", "b"]},
    ).status_code == 404
    assert client.get(
        "/v1/replication-evidence-coverage-dossiers/missing"
    ).status_code == 404


def test_replication_evidence_coverage_info_contract():
    info = TestClient(app).get("/info").json()
    assert info["replication_evidence_coverage_method"] == "replication-evidence-protocol-coverage-v1"
    assert info["replication_evidence_coverage_required_check_count"] == 8
