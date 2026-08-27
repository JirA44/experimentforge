CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE experiments(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_hash char(64) NOT NULL UNIQUE,
  name text NOT NULL,
  description text NOT NULL,
  hypothesis jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE protocols(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id uuid NOT NULL REFERENCES experiments(id),
  version integer NOT NULL CHECK(version >= 1),
  protocol_hash char(64) NOT NULL,
  specification jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(experiment_id, version),
  UNIQUE(experiment_id, protocol_hash)
);

CREATE TABLE observations(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id uuid NOT NULL REFERENCES experiments(id),
  protocol_id uuid NOT NULL REFERENCES protocols(id),
  idempotency_key text NOT NULL,
  group_name text NOT NULL,
  value double precision NOT NULL CHECK(
    value > '-Infinity'::double precision
    AND value < 'Infinity'::double precision
    AND value::text <> 'NaN'
  ),
  observed_at timestamptz NOT NULL,
  source_ref text NOT NULL,
  subject_ref text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  observation_hash char(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(experiment_id, idempotency_key),
  UNIQUE(experiment_id, observation_hash)
);

CREATE TABLE evaluations(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id uuid NOT NULL REFERENCES experiments(id),
  protocol_id uuid NOT NULL REFERENCES protocols(id),
  method text NOT NULL,
  verdict text NOT NULL CHECK(verdict IN ('SUPPORTED','REJECTED','INCONCLUSIVE','INSUFFICIENT')),
  aggregates jsonb NOT NULL,
  contrast double precision,
  standard_error double precision,
  interval95 jsonb NOT NULL,
  observations_snapshot_hash char(64) NOT NULL,
  evaluation_hash char(64) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(experiment_id, protocol_id, observations_snapshot_hash, method)
);

CREATE TABLE replication_reports(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  original_experiment_id uuid NOT NULL REFERENCES experiments(id),
  original_protocol_id uuid NOT NULL REFERENCES protocols(id),
  replication_experiment_id uuid NOT NULL REFERENCES experiments(id),
  replication_protocol_id uuid NOT NULL REFERENCES protocols(id),
  verdict text NOT NULL CHECK(
    verdict IN ('REPLICATED','NOT_REPLICATED','INSUFFICIENT','INCOMPATIBLE')
  ),
  compatibility jsonb NOT NULL,
  original_snapshot jsonb NOT NULL,
  replication_snapshot jsonb NOT NULL,
  intervals_overlap boolean,
  report_hash char(64) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE synthesis_reports(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  evaluation_ids jsonb NOT NULL CHECK(jsonb_typeof(evaluation_ids) = 'array'),
  experiment_ids jsonb NOT NULL CHECK(jsonb_typeof(experiment_ids) = 'array'),
  verdict text NOT NULL CHECK(
    verdict IN ('CONSISTENT','HETEROGENEOUS','INSUFFICIENT','INCOMPATIBLE')
  ),
  report jsonb NOT NULL,
  synthesis_hash char(64) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE influence_reports(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  synthesis_id uuid NOT NULL REFERENCES synthesis_reports(id),
  experiment_ids jsonb NOT NULL CHECK(jsonb_typeof(experiment_ids) = 'array'),
  verdict text NOT NULL CHECK(
    verdict IN ('ROBUST','INFLUENTIAL','INSUFFICIENT','INCOMPATIBLE')
  ),
  report jsonb NOT NULL,
  influence_hash char(64) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE deviation_reports(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id uuid NOT NULL REFERENCES experiments(id),
  protocol_id uuid NOT NULL REFERENCES protocols(id),
  evaluation_id uuid REFERENCES evaluations(id),
  verdict text NOT NULL CHECK(verdict IN ('ADHERENT','MINOR_DEVIATIONS','MATERIAL_DEVIATIONS','INSUFFICIENT','INCOMPATIBLE')),
  report jsonb NOT NULL,
  report_hash char(64) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE effect_stability_dossiers(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  evaluation_ids jsonb NOT NULL CHECK(jsonb_typeof(evaluation_ids) = 'array'),
  experiment_id uuid REFERENCES experiments(id),
  qualification text NOT NULL CHECK(
    qualification IN ('STABLE','SHIFTED','INSUFFICIENT','INCOMPATIBLE')
  ),
  dossier jsonb NOT NULL,
  dossier_hash char(64) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE replication_robustness_dossiers(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  evaluation_ids jsonb NOT NULL CHECK(jsonb_typeof(evaluation_ids) = 'array'),
  experiment_ids jsonb NOT NULL CHECK(jsonb_typeof(experiment_ids) = 'array'),
  qualification text NOT NULL CHECK(
    qualification IN ('ROBUST','DIVERGENT','INSUFFICIENT','INCOMPATIBLE')
  ),
  dossier jsonb NOT NULL,
  dossier_hash char(64) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE replication_evidence_coverage_dossiers(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  evaluation_ids jsonb NOT NULL CHECK(jsonb_typeof(evaluation_ids) = 'array'),
  experiment_ids jsonb NOT NULL CHECK(jsonb_typeof(experiment_ids) = 'array'),
  qualification text NOT NULL CHECK(
    qualification IN ('COMPLETE','PARTIAL','INSUFFICIENT','INCOMPATIBLE')
  ),
  dossier jsonb NOT NULL,
  dossier_hash char(64) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_events(
  sequence bigserial PRIMARY KEY,
  event_type text NOT NULL,
  entity_type text NOT NULL,
  entity_id text NOT NULL,
  payload jsonb NOT NULL,
  previous_event_hash char(64),
  event_hash char(64) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION reject_immutable_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is immutable/append-only', TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER experiments_immutable BEFORE UPDATE OR DELETE ON experiments
FOR EACH ROW EXECUTE FUNCTION reject_immutable_mutation();
CREATE TRIGGER protocols_immutable BEFORE UPDATE OR DELETE ON protocols
FOR EACH ROW EXECUTE FUNCTION reject_immutable_mutation();
CREATE TRIGGER observations_append_only BEFORE UPDATE OR DELETE ON observations
FOR EACH ROW EXECUTE FUNCTION reject_immutable_mutation();
CREATE TRIGGER evaluations_immutable BEFORE UPDATE OR DELETE ON evaluations
FOR EACH ROW EXECUTE FUNCTION reject_immutable_mutation();
CREATE TRIGGER replication_reports_immutable BEFORE UPDATE OR DELETE ON replication_reports
FOR EACH ROW EXECUTE FUNCTION reject_immutable_mutation();
CREATE TRIGGER synthesis_reports_immutable BEFORE UPDATE OR DELETE ON synthesis_reports
FOR EACH ROW EXECUTE FUNCTION reject_immutable_mutation();
CREATE TRIGGER influence_reports_immutable BEFORE UPDATE OR DELETE ON influence_reports
FOR EACH ROW EXECUTE FUNCTION reject_immutable_mutation();
CREATE TRIGGER deviation_reports_immutable BEFORE UPDATE OR DELETE ON deviation_reports
FOR EACH ROW EXECUTE FUNCTION reject_immutable_mutation();
CREATE TRIGGER effect_stability_dossiers_immutable BEFORE UPDATE OR DELETE ON effect_stability_dossiers
FOR EACH ROW EXECUTE FUNCTION reject_immutable_mutation();
CREATE TRIGGER replication_robustness_dossiers_immutable BEFORE UPDATE OR DELETE ON replication_robustness_dossiers
FOR EACH ROW EXECUTE FUNCTION reject_immutable_mutation();
CREATE TRIGGER replication_evidence_coverage_dossiers_immutable BEFORE UPDATE OR DELETE ON replication_evidence_coverage_dossiers
FOR EACH ROW EXECUTE FUNCTION reject_immutable_mutation();
CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION reject_immutable_mutation();
