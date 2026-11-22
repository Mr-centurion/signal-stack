from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from backend.config import settings
from backend.models import Base

# Configure SQLite engine with foreign key support
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db() -> None:
    """Create all database tables and safely add missing columns if upgrading."""
    Base.metadata.create_all(bind=engine)
    
    # Safe auto-migration for SQLite dev instances
    if settings.DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            # Check companies table columns
            try:
                res = conn.execute(text("PRAGMA table_info(companies)")).fetchall()
                cols = {row[1] for row in res}
                new_comp_cols = [
                    ("website_url", "VARCHAR(512)"),
                    ("industry", "VARCHAR(255)"),
                    ("description", "TEXT"),
                    ("intelligence_profile", "TEXT"),
                    ("settings_json", "TEXT")
                ]
                for col_name, col_type in new_comp_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE companies ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception:
                pass

            # Check sources table columns
            try:
                res = conn.execute(text("PRAGMA table_info(sources)")).fetchall()
                cols = {row[1] for row in res}
                new_cols = [
                    ("source_type", "VARCHAR(50) DEFAULT 'rss' NOT NULL"),
                    ("rejection_reason", "TEXT"),
                    ("specificity_score", "FLOAT DEFAULT 0.8 NOT NULL"),
                    ("credibility_score", "FLOAT DEFAULT 0.8 NOT NULL"),
                    ("recency_score", "FLOAT DEFAULT 0.8 NOT NULL"),
                    ("overall_score", "FLOAT DEFAULT 0.8 NOT NULL"),
                    ("http_status", "INTEGER"),
                    ("content_length", "INTEGER"),
                    ("etag", "VARCHAR(255)"),
                    ("last_modified_header", "VARCHAR(255)"),
                    ("duplicate_count", "INTEGER DEFAULT 0 NOT NULL")
                ]
                for col_name, col_type in new_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE sources ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception:
                pass

            # Check documents table columns
            try:
                res = conn.execute(text("PRAGMA table_info(documents)")).fetchall()
                cols = {row[1] for row in res}
                new_doc_cols = [
                    ("category", "VARCHAR(50) DEFAULT 'market' NOT NULL"),
                    ("document_type", "VARCHAR(50) DEFAULT 'web_page' NOT NULL"),
                    ("metadata_json", "TEXT"),
                    ("canonical_url", "VARCHAR(1024)"),
                    ("simhash", "VARCHAR(64)"),
                    ("last_seen", "DATETIME"),
                    ("is_snapshot", "BOOLEAN DEFAULT 0 NOT NULL"),
                    ("is_duplicate", "BOOLEAN DEFAULT 0 NOT NULL"),
                    ("duplicate_of_id", "INTEGER")
                ]
                for col_name, col_type in new_doc_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE documents ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception:
                pass

            # Check crawl_runs table columns
            try:
                res = conn.execute(text("PRAGMA table_info(crawl_runs)")).fetchall()
                cols = {row[1] for row in res}
                source_id_info = next((row for row in res if row[1] == "source_id"), None)
                # If source_id has NOT NULL constraint (row[3] == 1), migrate table to allow NULL for company-wide crawl runs
                if source_id_info and source_id_info[3] == 1:
                    conn.execute(text("""
                        CREATE TABLE crawl_runs_temp (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            company_id INTEGER NOT NULL,
                            source_id INTEGER,
                            status VARCHAR(20) NOT NULL,
                            started_at DATETIME NOT NULL,
                            completed_at DATETIME,
                            documents_found INTEGER NOT NULL,
                            error_message TEXT,
                            items_new INTEGER NOT NULL DEFAULT 0,
                            items_changed INTEGER NOT NULL DEFAULT 0,
                            FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE,
                            FOREIGN KEY(source_id) REFERENCES sources(id) ON DELETE CASCADE
                        )
                    """))
                    conn.execute(text("""
                        INSERT INTO crawl_runs_temp (id, company_id, source_id, status, started_at, completed_at, documents_found, error_message, items_new, items_changed)
                        SELECT id, company_id, source_id, status, started_at, completed_at, documents_found, error_message, items_new, items_changed FROM crawl_runs
                    """))
                    conn.execute(text("DROP TABLE crawl_runs"))
                    conn.execute(text("ALTER TABLE crawl_runs_temp RENAME TO crawl_runs"))
                    conn.commit()

                new_run_cols = [
                    ("items_new", "INTEGER DEFAULT 0 NOT NULL"),
                    ("items_changed", "INTEGER DEFAULT 0 NOT NULL")
                ]
                for col_name, col_type in new_run_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE crawl_runs ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception as e:
                print(f"[DB MIGRATION WARNING] crawl_runs migration: {e}")
                pass

            # Check signals table columns
            try:
                res = conn.execute(text("PRAGMA table_info(signals)")).fetchall()
                cols = {row[1] for row in res}
                new_sig_cols = [
                    ("status", "VARCHAR(30) DEFAULT 'candidate' NOT NULL"),
                    ("publisher_url", "VARCHAR(1024)"),
                    ("publisher_name", "VARCHAR(255)"),
                    ("source_id", "INTEGER"),
                    ("crawl_run_id", "INTEGER"),
                    ("linked_competitor", "VARCHAR(255)"),
                    ("event_type", "VARCHAR(100)"),
                    ("customer_quote", "TEXT"),
                    ("unmet_need", "TEXT"),
                    ("published_date", "DATETIME"),
                    ("when_published", "VARCHAR(50)"),
                    ("is_discrete_event", "BOOLEAN DEFAULT 1 NOT NULL"),
                    ("event_reason", "TEXT"),
                    ("what_happened", "TEXT"),
                    ("verification_status", "VARCHAR(50) DEFAULT 'single_source' NOT NULL"),
                    ("why_it_matters", "TEXT"),
                    ("referenced_profile_fact", "TEXT"),
                    ("business_area", "VARCHAR(100)"),
                    ("direction", "VARCHAR(20) DEFAULT 'neutral' NOT NULL"),
                    ("what_to_consider", "TEXT"),
                    ("priority_score", "FLOAT DEFAULT 0.5 NOT NULL"),
                    ("why_important", "TEXT"),
                    ("is_background", "BOOLEAN DEFAULT 0 NOT NULL"),
                    ("is_paywalled", "BOOLEAN DEFAULT 0 NOT NULL")
                ]
                for col_name, col_type in new_sig_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE signals ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception as e:
                print(f"[DB MIGRATION WARNING] signals migration: {e}")
                pass

            # Check briefs table columns
            try:
                res = conn.execute(text("PRAGMA table_info(briefs)")).fetchall()
                cols = {row[1] for row in res}
                new_brief_cols = [
                    ("customer_signals", "TEXT DEFAULT '' NOT NULL"),
                    ("competitor_intelligence", "TEXT DEFAULT '' NOT NULL"),
                    ("market_intelligence", "TEXT DEFAULT '' NOT NULL"),
                    ("internal_intelligence", "TEXT DEFAULT '' NOT NULL"),
                    ("opportunities", "TEXT DEFAULT '' NOT NULL"),
                    ("risks_threats", "TEXT DEFAULT '' NOT NULL"),
                    ("recommended_actions", "TEXT DEFAULT '' NOT NULL"),
                    ("what_we_should_watch", "TEXT DEFAULT '' NOT NULL"),
                    ("source_appendix", "TEXT DEFAULT '' NOT NULL"),
                    ("validator_report", "TEXT"),
                    ("raw_json", "TEXT"),
                    ("html_export", "TEXT"),
                    ("markdown_export", "TEXT")
                ]
                for col_name, col_type in new_brief_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE briefs ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception as e:
                print(f"[DB MIGRATION WARNING] briefs migration: {e}")
                pass

            # Check action_items table columns
            try:
                res = conn.execute(text("PRAGMA table_info(action_items)")).fetchall()
                cols = {row[1] for row in res}
                new_ai_cols = [
                    ("reason", "TEXT"),
                    ("owner_role", "VARCHAR(100)"),
                    ("due_date", "VARCHAR(50)")
                ]
                for col_name, col_type in new_ai_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE action_items ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception as e:
                print(f"[DB MIGRATION WARNING] action_items migration: {e}")
                pass

            # Check scheduler_logs table columns
            try:
                res = conn.execute(text("PRAGMA table_info(scheduler_logs)")).fetchall()
                cols = {row[1] for row in res}
                new_sched_cols = [
                    ("job", "VARCHAR(100) DEFAULT 'weekly_intelligence_brief' NOT NULL"),
                    ("company", "VARCHAR(255)"),
                    ("company_id", "INTEGER"),
                    ("scheduled_for", "DATETIME"),
                    ("started", "DATETIME"),
                    ("finished", "DATETIME"),
                    ("error", "TEXT"),
                    ("records_collected", "INTEGER DEFAULT 0 NOT NULL")
                ]
                for col_name, col_type in new_sched_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE scheduler_logs ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception as e:
                print(f"[DB MIGRATION WARNING] scheduler_logs migration: {e}")
                pass

            # Check source_health_reports table columns
            try:
                res = conn.execute(text("PRAGMA table_info(source_health_reports)")).fetchall()
                cols = {row[1] for row in res}
                if "blocked_sources_count" not in cols:
                    conn.execute(text("ALTER TABLE source_health_reports ADD COLUMN blocked_sources_count INTEGER DEFAULT 0 NOT NULL"))
                conn.commit()
            except Exception as e:
                print(f"[DB MIGRATION WARNING] source_health_reports migration: {e}")
                pass

            # Check profile_facts table columns
            try:
                res = conn.execute(text("PRAGMA table_info(profile_facts)")).fetchall()
                cols = {row[1] for row in res}
                new_fact_cols = [
                    ("is_current", "BOOLEAN DEFAULT 1 NOT NULL"),
                    ("is_anchored", "BOOLEAN DEFAULT 1 NOT NULL")
                ]
                for col_name, col_type in new_fact_cols:
                    if col_name not in cols:
                        conn.execute(text(f"ALTER TABLE profile_facts ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception as e:
                print(f"[DB MIGRATION WARNING] profile_facts migration: {e}")
                pass

def get_db() -> Generator[Session, None, None]:
    """Yield a database session and ensure clean close."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
