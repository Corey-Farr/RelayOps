"""Initial durable queue and control plane schema (frozen DDL)."""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE audit (\n\tid VARCHAR(36) NOT NULL, \n\tactor VARCHAR(254) NOT NULL, \n\taction VARCHAR(80) NOT NULL, \n\tresource VARCHAR(100) NOT NULL, \n\tdetails JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id)\n)"
    )
    op.execute(
        "CREATE TABLE incidents (\n\tid VARCHAR(36) NOT NULL, \n\tfingerprint VARCHAR(100) NOT NULL, \n\ttitle VARCHAR(200) NOT NULL, \n\tdescription TEXT NOT NULL, \n\tseverity VARCHAR(20) NOT NULL, \n\tsource VARCHAR(50) NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tcomponent VARCHAR(50) NOT NULL, \n\tevidence JSONB NOT NULL, \n\ttimeline JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (fingerprint)\n)"
    )
    op.execute(
        "CREATE TABLE policies (\n\tid VARCHAR(36) NOT NULL, \n\tversion INTEGER NOT NULL, \n\ttimeout_seconds FLOAT NOT NULL, \n\tmax_attempts INTEGER NOT NULL, \n\tbackoff_base FLOAT NOT NULL, \n\tbackoff_cap FLOAT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (version)\n)"
    )
    op.execute(
        "CREATE TABLE pools (\n\tregion VARCHAR(20) NOT NULL, \n\tpaused BOOLEAN NOT NULL, \n\tPRIMARY KEY (region)\n)"
    )
    op.execute(
        "CREATE TABLE projects (\n\tid VARCHAR(36) NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (name)\n)"
    )
    op.execute(
        "CREATE TABLE users (\n\tid VARCHAR(36) NOT NULL, \n\temail VARCHAR(254) NOT NULL, \n\tpassword_hash TEXT NOT NULL, \n\trole VARCHAR(16) NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (email)\n)"
    )
    op.execute(
        "CREATE TABLE workers (\n\tid VARCHAR(100) NOT NULL, \n\tregion VARCHAR(20) NOT NULL, \n\tlast_heartbeat TIMESTAMP WITH TIME ZONE NOT NULL, \n\tversion VARCHAR(30) NOT NULL, \n\tcapacity INTEGER NOT NULL, \n\tstate VARCHAR(20) NOT NULL, \n\tPRIMARY KEY (id)\n)"
    )
    op.execute("CREATE INDEX ix_workers_region ON workers (region)")
    op.execute(
        "CREATE TABLE api_keys (\n\tid VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(36) NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\tprefix VARCHAR(12) NOT NULL, \n\tdigest VARCHAR(64) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\trevoked_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(project_id) REFERENCES projects (id), \n\tUNIQUE (digest)\n)"
    )
    op.execute("CREATE INDEX ix_api_keys_project_id ON api_keys (project_id)")
    op.execute(
        "CREATE TABLE control (\n\tid INTEGER NOT NULL, \n\tstable_id VARCHAR(36) NOT NULL, \n\tcandidate_id VARCHAR(36), \n\tprevious_id VARCHAR(36), \n\tcanary_percent INTEGER NOT NULL, \n\tlab_mode VARCHAR(30) NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(stable_id) REFERENCES policies (id), \n\tFOREIGN KEY(candidate_id) REFERENCES policies (id), \n\tFOREIGN KEY(previous_id) REFERENCES policies (id)\n)"
    )
    op.execute(
        "CREATE TABLE destinations (\n\tid VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(36) NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\turl TEXT NOT NULL, \n\tevent_types JSONB NOT NULL, \n\tenabled BOOLEAN NOT NULL, \n\tsecret_encrypted TEXT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(project_id) REFERENCES projects (id)\n)"
    )
    op.execute("CREATE INDEX ix_destinations_project_id ON destinations (project_id)")
    op.execute(
        "CREATE TABLE events (\n\tid VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(36) NOT NULL, \n\ttype VARCHAR(120) NOT NULL, \n\tpayload JSONB NOT NULL, \n\tidempotency_key VARCHAR(200) NOT NULL, \n\tpayload_hash VARCHAR(64) NOT NULL, \n\ttrace_context JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (project_id, idempotency_key), \n\tFOREIGN KEY(project_id) REFERENCES projects (id)\n)"
    )
    op.execute("CREATE INDEX ix_events_created_at ON events (created_at)")
    op.execute("CREATE INDEX ix_events_project_id ON events (project_id)")
    op.execute("CREATE INDEX ix_events_type ON events (type)")
    op.execute(
        "CREATE TABLE sessions (\n\tid VARCHAR(64) NOT NULL, \n\tuser_id VARCHAR(36) NOT NULL, \n\tcsrf VARCHAR(64) NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)"
    )
    op.execute(
        "CREATE TABLE deliveries (\n\tid VARCHAR(36) NOT NULL, \n\tevent_id VARCHAR(36) NOT NULL, \n\tdestination_id VARCHAR(36) NOT NULL, \n\tpolicy_id VARCHAR(36) NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tregion VARCHAR(20) NOT NULL, \n\tattempt_count INTEGER NOT NULL, \n\tlease_version INTEGER NOT NULL, \n\tlease_owner VARCHAR(100), \n\tlease_until TIMESTAMP WITH TIME ZONE, \n\tnext_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tdelivered_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tUNIQUE (event_id, destination_id), \n\tFOREIGN KEY(event_id) REFERENCES events (id), \n\tFOREIGN KEY(destination_id) REFERENCES destinations (id), \n\tFOREIGN KEY(policy_id) REFERENCES policies (id)\n)"
    )
    op.execute("CREATE INDEX ix_deliveries_created_at ON deliveries (created_at)")
    op.execute("CREATE INDEX ix_deliveries_event_id ON deliveries (event_id)")
    op.execute("CREATE INDEX ix_deliveries_status ON deliveries (status)")
    op.execute("CREATE INDEX ix_delivery_claim ON deliveries (status, next_attempt_at)")
    op.execute(
        "CREATE TABLE attempts (\n\tid VARCHAR(36) NOT NULL, \n\tdelivery_id VARCHAR(36) NOT NULL, \n\tnumber INTEGER NOT NULL, \n\tworker_id VARCHAR(100) NOT NULL, \n\tregion VARCHAR(20) NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tended_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tduration_ms FLOAT NOT NULL, \n\thttp_status INTEGER, \n\tfailure_category VARCHAR(50), \n\terror VARCHAR(200), \n\ttrace_id VARCHAR(32) NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(delivery_id) REFERENCES deliveries (id)\n)"
    )
    op.execute("CREATE INDEX ix_attempts_delivery_id ON attempts (delivery_id)")


def downgrade():
    op.drop_table("attempts")
    op.drop_table("deliveries")
    op.drop_table("sessions")
    op.drop_table("events")
    op.drop_table("destinations")
    op.drop_table("control")
    op.drop_table("api_keys")
    op.drop_table("workers")
    op.drop_table("users")
    op.drop_table("projects")
    op.drop_table("pools")
    op.drop_table("policies")
    op.drop_table("incidents")
    op.drop_table("audit")
