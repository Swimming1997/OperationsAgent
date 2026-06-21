from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 5


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS platform_account (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            external_account_id TEXT,
            account_role TEXT NOT NULL DEFAULT 'intelligence_collector',
            status TEXT NOT NULL DEFAULT 'active',
            auth_status TEXT NOT NULL DEFAULT 'not_logged_in',
            health_status TEXT NOT NULL DEFAULT 'unknown',
            profile_key TEXT NOT NULL,
            cdp_port INTEGER,
            platform_nickname TEXT,
            platform_home_url TEXT,
            last_verified_at TEXT,
            last_success_at TEXT,
            last_failure_at TEXT,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS ix_platform_account_platform
            ON platform_account(platform);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_platform_account_external
            ON platform_account(platform, external_account_id)
            WHERE external_account_id IS NOT NULL;

        CREATE TABLE IF NOT EXISTS local_setting (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS creator (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            platform_user_id TEXT NOT NULL,
            nickname TEXT,
            avatar_url TEXT,
            fans_count INTEGER,
            total_liked_collected INTEGER,
            works_count INTEGER,
            verify_type TEXT,
            signature TEXT,
            ip_location TEXT,
            raw_json TEXT NOT NULL DEFAULT '{}',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE(platform, platform_user_id)
        );

        CREATE TABLE IF NOT EXISTS content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            central_content_id TEXT UNIQUE,
            platform TEXT NOT NULL,
            platform_content_id TEXT NOT NULL,
            creator_id INTEGER REFERENCES creator(id) ON DELETE SET NULL,
            canonical_url TEXT,
            content_type TEXT NOT NULL DEFAULT 'unknown',
            title TEXT,
            cover_url TEXT,
            published_at TEXT,
            topics_json TEXT NOT NULL DEFAULT '[]',
            platform_tags_json TEXT NOT NULL DEFAULT '[]',
            video_duration REAL,
            is_ad INTEGER,
            ip_location TEXT,
            like_count INTEGER,
            comment_count INTEGER,
            collect_count INTEGER,
            share_count INTEGER,
            body_text TEXT,
            image_urls_json TEXT NOT NULL DEFAULT '[]',
            video_url TEXT,
            detail_fetched_at TEXT,
            acquisition_hit_count INTEGER NOT NULL DEFAULT 0,
            acquisition_checked_at TEXT,
            processing_status TEXT NOT NULL DEFAULT 'pending',
            raw_json TEXT NOT NULL DEFAULT '{}',
            platform_context_json TEXT NOT NULL DEFAULT '{}',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE(platform, platform_content_id)
        );

        CREATE INDEX IF NOT EXISTS ix_content_creator_id ON content(creator_id);
        CREATE INDEX IF NOT EXISTS ix_content_published_at ON content(published_at);
        CREATE INDEX IF NOT EXISTS ix_content_last_seen_at ON content(last_seen_at);

        CREATE TABLE IF NOT EXISTS content_source (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
            source_type TEXT NOT NULL,
            source_ref TEXT NOT NULL DEFAULT '',
            job_id TEXT,
            account_id TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE(content_id, source_type, source_ref)
        );

        CREATE INDEX IF NOT EXISTS ix_content_source_lookup
            ON content_source(source_type, source_ref, last_seen_at);

        CREATE TABLE IF NOT EXISTS comment_hit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
            platform_comment_id TEXT NOT NULL,
            parent_platform_comment_id TEXT,
            comment_text TEXT NOT NULL,
            comment_author TEXT,
            like_count INTEGER,
            matched_keyword TEXT,
            published_at TEXT,
            fetched_at TEXT NOT NULL,
            raw_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(content_id, platform_comment_id, matched_keyword)
        );

        CREATE TABLE IF NOT EXISTS comment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
            platform_comment_id TEXT NOT NULL,
            parent_platform_comment_id TEXT,
            comment_text TEXT NOT NULL,
            comment_author TEXT,
            author_platform_id TEXT,
            like_count INTEGER,
            published_at TEXT,
            fetched_at TEXT NOT NULL,
            raw_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(content_id, platform_comment_id)
        );

        CREATE INDEX IF NOT EXISTS ix_comment_content ON comment(content_id);
        CREATE INDEX IF NOT EXISTS ix_comment_fetched_at ON comment(fetched_at);

        CREATE TABLE IF NOT EXISTS search_suggestion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            core_keyword TEXT NOT NULL,
            suggested_keyword TEXT NOT NULL,
            rank INTEGER,
            fetched_at TEXT NOT NULL,
            raw_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(platform, core_keyword, suggested_keyword)
        );

        CREATE INDEX IF NOT EXISTS ix_search_suggestion_lookup
            ON search_suggestion(platform, core_keyword, rank);

        CREATE TABLE IF NOT EXISTS collect_task (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            target TEXT NOT NULL DEFAULT '',
            params_json TEXT NOT NULL DEFAULT '{}',
            schedule_seconds INTEGER,
            last_run_at TEXT,
            last_viewed_at TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS collect_run (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER REFERENCES collect_task(id) ON DELETE SET NULL,
            central_job_id TEXT UNIQUE,
            job_type TEXT,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 1,
            item_count INTEGER NOT NULL DEFAULT 0,
            error_summary_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS ingestion_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation TEXT NOT NULL,
            dedupe_key TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(operation, dedupe_key)
        );

        CREATE TABLE IF NOT EXISTS material_export (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id INTEGER NOT NULL UNIQUE REFERENCES content(id) ON DELETE CASCADE,
            central_content_id TEXT,
            central_reference_item_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            library_type TEXT NOT NULL DEFAULT 'uncategorized',
            rating TEXT,
            material_tags_json TEXT NOT NULL DEFAULT '[]',
            note TEXT,
            selected_reason TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            synced_at TEXT
        );
        """
    )
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(content)").fetchall()
    }
    if "processing_status" not in columns:
        connection.execute(
            "ALTER TABLE content ADD COLUMN processing_status TEXT NOT NULL DEFAULT 'pending'"
        )
    if "comments_fetched_at" not in columns:
        connection.execute("ALTER TABLE content ADD COLUMN comments_fetched_at TEXT")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_content_processing_status ON content(processing_status)"
    )
    connection.execute(
        """
        INSERT INTO schema_meta(key, value) VALUES('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(SCHEMA_VERSION),),
    )
    connection.commit()
