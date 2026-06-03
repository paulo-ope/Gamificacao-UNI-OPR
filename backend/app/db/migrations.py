from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_runtime_schema(engine: Engine) -> None:
    """Small compatibility migration for local Docker/SQLite databases.

    The project intentionally stays lightweight for this phase, without Alembic.
    This keeps existing installations working when columns are added to tables
    that were already created by earlier versions.
    """

    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "service_orders" not in table_names:
        return

    statements: list[str] = []
    is_postgres = engine.dialect.name == "postgresql"

    if "users" not in table_names:
        statements.append(
            """
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(160) NOT NULL,
                email VARCHAR(180) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(30) DEFAULT 'viewer' NOT NULL,
                active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
            )
            """
            if is_postgres
            else """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name VARCHAR(160) NOT NULL,
                email VARCHAR(180) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(30) DEFAULT 'viewer' NOT NULL,
                active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        if is_postgres:
            statements.append("CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)")
            statements.append("CREATE INDEX IF NOT EXISTS ix_users_role ON users (role)")

    if "audit_logs" not in table_names:
        statements.append(
            """
            CREATE TABLE audit_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                action VARCHAR(120) NOT NULL,
                entity VARCHAR(120) NOT NULL,
                entity_id VARCHAR(80),
                before_data JSONB,
                after_data JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
            )
            """
            if is_postgres
            else """
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                action VARCHAR(120) NOT NULL,
                entity VARCHAR(120) NOT NULL,
                entity_id VARCHAR(80),
                before_data JSON,
                after_data JSON,
                created_at DATETIME NOT NULL
            )
            """
        )
        if is_postgres:
            statements.append("CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id)")
            statements.append("CREATE INDEX IF NOT EXISTS ix_audit_logs_entity ON audit_logs (entity)")
            statements.append("CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action)")

    service_order_columns = {column["name"] for column in inspector.get_columns("service_orders")}
    if "diagnosis" not in service_order_columns:
        statements.append("ALTER TABLE service_orders ADD COLUMN diagnosis VARCHAR(180) DEFAULT 'Nao informado' NOT NULL")
    if "customer_login" not in service_order_columns:
        statements.append("ALTER TABLE service_orders ADD COLUMN customer_login VARCHAR(120)")
        if engine.dialect.name == "postgresql":
            statements.append("CREATE INDEX IF NOT EXISTS ix_service_orders_customer_login ON service_orders (customer_login)")

    if "scoring_groups" not in table_names:
        collaborator_columns = {column["name"] for column in inspector.get_columns("collaborators")} if "collaborators" in table_names else set()
        if "collaborators" in table_names and "is_registered" not in collaborator_columns:
            statements.append("ALTER TABLE collaborators ADD COLUMN is_registered BOOLEAN DEFAULT TRUE NOT NULL")
        if not statements:
            return
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
        return

    if "collaborators" in table_names:
        collaborator_columns = {column["name"] for column in inspector.get_columns("collaborators")}
        if "is_registered" not in collaborator_columns:
            statements.append("ALTER TABLE collaborators ADD COLUMN is_registered BOOLEAN DEFAULT TRUE NOT NULL")

    scoring_group_columns = {column["name"] for column in inspector.get_columns("scoring_groups")}
    if "created_at" not in scoring_group_columns:
        if engine.dialect.name == "postgresql":
            statements.append("ALTER TABLE scoring_groups ADD COLUMN created_at TIMESTAMP WITH TIME ZONE")
        else:
            statements.append("ALTER TABLE scoring_groups ADD COLUMN created_at DATETIME")

    if "updated_at" not in scoring_group_columns:
        if engine.dialect.name == "postgresql":
            statements.append("ALTER TABLE scoring_groups ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE")
        else:
            statements.append("ALTER TABLE scoring_groups ADD COLUMN updated_at DATETIME")

    if "point_value_override" not in scoring_group_columns:
        statements.append("ALTER TABLE scoring_groups ADD COLUMN point_value_override FLOAT")

    if "scoring_subject_rules" in table_names:
        subject_rule_columns = {column["name"] for column in inspector.get_columns("scoring_subject_rules")}
        if "point_value_override" not in subject_rule_columns:
            statements.append("ALTER TABLE scoring_subject_rules ADD COLUMN point_value_override FLOAT")
        if "subject_category" not in subject_rule_columns:
            statements.append("ALTER TABLE scoring_subject_rules ADD COLUMN subject_category VARCHAR(80)")
            if engine.dialect.name == "postgresql":
                statements.append("CREATE INDEX IF NOT EXISTS ix_scoring_subject_rules_subject_category ON scoring_subject_rules (subject_category)")

    if "diagnosis_penalty_rules" in table_names:
        diagnosis_rule_columns = {column["name"] for column in inspector.get_columns("diagnosis_penalty_rules")}
        if "force_points_value" not in diagnosis_rule_columns:
            statements.append("ALTER TABLE diagnosis_penalty_rules ADD COLUMN force_points_value FLOAT")

    if "recurrence_classification_rules" in table_names:
        recurrence_rule_columns = {column["name"] for column in inspector.get_columns("recurrence_classification_rules")}
        recurrence_columns = {
            "original_os_type_pattern": "VARCHAR(160)",
            "original_os_subject_pattern": "VARCHAR(220)",
            "return_os_type_pattern": "VARCHAR(160)",
            "return_os_subject_pattern": "VARCHAR(220)",
            "return_diagnosis_pattern": "VARCHAR(220)",
            "ignore_diagnosis_pattern": "VARCHAR(220)",
        }
        for column_name, column_type in recurrence_columns.items():
            if column_name not in recurrence_rule_columns:
                statements.append(f"ALTER TABLE recurrence_classification_rules ADD COLUMN {column_name} {column_type}")

    if "calculation_runs" in table_names:
        calculation_run_columns = {column["name"] for column in inspector.get_columns("calculation_runs")}
        if "source_import_id" not in calculation_run_columns:
            statements.append("ALTER TABLE calculation_runs ADD COLUMN source_import_id INTEGER")
        if "source_filename" not in calculation_run_columns:
            statements.append("ALTER TABLE calculation_runs ADD COLUMN source_filename VARCHAR(255)")
        if "rules_version_id" not in calculation_run_columns:
            statements.append("ALTER TABLE calculation_runs ADD COLUMN rules_version_id INTEGER")
        if "result_summary" not in calculation_run_columns:
            if engine.dialect.name == "postgresql":
                statements.append("ALTER TABLE calculation_runs ADD COLUMN result_summary JSONB")
            else:
                statements.append("ALTER TABLE calculation_runs ADD COLUMN result_summary JSON")

    if "leadership_role_profiles" not in table_names:
        statements.append(
            """
            CREATE TABLE leadership_role_profiles (
                id SERIAL PRIMARY KEY,
                name VARCHAR(160) UNIQUE NOT NULL,
                scope_type VARCHAR(40) NOT NULL,
                default_multiplier FLOAT DEFAULT 1 NOT NULL,
                active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
            )
            """
            if is_postgres
            else """
            CREATE TABLE leadership_role_profiles (
                id INTEGER PRIMARY KEY,
                name VARCHAR(160) UNIQUE NOT NULL,
                scope_type VARCHAR(40) NOT NULL,
                default_multiplier FLOAT DEFAULT 1 NOT NULL,
                active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        if is_postgres:
            statements.append("CREATE INDEX IF NOT EXISTS ix_leadership_role_profiles_scope_type ON leadership_role_profiles (scope_type)")

    if "leadership_profiles" not in table_names:
        statements.append(
            """
            CREATE TABLE leadership_profiles (
                id SERIAL PRIMARY KEY,
                name VARCHAR(160) NOT NULL,
                role_type VARCHAR(40) NOT NULL,
                multiplier FLOAT DEFAULT 1 NOT NULL,
                role_profile_id INTEGER REFERENCES leadership_role_profiles(id),
                use_custom_multiplier BOOLEAN DEFAULT FALSE NOT NULL,
                custom_multiplier FLOAT,
                active BOOLEAN DEFAULT TRUE NOT NULL,
                collaborator_id INTEGER REFERENCES collaborators(id),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
            )
            """
            if is_postgres
            else """
            CREATE TABLE leadership_profiles (
                id INTEGER PRIMARY KEY,
                name VARCHAR(160) NOT NULL,
                role_type VARCHAR(40) NOT NULL,
                multiplier FLOAT DEFAULT 1 NOT NULL,
                role_profile_id INTEGER,
                use_custom_multiplier BOOLEAN DEFAULT FALSE NOT NULL,
                custom_multiplier FLOAT,
                active BOOLEAN DEFAULT TRUE NOT NULL,
                collaborator_id INTEGER,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        if is_postgres:
            statements.append("CREATE INDEX IF NOT EXISTS ix_leadership_profiles_role_type ON leadership_profiles (role_type)")
            statements.append("CREATE INDEX IF NOT EXISTS ix_leadership_profiles_collaborator_id ON leadership_profiles (collaborator_id)")
            statements.append("CREATE INDEX IF NOT EXISTS ix_leadership_profiles_role_profile_id ON leadership_profiles (role_profile_id)")
    else:
        leadership_profile_columns = {column["name"] for column in inspector.get_columns("leadership_profiles")}
        if "multiplier" not in leadership_profile_columns:
            statements.append("ALTER TABLE leadership_profiles ADD COLUMN multiplier FLOAT DEFAULT 1 NOT NULL")
            statements.append(
                """
                UPDATE leadership_profiles
                SET multiplier = CASE role_type
                    WHEN 'supervisor' THEN 1.5
                    WHEN 'regional_manager' THEN 2
                    WHEN 'portfolio_manager' THEN 3
                    ELSE 1
                END
                """
            )
        if "role_profile_id" not in leadership_profile_columns:
            statements.append("ALTER TABLE leadership_profiles ADD COLUMN role_profile_id INTEGER")
        if "use_custom_multiplier" not in leadership_profile_columns:
            statements.append("ALTER TABLE leadership_profiles ADD COLUMN use_custom_multiplier BOOLEAN DEFAULT FALSE NOT NULL")
        if "custom_multiplier" not in leadership_profile_columns:
            statements.append("ALTER TABLE leadership_profiles ADD COLUMN custom_multiplier FLOAT")

    if "leadership_profile_regionals" not in table_names:
        statements.append(
            """
            CREATE TABLE leadership_profile_regionals (
                id SERIAL PRIMARY KEY,
                leadership_profile_id INTEGER NOT NULL REFERENCES leadership_profiles(id),
                regional_name VARCHAR(120) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
                CONSTRAINT uq_leadership_profile_regional UNIQUE (leadership_profile_id, regional_name)
            )
            """
            if is_postgres
            else """
            CREATE TABLE leadership_profile_regionals (
                id INTEGER PRIMARY KEY,
                leadership_profile_id INTEGER NOT NULL,
                regional_name VARCHAR(120) NOT NULL,
                created_at DATETIME NOT NULL,
                CONSTRAINT uq_leadership_profile_regional UNIQUE (leadership_profile_id, regional_name)
            )
            """
        )
        if is_postgres:
            statements.append("CREATE INDEX IF NOT EXISTS ix_leadership_profile_regionals_profile ON leadership_profile_regionals (leadership_profile_id)")
            statements.append("CREATE INDEX IF NOT EXISTS ix_leadership_profile_regionals_regional ON leadership_profile_regionals (regional_name)")

    if "leadership_bonus_results" not in table_names:
        statements.append(
            """
            CREATE TABLE leadership_bonus_results (
                id SERIAL PRIMARY KEY,
                calculation_run_id INTEGER NOT NULL REFERENCES calculation_runs(id),
                leadership_profile_id INTEGER NOT NULL REFERENCES leadership_profiles(id),
                role_type VARCHAR(40) NOT NULL,
                multiplier FLOAT DEFAULT 1 NOT NULL,
                average_final_points FLOAT DEFAULT 0 NOT NULL,
                scoped_collaborators INTEGER DEFAULT 0 NOT NULL,
                point_value FLOAT DEFAULT 0 NOT NULL,
                base_amount FLOAT DEFAULT 0 NOT NULL,
                bonus_amount FLOAT DEFAULT 0 NOT NULL,
                regionals_snapshot JSONB DEFAULT '[]'::jsonb NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
                CONSTRAINT uq_leadership_bonus_run_profile UNIQUE (calculation_run_id, leadership_profile_id)
            )
            """
            if is_postgres
            else """
            CREATE TABLE leadership_bonus_results (
                id INTEGER PRIMARY KEY,
                calculation_run_id INTEGER NOT NULL,
                leadership_profile_id INTEGER NOT NULL,
                role_type VARCHAR(40) NOT NULL,
                multiplier FLOAT DEFAULT 1 NOT NULL,
                average_final_points FLOAT DEFAULT 0 NOT NULL,
                scoped_collaborators INTEGER DEFAULT 0 NOT NULL,
                point_value FLOAT DEFAULT 0 NOT NULL,
                base_amount FLOAT DEFAULT 0 NOT NULL,
                bonus_amount FLOAT DEFAULT 0 NOT NULL,
                regionals_snapshot JSON NOT NULL,
                created_at DATETIME NOT NULL,
                CONSTRAINT uq_leadership_bonus_run_profile UNIQUE (calculation_run_id, leadership_profile_id)
            )
            """
        )
        if is_postgres:
            statements.append("CREATE INDEX IF NOT EXISTS ix_leadership_bonus_results_run ON leadership_bonus_results (calculation_run_id)")
            statements.append("CREATE INDEX IF NOT EXISTS ix_leadership_bonus_results_profile ON leadership_bonus_results (leadership_profile_id)")
    else:
        leadership_result_columns = {column["name"] for column in inspector.get_columns("leadership_bonus_results")}
        if "multiplier" not in leadership_result_columns:
            statements.append("ALTER TABLE leadership_bonus_results ADD COLUMN multiplier FLOAT DEFAULT 1 NOT NULL")
        if "average_final_points" not in leadership_result_columns:
            statements.append("ALTER TABLE leadership_bonus_results ADD COLUMN average_final_points FLOAT DEFAULT 0 NOT NULL")
        if "scoped_collaborators" not in leadership_result_columns:
            statements.append("ALTER TABLE leadership_bonus_results ADD COLUMN scoped_collaborators INTEGER DEFAULT 0 NOT NULL")
        if "point_value" not in leadership_result_columns:
            statements.append("ALTER TABLE leadership_bonus_results ADD COLUMN point_value FLOAT DEFAULT 0 NOT NULL")
        if "percentage" in leadership_result_columns:
            if is_postgres:
                statements.append("ALTER TABLE leadership_bonus_results ALTER COLUMN percentage DROP NOT NULL")
                statements.append("ALTER TABLE leadership_bonus_results ALTER COLUMN percentage DROP DEFAULT")
            else:
                statements.append("UPDATE leadership_bonus_results SET percentage = COALESCE(percentage, 0)")

    if "recurrence_classification_rules" not in table_names:
        statements.append(
            """
            CREATE TABLE recurrence_classification_rules (
                id SERIAL PRIMARY KEY,
                name VARCHAR(160) UNIQUE NOT NULL,
                os_type_pattern VARCHAR(160),
                os_subject_pattern VARCHAR(220),
                diagnosis_pattern VARCHAR(220),
                original_os_type_pattern VARCHAR(160),
                original_os_subject_pattern VARCHAR(220),
                return_os_type_pattern VARCHAR(160),
                return_os_subject_pattern VARCHAR(220),
                return_diagnosis_pattern VARCHAR(220),
                ignore_diagnosis_pattern VARCHAR(220),
                classification VARCHAR(60) DEFAULT 'nao_identificado' NOT NULL,
                discount_points BOOLEAN DEFAULT FALSE NOT NULL,
                max_days INTEGER,
                require_same_subject BOOLEAN DEFAULT FALSE NOT NULL,
                require_same_diagnosis BOOLEAN DEFAULT FALSE NOT NULL,
                priority INTEGER DEFAULT 100 NOT NULL,
                description TEXT,
                active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE,
                updated_at TIMESTAMP WITH TIME ZONE
            )
            """
            if engine.dialect.name == "postgresql"
            else """
            CREATE TABLE recurrence_classification_rules (
                id INTEGER PRIMARY KEY,
                name VARCHAR(160) UNIQUE NOT NULL,
                os_type_pattern VARCHAR(160),
                os_subject_pattern VARCHAR(220),
                diagnosis_pattern VARCHAR(220),
                original_os_type_pattern VARCHAR(160),
                original_os_subject_pattern VARCHAR(220),
                return_os_type_pattern VARCHAR(160),
                return_os_subject_pattern VARCHAR(220),
                return_diagnosis_pattern VARCHAR(220),
                ignore_diagnosis_pattern VARCHAR(220),
                classification VARCHAR(60) DEFAULT 'nao_identificado' NOT NULL,
                discount_points BOOLEAN DEFAULT FALSE NOT NULL,
                max_days INTEGER,
                require_same_subject BOOLEAN DEFAULT FALSE NOT NULL,
                require_same_diagnosis BOOLEAN DEFAULT FALSE NOT NULL,
                priority INTEGER DEFAULT 100 NOT NULL,
                description TEXT,
                active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )

    if not statements:
        statements = []

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

        if "leadership_role_profiles" in inspect(engine).get_table_names() or any("CREATE TABLE leadership_role_profiles" in stmt for stmt in statements):
            defaults = [
                ("Supervisor", "supervisor", 1.5),
                ("Gerente da unidade", "regional_manager", 2.0),
                ("Gerente de pasta", "portfolio_manager", 3.0),
            ]
            for name, scope_type, default_multiplier in defaults:
                exists = connection.execute(
                    text("SELECT id FROM leadership_role_profiles WHERE name = :name"),
                    {"name": name},
                ).first()
                if not exists:
                    connection.execute(
                        text(
                            """
                            INSERT INTO leadership_role_profiles (name, scope_type, default_multiplier, active, created_at, updated_at)
                            VALUES (:name, :scope_type, :default_multiplier, :active, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            """
                        ),
                        {
                            "name": name,
                            "scope_type": scope_type,
                            "default_multiplier": default_multiplier,
                            "active": True,
                        },
                    )

            if "leadership_profiles" in inspect(engine).get_table_names():
                role_profiles = {
                    row.scope_type: row.id
                    for row in connection.execute(text("SELECT id, scope_type FROM leadership_role_profiles")).fetchall()
                }
                rows = connection.execute(
                    text("SELECT id, role_type, multiplier, role_profile_id FROM leadership_profiles")
                ).fetchall()
                default_multipliers = {
                    "supervisor": 1.5,
                    "regional_manager": 2.0,
                    "portfolio_manager": 3.0,
                }
                for row in rows:
                    updates: dict[str, object] = {}
                    role_type = row.role_type or "supervisor"
                    default_multiplier = default_multipliers.get(role_type, 1.0)
                    if row.role_profile_id is None and role_type in role_profiles:
                        updates["role_profile_id"] = role_profiles[role_type]
                    if abs(float(row.multiplier or default_multiplier) - float(default_multiplier)) > 0.0001:
                        updates["use_custom_multiplier"] = True
                        updates["custom_multiplier"] = float(row.multiplier)
                    elif row.multiplier is None:
                        updates["multiplier"] = float(default_multiplier)
                    if updates:
                        assignments = ", ".join(f"{key} = :{key}" for key in updates)
                        updates["id"] = row.id
                        connection.execute(
                            text(f"UPDATE leadership_profiles SET {assignments} WHERE id = :id"),
                            updates,
                        )
