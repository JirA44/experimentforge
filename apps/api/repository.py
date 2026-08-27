import json
import sqlite3
import statistics
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .analysis import (
    canonical_hash,
    compute_evaluation,
    fixed_effect_synthesis,
    qualify_replication,
    replication_compatibility,
    synthesis_compatibility,
)
from .models import (
    AuditEvent,
    Evaluation,
    EvaluationCreate,
    Experiment,
    ExperimentCreate,
    DeviationFinding,
    DeviationReportCreate,
    DeviationVerdict,
    EffectStabilityCompatibility,
    EffectStabilityDossier,
    EffectStabilityDossierCreate,
    EffectStabilityEvaluationSnapshot,
    EffectStabilityQualification,
    EffectStabilityTransition,
    HypothesisSpec,
    InfluenceReport,
    InfluenceReportCreate,
    InfluenceVerdict,
    Interval95,
    LeaveOneOutResult,
    Observation,
    ObservationCreate,
    ProtocolCreate,
    ProtocolDeviationReport,
    ProtocolSpec,
    ProtocolVersion,
    ReplicationEvaluationSnapshot,
    ReplicationReport,
    ReplicationReportCreate,
    ReplicationRobustnessDossier,
    ReplicationRobustnessDossierCreate,
    ReplicationRobustnessQualification,
    ReplicationRobustnessSnapshot,
    ReplicationRobustnessTransition,
    ReplicationEvidenceCoverageDossier,
    ReplicationEvidenceCoverageDossierCreate,
    ReplicationEvidenceCoverageQualification,
    ReplicationEvidenceCoverageSnapshot,
    SynthesisCreate,
    SynthesisEvaluationSnapshot,
    SynthesisReport,
    SynthesisVerdict,
    Verdict,
)


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS experiments(
  id TEXT PRIMARY KEY,
  experiment_hash TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  hypothesis_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS protocols(
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  version INTEGER NOT NULL CHECK(version >= 1),
  protocol_hash TEXT NOT NULL,
  specification_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(experiment_id, version),
  UNIQUE(experiment_id, protocol_hash)
);
CREATE TABLE IF NOT EXISTS observations(
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  protocol_id TEXT NOT NULL REFERENCES protocols(id),
  idempotency_key TEXT NOT NULL,
  group_name TEXT NOT NULL,
  value REAL NOT NULL,
  observed_at TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  subject_ref TEXT,
  metadata_json TEXT NOT NULL,
  observation_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(experiment_id, idempotency_key),
  UNIQUE(experiment_id, observation_hash)
);
CREATE TABLE IF NOT EXISTS evaluations(
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  protocol_id TEXT NOT NULL REFERENCES protocols(id),
  method TEXT NOT NULL,
  verdict TEXT NOT NULL CHECK(verdict IN ('SUPPORTED','REJECTED','INCONCLUSIVE','INSUFFICIENT')),
  aggregates_json TEXT NOT NULL,
  contrast REAL,
  standard_error REAL,
  interval_json TEXT NOT NULL,
  observations_snapshot_hash TEXT NOT NULL,
  evaluation_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  UNIQUE(experiment_id, protocol_id, observations_snapshot_hash, method)
);
CREATE TABLE IF NOT EXISTS replication_reports(
  id TEXT PRIMARY KEY,
  original_experiment_id TEXT NOT NULL REFERENCES experiments(id),
  original_protocol_id TEXT NOT NULL REFERENCES protocols(id),
  replication_experiment_id TEXT NOT NULL REFERENCES experiments(id),
  replication_protocol_id TEXT NOT NULL REFERENCES protocols(id),
  verdict TEXT NOT NULL CHECK(verdict IN ('REPLICATED','NOT_REPLICATED','INSUFFICIENT','INCOMPATIBLE')),
  compatibility_json TEXT NOT NULL,
  original_snapshot_json TEXT NOT NULL,
  replication_snapshot_json TEXT NOT NULL,
  intervals_overlap INTEGER,
  report_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS synthesis_reports(
  id TEXT PRIMARY KEY,
  evaluation_ids_json TEXT NOT NULL,
  experiment_ids_json TEXT NOT NULL,
  verdict TEXT NOT NULL CHECK(verdict IN ('CONSISTENT','HETEROGENEOUS','INSUFFICIENT','INCOMPATIBLE')),
  report_json TEXT NOT NULL,
  synthesis_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS influence_reports(
  id TEXT PRIMARY KEY,
  synthesis_id TEXT NOT NULL REFERENCES synthesis_reports(id),
  experiment_ids_json TEXT NOT NULL,
  verdict TEXT NOT NULL CHECK(verdict IN ('ROBUST','INFLUENTIAL','INSUFFICIENT','INCOMPATIBLE')),
  report_json TEXT NOT NULL,
  influence_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deviation_reports(
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  protocol_id TEXT NOT NULL REFERENCES protocols(id),
  evaluation_id TEXT REFERENCES evaluations(id),
  verdict TEXT NOT NULL CHECK(verdict IN ('ADHERENT','MINOR_DEVIATIONS','MATERIAL_DEVIATIONS','INSUFFICIENT','INCOMPATIBLE')),
  report_json TEXT NOT NULL,
  report_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS effect_stability_dossiers(
  id TEXT PRIMARY KEY,
  evaluation_ids_json TEXT NOT NULL,
  experiment_id TEXT REFERENCES experiments(id),
  qualification TEXT NOT NULL CHECK(qualification IN ('STABLE','SHIFTED','INSUFFICIENT','INCOMPATIBLE')),
  dossier_json TEXT NOT NULL,
  dossier_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS replication_robustness_dossiers(
  id TEXT PRIMARY KEY,
  evaluation_ids_json TEXT NOT NULL,
  experiment_ids_json TEXT NOT NULL,
  qualification TEXT NOT NULL CHECK(qualification IN ('ROBUST','DIVERGENT','INSUFFICIENT','INCOMPATIBLE')),
  dossier_json TEXT NOT NULL,
  dossier_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS replication_evidence_coverage_dossiers(
  id TEXT PRIMARY KEY,
  evaluation_ids_json TEXT NOT NULL,
  experiment_ids_json TEXT NOT NULL,
  qualification TEXT NOT NULL CHECK(qualification IN ('COMPLETE','PARTIAL','INSUFFICIENT','INCOMPATIBLE')),
  dossier_json TEXT NOT NULL,
  dossier_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events(
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  previous_event_hash TEXT,
  event_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS experiments_no_update BEFORE UPDATE ON experiments BEGIN
  SELECT RAISE(ABORT, 'experiments are immutable'); END;
CREATE TRIGGER IF NOT EXISTS experiments_no_delete BEFORE DELETE ON experiments BEGIN
  SELECT RAISE(ABORT, 'experiments are immutable'); END;
CREATE TRIGGER IF NOT EXISTS protocols_no_update BEFORE UPDATE ON protocols BEGIN
  SELECT RAISE(ABORT, 'protocols are immutable'); END;
CREATE TRIGGER IF NOT EXISTS protocols_no_delete BEFORE DELETE ON protocols BEGIN
  SELECT RAISE(ABORT, 'protocols are immutable'); END;
CREATE TRIGGER IF NOT EXISTS observations_no_update BEFORE UPDATE ON observations BEGIN
  SELECT RAISE(ABORT, 'observations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS observations_no_delete BEFORE DELETE ON observations BEGIN
  SELECT RAISE(ABORT, 'observations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS evaluations_no_update BEFORE UPDATE ON evaluations BEGIN
  SELECT RAISE(ABORT, 'evaluations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS evaluations_no_delete BEFORE DELETE ON evaluations BEGIN
  SELECT RAISE(ABORT, 'evaluations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS replication_reports_no_update BEFORE UPDATE ON replication_reports BEGIN
  SELECT RAISE(ABORT, 'replication reports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS replication_reports_no_delete BEFORE DELETE ON replication_reports BEGIN
  SELECT RAISE(ABORT, 'replication reports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS synthesis_reports_no_update BEFORE UPDATE ON synthesis_reports BEGIN
  SELECT RAISE(ABORT, 'synthesis reports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS synthesis_reports_no_delete BEFORE DELETE ON synthesis_reports BEGIN
  SELECT RAISE(ABORT, 'synthesis reports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS influence_reports_no_update BEFORE UPDATE ON influence_reports BEGIN
  SELECT RAISE(ABORT, 'influence reports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS influence_reports_no_delete BEFORE DELETE ON influence_reports BEGIN
  SELECT RAISE(ABORT, 'influence reports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS deviation_reports_no_update BEFORE UPDATE ON deviation_reports BEGIN
  SELECT RAISE(ABORT, 'deviation reports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS deviation_reports_no_delete BEFORE DELETE ON deviation_reports BEGIN
  SELECT RAISE(ABORT, 'deviation reports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS effect_stability_dossiers_no_update BEFORE UPDATE ON effect_stability_dossiers BEGIN
  SELECT RAISE(ABORT, 'effect stability dossiers are immutable'); END;
CREATE TRIGGER IF NOT EXISTS effect_stability_dossiers_no_delete BEFORE DELETE ON effect_stability_dossiers BEGIN
  SELECT RAISE(ABORT, 'effect stability dossiers are immutable'); END;
CREATE TRIGGER IF NOT EXISTS replication_robustness_dossiers_no_update BEFORE UPDATE ON replication_robustness_dossiers BEGIN
  SELECT RAISE(ABORT, 'replication robustness dossiers are immutable'); END;
CREATE TRIGGER IF NOT EXISTS replication_robustness_dossiers_no_delete BEFORE DELETE ON replication_robustness_dossiers BEGIN
  SELECT RAISE(ABORT, 'replication robustness dossiers are immutable'); END;
CREATE TRIGGER IF NOT EXISTS replication_evidence_coverage_dossiers_no_update BEFORE UPDATE ON replication_evidence_coverage_dossiers BEGIN
  SELECT RAISE(ABORT, 'replication evidence coverage dossiers are immutable'); END;
CREATE TRIGGER IF NOT EXISTS replication_evidence_coverage_dossiers_no_delete BEFORE DELETE ON replication_evidence_coverage_dossiers BEGIN
  SELECT RAISE(ABORT, 'replication evidence coverage dossiers are immutable'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events BEGIN
  SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events BEGIN
  SELECT RAISE(ABORT, 'audit log is append-only'); END;
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def _audit(self, connection, event_type: str, entity_type: str, entity_id: str, payload: dict):
        previous = connection.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous["event_hash"] if previous else None
        created_at = now()
        event_hash = canonical_hash(
            {
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "payload": payload,
                "previous_event_hash": previous_hash,
                "created_at": created_at,
            }
        )
        connection.execute(
            """INSERT INTO audit_events(
                event_type,entity_type,entity_id,payload_json,previous_event_hash,event_hash,created_at
            ) VALUES(?,?,?,?,?,?,?)""",
            (
                event_type,
                entity_type,
                entity_id,
                json.dumps(payload, sort_keys=True),
                previous_hash,
                event_hash,
                created_at,
            ),
        )

    def create_experiment(self, data: ExperimentCreate) -> Experiment:
        experiment_hash = canonical_hash(data.model_dump(mode="json"))
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM experiments WHERE experiment_hash=?", (experiment_hash,)
            ).fetchone()
            if existing:
                return self._experiment(existing)

            experiment_id = str(uuid.uuid4())
            protocol_id = str(uuid.uuid4())
            created_at = now()
            protocol_hash = canonical_hash(data.initial_protocol.model_dump(mode="json"))
            connection.execute(
                "INSERT INTO experiments VALUES(?,?,?,?,?,?)",
                (
                    experiment_id,
                    experiment_hash,
                    data.name,
                    data.description,
                    data.hypothesis.model_dump_json(),
                    created_at,
                ),
            )
            connection.execute(
                "INSERT INTO protocols VALUES(?,?,?,?,?,?)",
                (
                    protocol_id,
                    experiment_id,
                    1,
                    protocol_hash,
                    data.initial_protocol.model_dump_json(),
                    created_at,
                ),
            )
            self._audit(
                connection,
                "EXPERIMENT_FROZEN",
                "experiment",
                experiment_id,
                {"experiment_hash": experiment_hash},
            )
            self._audit(
                connection,
                "PROTOCOL_FROZEN",
                "protocol",
                protocol_id,
                {"version": 1, "protocol_hash": protocol_hash},
            )
            row = connection.execute(
                "SELECT * FROM experiments WHERE id=?", (experiment_id,)
            ).fetchone()
        return self._experiment(row)

    def _experiment(self, row) -> Experiment:
        return Experiment(
            id=row["id"],
            experiment_hash=row["experiment_hash"],
            name=row["name"],
            description=row["description"],
            hypothesis=HypothesisSpec.model_validate_json(row["hypothesis_json"]),
            created_at=row["created_at"],
        )

    def get_experiment(self, experiment_id: str) -> Experiment:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM experiments WHERE id=?", (experiment_id,)
            ).fetchone()
        if not row:
            raise KeyError("experiment not found")
        return self._experiment(row)

    def list_experiments(self) -> list[Experiment]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM experiments ORDER BY created_at DESC"
            ).fetchall()
        return [self._experiment(row) for row in rows]

    def add_protocol(self, experiment_id: str, data: ProtocolCreate) -> ProtocolVersion:
        experiment = self.get_experiment(experiment_id)
        required = {experiment.hypothesis.control_group, experiment.hypothesis.treatment_group}
        if not required.issubset(set(data.specification.groups)):
            raise ValueError("protocol groups must include control_group and treatment_group")
        protocol_hash = canonical_hash(data.specification.model_dump(mode="json"))
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM protocols WHERE experiment_id=? AND protocol_hash=?",
                (experiment_id, protocol_hash),
            ).fetchone()
            if existing:
                return self._protocol(existing, idempotent=True)
            version = connection.execute(
                "SELECT COALESCE(MAX(version),0)+1 AS next FROM protocols WHERE experiment_id=?",
                (experiment_id,),
            ).fetchone()["next"]
            protocol_id = str(uuid.uuid4())
            created_at = now()
            connection.execute(
                "INSERT INTO protocols VALUES(?,?,?,?,?,?)",
                (
                    protocol_id,
                    experiment_id,
                    version,
                    protocol_hash,
                    data.specification.model_dump_json(),
                    created_at,
                ),
            )
            self._audit(
                connection,
                "PROTOCOL_FROZEN",
                "protocol",
                protocol_id,
                {"version": version, "protocol_hash": protocol_hash},
            )
            row = connection.execute(
                "SELECT * FROM protocols WHERE id=?", (protocol_id,)
            ).fetchone()
        return self._protocol(row)

    def _protocol(self, row, idempotent: bool = False) -> ProtocolVersion:
        return ProtocolVersion(
            id=row["id"],
            experiment_id=row["experiment_id"],
            version=row["version"],
            protocol_hash=row["protocol_hash"],
            specification=ProtocolSpec.model_validate_json(row["specification_json"]),
            idempotent_replay=idempotent,
            created_at=row["created_at"],
        )

    def list_protocols(self, experiment_id: str) -> list[ProtocolVersion]:
        self.get_experiment(experiment_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM protocols WHERE experiment_id=? ORDER BY version",
                (experiment_id,),
            ).fetchall()
        return [self._protocol(row) for row in rows]

    def _get_protocol_row(self, experiment_id: str, version: int):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM protocols WHERE experiment_id=? AND version=?",
                (experiment_id, version),
            ).fetchone()
        if not row:
            raise KeyError("protocol version not found")
        return row

    def add_observation(self, experiment_id: str, data: ObservationCreate) -> Observation:
        self.get_experiment(experiment_id)
        protocol = self._get_protocol_row(experiment_id, data.protocol_version)
        specification = ProtocolSpec.model_validate_json(protocol["specification_json"])
        if data.group not in specification.groups:
            raise ValueError("observation group is not declared by this protocol version")
        payload = data.model_dump(mode="json", exclude={"idempotency_key"})
        observation_hash = canonical_hash(
            {"experiment_id": experiment_id, "observation": payload}
        )
        with self.connect() as connection:
            existing_key = connection.execute(
                "SELECT * FROM observations WHERE experiment_id=? AND idempotency_key=?",
                (experiment_id, data.idempotency_key),
            ).fetchone()
            if existing_key:
                if existing_key["observation_hash"] != observation_hash:
                    raise ValueError("idempotency key was already used with different observation data")
                return self._observation(existing_key, data.protocol_version, idempotent=True)
            existing_hash = connection.execute(
                "SELECT * FROM observations WHERE experiment_id=? AND observation_hash=?",
                (experiment_id, observation_hash),
            ).fetchone()
            if existing_hash:
                return self._observation(existing_hash, data.protocol_version, idempotent=True)

            observation_id = str(uuid.uuid4())
            created_at = now()
            connection.execute(
                """INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    observation_id,
                    experiment_id,
                    protocol["id"],
                    data.idempotency_key,
                    data.group,
                    data.value,
                    data.observed_at.isoformat(),
                    data.source_ref,
                    data.subject_ref,
                    json.dumps(data.metadata, sort_keys=True),
                    observation_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "OBSERVATION_APPENDED",
                "observation",
                observation_id,
                {
                    "protocol_version": data.protocol_version,
                    "observation_hash": observation_hash,
                },
            )
            row = connection.execute(
                "SELECT * FROM observations WHERE id=?", (observation_id,)
            ).fetchone()
        return self._observation(row, data.protocol_version)

    def _observation(self, row, protocol_version: int, idempotent: bool = False) -> Observation:
        return Observation(
            id=row["id"],
            experiment_id=row["experiment_id"],
            protocol_version=protocol_version,
            group=row["group_name"],
            value=row["value"],
            observed_at=row["observed_at"],
            source_ref=row["source_ref"],
            subject_ref=row["subject_ref"],
            metadata=json.loads(row["metadata_json"]),
            observation_hash=row["observation_hash"],
            idempotent_replay=idempotent,
            created_at=row["created_at"],
        )

    def list_observations(self, experiment_id: str, protocol_version: int) -> list[Observation]:
        protocol = self._get_protocol_row(experiment_id, protocol_version)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM observations WHERE experiment_id=? AND protocol_id=? ORDER BY created_at,id",
                (experiment_id, protocol["id"]),
            ).fetchall()
        return [self._observation(row, protocol_version) for row in rows]

    def evaluate(self, experiment_id: str, data: EvaluationCreate) -> Evaluation:
        experiment = self.get_experiment(experiment_id)
        protocol = self._get_protocol_row(experiment_id, data.protocol_version)
        specification = ProtocolSpec.model_validate_json(protocol["specification_json"])
        with self.connect() as connection:
            observations = connection.execute(
                "SELECT * FROM observations WHERE experiment_id=? AND protocol_id=? ORDER BY observation_hash",
                (experiment_id, protocol["id"]),
            ).fetchall()

        snapshot_hash = canonical_hash([row["observation_hash"] for row in observations])
        with self.connect() as connection:
            existing = connection.execute(
                """SELECT * FROM evaluations
                   WHERE experiment_id=? AND protocol_id=?
                     AND observations_snapshot_hash=? AND method=?""",
                (
                    experiment_id,
                    protocol["id"],
                    snapshot_hash,
                    specification.analysis_method,
                ),
            ).fetchone()
        if existing:
            return self._evaluation(
                existing, experiment, protocol, specification, idempotent=True
            )

        values_by_group = {group: [] for group in specification.groups}
        for row in observations:
            values_by_group[row["group_name"]].append(row["value"])
        verdict, aggregates, contrast, standard_error, interval = compute_evaluation(
            experiment.hypothesis, specification, values_by_group
        )
        result_payload = {
            "experiment_hash": experiment.experiment_hash,
            "protocol_hash": protocol["protocol_hash"],
            "observations_snapshot_hash": snapshot_hash,
            "method": specification.analysis_method,
            "verdict": verdict.value,
            "aggregates": {
                name: aggregate.model_dump(mode="json") for name, aggregate in aggregates.items()
            },
            "treatment_minus_control": contrast,
            "standard_error": standard_error,
            "interval95": interval.model_dump(mode="json"),
            "seed": specification.seed,
        }
        evaluation_hash = canonical_hash(result_payload)
        evaluation_id = str(uuid.uuid4())
        created_at = now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO evaluations(
                     id,experiment_id,protocol_id,method,verdict,aggregates_json,
                     contrast,standard_error,interval_json,observations_snapshot_hash,
                     evaluation_hash,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    evaluation_id,
                    experiment_id,
                    protocol["id"],
                    specification.analysis_method,
                    verdict.value,
                    json.dumps(result_payload["aggregates"], sort_keys=True),
                    contrast,
                    standard_error,
                    interval.model_dump_json(),
                    snapshot_hash,
                    evaluation_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "EVALUATION_COMPUTED",
                "evaluation",
                evaluation_id,
                {"evaluation_hash": evaluation_hash, "verdict": verdict.value},
            )
            row = connection.execute(
                "SELECT * FROM evaluations WHERE id=?", (evaluation_id,)
            ).fetchone()
        return self._evaluation(row, experiment, protocol, specification)

    def _evaluation(self, row, experiment, protocol, specification, idempotent=False) -> Evaluation:
        return Evaluation(
            id=row["id"],
            experiment_id=row["experiment_id"],
            protocol_version=protocol["version"],
            method=row["method"],
            verdict=row["verdict"],
            aggregates=json.loads(row["aggregates_json"]),
            treatment_minus_control=row["contrast"],
            standard_error=row["standard_error"],
            interval95=Interval95.model_validate_json(row["interval_json"]),
            experiment_hash=experiment.experiment_hash,
            protocol_hash=protocol["protocol_hash"],
            observations_snapshot_hash=row["observations_snapshot_hash"],
            evaluation_hash=row["evaluation_hash"],
            seed=specification.seed,
            idempotent_replay=idempotent,
            created_at=row["created_at"],
        )

    def list_evaluations(self, experiment_id: str) -> list[Evaluation]:
        experiment = self.get_experiment(experiment_id)
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT evaluations.*,protocols.version,protocols.protocol_hash,
                          protocols.specification_json
                   FROM evaluations JOIN protocols ON protocols.id=evaluations.protocol_id
                   WHERE evaluations.experiment_id=? ORDER BY evaluations.created_at""",
                (experiment_id,),
            ).fetchall()
        results = []
        for row in rows:
            specification = ProtocolSpec.model_validate_json(row["specification_json"])
            results.append(self._evaluation(row, experiment, row, specification))
        return results

    def _replication_snapshot(
        self,
        evaluation: Evaluation,
        hypothesis: HypothesisSpec,
    ) -> ReplicationEvaluationSnapshot:
        control = evaluation.aggregates.get(hypothesis.control_group)
        treatment = evaluation.aggregates.get(hypothesis.treatment_group)
        return ReplicationEvaluationSnapshot(
            evaluation_id=evaluation.id,
            verdict=evaluation.verdict,
            treatment_minus_control=evaluation.treatment_minus_control,
            interval95=evaluation.interval95,
            experiment_hash=evaluation.experiment_hash,
            protocol_hash=evaluation.protocol_hash,
            observations_snapshot_hash=evaluation.observations_snapshot_hash,
            evaluation_hash=evaluation.evaluation_hash,
            control_count=control.count if control else 0,
            treatment_count=treatment.count if treatment else 0,
        )

    def create_replication_report(
        self, data: ReplicationReportCreate
    ) -> ReplicationReport:
        original_experiment = self.get_experiment(data.original_experiment_id)
        replication_experiment = self.get_experiment(data.replication_experiment_id)
        original_protocol = self._get_protocol_row(
            data.original_experiment_id, data.original_protocol_version
        )
        replication_protocol = self._get_protocol_row(
            data.replication_experiment_id, data.replication_protocol_version
        )
        original_specification = ProtocolSpec.model_validate_json(
            original_protocol["specification_json"]
        )
        replication_specification = ProtocolSpec.model_validate_json(
            replication_protocol["specification_json"]
        )

        # Evaluations are always recalculated from immutable observation snapshots.
        original_evaluation = self.evaluate(
            data.original_experiment_id,
            EvaluationCreate(protocol_version=data.original_protocol_version),
        )
        replication_evaluation = self.evaluate(
            data.replication_experiment_id,
            EvaluationCreate(protocol_version=data.replication_protocol_version),
        )
        compatibility = replication_compatibility(
            original_experiment.hypothesis,
            original_specification,
            replication_experiment.hypothesis,
            replication_specification,
        )
        verdict, overlap = qualify_replication(
            compatibility, original_evaluation, replication_evaluation
        )
        original_snapshot = self._replication_snapshot(
            original_evaluation, original_experiment.hypothesis
        )
        replication_snapshot = self._replication_snapshot(
            replication_evaluation, replication_experiment.hypothesis
        )
        report_payload = {
            "original_experiment_id": data.original_experiment_id,
            "original_protocol_version": data.original_protocol_version,
            "replication_experiment_id": data.replication_experiment_id,
            "replication_protocol_version": data.replication_protocol_version,
            "verdict": verdict.value,
            "compatibility": compatibility.model_dump(mode="json"),
            "original_evaluation_hash": original_evaluation.evaluation_hash,
            "replication_evaluation_hash": replication_evaluation.evaluation_hash,
            "intervals_overlap": overlap,
            "method": "replication-direction-and-ci-overlap-v1",
        }
        report_hash = canonical_hash(report_payload)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM replication_reports WHERE report_hash=?", (report_hash,)
            ).fetchone()
            if existing:
                return self._replication_report(existing, idempotent=True)

            report_id = str(uuid.uuid4())
            created_at = now()
            connection.execute(
                """INSERT INTO replication_reports(
                     id,original_experiment_id,original_protocol_id,
                     replication_experiment_id,replication_protocol_id,verdict,
                     compatibility_json,original_snapshot_json,
                     replication_snapshot_json,intervals_overlap,report_hash,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    report_id,
                    data.original_experiment_id,
                    original_protocol["id"],
                    data.replication_experiment_id,
                    replication_protocol["id"],
                    verdict.value,
                    compatibility.model_dump_json(),
                    original_snapshot.model_dump_json(),
                    replication_snapshot.model_dump_json(),
                    None if overlap is None else int(overlap),
                    report_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "REPLICATION_REPORT_FROZEN",
                "replication_report",
                report_id,
                {
                    "original_experiment_id": data.original_experiment_id,
                    "replication_experiment_id": data.replication_experiment_id,
                    "report_hash": report_hash,
                    "verdict": verdict.value,
                },
            )
            row = connection.execute(
                "SELECT * FROM replication_reports WHERE id=?", (report_id,)
            ).fetchone()
        return self._replication_report(row)

    def _replication_report(self, row, idempotent: bool = False) -> ReplicationReport:
        with self.connect() as connection:
            original_version = connection.execute(
                "SELECT version FROM protocols WHERE id=?", (row["original_protocol_id"],)
            ).fetchone()["version"]
            replication_version = connection.execute(
                "SELECT version FROM protocols WHERE id=?", (row["replication_protocol_id"],)
            ).fetchone()["version"]
        overlap = row["intervals_overlap"]
        return ReplicationReport(
            id=row["id"],
            original_experiment_id=row["original_experiment_id"],
            original_protocol_version=original_version,
            replication_experiment_id=row["replication_experiment_id"],
            replication_protocol_version=replication_version,
            verdict=row["verdict"],
            compatibility=json.loads(row["compatibility_json"]),
            original=ReplicationEvaluationSnapshot.model_validate_json(
                row["original_snapshot_json"]
            ),
            replication=ReplicationEvaluationSnapshot.model_validate_json(
                row["replication_snapshot_json"]
            ),
            intervals_overlap=None if overlap is None else bool(overlap),
            report_hash=row["report_hash"],
            idempotent_replay=idempotent,
            created_at=row["created_at"],
        )

    def get_replication_report(self, report_id: str) -> ReplicationReport:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM replication_reports WHERE id=?", (report_id,)
            ).fetchone()
        if not row:
            raise KeyError("replication report not found")
        return self._replication_report(row)

    def list_replication_reports(self) -> list[ReplicationReport]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM replication_reports ORDER BY created_at,id"
            ).fetchall()
        return [self._replication_report(row) for row in rows]

    def _load_synthesis_input(self, evaluation_id: str) -> dict:
        """Reload and recalculate one immutable evaluation snapshot server-side."""
        with self.connect() as connection:
            row = connection.execute(
                """SELECT evaluations.*,protocols.version,protocols.protocol_hash,
                          protocols.specification_json,experiments.experiment_hash,
                          experiments.hypothesis_json,
                          experiments.name AS experiment_name,
                          experiments.description AS experiment_description,
                          initial_protocol.specification_json AS initial_specification_json
                   FROM evaluations
                   JOIN protocols ON protocols.id=evaluations.protocol_id
                   JOIN experiments ON experiments.id=evaluations.experiment_id
                   JOIN protocols AS initial_protocol
                     ON initial_protocol.experiment_id=experiments.id
                    AND initial_protocol.version=1
                   WHERE evaluations.id=?""",
                (evaluation_id,),
            ).fetchone()
            if not row:
                raise KeyError("evaluation not found")
            observations = connection.execute(
                """SELECT * FROM observations
                   WHERE experiment_id=? AND protocol_id=? ORDER BY observation_hash""",
                (row["experiment_id"], row["protocol_id"]),
            ).fetchall()

        for observation in observations:
            normalized = ObservationCreate(
                idempotency_key=observation["idempotency_key"],
                protocol_version=row["version"],
                group=observation["group_name"],
                value=observation["value"],
                observed_at=observation["observed_at"],
                source_ref=observation["source_ref"],
                subject_ref=observation["subject_ref"],
                metadata=json.loads(observation["metadata_json"]),
            ).model_dump(mode="json", exclude={"idempotency_key"})
            if canonical_hash({"experiment_id": row["experiment_id"], "observation": normalized}) != observation["observation_hash"]:
                raise ValueError("stored observation hash does not match observation data")
        current_snapshot_hash = canonical_hash(
            [observation["observation_hash"] for observation in observations]
        )
        if current_snapshot_hash != row["observations_snapshot_hash"]:
            raise ValueError(
                "evaluation snapshot is not current; create a new evaluation identifier"
            )
        hypothesis = HypothesisSpec.model_validate_json(row["hypothesis_json"])
        specification = ProtocolSpec.model_validate_json(row["specification_json"])
        experiment_hash = canonical_hash(
            ExperimentCreate(
                name=row["experiment_name"],
                description=row["experiment_description"],
                hypothesis=hypothesis,
                initial_protocol=ProtocolSpec.model_validate_json(
                    row["initial_specification_json"]
                ),
            ).model_dump(mode="json")
        )
        if experiment_hash != row["experiment_hash"]:
            raise ValueError("stored experiment hash does not match experiment data")
        values_by_group = {group: [] for group in specification.groups}
        for observation in observations:
            values_by_group[observation["group_name"]].append(observation["value"])
        verdict, aggregates, effect, standard_error, interval = compute_evaluation(
            hypothesis, specification, values_by_group
        )
        if verdict.value != row["verdict"]:
            raise ValueError("stored evaluation verdict does not match recalculated observations")
        return {
            "row": row,
            "hypothesis": hypothesis,
            "specification": specification,
            "effect": effect,
            "effect_variance": (
                standard_error * standard_error if standard_error is not None else None
            ),
            "standard_error": standard_error,
            "interval": interval,
            "verdict": verdict,
            "aggregates": aggregates,
        }

    def create_synthesis(self, data: SynthesisCreate) -> SynthesisReport:
        evaluation_ids = sorted(data.evaluation_ids)
        inputs = [self._load_synthesis_input(item) for item in evaluation_ids]
        experiment_ids = sorted({item["row"]["experiment_id"] for item in inputs})
        compatibility = synthesis_compatibility(
            [(item["hypothesis"], item["specification"]) for item in inputs]
        )
        sufficient = (
            len(experiment_ids) >= 2
            and all(item["effect"] is not None for item in inputs)
            and all(item["effect_variance"] is not None for item in inputs)
        )

        calculation = None
        if compatibility.compatible and sufficient:
            calculation = fixed_effect_synthesis(
                inputs[0]["hypothesis"].direction,
                [item["effect"] for item in inputs],
                [item["effect_variance"] for item in inputs],
            )
            verdict = (
                SynthesisVerdict.HETEROGENEOUS
                if (
                    not calculation["direction_consistent"]
                    or calculation["heterogeneity_i2_percent"] >= 50.0
                )
                else SynthesisVerdict.CONSISTENT
            )
        elif not compatibility.compatible:
            verdict = SynthesisVerdict.INCOMPATIBLE
        else:
            verdict = SynthesisVerdict.INSUFFICIENT

        snapshots = []
        for index, item in enumerate(inputs):
            snapshots.append(
                SynthesisEvaluationSnapshot(
                    evaluation_id=item["row"]["id"],
                    experiment_id=item["row"]["experiment_id"],
                    protocol_version=item["row"]["version"],
                    evaluation_hash=item["row"]["evaluation_hash"],
                    observations_snapshot_hash=item["row"]["observations_snapshot_hash"],
                    effect=item["effect"],
                    effect_variance=item["effect_variance"],
                    interval95=item["interval"],
                    weight=(calculation["weights"][index] if calculation else None),
                    source_verdict=item["verdict"],
                )
            )

        worst_interval = Interval95()
        worst_effect = None
        if calculation:
            worst_index = calculation["worst_index"]
            worst_effect = inputs[worst_index]["effect"]
            worst_interval = inputs[worst_index]["interval"]
        result_payload = {
            "evaluation_ids": evaluation_ids,
            "experiment_ids": experiment_ids,
            "evaluation_hashes": [item["row"]["evaluation_hash"] for item in inputs],
            "observation_snapshot_hashes": [
                item["row"]["observations_snapshot_hash"] for item in inputs
            ],
            "compatibility": compatibility.model_dump(mode="json"),
            "method": "fixed-effect-inverse-variance-v1",
            "verdict": verdict.value,
            "pooled_effect": calculation["pooled_effect"] if calculation else None,
            "pooled_standard_error": (
                calculation["pooled_standard_error"] if calculation else None
            ),
            "interval95": (
                calculation["interval95"].model_dump(mode="json")
                if calculation
                else Interval95().model_dump(mode="json")
            ),
            "worst_effect": worst_effect,
            "worst_interval95": worst_interval.model_dump(mode="json"),
            "direction_consistent": (
                calculation["direction_consistent"] if calculation else None
            ),
            "cochran_q": calculation["cochran_q"] if calculation else None,
            "heterogeneity_i2_percent": (
                calculation["heterogeneity_i2_percent"] if calculation else None
            ),
        }
        synthesis_hash = canonical_hash(result_payload)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM synthesis_reports WHERE synthesis_hash=?",
                (synthesis_hash,),
            ).fetchone()
            if existing:
                return self._synthesis(existing, idempotent=True)

            synthesis_id = str(uuid.uuid4())
            created_at = now()
            report = SynthesisReport(
                id=synthesis_id,
                evaluation_ids=evaluation_ids,
                experiment_ids=experiment_ids,
                verdict=verdict,
                compatibility=compatibility,
                evaluations=snapshots,
                pooled_effect=result_payload["pooled_effect"],
                pooled_standard_error=result_payload["pooled_standard_error"],
                interval95=result_payload["interval95"],
                worst_effect=worst_effect,
                worst_interval95=worst_interval,
                direction_consistent=result_payload["direction_consistent"],
                cochran_q=result_payload["cochran_q"],
                heterogeneity_i2_percent=result_payload["heterogeneity_i2_percent"],
                synthesis_hash=synthesis_hash,
                created_at=created_at,
            )
            connection.execute(
                "INSERT INTO synthesis_reports VALUES(?,?,?,?,?,?,?)",
                (
                    synthesis_id,
                    json.dumps(evaluation_ids),
                    json.dumps(experiment_ids),
                    verdict.value,
                    report.model_dump_json(),
                    synthesis_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "SYNTHESIS_FROZEN",
                "synthesis_report",
                synthesis_id,
                {
                    "evaluation_ids": evaluation_ids,
                    "experiment_ids": experiment_ids,
                    "synthesis_hash": synthesis_hash,
                    "verdict": verdict.value,
                },
            )
        return report

    def _synthesis(self, row, idempotent: bool = False) -> SynthesisReport:
        report = SynthesisReport.model_validate_json(row["report_json"])
        return report.model_copy(update={"idempotent_replay": idempotent})

    def get_synthesis(self, synthesis_id: str) -> SynthesisReport:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM synthesis_reports WHERE id=?", (synthesis_id,)
            ).fetchone()
        if not row:
            raise KeyError("synthesis report not found")
        return self._synthesis(row)

    def list_syntheses(self) -> list[SynthesisReport]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM synthesis_reports ORDER BY created_at,id"
            ).fetchall()
        return [self._synthesis(row) for row in rows]

    @staticmethod
    def _qualification(calculation: dict) -> SynthesisVerdict:
        return (
            SynthesisVerdict.HETEROGENEOUS
            if (
                not calculation["direction_consistent"]
                or calculation["heterogeneity_i2_percent"] >= 50.0
            )
            else SynthesisVerdict.CONSISTENT
        )

    def create_influence_report(
        self, data: InfluenceReportCreate
    ) -> InfluenceReport:
        source = self.get_synthesis(data.synthesis_id)
        inputs = [self._load_synthesis_input(item) for item in source.evaluation_ids]
        compatibility = synthesis_compatibility(
            [(item["hypothesis"], item["specification"]) for item in inputs]
        )
        experiment_ids = sorted({item["row"]["experiment_id"] for item in inputs})
        effects_ready = all(item["effect"] is not None for item in inputs)
        variances_ready = all(item["effect_variance"] is not None for item in inputs)
        full_calculation = None
        if compatibility.compatible and effects_ready and variances_ready:
            full_calculation = fixed_effect_synthesis(
                inputs[0]["hypothesis"].direction,
                [item["effect"] for item in inputs],
                [item["effect_variance"] for item in inputs],
            )
            full_qualification = self._qualification(full_calculation)
        elif not compatibility.compatible:
            full_qualification = SynthesisVerdict.INCOMPATIBLE
        else:
            full_qualification = SynthesisVerdict.INSUFFICIENT

        cases: list[LeaveOneOutResult] = []
        most_influential_experiment_id = None
        if not compatibility.compatible:
            verdict = InfluenceVerdict.INCOMPATIBLE
        elif (
            len(inputs) < 3
            or len(experiment_ids) < 3
            or full_calculation is None
        ):
            verdict = InfluenceVerdict.INSUFFICIENT
        else:
            full_effect = full_calculation["pooled_effect"]
            direction = inputs[0]["hypothesis"].direction
            minimum_effect = inputs[0]["hypothesis"].minimum_effect
            denominator = max(abs(full_effect), abs(minimum_effect), 1e-12)
            for experiment_id in experiment_ids:
                remaining = [
                    item
                    for item in inputs
                    if item["row"]["experiment_id"] != experiment_id
                ]
                calculation = fixed_effect_synthesis(
                    direction,
                    [item["effect"] for item in remaining],
                    [item["effect_variance"] for item in remaining],
                )
                qualification = self._qualification(calculation)
                delta = calculation["pooled_effect"] - full_effect
                relative_delta = abs(delta) / denominator
                direction_changed = (
                    calculation["direction_consistent"]
                    != full_calculation["direction_consistent"]
                )
                qualification_changed = qualification != full_qualification
                influential = (
                    relative_delta >= 0.10
                    or direction_changed
                    or qualification_changed
                )
                removed_ids = sorted(
                    item["row"]["id"]
                    for item in inputs
                    if item["row"]["experiment_id"] == experiment_id
                )
                cases.append(
                    LeaveOneOutResult(
                        removed_experiment_id=experiment_id,
                        removed_evaluation_ids=removed_ids,
                        remaining_evaluation_count=len(remaining),
                        pooled_effect=calculation["pooled_effect"],
                        pooled_effect_variance=(
                            calculation["pooled_standard_error"] ** 2
                        ),
                        interval95=calculation["interval95"],
                        direction_consistent=calculation["direction_consistent"],
                        cochran_q=calculation["cochran_q"],
                        heterogeneity_i2_percent=calculation[
                            "heterogeneity_i2_percent"
                        ],
                        synthesis_qualification=qualification,
                        delta_pooled_effect=delta,
                        relative_delta=relative_delta,
                        direction_changed=direction_changed,
                        qualification_changed=qualification_changed,
                        influential=influential,
                    )
                )
            cases.sort(key=lambda item: item.removed_experiment_id)
            most_influential = max(
                cases,
                key=lambda item: (
                    int(bool(item.direction_changed or item.qualification_changed)),
                    item.relative_delta or 0.0,
                    item.removed_experiment_id,
                ),
            )
            most_influential_experiment_id = most_influential.removed_experiment_id
            verdict = (
                InfluenceVerdict.INFLUENTIAL
                if any(item.influential for item in cases)
                else InfluenceVerdict.ROBUST
            )

        full_interval = (
            full_calculation["interval95"] if full_calculation else Interval95()
        )
        payload = {
            "synthesis_id": source.id,
            "source_synthesis_hash": source.synthesis_hash,
            "evaluation_hashes": [item["row"]["evaluation_hash"] for item in inputs],
            "verdict": verdict.value,
            "method": "leave-one-experiment-out-fixed-effect-v1",
            "full_synthesis_qualification": full_qualification.value,
            "full_pooled_effect": (
                full_calculation["pooled_effect"] if full_calculation else None
            ),
            "full_pooled_effect_variance": (
                full_calculation["pooled_standard_error"] ** 2
                if full_calculation
                else None
            ),
            "full_interval95": full_interval.model_dump(mode="json"),
            "full_direction_consistent": (
                full_calculation["direction_consistent"] if full_calculation else None
            ),
            "full_cochran_q": (
                full_calculation["cochran_q"] if full_calculation else None
            ),
            "full_heterogeneity_i2_percent": (
                full_calculation["heterogeneity_i2_percent"]
                if full_calculation
                else None
            ),
            "cases": [item.model_dump(mode="json") for item in cases],
            "most_influential_experiment_id": most_influential_experiment_id,
            "relative_delta_threshold": 0.10,
        }
        influence_hash = canonical_hash(payload)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM influence_reports WHERE influence_hash=?",
                (influence_hash,),
            ).fetchone()
            if existing:
                return self._influence_report(existing, idempotent=True)
            report_id = str(uuid.uuid4())
            created_at = now()
            report = InfluenceReport(
                id=report_id,
                synthesis_id=source.id,
                source_synthesis_hash=source.synthesis_hash,
                verdict=verdict,
                full_synthesis_qualification=full_qualification,
                full_pooled_effect=payload["full_pooled_effect"],
                full_pooled_effect_variance=payload["full_pooled_effect_variance"],
                full_interval95=full_interval,
                full_direction_consistent=payload["full_direction_consistent"],
                full_cochran_q=payload["full_cochran_q"],
                full_heterogeneity_i2_percent=payload[
                    "full_heterogeneity_i2_percent"
                ],
                cases=cases,
                most_influential_experiment_id=most_influential_experiment_id,
                influence_hash=influence_hash,
                created_at=created_at,
            )
            connection.execute(
                "INSERT INTO influence_reports VALUES(?,?,?,?,?,?,?)",
                (
                    report_id,
                    source.id,
                    json.dumps(experiment_ids),
                    verdict.value,
                    report.model_dump_json(),
                    influence_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "INFLUENCE_REPORT_FROZEN",
                "influence_report",
                report_id,
                {
                    "synthesis_id": source.id,
                    "experiment_ids": experiment_ids,
                    "influence_hash": influence_hash,
                    "verdict": verdict.value,
                },
            )
        return report

    def _influence_report(self, row, idempotent: bool = False) -> InfluenceReport:
        report = InfluenceReport.model_validate_json(row["report_json"])
        return report.model_copy(update={"idempotent_replay": idempotent})

    def get_influence_report(self, report_id: str) -> InfluenceReport:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM influence_reports WHERE id=?", (report_id,)
            ).fetchone()
        if not row:
            raise KeyError("influence report not found")
        return self._influence_report(row)

    def list_influence_reports(self) -> list[InfluenceReport]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM influence_reports ORDER BY created_at,id"
            ).fetchall()
        return [self._influence_report(row) for row in rows]

    def create_deviation_report(
        self, data: DeviationReportCreate
    ) -> ProtocolDeviationReport:
        evaluation_row = None
        if data.evaluation_id:
            with self.connect() as connection:
                evaluation_row = connection.execute(
                    """SELECT evaluations.*,protocols.version
                       FROM evaluations JOIN protocols ON protocols.id=evaluations.protocol_id
                       WHERE evaluations.id=?""",
                    (data.evaluation_id,),
                ).fetchone()
            if not evaluation_row:
                raise KeyError("evaluation not found")
        experiment_id = data.experiment_id or evaluation_row["experiment_id"]
        protocol_version = data.protocol_version or evaluation_row["version"]
        experiment = self.get_experiment(experiment_id)
        protocol = self._get_protocol_row(experiment_id, protocol_version)
        specification = ProtocolSpec.model_validate_json(protocol["specification_json"])
        incompatible_reference = bool(
            evaluation_row
            and (
                evaluation_row["experiment_id"] != experiment_id
                or evaluation_row["protocol_id"] != protocol["id"]
            )
        )
        with self.connect() as connection:
            observations = connection.execute(
                """SELECT * FROM observations WHERE experiment_id=? AND protocol_id=?
                   ORDER BY observation_hash""",
                (experiment_id, protocol["id"]),
            ).fetchall()
        snapshot_hash = canonical_hash([row["observation_hash"] for row in observations])
        stale_evaluation = bool(
            evaluation_row
            and evaluation_row["observations_snapshot_hash"] != snapshot_hash
        )
        findings: list[DeviationFinding] = []
        if incompatible_reference:
            findings.append(DeviationFinding(
                category="reference", code="INCOMPATIBLE_EVALUATION_REFERENCE", material=True,
                observed=data.evaluation_id, planned=f"{experiment_id}:{protocol_version}",
                detail="L'évaluation ne référence pas ce protocole et cette expérience.",
            ))
        if stale_evaluation:
            findings.append(DeviationFinding(
                category="snapshot", code="EVALUATION_SNAPSHOT_NOT_CURRENT", material=False,
                observed=evaluation_row["observations_snapshot_hash"], planned=snapshot_hash,
                detail="Les observations actuelles ne permettent pas de reconstruire exactement cet ancien instantané.",
            ))

        required_groups = [experiment.hypothesis.control_group, experiment.hypothesis.treatment_group]
        usable = {group: 0 for group in specification.groups}
        excluded = missing = outside = endpoint_mismatches = parameter_mismatches = 0
        allowed_reasons = set(specification.allowed_exclusion_reasons)
        for row in observations:
            metadata = json.loads(row["metadata_json"])
            is_excluded = bool(metadata.get("excluded", False))
            is_missing = bool(metadata.get("missing", False))
            excluded += int(is_excluded)
            missing += int(is_missing)
            if not is_excluded and not is_missing:
                usable[row["group_name"]] += 1
            if is_excluded:
                reason = metadata.get("exclusion_reason")
                if not reason or reason not in allowed_reasons:
                    findings.append(DeviationFinding(
                        category="exclusions", code="UNDOCUMENTED_EXCLUSION", material=True,
                        observed=reason, planned=sorted(allowed_reasons),
                        detail="Une exclusion ne correspond pas à une raison préenregistrée.",
                    ))
            metric_name = metadata.get("metric_name", specification.metric_name)
            metric_unit = metadata.get("metric_unit", specification.metric_unit)
            if metric_name.casefold() != specification.metric_name.casefold() or metric_unit.casefold() != specification.metric_unit.casefold():
                endpoint_mismatches += 1
            expected_metadata = {
                "collection_method": specification.collection_method,
                "analysis_method": specification.analysis_method,
                "seed": specification.seed,
                "analysis_parameters": specification.analysis_parameters,
            }
            for key, planned in expected_metadata.items():
                if key in metadata and metadata[key] != planned:
                    parameter_mismatches += 1
            if specification.collection_window_start is not None:
                observed_at = datetime.fromisoformat(row["observed_at"])
                if not (specification.collection_window_start <= observed_at <= specification.collection_window_end):
                    outside += 1

        total = len(observations)
        for group in required_groups:
            count = usable.get(group, 0)
            planned = specification.min_samples_per_group
            if 0 < count < planned:
                material = count / planned < 0.80
                findings.append(DeviationFinding(
                    category="sample_size", code="SAMPLE_BELOW_PLAN", material=material,
                    observed=count, planned=planned,
                    detail="La taille utilisable est inférieure au minimum préenregistré.",
                ))
        if endpoint_mismatches:
            findings.append(DeviationFinding(
                category="endpoint", code="ENDPOINT_OR_UNIT_MISMATCH", material=True,
                observed=endpoint_mismatches, planned=0,
                detail="Des mesures déclarent un endpoint ou une unité différente du protocole.",
            ))
        if parameter_mismatches:
            findings.append(DeviationFinding(
                category="parameters", code="METHOD_OR_PARAMETER_MISMATCH", material=True,
                observed=parameter_mismatches, planned=0,
                detail="Des paramètres d'exécution diffèrent du préenregistrement.",
            ))
        if total and outside:
            fraction = outside / total
            findings.append(DeviationFinding(
                category="time_window", code="OUTSIDE_COLLECTION_WINDOW", material=fraction > 0.10,
                observed=fraction, planned="<= 0.10",
                detail="Des observations se situent hors de la fenêtre préenregistrée.",
            ))
        if total and excluded:
            fraction = excluded / total
            findings.append(DeviationFinding(
                category="exclusions", code="EXCLUSIONS_PRESENT", material=fraction > specification.max_exclusion_fraction,
                observed=fraction, planned=f"<= {specification.max_exclusion_fraction}",
                detail="La proportion d'exclusions est comparée au plafond préenregistré.",
            ))
        if total and missing:
            fraction = missing / total
            findings.append(DeviationFinding(
                category="missing_data", code="MISSING_DATA_PRESENT", material=fraction > specification.max_missing_fraction,
                observed=fraction, planned=f"<= {specification.max_missing_fraction}",
                detail="La proportion de données manquantes est comparée au plafond préenregistré.",
            ))

        if incompatible_reference:
            verdict = DeviationVerdict.INCOMPATIBLE
        elif stale_evaluation or total == 0 or any(usable.get(group, 0) == 0 for group in required_groups):
            verdict = DeviationVerdict.INSUFFICIENT
        elif any(item.material for item in findings):
            verdict = DeviationVerdict.MATERIAL_DEVIATIONS
        elif findings:
            verdict = DeviationVerdict.MINOR_DEVIATIONS
        else:
            verdict = DeviationVerdict.ADHERENT
        payload = {
            "experiment_id": experiment_id, "protocol_version": protocol_version,
            "evaluation_id": data.evaluation_id, "experiment_hash": experiment.experiment_hash,
            "protocol_hash": protocol["protocol_hash"], "observations_snapshot_hash": snapshot_hash,
            "verdict": verdict.value, "findings": [item.model_dump(mode="json") for item in findings],
            "planned_samples_per_required_group": specification.min_samples_per_group,
            "usable_samples_by_group": usable, "total_observations": total,
            "excluded_observations": excluded, "missing_observations": missing,
            "out_of_window_observations": outside, "endpoint_mismatches": endpoint_mismatches,
            "parameter_mismatches": parameter_mismatches,
            "sample_materiality_floor": 0.80, "out_of_window_material_fraction": 0.10,
        }
        report_hash = canonical_hash(payload)
        with self.connect() as connection:
            existing = connection.execute("SELECT * FROM deviation_reports WHERE report_hash=?", (report_hash,)).fetchone()
            if existing:
                return self._deviation_report(existing, idempotent=True)
            report_id, created_at = str(uuid.uuid4()), now()
            report = ProtocolDeviationReport(id=report_id, report_hash=report_hash, created_at=created_at, **payload)
            connection.execute(
                "INSERT INTO deviation_reports VALUES(?,?,?,?,?,?,?,?)",
                (report_id, experiment_id, protocol["id"], data.evaluation_id, verdict.value, report.model_dump_json(), report_hash, created_at),
            )
            self._audit(connection, "DEVIATION_REPORT_FROZEN", "deviation_report", report_id, {
                "experiment_id": experiment_id, "protocol_version": protocol_version,
                "report_hash": report_hash, "verdict": verdict.value,
            })
        return report

    def _deviation_report(self, row, idempotent: bool = False) -> ProtocolDeviationReport:
        report = ProtocolDeviationReport.model_validate_json(row["report_json"])
        return report.model_copy(update={"idempotent_replay": idempotent})

    def get_deviation_report(self, report_id: str) -> ProtocolDeviationReport:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM deviation_reports WHERE id=?", (report_id,)).fetchone()
        if not row:
            raise KeyError("deviation report not found")
        return self._deviation_report(row)

    def list_deviation_reports(self) -> list[ProtocolDeviationReport]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM deviation_reports ORDER BY created_at,id").fetchall()
        return [self._deviation_report(row) for row in rows]

    def create_effect_stability_dossier(
        self, data: EffectStabilityDossierCreate
    ) -> EffectStabilityDossier:
        inputs = [self._load_synthesis_input(item) for item in data.evaluation_ids]
        for item in inputs:
            if canonical_hash(item["specification"].model_dump(mode="json")) != item["row"]["protocol_hash"]:
                raise ValueError("stored protocol hash does not match its specification")
            recalculated_hash = canonical_hash({
                "experiment_hash": item["row"]["experiment_hash"],
                "protocol_hash": item["row"]["protocol_hash"],
                "observations_snapshot_hash": item["row"]["observations_snapshot_hash"],
                "method": item["specification"].analysis_method,
                "verdict": item["verdict"].value,
                "aggregates": {
                    name: aggregate.model_dump(mode="json")
                    for name, aggregate in item["aggregates"].items()
                },
                "treatment_minus_control": item["effect"],
                "standard_error": item["standard_error"],
                "interval95": item["interval"].model_dump(mode="json"),
                "seed": item["specification"].seed,
            })
            if recalculated_hash != item["row"]["evaluation_hash"]:
                raise ValueError("stored evaluation hash does not match recalculated observations")
        # Protocol version is the semantic order; IDs only break impossible ties.
        inputs.sort(key=lambda item: (item["row"]["version"], item["row"]["id"]))
        baseline = inputs[0]
        base_hypothesis = baseline["hypothesis"]
        base_specification = baseline["specification"]
        compatibility = EffectStabilityCompatibility(
            same_experiment=all(
                item["row"]["experiment_id"] == baseline["row"]["experiment_id"]
                for item in inputs
            ),
            hypothesis_statement=all(
                item["hypothesis"].statement.casefold()
                == base_hypothesis.statement.casefold()
                for item in inputs
            ),
            metric_name=all(
                item["specification"].metric_name.casefold()
                == base_specification.metric_name.casefold()
                for item in inputs
            ),
            metric_unit=all(
                item["specification"].metric_unit.casefold()
                == base_specification.metric_unit.casefold()
                for item in inputs
            ),
            group_roles=all(
                item["hypothesis"].control_group == base_hypothesis.control_group
                and item["hypothesis"].treatment_group == base_hypothesis.treatment_group
                and set(item["specification"].groups) == set(base_specification.groups)
                for item in inputs
            ),
            direction=all(
                item["hypothesis"].direction == base_hypothesis.direction
                for item in inputs
            ),
            analysis_method=all(
                item["specification"].analysis_method
                == base_specification.analysis_method
                for item in inputs
            ),
        )
        distinct_versions = len({item["row"]["version"] for item in inputs}) == len(inputs)
        sufficient = distinct_versions and all(
            item["effect"] is not None
            and item["interval"].lower is not None
            and item["interval"].upper is not None
            for item in inputs
        )
        snapshots = [
            EffectStabilityEvaluationSnapshot(
                evaluation_id=item["row"]["id"],
                experiment_id=item["row"]["experiment_id"],
                protocol_version=item["row"]["version"],
                protocol_hash=item["row"]["protocol_hash"],
                evaluation_hash=item["row"]["evaluation_hash"],
                observations_snapshot_hash=item["row"]["observations_snapshot_hash"],
                effect=item["effect"],
                interval95=item["interval"],
            )
            for item in inputs
        ]
        transitions: list[EffectStabilityTransition] = []
        relative_range = None
        if compatibility.compatible and sufficient:
            effects = [item["effect"] for item in inputs]
            scale = max(max(abs(effect) for effect in effects), 1e-12)
            relative_range = (max(effects) - min(effects)) / scale
            for previous, current in zip(inputs, inputs[1:]):
                delta = current["effect"] - previous["effect"]
                denominator = max(abs(previous["effect"]), abs(current["effect"]), 1e-12)
                relative_delta = abs(delta) / denominator
                direction_changed = (
                    (previous["effect"] < 0 < current["effect"])
                    or (current["effect"] < 0 < previous["effect"])
                )
                overlap = max(previous["interval"].lower, current["interval"].lower) <= min(
                    previous["interval"].upper, current["interval"].upper
                )
                transitions.append(EffectStabilityTransition(
                    from_evaluation_id=previous["row"]["id"],
                    to_evaluation_id=current["row"]["id"],
                    from_protocol_version=previous["row"]["version"],
                    to_protocol_version=current["row"]["version"],
                    effect_delta=delta,
                    relative_delta=relative_delta,
                    direction_changed=direction_changed,
                    intervals_overlap=overlap,
                    shifted=direction_changed or not overlap or relative_delta >= 0.10,
                ))
        if not compatibility.compatible:
            qualification = EffectStabilityQualification.INCOMPATIBLE
        elif not sufficient:
            qualification = EffectStabilityQualification.INSUFFICIENT
        elif any(item.shifted for item in transitions):
            qualification = EffectStabilityQualification.SHIFTED
        else:
            qualification = EffectStabilityQualification.STABLE
        worst = max(
            transitions,
            key=lambda item: (item.direction_changed, not item.intervals_overlap, item.relative_delta),
            default=None,
        )
        evaluation_ids = [item.evaluation_id for item in snapshots]
        payload = {
            "evaluation_ids": evaluation_ids,
            "experiment_id": baseline["row"]["experiment_id"] if compatibility.same_experiment else None,
            "qualification": qualification.value,
            "compatibility": compatibility.model_dump(mode="json"),
            "evaluations": [item.model_dump(mode="json") for item in snapshots],
            "transitions": [item.model_dump(mode="json") for item in transitions],
            "relative_range": relative_range,
            "worst_transition": worst.model_dump(mode="json") if worst else None,
            "method": "protocol-version-effect-stability-v1",
            "relative_delta_threshold": 0.10,
        }
        dossier_hash = canonical_hash(payload)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM effect_stability_dossiers WHERE dossier_hash=?",
                (dossier_hash,),
            ).fetchone()
            if existing:
                return self._effect_stability_dossier(existing, idempotent=True)
            dossier_id, created_at = str(uuid.uuid4()), now()
            dossier = EffectStabilityDossier(
                id=dossier_id, dossier_hash=dossier_hash, created_at=created_at, **payload
            )
            connection.execute(
                "INSERT INTO effect_stability_dossiers VALUES(?,?,?,?,?,?,?)",
                (dossier_id, json.dumps(evaluation_ids), payload["experiment_id"],
                 qualification.value, dossier.model_dump_json(), dossier_hash, created_at),
            )
            self._audit(connection, "EFFECT_STABILITY_DOSSIER_FROZEN", "effect_stability_dossier", dossier_id, {
                "experiment_id": payload["experiment_id"], "evaluation_ids": evaluation_ids,
                "dossier_hash": dossier_hash, "qualification": qualification.value,
            })
        return dossier

    def _effect_stability_dossier(self, row, idempotent=False) -> EffectStabilityDossier:
        dossier = EffectStabilityDossier.model_validate_json(row["dossier_json"])
        return dossier.model_copy(update={"idempotent_replay": idempotent})

    def get_effect_stability_dossier(self, dossier_id: str) -> EffectStabilityDossier:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM effect_stability_dossiers WHERE id=?", (dossier_id,)
            ).fetchone()
        if not row:
            raise KeyError("effect stability dossier not found")
        return self._effect_stability_dossier(row)

    def list_effect_stability_dossiers(self) -> list[EffectStabilityDossier]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM effect_stability_dossiers ORDER BY created_at,id"
            ).fetchall()
        return [self._effect_stability_dossier(row) for row in rows]

    def create_replication_robustness_dossier(
        self, data: ReplicationRobustnessDossierCreate
    ) -> ReplicationRobustnessDossier:
        inputs = [self._load_synthesis_input(item) for item in data.evaluation_ids]
        for item in inputs:
            if canonical_hash(item["specification"].model_dump(mode="json")) != item["row"]["protocol_hash"]:
                raise ValueError("stored protocol hash does not match its specification")
            recalculated_hash = canonical_hash({
                "experiment_hash": item["row"]["experiment_hash"],
                "protocol_hash": item["row"]["protocol_hash"],
                "observations_snapshot_hash": item["row"]["observations_snapshot_hash"],
                "method": item["specification"].analysis_method,
                "verdict": item["verdict"].value,
                "aggregates": {
                    name: aggregate.model_dump(mode="json")
                    for name, aggregate in item["aggregates"].items()
                },
                "treatment_minus_control": item["effect"],
                "standard_error": item["standard_error"],
                "interval95": item["interval"].model_dump(mode="json"),
                "seed": item["specification"].seed,
            })
            if recalculated_hash != item["row"]["evaluation_hash"]:
                raise ValueError("stored evaluation hash does not match recalculated observations")
        inputs.sort(key=lambda item: (
            item["row"]["created_at"], item["row"]["experiment_id"],
            item["row"]["version"], item["row"]["id"],
        ))
        compatibility = synthesis_compatibility(
            [(item["hypothesis"], item["specification"]) for item in inputs]
        )
        sufficient = all(
            item["effect"] is not None
            and item["effect_variance"] is not None
            and item["interval"].lower is not None
            and item["interval"].upper is not None
            for item in inputs
        )
        deviations = {
            item["row"]["id"]: self.create_deviation_report(
                DeviationReportCreate(evaluation_id=item["row"]["id"])
            )
            for item in inputs
        }
        reference = inputs[0]
        reference_effect = reference["effect"]
        reference_interval = reference["interval"]
        reference_sign = (
            1 if reference_effect is not None and reference_effect > 0
            else -1 if reference_effect is not None and reference_effect < 0
            else 0 if reference_effect is not None else None
        )
        snapshots: list[ReplicationRobustnessSnapshot] = []
        for index, item in enumerate(inputs):
            effect = item["effect"]
            sign = 1 if effect is not None and effect > 0 else -1 if effect is not None and effect < 0 else 0 if effect is not None else None
            overlap = None
            relative_delta = None
            supports = None
            contradicts = None
            if index > 0 and sufficient:
                overlap = max(reference_interval.lower, item["interval"].lower) <= min(
                    reference_interval.upper, item["interval"].upper
                )
                relative_delta = abs(effect - reference_effect) / max(
                    abs(effect), abs(reference_effect), 1e-12
                )
                supports = sign == reference_sign and overlap and item["verdict"].value != "REJECTED"
                contradicts = sign != reference_sign or not overlap or item["verdict"].value == "REJECTED"
            deviation = deviations[item["row"]["id"]]
            snapshots.append(ReplicationRobustnessSnapshot(
                evaluation_id=item["row"]["id"],
                experiment_id=item["row"]["experiment_id"],
                protocol_version=item["row"]["version"],
                protocol_hash=item["row"]["protocol_hash"],
                evaluation_hash=item["row"]["evaluation_hash"],
                observations_snapshot_hash=item["row"]["observations_snapshot_hash"],
                effect=effect,
                effect_variance=item["effect_variance"],
                interval95=item["interval"],
                source_verdict=item["verdict"],
                deviation_qualification=deviation.verdict,
                deviation_report_hash=deviation.report_hash,
                sign=sign,
                supports_reference=supports,
                contradicts_reference=contradicts,
                interval_overlaps_reference=overlap,
                relative_delta_from_reference=relative_delta,
            ))
        transitions: list[ReplicationRobustnessTransition] = []
        if sufficient:
            for previous, current in zip(inputs, inputs[1:]):
                delta = current["effect"] - previous["effect"]
                relative_delta = abs(delta) / max(
                    abs(current["effect"]), abs(previous["effect"]), 1e-12
                )
                previous_sign = 1 if previous["effect"] > 0 else -1 if previous["effect"] < 0 else 0
                current_sign = 1 if current["effect"] > 0 else -1 if current["effect"] < 0 else 0
                overlap = max(previous["interval"].lower, current["interval"].lower) <= min(
                    previous["interval"].upper, current["interval"].upper
                )
                transitions.append(ReplicationRobustnessTransition(
                    from_evaluation_id=previous["row"]["id"],
                    to_evaluation_id=current["row"]["id"],
                    effect_delta=delta,
                    relative_delta=relative_delta,
                    direction_changed=previous_sign != current_sign,
                    intervals_overlap=overlap,
                ))
        calculation = None
        mean_effect = effect_range = relative_effect_range = effect_standard_deviation = None
        if compatibility.compatible and sufficient:
            effects = [item["effect"] for item in inputs]
            calculation = fixed_effect_synthesis(
                inputs[0]["hypothesis"].direction,
                effects,
                [item["effect_variance"] for item in inputs],
            )
            mean_effect = statistics.fmean(effects)
            effect_range = max(effects) - min(effects)
            relative_effect_range = effect_range / max(max(abs(effect) for effect in effects), 1e-12)
            effect_standard_deviation = statistics.stdev(effects)
        replicas = snapshots[1:]
        supporting_count = sum(item.supports_reference is True for item in replicas)
        contradicting_count = sum(item.contradicts_reference is True for item in replicas)
        worst_replication = max(
            replicas,
            key=lambda item: (
                item.contradicts_reference is True,
                item.relative_delta_from_reference or 0.0,
                item.evaluation_id,
            ),
            default=None,
        )
        worst_transition = max(
            transitions,
            key=lambda item: (
                item.direction_changed, not item.intervals_overlap,
                item.relative_delta, item.to_evaluation_id,
            ),
            default=None,
        )
        material_deviation = any(
            item.deviation_qualification in {
                DeviationVerdict.MATERIAL_DEVIATIONS, DeviationVerdict.INCOMPATIBLE
            }
            for item in snapshots
        )
        insufficient_deviation = any(
            item.deviation_qualification is DeviationVerdict.INSUFFICIENT
            for item in snapshots
        )
        if not compatibility.compatible:
            qualification = ReplicationRobustnessQualification.INCOMPATIBLE
        elif not sufficient or insufficient_deviation:
            qualification = ReplicationRobustnessQualification.INSUFFICIENT
        elif (
            not calculation["direction_consistent"]
            or calculation["heterogeneity_i2_percent"] >= 50.0
            or relative_effect_range >= 0.20
            or contradicting_count > 0
            or material_deviation
        ):
            qualification = ReplicationRobustnessQualification.DIVERGENT
        else:
            qualification = ReplicationRobustnessQualification.ROBUST
        evaluation_ids = [item.evaluation_id for item in snapshots]
        experiment_ids = sorted({item.experiment_id for item in snapshots})
        payload = {
            "evaluation_ids": evaluation_ids,
            "qualification": qualification.value,
            "compatibility": compatibility.model_dump(mode="json"),
            "reference_evaluation_id": snapshots[0].evaluation_id,
            "evaluations": [item.model_dump(mode="json") for item in snapshots],
            "transitions": [item.model_dump(mode="json") for item in transitions],
            "supporting_replication_count": supporting_count,
            "contradicting_replication_count": contradicting_count,
            "direction_consistent": calculation["direction_consistent"] if calculation else None,
            "mean_effect": mean_effect,
            "effect_range": effect_range,
            "relative_effect_range": relative_effect_range,
            "effect_standard_deviation": effect_standard_deviation,
            "heterogeneity_i2_percent": calculation["heterogeneity_i2_percent"] if calculation else None,
            "worst_replication": worst_replication.model_dump(mode="json") if worst_replication else None,
            "worst_transition": worst_transition.model_dump(mode="json") if worst_transition else None,
            "method": "multi-evaluation-replication-robustness-v1",
            "relative_dispersion_threshold": 0.20,
            "heterogeneity_i2_threshold_percent": 50.0,
        }
        dossier_hash = canonical_hash(payload)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM replication_robustness_dossiers WHERE dossier_hash=?",
                (dossier_hash,),
            ).fetchone()
            if existing:
                return self._replication_robustness_dossier(existing, idempotent=True)
            dossier_id, created_at = str(uuid.uuid4()), now()
            dossier = ReplicationRobustnessDossier(
                id=dossier_id, dossier_hash=dossier_hash, created_at=created_at, **payload
            )
            connection.execute(
                "INSERT INTO replication_robustness_dossiers VALUES(?,?,?,?,?,?,?)",
                (dossier_id, json.dumps(evaluation_ids), json.dumps(experiment_ids),
                 qualification.value, dossier.model_dump_json(), dossier_hash, created_at),
            )
            self._audit(connection, "REPLICATION_ROBUSTNESS_DOSSIER_FROZEN", "replication_robustness_dossier", dossier_id, {
                "evaluation_ids": evaluation_ids, "experiment_ids": experiment_ids,
                "dossier_hash": dossier_hash, "qualification": qualification.value,
            })
        return dossier

    def _replication_robustness_dossier(self, row, idempotent=False) -> ReplicationRobustnessDossier:
        dossier = ReplicationRobustnessDossier.model_validate_json(row["dossier_json"])
        return dossier.model_copy(update={"idempotent_replay": idempotent})

    def get_replication_robustness_dossier(self, dossier_id: str) -> ReplicationRobustnessDossier:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM replication_robustness_dossiers WHERE id=?", (dossier_id,)
            ).fetchone()
        if not row:
            raise KeyError("replication robustness dossier not found")
        return self._replication_robustness_dossier(row)

    def list_replication_robustness_dossiers(self) -> list[ReplicationRobustnessDossier]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM replication_robustness_dossiers ORDER BY created_at,id"
            ).fetchall()
        return [self._replication_robustness_dossier(row) for row in rows]

    def create_replication_evidence_coverage_dossier(
        self, data: ReplicationEvidenceCoverageDossierCreate
    ) -> ReplicationEvidenceCoverageDossier:
        inputs = [self._load_synthesis_input(item) for item in data.evaluation_ids]
        for item in inputs:
            if canonical_hash(item["specification"].model_dump(mode="json")) != item["row"]["protocol_hash"]:
                raise ValueError("stored protocol hash does not match its specification")
            recalculated_hash = canonical_hash({
                "experiment_hash": item["row"]["experiment_hash"],
                "protocol_hash": item["row"]["protocol_hash"],
                "observations_snapshot_hash": item["row"]["observations_snapshot_hash"],
                "method": item["specification"].analysis_method,
                "verdict": item["verdict"].value,
                "aggregates": {
                    name: aggregate.model_dump(mode="json")
                    for name, aggregate in item["aggregates"].items()
                },
                "treatment_minus_control": item["effect"],
                "standard_error": item["standard_error"],
                "interval95": item["interval"].model_dump(mode="json"),
                "seed": item["specification"].seed,
            })
            if recalculated_hash != item["row"]["evaluation_hash"]:
                raise ValueError("stored evaluation hash does not match recalculated observations")

        inputs.sort(key=lambda item: (
            item["row"]["created_at"], item["row"]["experiment_id"],
            item["row"]["version"], item["row"]["id"],
        ))
        compatibility = synthesis_compatibility(
            [(item["hypothesis"], item["specification"]) for item in inputs]
        )
        required_checks = [
            "HASHES_VERIFIED",
            "REQUIRED_GROUPS_OBSERVED",
            "MINIMUM_SAMPLE_PLAN_MET",
            "SOURCE_PROVENANCE_PRESENT",
            "SUBJECT_PROVENANCE_PRESENT",
            "CURRENT_SNAPSHOT_VERIFIED",
            "PROTOCOL_ADHERENT",
            "ANALYTIC_RESULT_AVAILABLE",
        ]
        snapshots: list[ReplicationEvidenceCoverageSnapshot] = []
        for item in inputs:
            deviation = self.create_deviation_report(
                DeviationReportCreate(evaluation_id=item["row"]["id"])
            )
            with self.connect() as connection:
                observations = connection.execute(
                    """SELECT source_ref,subject_ref FROM observations
                       WHERE experiment_id=? AND protocol_id=? ORDER BY observation_hash""",
                    (item["row"]["experiment_id"], item["row"]["protocol_id"]),
                ).fetchall()
            hypothesis = item["hypothesis"]
            specification = item["specification"]
            required_groups = [hypothesis.control_group, hypothesis.treatment_group]
            group_counts = {
                group: item["aggregates"].get(group).count
                if item["aggregates"].get(group) is not None else 0
                for group in required_groups
            }
            checks = {
                "HASHES_VERIFIED": True,
                "REQUIRED_GROUPS_OBSERVED": all(group_counts[group] > 0 for group in required_groups),
                "MINIMUM_SAMPLE_PLAN_MET": all(
                    group_counts[group] >= specification.min_samples_per_group
                    for group in required_groups
                ),
                "SOURCE_PROVENANCE_PRESENT": bool(observations) and all(
                    bool(row["source_ref"].strip()) for row in observations
                ),
                "SUBJECT_PROVENANCE_PRESENT": bool(observations) and all(
                    bool(row["subject_ref"] and row["subject_ref"].strip())
                    for row in observations
                ),
                "CURRENT_SNAPSHOT_VERIFIED": True,
                "PROTOCOL_ADHERENT": deviation.verdict is DeviationVerdict.ADHERENT,
                "ANALYTIC_RESULT_AVAILABLE": (
                    item["effect"] is not None
                    and item["interval"].lower is not None
                    and item["interval"].upper is not None
                ),
            }
            covered = [code for code in required_checks if checks[code]]
            gaps = [code for code in required_checks if not checks[code]]
            snapshots.append(ReplicationEvidenceCoverageSnapshot(
                evaluation_id=item["row"]["id"],
                experiment_id=item["row"]["experiment_id"],
                protocol_version=item["row"]["version"],
                protocol_hash=item["row"]["protocol_hash"],
                evaluation_hash=item["row"]["evaluation_hash"],
                observations_snapshot_hash=item["row"]["observations_snapshot_hash"],
                source_verdict=item["verdict"],
                deviation_qualification=deviation.verdict,
                deviation_report_hash=deviation.report_hash,
                covered_checks=covered,
                gap_codes=gaps,
                covered_check_count=len(covered),
                required_check_count=len(required_checks),
                coverage_ratio=len(covered) / len(required_checks),
            ))

        experiment_ids = sorted({item.experiment_id for item in snapshots})
        common_covered = [
            code for code in required_checks
            if all(code in item.covered_checks for item in snapshots)
        ]
        common_gaps = [
            code for code in required_checks
            if all(code in item.gap_codes for item in snapshots)
        ]
        total_gap_count = sum(len(item.gap_codes) for item in snapshots)
        mean_ratio = statistics.fmean(item.coverage_ratio for item in snapshots)
        minimum_ratio = min(item.coverage_ratio for item in snapshots)
        worst = min(
            snapshots,
            key=lambda item: (item.coverage_ratio, -len(item.gap_codes), item.evaluation_id),
        )
        if not compatibility.compatible:
            qualification = ReplicationEvidenceCoverageQualification.INCOMPATIBLE
        elif len(experiment_ids) < 2 or any(
            item.source_verdict is Verdict.INSUFFICIENT
            or item.deviation_qualification is DeviationVerdict.INSUFFICIENT
            for item in snapshots
        ):
            qualification = ReplicationEvidenceCoverageQualification.INSUFFICIENT
        elif total_gap_count == 0:
            qualification = ReplicationEvidenceCoverageQualification.COMPLETE
        else:
            qualification = ReplicationEvidenceCoverageQualification.PARTIAL
        evaluation_ids = [item.evaluation_id for item in snapshots]
        payload = {
            "evaluation_ids": evaluation_ids,
            "experiment_ids": experiment_ids,
            "qualification": qualification.value,
            "compatibility": compatibility.model_dump(mode="json"),
            "evaluations": [item.model_dump(mode="json") for item in snapshots],
            "required_checks": required_checks,
            "common_covered_checks": common_covered,
            "common_gap_codes": common_gaps,
            "total_gap_count": total_gap_count,
            "mean_coverage_ratio": mean_ratio,
            "minimum_coverage_ratio": minimum_ratio,
            "worst_evaluation": worst.model_dump(mode="json"),
            "method": "replication-evidence-protocol-coverage-v1",
        }
        dossier_hash = canonical_hash(payload)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM replication_evidence_coverage_dossiers WHERE dossier_hash=?",
                (dossier_hash,),
            ).fetchone()
            if existing:
                return self._replication_evidence_coverage_dossier(existing, idempotent=True)
            dossier_id, created_at = str(uuid.uuid4()), now()
            dossier = ReplicationEvidenceCoverageDossier(
                id=dossier_id, dossier_hash=dossier_hash, created_at=created_at, **payload
            )
            connection.execute(
                "INSERT INTO replication_evidence_coverage_dossiers VALUES(?,?,?,?,?,?,?)",
                (dossier_id, json.dumps(evaluation_ids), json.dumps(experiment_ids),
                 qualification.value, dossier.model_dump_json(), dossier_hash, created_at),
            )
            self._audit(connection, "REPLICATION_EVIDENCE_COVERAGE_DOSSIER_FROZEN",
                        "replication_evidence_coverage_dossier", dossier_id, {
                "evaluation_ids": evaluation_ids, "experiment_ids": experiment_ids,
                "dossier_hash": dossier_hash, "qualification": qualification.value,
            })
        return dossier

    def _replication_evidence_coverage_dossier(
        self, row, idempotent: bool = False
    ) -> ReplicationEvidenceCoverageDossier:
        dossier = ReplicationEvidenceCoverageDossier.model_validate_json(row["dossier_json"])
        return dossier.model_copy(update={"idempotent_replay": idempotent})

    def get_replication_evidence_coverage_dossier(
        self, dossier_id: str
    ) -> ReplicationEvidenceCoverageDossier:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM replication_evidence_coverage_dossiers WHERE id=?",
                (dossier_id,),
            ).fetchone()
        if not row:
            raise KeyError("replication evidence coverage dossier not found")
        return self._replication_evidence_coverage_dossier(row)

    def list_replication_evidence_coverage_dossiers(
        self,
    ) -> list[ReplicationEvidenceCoverageDossier]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM replication_evidence_coverage_dossiers ORDER BY created_at,id"
            ).fetchall()
        return [self._replication_evidence_coverage_dossier(row) for row in rows]

    def list_audit(self, experiment_id: str) -> list[AuditEvent]:
        self.get_experiment(experiment_id)
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT audit_events.* FROM audit_events
                   WHERE (entity_type='experiment' AND entity_id=?)
                      OR json_extract(payload_json,'$.experiment_id')=?
                      OR entity_id IN (SELECT id FROM protocols WHERE experiment_id=?)
                      OR entity_id IN (SELECT id FROM observations WHERE experiment_id=?)
                      OR entity_id IN (SELECT id FROM evaluations WHERE experiment_id=?)
                      OR entity_id IN (
                           SELECT id FROM replication_reports
                           WHERE original_experiment_id=? OR replication_experiment_id=?
                      )
                      OR entity_id IN (
                           SELECT id FROM synthesis_reports
                           WHERE EXISTS (
                             SELECT 1 FROM json_each(experiment_ids_json) WHERE value=?
                           )
                      )
                      OR entity_id IN (
                           SELECT id FROM influence_reports
                           WHERE EXISTS (
                             SELECT 1 FROM json_each(experiment_ids_json) WHERE value=?
                           )
                      )
                      OR entity_id IN (
                           SELECT id FROM deviation_reports WHERE experiment_id=?
                      )
                      OR entity_id IN (
                           SELECT id FROM effect_stability_dossiers WHERE experiment_id=?
                      )
                      OR entity_id IN (
                           SELECT id FROM replication_robustness_dossiers
                           WHERE EXISTS (
                             SELECT 1 FROM json_each(experiment_ids_json) WHERE value=?
                           )
                      )
                      OR entity_id IN (
                           SELECT id FROM replication_evidence_coverage_dossiers
                           WHERE EXISTS (
                             SELECT 1 FROM json_each(experiment_ids_json) WHERE value=?
                           )
                      )
                   ORDER BY sequence""",
                (
                    experiment_id,
                    experiment_id,
                    experiment_id,
                    experiment_id,
                    experiment_id,
                    experiment_id,
                    experiment_id,
                    experiment_id,
                    experiment_id,
                    experiment_id,
                    experiment_id,
                    experiment_id,
                    experiment_id,
                ),
            ).fetchall()
        return [
            AuditEvent(
                sequence=row["sequence"],
                event_type=row["event_type"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                payload=json.loads(row["payload_json"]),
                previous_event_hash=row["previous_event_hash"],
                event_hash=row["event_hash"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
