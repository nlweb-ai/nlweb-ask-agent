import pymssql
from datetime import datetime
import os
import threading
from collections import defaultdict
import re
import config  # This will automatically load .env file
import logging

import log


log.configure(os.environ)
logger = logging.getLogger("db")


# Per-site semaphores to prevent concurrent operations on the same site
_site_locks = defaultdict(lambda: threading.Semaphore(1))
_lock_mutex = threading.Lock()  # Mutex to protect the _site_locks dictionary


def normalize_site_url(site_url):
    """
    Normalize site URL by removing protocol and www prefix.
    Examples:
        https://www.imdb.com -> imdb.com
        http://example.com -> example.com
        www.site.org -> site.org
        site.com -> site.com
    """
    if not site_url:
        return site_url

    # Remove protocol (http:// or https://)
    url = re.sub(r"^https?://", "", site_url)

    # Remove www. prefix
    url = re.sub(r"^www\.", "", url)

    # Remove trailing slash
    url = url.rstrip("/")

    return url


def get_site_lock(site_url):
    """Get or create a semaphore for a specific site"""
    with _lock_mutex:
        return _site_locks[site_url]


def get_connection():
    """Get connection to Azure SQL Database using pymssql (simpler than ODBC)"""
    server = os.getenv("DB_SERVER") or os.getenv("AZURE_SQL_SERVER")
    database = os.getenv("DB_DATABASE") or os.getenv("AZURE_SQL_DATABASE")
    username = os.getenv("DB_USERNAME") or os.getenv("AZURE_SQL_USERNAME")
    password = os.getenv("DB_PASSWORD") or os.getenv("AZURE_SQL_PASSWORD")

    # Remove port if present in server string
    if ":" in server:
        server = server.split(":")[0]

    # Simple connection using pymssql - no ODBC complexity
    # TDS version and encryption configured in /etc/freetds/freetds.conf
    conn = pymssql.connect(
        server=server, user=username, password=password, database=database
    )
    return conn


def create_tables(conn: pymssql.Connection):
    """Create tables if they don't exist"""
    cursor = conn.cursor()

    cursor.execute(
        """
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'sites')
    CREATE TABLE sites (
        site_url VARCHAR(500),
        user_id VARCHAR(255),
        process_interval_hours DECIMAL(10,2) DEFAULT 720,
        last_processed DATETIME,
        is_active BIT DEFAULT 1,
        created_at DATETIME DEFAULT GETUTCDATE(),
        schema_map_url NVARCHAR(2000) NULL,
        refresh_mode VARCHAR(10) DEFAULT 'diff',
        PRIMARY KEY (site_url, user_id)
    )
    """
    )

    cursor.execute(
        """
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'files')
    CREATE TABLE files (
        site_url VARCHAR(500),
        user_id VARCHAR(255),
        file_url VARCHAR(500),
        schema_map VARCHAR(500),
        last_read_time DATETIME,
        number_of_items INT,
        is_manual BIT DEFAULT 0,
        is_active BIT DEFAULT 1,
        file_hash VARCHAR(64),
        content_type VARCHAR(100),
        PRIMARY KEY (file_url, user_id)
    )
    """
    )

    cursor.execute(
        """
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ids')
    CREATE TABLE ids (
        file_url VARCHAR(500),
        user_id VARCHAR(255),
        id VARCHAR(500)
    )
    """
    )

    cursor.execute(
        """
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'processing_errors')
    CREATE TABLE processing_errors (
        id INT IDENTITY(1,1) PRIMARY KEY,
        file_url VARCHAR(500) NOT NULL,
        user_id VARCHAR(255) NOT NULL,
        error_type VARCHAR(100) NOT NULL,
        error_message VARCHAR(MAX),
        error_details VARCHAR(MAX),
        occurred_at DATETIME DEFAULT GETUTCDATE()
    )
    """
    )

    # Create indexes for performance
    # These are critical for query performance - the ids table can have millions of rows
    logger.info("Ensuring performance indexes exist on ids table...")

    cursor.execute(
        """
    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_ids_user_id' AND object_id = OBJECT_ID('ids'))
    BEGIN
        CREATE INDEX idx_ids_user_id ON ids(user_id, id)
        SELECT 'CREATED' as status
    END
    ELSE
        SELECT 'EXISTS' as status
    """
    )
    result = cursor.fetchone()
    if result and result[0] == 'CREATED':
        logger.info("✓ Created index idx_ids_user_id on ids(user_id, id)")
    else:
        logger.info("✓ Index idx_ids_user_id already exists")

    cursor.execute(
        """
    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_ids_file_url' AND object_id = OBJECT_ID('ids'))
    BEGIN
        CREATE INDEX idx_ids_file_url ON ids(file_url, user_id)
        SELECT 'CREATED' as status
    END
    ELSE
        SELECT 'EXISTS' as status
    """
    )
    result = cursor.fetchone()
    if result and result[0] == 'CREATED':
        logger.info("✓ Created index idx_ids_file_url on ids(file_url, user_id)")
    else:
        logger.info("✓ Index idx_ids_file_url already exists")

    # Index for schema_map_url lookups on sites table
    cursor.execute(
        """
    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_sites_schema_map' AND object_id = OBJECT_ID('sites'))
    BEGIN
        CREATE INDEX idx_sites_schema_map ON sites(schema_map_url)
        SELECT 'CREATED' as status
    END
    ELSE
        SELECT 'EXISTS' as status
    """
    )
    result = cursor.fetchone()
    if result and result[0] == 'CREATED':
        logger.info("✓ Created index idx_sites_schema_map on sites(schema_map_url)")
    else:
        logger.info("✓ Index idx_sites_schema_map already exists")

    conn.commit()


def ensure_system_user(conn: pymssql.Connection):
    """Ensure the 'system' user exists for default operations"""
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = 'system'")
    if not cursor.fetchone():
        cursor.execute(
            """
            INSERT INTO users (user_id, email, name, provider, created_at)
            VALUES ('system', NULL, 'System', 'system', GETUTCDATE())
        """
        )
        conn.commit()
        logger.info("Created 'system' user")
    else:
        logger.info("'system' user already exists")


def log_processing_error(
    conn: pymssql.Connection,
    file_url,
    user_id,
    error_type,
    error_message,
    error_details=None,
):
    """Log a processing error for a file"""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO processing_errors (file_url, user_id, error_type, error_message, error_details)
        VALUES (%s, %s, %s, %s, %s)
    """,
        (file_url, user_id, error_type, error_message, error_details),
    )
    conn.commit()


def get_file_errors(conn: pymssql.Connection, file_url, user_id=None, limit=50):
    """Get recent errors for a file"""
    cursor = conn.cursor(as_dict=True)
    cursor.execute(
        """
        SELECT TOP (%s) error_type, error_message, error_details, occurred_at
        FROM processing_errors
        WHERE file_url = %s
        ORDER BY occurred_at DESC
    """,
        (limit, file_url),
    )
    return cursor.fetchall()


def clear_file_errors(conn: pymssql.Connection, file_url: str):
    """Clear all errors for a file (called when file successfully processes)"""
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM processing_errors
        WHERE file_url = %s
    """,
        (file_url,),
    )
    conn.commit()


def get_site_files(conn: pymssql.Connection, site_url: str, user_id: str):
    """Get all active files currently associated with a site"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT file_url FROM files WHERE site_url = %s AND user_id = %s AND is_active = 1",
        (site_url, user_id),
    )
    return [row[0] for row in cursor.fetchall()]


def update_site_files(
    conn: pymssql.Connection,
    site_url: str,
    user_id: str,
    current_files: list[tuple[str, str, str]],
):
    """Update files for a site, returns (added_files, removed_files)

    Args:
        site_url: Site URL
        user_id: User ID
        current_files: List of triples (site_url, schema_map_url, file_url)
    """
    # Acquire semaphore for this site to prevent concurrent modifications
    site_lock = get_site_lock(site_url)

    with site_lock:
        cursor = conn.cursor()

        existing_files = get_site_files(conn, site_url, user_id)

        # Convert current_files to dict for easy lookup
        # Triples format: (site_url, schema_map_url, file_url)
        current_files_dict = {
            file_url: schema_map for _, schema_map, file_url in current_files
        }

        current_set = set(current_files_dict.keys())
        existing_set = set(existing_files)
        added = current_set - existing_set
        removed = existing_set - current_set

        # For "added" files, use MERGE pattern to handle existing records
        for file_url in added:
            schema_map = current_files_dict[file_url]
            # Use MERGE statement for atomic upsert
            cursor.execute(
                """
                MERGE files AS target
                USING (SELECT %s AS site_url, %s AS user_id, %s AS file_url, %s AS schema_map) AS source
                ON target.file_url = source.file_url AND target.user_id = source.user_id
                WHEN MATCHED THEN
                    UPDATE SET is_active = 1, site_url = source.site_url, schema_map = source.schema_map
                WHEN NOT MATCHED THEN
                    INSERT (site_url, user_id, file_url, schema_map, is_active) VALUES (source.site_url, source.user_id, source.file_url, source.schema_map, 1);
            """,
                (site_url, user_id, file_url, schema_map),
            )

        if removed:
            # Mark removed files as inactive instead of deleting
            cursor.execute(
                "UPDATE files SET is_active = 0 WHERE site_url = %s AND user_id = %s AND file_url IN ({})".format(
                    ",".join(["%s"] * len(removed))
                ),
                tuple([site_url, user_id] + list(removed)),
            )

        conn.commit()
        return (list(added), list(removed))


def get_file_ids(conn: pymssql.Connection, file_url: str, user_id: str) -> set[str]:
    """Get all IDs associated with a file"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM ids WHERE file_url = %s AND user_id = %s", (file_url, user_id)
    )
    return {row[0] for row in cursor.fetchall()}


def update_file_ids(
    conn: pymssql.Connection, file_url: str, user_id: str, current_ids: set[str]
):
    """Update IDs for a file, returns (added_ids, removed_ids)"""
    cursor = conn.cursor()

    existing_ids = get_file_ids(conn, file_url, user_id)

    added = current_ids - existing_ids
    removed = existing_ids - current_ids

    if added:
        # Use bulk insert via temp table for performance with large batches
        # This is much faster than executemany for 100+ rows
        added_list = list(added)

        if len(added_list) < 100:
            # For small batches, use executemany (simpler)
            cursor.executemany(
                "INSERT INTO ids (file_url, user_id, id) VALUES (%s, %s, %s)",
                [(file_url, user_id, id) for id in added_list],
            )
        else:
            # For large batches, use temp table bulk insert
            cursor.execute("""
                CREATE TABLE #temp_insert_ids (
                    file_url VARCHAR(500),
                    user_id VARCHAR(255),
                    id VARCHAR(500)
                )
            """)

            # Insert in batches to avoid parameter limit
            batch_size = 500
            for i in range(0, len(added_list), batch_size):
                batch = added_list[i : i + batch_size]
                placeholders = ','.join(['(%s, %s, %s)'] * len(batch))
                values = []
                for id in batch:
                    values.extend([file_url, user_id, id])
                cursor.execute(
                    f"INSERT INTO #temp_insert_ids (file_url, user_id, id) VALUES {placeholders}",
                    tuple(values)
                )

            # Bulk insert from temp table
            cursor.execute("""
                INSERT INTO ids (file_url, user_id, id)
                SELECT file_url, user_id, id FROM #temp_insert_ids
            """)

            cursor.execute("DROP TABLE #temp_insert_ids")

    if removed:
        # If removing all IDs (current_ids is empty), use simple DELETE
        # to avoid SQL Server's 2100 parameter limit
        if not current_ids:
            cursor.execute(
                "DELETE FROM ids WHERE file_url = %s AND user_id = %s",
                (file_url, user_id),
            )
        else:
            # Batch deletions to avoid parameter limit (max 2100 params in SQL Server)
            # Use batches of 500 to be safe
            removed_list = list(removed)
            batch_size = 500
            for i in range(0, len(removed_list), batch_size):
                batch = removed_list[i : i + batch_size]
                cursor.execute(
                    "DELETE FROM ids WHERE file_url = %s AND user_id = %s AND id IN ({})".format(
                        ",".join(["%s"] * len(batch))
                    ),
                    tuple([file_url, user_id] + batch),
                )

    cursor.execute(
        "UPDATE files SET last_read_time = GETUTCDATE(), number_of_items = %s WHERE file_url = %s AND user_id = %s",
        (len(current_ids), file_url, user_id),
    )

    conn.commit()
    return (list(added), list(removed))


def count_id_references(conn: pymssql.Connection, id: str, user_id: str):
    """Count how many files reference an ID"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM ids WHERE id = %s AND user_id = %s", (id, user_id)
    )
    return cursor.fetchone()[0]


def batch_count_id_references(conn: pymssql.Connection, ids: list[str], user_id: str) -> dict[str, int]:
    """
    Count references for multiple IDs in a single query using a temp table.
    Returns a dict mapping id -> count.
    """
    if not ids:
        return {}

    import time
    start_time = time.time()

    cursor = conn.cursor()

    # Use temp table approach instead of large IN clause
    # This is much faster for large numbers of IDs (100+)
    logger.debug(f"batch_count_id_references: Querying {len(ids)} IDs using temp table...")

    # Create temp table
    temp_table_start = time.time()
    cursor.execute("""
        CREATE TABLE #temp_ids (id VARCHAR(500))
    """)

    # Batch insert into temp table (avoid 2100 parameter limit)
    batch_size = 1000
    for i in range(0, len(ids), batch_size):
        batch = ids[i:i + batch_size]
        placeholders = ','.join(['(%s)'] * len(batch))
        cursor.execute(f"INSERT INTO #temp_ids (id) VALUES {placeholders}", tuple(batch))

    temp_table_time = time.time() - temp_table_start
    logger.debug(f"batch_count_id_references: Temp table created in {temp_table_time:.2f}s")

    # Query using JOIN instead of IN clause
    query_start = time.time()
    cursor.execute("""
        SELECT i.id, COUNT(*) as ref_count
        FROM ids i
        INNER JOIN #temp_ids t ON i.id = t.id
        WHERE i.user_id = %s
        GROUP BY i.id
    """, (user_id,))

    query_time = time.time() - query_start
    logger.debug(f"batch_count_id_references: Query executed in {query_time:.2f}s")

    fetch_start = time.time()
    rows = cursor.fetchall()
    fetch_time = time.time() - fetch_start
    logger.debug(f"batch_count_id_references: Fetched {len(rows)} results in {fetch_time:.2f}s")

    # Clean up temp table
    cursor.execute("DROP TABLE #temp_ids")

    # Build result dict
    result = {id: 0 for id in ids}  # Default to 0 for IDs not found
    for row in rows:
        result[row[0]] = row[1]

    total_time = time.time() - start_time
    logger.info(f"batch_count_id_references: Total time {total_time:.2f}s for {len(ids)} IDs")

    return result


def clear_all_data(conn: pymssql.Connection):
    """Clear all data from database tables (for testing)"""
    cursor = conn.cursor()

    logger.info("Clearing database tables...")

    # Delete in correct order due to foreign keys
    cursor.execute("DELETE FROM ids")
    logger.info("Deleted %d rows from ids table", cursor.rowcount)

    cursor.execute("DELETE FROM files")
    logger.info("Deleted %d rows from files table", cursor.rowcount)

    cursor.execute("DELETE FROM sites")
    logger.info("Deleted %d rows from sites table", cursor.rowcount)

    conn.commit()
    logger.info("Database cleared successfully")


def get_all_sites(conn: pymssql.Connection, user_id: str = None):
    """Get all sites with their status"""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT site_url, process_interval_hours, last_processed, is_active, created_at
        FROM sites
        ORDER BY site_url
    """
    )
    return [
        {
            "site_url": row[0],
            "process_interval_hours": row[1],
            "last_processed": row[2].isoformat() if row[2] else None,
            "is_active": bool(row[3]),
            "created_at": row[4].isoformat() if row[4] else None,
        }
        for row in cursor.fetchall()
    ]


def add_site(
    conn: pymssql.Connection, site_url: str, user_id: str, interval_hours: int = 720, schema_map_url: str = None, refresh_mode: str = "diff"
):
    """Add a new site to monitor"""
    # Normalize site URL
    site_url = normalize_site_url(site_url)

    cursor = conn.cursor()

    # Check if site already exists for this user
    cursor.execute(
        "SELECT site_url FROM sites WHERE site_url = %s AND user_id = %s",
        (site_url, user_id),
    )
    if cursor.fetchone():
        # Update existing site
        if schema_map_url:
            cursor.execute(
                """
                UPDATE sites
                SET process_interval_hours = %s, is_active = 1, schema_map_url = %s, refresh_mode = %s
                WHERE site_url = %s AND user_id = %s
            """,
                (interval_hours, schema_map_url, refresh_mode, site_url, user_id),
            )
        else:
            cursor.execute(
                """
                UPDATE sites
                SET process_interval_hours = %s, is_active = 1, refresh_mode = %s
                WHERE site_url = %s AND user_id = %s
            """,
                (interval_hours, refresh_mode, site_url, user_id),
            )
        logger.info("Site %s already exists - updated settings", site_url)
    else:
        # Insert new site
        if schema_map_url:
            cursor.execute(
                """
                INSERT INTO sites (site_url, user_id, process_interval_hours, schema_map_url, refresh_mode)
                VALUES (%s, %s, %s, %s, %s)
            """,
                (site_url, user_id, interval_hours, schema_map_url, refresh_mode),
            )
        else:
            cursor.execute(
                """
                INSERT INTO sites (site_url, user_id, process_interval_hours, refresh_mode)
                VALUES (%s, %s, %s, %s)
            """,
                (site_url, user_id, interval_hours, refresh_mode),
            )
        logger.info("Site %s added successfully", site_url)

    conn.commit()


def remove_site(conn: pymssql.Connection, site_url: str, user_id: str):
    """Remove a site (hard delete from database)"""
    cursor = conn.cursor()

    # Delete in correct order due to foreign keys
    # First delete IDs associated with files from this site
    cursor.execute(
        """
        DELETE FROM ids
        WHERE user_id = %s AND file_url IN (SELECT file_url FROM files WHERE site_url = %s AND user_id = %s)
    """,
        (user_id, site_url, user_id),
    )

    # Then delete files from this site
    cursor.execute(
        """
        DELETE FROM files WHERE site_url = %s AND user_id = %s
    """,
        (site_url, user_id),
    )

    # Finally delete the site itself
    cursor.execute(
        """
        DELETE FROM sites WHERE site_url = %s AND user_id = %s
    """,
        (site_url, user_id),
    )

    conn.commit()


def add_manual_schema_file(
    conn: pymssql.Connection,
    site_url: str,
    user_id: str,
    file_url: str,
    schema_map=None,
):
    """Add a manual schema file for a site"""
    cursor = conn.cursor()
    # Check if file exists first
    cursor.execute(
        "SELECT file_url FROM files WHERE file_url = %s AND user_id = %s",
        (file_url, user_id),
    )
    if cursor.fetchone():
        # Update existing file
        cursor.execute(
            """
            UPDATE files SET is_active = 1, is_manual = 1, schema_map = %s
            WHERE file_url = %s AND user_id = %s
        """,
            (schema_map, file_url, user_id),
        )
    else:
        # Insert new file
        cursor.execute(
            """
            INSERT INTO files (site_url, user_id, file_url, schema_map, is_manual, is_active)
            VALUES (%s, %s, %s, %s, 1, 1)
        """,
            (site_url, user_id, file_url, schema_map),
        )
    conn.commit()


def remove_schema_file(conn: pymssql.Connection, file_url: str, user_id: str):
    """Remove a schema file (soft delete)"""
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE files SET is_active = 0 WHERE file_url = %s AND user_id = %s
    """,
        (file_url, user_id),
    )
    conn.commit()


def get_site_status(conn: pymssql.Connection, user_id: str = None):
    """Get status information for all sites"""
    cursor = conn.cursor()

    # Build query with user_id filter to avoid scanning entire ids table
    if user_id:
        cursor.execute(
            """
            SELECT
                s.site_url,
                s.is_active,
                s.last_processed,
                COUNT(DISTINCT f.file_url) as total_files,
                COUNT(DISTINCT CASE WHEN f.is_manual = 1 THEN f.file_url END) as manual_files,
                COUNT(DISTINCT i.id) as total_ids
            FROM sites s
            LEFT JOIN files f ON s.site_url = f.site_url AND f.is_active = 1 AND f.user_id = %s
            LEFT JOIN ids i ON f.file_url = i.file_url AND i.user_id = %s
            WHERE s.user_id = %s
            GROUP BY s.site_url, s.is_active, s.last_processed
            ORDER BY s.site_url
        """,
            (user_id, user_id, user_id),
        )
    else:
        # Fallback without user_id (legacy, not recommended for production)
        cursor.execute(
            """
            SELECT
                s.site_url,
                s.is_active,
                s.last_processed,
                COUNT(DISTINCT f.file_url) as total_files,
                COUNT(DISTINCT CASE WHEN f.is_manual = 1 THEN f.file_url END) as manual_files,
                COUNT(DISTINCT i.id) as total_ids
            FROM sites s
            LEFT JOIN files f ON s.site_url = f.site_url AND f.is_active = 1
            LEFT JOIN ids i ON f.file_url = i.file_url
            GROUP BY s.site_url, s.is_active, s.last_processed
            ORDER BY s.site_url
        """
        )
    return [
        {
            "site_url": row[0],
            "is_active": bool(row[1]),
            "last_processed": row[2].isoformat() if row[2] else None,
            "total_files": row[3],
            "manual_files": row[4],
            "total_ids": row[5],
        }
        for row in cursor.fetchall()
    ]
