import hashlib
import json
import logging
import os
import signal
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import feedparser
import requests
from flask import Flask, jsonify
from rss2schema import _entry_to_schema_article

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
import config  # Load environment variables
import db
import log
from cosmos_db import cosmos_db_batch_add, cosmos_db_batch_delete
from get_queue import get_queue
from rss2schema import parse_rss_to_schema
from scheduler import update_site_last_processed
from vector_db import vector_db_add, vector_db_delete

log.configure(os.environ)
logger = logging.getLogger("worker")

# Global worker status
worker_status = {
    "worker_id": os.getenv("HOSTNAME", "unknown"),
    "started_at": datetime.now(timezone.utc).isoformat(),
    "current_job": None,
    "total_jobs_processed": 0,
    "total_jobs_failed": 0,
    "last_job_at": None,
    "last_job_status": None,
    "status": "idle",
}

skip_types = (
    "ListItem",
    "ItemList",
    "Organization",
    "BreadcrumbList",
    "Breadcrumb",
    "WebSite",
    "SearchAction",
    "SiteNavigationElement",
    "WebPageElement",
    "WebPage",
    "NewsMediaOrganization",
    "MerchantReturnPolicy",
    "ReturnPolicy",
    "CollectionPage",
    "Brand",
    "Corporation",
    "ReadAction",
)


def old_process_json_array(json_array):
    """
    Helper function to process an array of JSON objects and extract @id values.

    Args:
        json_array (list): List of JSON objects to process

    Returns:
        tuple: (list of @id values, list of JSON objects)
    """
    ids = []
    objects = []
    for item in json_array:
        if isinstance(item, dict) and "@id" in item:
            ids.append(item["@id"])
            objects.append(item)
    return ids, objects


type_inherits = lambda parent, type_: (
    type_ == parent or (isinstance(type_, list) and parent in type_)
)


should_not_skip = lambda obj: (
    isinstance(obj, dict)
    # Removed @id/url requirement - will generate hash-based ID if needed
    and not any(type_inherits(skipped, obj.get("@type")) for skipped in skip_types)
    and not (
        "@graph" in obj and "@id" not in obj
    )  # Exclude graph containers without @id
)


def normalize_object_id(obj: dict, file_url: str) -> dict:
    """
    Ensure object has an @id field.
    Priority: @id > url > generated (file_url#hash)

    Modifies object in place and returns it.

    Args:
        obj: Schema.org object
        file_url: URL of the file being processed

    Returns:
        Modified object with @id field
    """
    if "@id" in obj:
        # Already has @id, but ensure it's a string (not a list)
        if isinstance(obj["@id"], list):
            if obj["@id"]:  # Non-empty list
                obj["@id"] = obj["@id"][0]
                logger.debug(f"Converted @id from list to string: {obj['@id']}")
            else:
                # Empty list, remove @id and fall through to generate one
                del obj["@id"]
        else:
            return obj

    if "url" in obj:
        # Has url field, use it as @id
        url_value = obj["url"]
        if isinstance(url_value, list):
            if url_value:  # Non-empty list
                obj["@id"] = url_value[0]
                logger.debug(f"Converted url from list to string for @id: {obj['@id']}")
            else:
                # Empty list, fall through to generate @id
                pass
        else:
            obj["@id"] = url_value

        if "@id" in obj:
            return obj

    # No @id or url - generate one from file_url + content hash
    # Create stable hash of object content
    content_str = json.dumps(obj, sort_keys=True, ensure_ascii=True)
    content_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()[:16]

    # Use # as delimiter (standard URI fragment identifier)
    obj["@id"] = f"{file_url}#{content_hash}"
    logger.debug(f"Generated @id for entity: {obj['@id']}")

    return obj


is_graph = lambda item: (
    isinstance(item, dict)
    and "@graph" in item
    and "@id" not in item
    and isinstance(item["@graph"], list)
)


def extract_objects_from_schema_file(
    content: str, content_type: str | None, file_url: str
):
    ### Check if this is an RSS feed ###
    if content_type and "rss" in content_type.lower():
        logger.info(f"Parsing RSS feed content")
        try:
            # Parse RSS content directly (no download needed)
            feed = feedparser.parse(content)

            if not hasattr(feed, "entries") or not feed.entries:
                logger.warning(f"No entries found in RSS feed")
                return [], []

            logger.info(f"Parsed {len(feed.entries)} entries from RSS feed")

            # Convert each entry to schema.org Article (same logic as rss2schema.py)
            articles = []
            for entry in feed.entries:
                article = _entry_to_schema_article(entry, feed)
                if article:
                    articles.append(article)

            # Extract IDs
            ids = [article.get("@id") for article in articles if "@id" in article]
            logger.info(f"Extracted {len(ids)} articles from RSS feed")

            return ids, articles
        except Exception as e:
            logger.error(f"Error parsing RSS feed: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return [], []

    ### Maybe each line of the schema file is a tab-separated pair: "URL\tJSON_STRING" ###

    if content_type and "tsv" in content_type.lower():
        logger.info(f"Parsing TSV format (tab-separated URL and JSON)")
        lines = content.strip().split("\n")
        unique_objects = {}

        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            if "\t" not in line:
                logger.warning(
                    f"[WORKER] Warning: Line {i} has no tab separator, skipping"
                )
                continue

            try:
                # Split by tab: first part is URL, second part is JSON
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    logger.warning(f"Line {i} doesn't have exactly 2 parts, skipping")
                    continue

                page_url, json_str = parts
                parsed = json.loads(json_str)
                for obj in filter(should_not_skip, parsed):
                    # Use page_url (first column) not file_url for TSV format
                    normalize_object_id(obj, page_url)  # Ensure @id exists
                    if obj["@id"] not in unique_objects:
                        unique_objects[obj["@id"]] = obj

                # Check for @graph arrays within each object which do not have an @id
                for obj in filter(is_graph, parsed):
                    graph_objects = list(filter(should_not_skip, obj["@graph"]))
                    for gobj in graph_objects:
                        # Use page_url (first column) not file_url for TSV format
                        normalize_object_id(gobj, page_url)  # Ensure @id exists
                        if gobj["@id"] not in unique_objects:
                            unique_objects[gobj["@id"]] = gobj
            except json.JSONDecodeError as e:
                logger.warning(f"Error parsing JSON on line {i}: {e}")
                continue

        return list(unique_objects.keys()), list(unique_objects.values())

    ### Maybe the schema file is a JSON object or array. ###

    try:
        content_json = json.loads(content)
        is_json = True
    except json.JSONDecodeError as e:
        content_json = None
        is_json = False

    if is_json and isinstance(content_json, (list, dict)):
        content_json: list = (
            [content_json] if not isinstance(content_json, list) else content_json
        )

        unique_objects = {}

        # Skip objects which are invalid or masked in skip_types
        for obj in filter(should_not_skip, content_json):
            normalize_object_id(obj, file_url)  # Ensure @id exists
            if obj["@id"] not in unique_objects:  # Keep first occurrence
                unique_objects[obj["@id"]] = obj

        # Check for @graph arrays within each object which do not have an @id
        for obj in filter(is_graph, content_json):
            graph_objects = list(filter(should_not_skip, obj["@graph"]))
            for gobj in graph_objects:
                normalize_object_id(gobj, file_url)  # Ensure @id exists
                if gobj["@id"] not in unique_objects:
                    unique_objects[gobj["@id"]] = gobj

        return list(unique_objects.keys()), list(unique_objects.values())

    ### Otherwise, each line of the schema file is a JSON object. ###

    objects = []

    for i, line in enumerate(content.strip().split("\n"), 1):
        line = line.strip()
        if not line:
            continue

        try:
            obj = json.loads(line)
            objects.append(obj)
        except json.JSONDecodeError as e:
            logger.warning(f"Error parsing JSON on line {i}: {e}")
            continue

    unique_objects = {}

    for obj in filter(should_not_skip, objects):
        normalize_object_id(obj, file_url)  # Ensure @id exists
        if obj["@id"] not in unique_objects:  # Keep first occurrence
            unique_objects[obj["@id"]] = obj

    # Check for @graph arrays within each object which do not have an @id
    for obj in filter(is_graph, objects):
        graph_objects = list(filter(should_not_skip, obj["@graph"]))
        for gobj in graph_objects:
            normalize_object_id(gobj, file_url)  # Ensure @id exists
            if gobj["@id"] not in unique_objects:
                unique_objects[gobj["@id"]] = gobj

    return list(unique_objects.keys()), list(unique_objects.values())


def extract_schema_data_from_url(url, content_type=None):
    """
    Extracts schema data from a URL containing JSON, TSV, or RSS content.

    Args:
        url (str): URL to fetch data from
        content_type (str, optional): Content type hint (e.g., 'structuredData/schema.org+tsv', 'RSS')

    Returns:
        tuple: (list of @id values, list of JSON objects)
    """
    try:
        # Check if this is an RSS feed
        if content_type and "rss" in content_type.lower():
            logger.info(f"Processing RSS feed from {url}")
            # Use RSS parser
            articles = parse_rss_to_schema(url, timeout=30)

            # Extract IDs and return objects
            ids = [article.get("@id") for article in articles if "@id" in article]
            num_objects = len(ids)

            logger.info(f"Extracted {num_objects} articles from RSS feed {url}")

            return ids, articles

        # Otherwise, process as JSON/TSV (existing logic)
        # Fetch content
        logger.info(f"Fetching {url}")
        response = requests.get(url, timeout=30)
        status_code = response.status_code
        content_length = len(response.content)

        response.raise_for_status()
        logger.info(f"Fetched {url}: {status_code} status, {content_length} bytes")

        ids, objects = extract_objects_from_schema_file(
            response.text, content_type, url
        )
        num_objects = len(ids)
        logger.debug(f"Extracted {num_objects} IDs from array in {url}")
        return ids, objects

    except requests.RequestException as e:
        error_msg = f"Request error: {str(e)}"
        logger.error(f"Error fetching {url}: {error_msg}")
        return [], []
    except ValueError as e:
        error_msg = f"JSON parse error: {str(e)}"
        logger.error(f"Error parsing JSON from {url}: {error_msg}")
        return [], []
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Unexpected error processing {url}: {error_msg}")
        return [], []


def augment_object(obj: dict[str, Any]) -> dict[str, Any]:
    """
    Set any fields which might be missing but can be derived from other fields.
    """
    augmented = obj.copy()
    if (
        obj.get("@type") == "Article"
        or (
            isinstance(obj.get("@type"), list) and "Article" in obj.get("@type")  # type: ignore
        )
    ) and "name" not in obj:
        augmented["name"] = obj.get("headline", "Untitled Article")
    return augmented


def process_job(conn, job):
    """Process a single job from the queue"""
    from metrics import CRAWLER_EXTERNAL_CALL_DURATION, CRAWLER_ITEMS_PER_JOB

    try:
        # Extract user_id from job, default to 'system' for legacy jobs
        user_id = job.get("user_id")
        if not user_id:
            user_id = "system"
            logger.warning(f"Job missing user_id, defaulting to '{user_id}'")

        if job["type"] == "process_file":
            job_start_time = time.time()
            logger.info(
                f"========== Starting process_file for {job['file_url']} =========="
            )
            logger.info(f"Job details - site: {job.get('site')}, user_id: {user_id}")

            # Check if the file still exists and get its current hash
            cursor = conn.cursor()
            cursor.execute(
                "SELECT file_hash FROM files WHERE file_url = %s",
                (job["file_url"],),
            )
            result = cursor.fetchone()
            if not result:
                logger.info(
                    f"File no longer exists in database, skipping: {job['file_url']}"
                )
                return True  # Job completed successfully (file was deleted)

            stored_hash = result[0]
            logger.info(
                f"File exists in database (stored hash: {stored_hash or 'NULL'})"
            )

            # Download the file content
            logger.info(f"Downloading file: {job['file_url']}")
            try:
                download_start = time.time()
                response = requests.get(job["file_url"], timeout=30)
                response.raise_for_status()
                file_content = response.text
                CRAWLER_EXTERNAL_CALL_DURATION.labels(service="download").observe(
                    time.time() - download_start
                )
                content_type = job.get("content_type")

                # For RSS: parse first, then hash the stable schema.org objects
                # For TSV/JSON: hash raw content (already stable schema.org format)
                if content_type and "rss" in content_type.lower():
                    logger.info(f"RSS feed detected - parsing first before hashing")
                    # Parse RSS to schema.org objects
                    ids, objects = extract_objects_from_schema_file(
                        file_content, content_type, job["file_url"]
                    )

                    # Hash the stable schema.org objects (sorted for consistency)
                    objects_json = json.dumps(
                        objects, sort_keys=True, ensure_ascii=True
                    )
                    current_hash = hashlib.sha256(
                        objects_json.encode("utf-8")
                    ).hexdigest()
                    logger.info(
                        f"Calculated hash from {len(objects)} schema.org objects: {current_hash}"
                    )

                    # Compare hashes - skip if unchanged
                    if stored_hash and current_hash == stored_hash:
                        logger.info(
                            f"RSS articles unchanged (hash match), skipping processing"
                        )
                        return True  # Job completed successfully (no work needed)

                    logger.info(
                        f"RSS articles changed or new file, proceeding with processing"
                    )
                    # Skip extraction below since we already parsed
                    skip_extraction = True
                else:
                    # For TSV/JSON: hash raw content
                    current_hash = hashlib.sha256(
                        file_content.encode("utf-8")
                    ).hexdigest()
                    logger.info(f"Calculated content hash: {current_hash}")

                    # Compare hashes - skip if unchanged
                    if stored_hash and current_hash == stored_hash:
                        logger.info(
                            f"File content unchanged (hash match), skipping processing"
                        )
                        return True  # Job completed successfully (no work needed)

                    logger.info(
                        f"File content changed or new file, proceeding with processing"
                    )
                    skip_extraction = False

            except requests.RequestException as e:
                error_msg = f"Failed to download file: {str(e)}"
                logger.error(error_msg)
                db.log_processing_error(
                    conn,
                    job["file_url"],
                    user_id,
                    "download_failed",
                    error_msg,
                    str(e.__class__.__name__),
                )
                return False

            # Extract entities from file content (skip if already done for RSS)
            if not skip_extraction:
                logger.info(f"Extracting entities from file")
                extraction_start = time.time()
                try:
                    ids, objects = extract_objects_from_schema_file(
                        file_content, content_type, job["file_url"]
                    )
                    extraction_time = time.time() - extraction_start
                    logger.info(f"⏱️  Extraction took {extraction_time:.2f}s")
                except Exception as e:
                    error_msg = f"Failed to extract schema data: {str(e)}"
                    logger.error(f"Error extracting schema data: {error_msg}")
                    import traceback

                    traceback.print_exc()
                    db.log_processing_error(
                        conn,
                        job["file_url"],
                        user_id,
                        "extraction_failed",
                        error_msg,
                        str(e.__class__.__name__),
                    )
                    return False  # Fail the job - cannot process without entities
            else:
                logger.info(
                    f"Using already extracted entities from RSS parsing ({len(objects)} objects)"
                )

            logger.info(
                f"Extracted {len(ids)} IDs, {len(objects)} objects from {job['file_url']}"
            )

            # Log if no entities extracted
            if len(objects) == 0:
                error_msg = "No schema.org objects found in file"
                logger.warning(error_msg)
                db.log_processing_error(
                    conn,
                    job["file_url"],
                    user_id,
                    "no_objects_found",
                    error_msg,
                    "",
                )
                # Continue processing - update hash to prevent retrying

            if len(ids) > 0:
                logger.debug(f"Sample IDs: {list(ids)[:3]}")
            if len(objects) > 0:
                logger.debug(
                    f"Sample object @type: {objects[0].get('@type', 'unknown')}"
                )

            # Prepare items to upsert to Vector/Cosmos DBs
            # No reference counting - just upsert everything
            logger.info(f"Preparing {len(objects)} objects for upsert")
            prep_start = time.time()
            items_to_add = []
            skipped_breadcrumbs = 0

            for obj in objects:
                # Skip BreadcrumbList items
                obj_type = obj.get("@type", "")
                if obj_type == "BreadcrumbList" or (
                    isinstance(obj_type, list) and "BreadcrumbList" in obj_type
                ):
                    skipped_breadcrumbs += 1
                    logger.debug(f"Skipping BreadcrumbList item: {obj.get('@id')}")
                    continue

                complete_obj = augment_object(obj)
                items_to_add.append((obj["@id"], job["site"], complete_obj))

            prep_time = time.time() - prep_start
            logger.info(f"  → Prepared {len(items_to_add)} items in {prep_time:.2f}s")
            CRAWLER_ITEMS_PER_JOB.observe(len(items_to_add))

            if skipped_breadcrumbs > 0:
                logger.info(f"Skipped {skipped_breadcrumbs} BreadcrumbList items")

            # Update file metadata in database (hash, item count, and content_type)
            logger.info(f"Updating file metadata (hash, item count, and content_type)")
            cursor.execute(
                """UPDATE files
                   SET last_read_time = GETUTCDATE(),
                       number_of_items = %s,
                       file_hash = %s,
                       content_type = %s
                   WHERE file_url = %s""",
                (len(objects), current_hash, job.get("content_type"), job["file_url"]),
            )

            # Commit SQL changes BEFORE Cosmos/Vector operations
            # Trade-off: If Cosmos/Vector fail, SQL is already committed (eventual consistency)
            conn.commit()
            logger.info("Committed SQL changes (file metadata updated)")

            # CRITICAL: Close connection immediately after commit to free up connection pool
            conn.close()
            logger.info("Closed database connection after SQL commit")
            conn = None

            # Upsert to Cosmos DB and Vector DB (merge/overwrite mode)
            # No reference counting - entities are simply upserted by @id
            if items_to_add:
                logger.info(
                    f"Upserting {len(items_to_add)} items to Cosmos DB and Vector DB"
                )
                logger.debug(
                    f"Sample items: {[(id, site) for id, site, _ in items_to_add[:3]]}"
                )

                # Step 1: Upsert to Cosmos DB (full objects) - SOURCE OF TRUTH
                logger.info(f"Calling cosmos_db_batch_add (upsert mode)...")
                cosmos_db_start = time.time()
                try:
                    # Extract just the objects from items_to_add
                    objects_to_upsert = [obj for _, _, obj in items_to_add]
                    cosmos_db_batch_add(objects_to_upsert)
                    cosmos_db_time = time.time() - cosmos_db_start
                    CRAWLER_EXTERNAL_CALL_DURATION.labels(
                        service="cosmos_db"
                    ).observe(cosmos_db_time)
                    logger.info(
                        f"⏱️  Cosmos DB upsert completed for {len(objects_to_upsert)} items in {cosmos_db_time:.2f}s"
                    )
                except Exception as e:
                    error_msg = f"Failed to upsert items to Cosmos DB: {str(e)}"
                    logger.error(error_msg)
                    import traceback

                    traceback.print_exc()
                    # Open fresh connection only for error logging
                    try:
                        error_conn = db.get_connection()
                        db.log_processing_error(
                            error_conn,
                            job["file_url"],
                            user_id,
                            "cosmos_db_upsert_failed",
                            error_msg,
                            str(e.__class__.__name__),
                        )
                        error_conn.commit()
                        error_conn.close()
                    except Exception as log_err:
                        logger.error(f"Failed to log error to database: {log_err}")
                    logger.warning(
                        f"Cosmos DB upsert failed - hash updated but objects not stored"
                    )
                    return False

                # Step 2: Upsert to Vector DB (searchable index)
                from vector_db import vector_db_batch_add

                logger.info(f"Calling vector_db_batch_add (upsert mode)...")
                vector_db_start = time.time()
                try:
                    vector_db_batch_add(items_to_add)
                    vector_db_time = time.time() - vector_db_start
                    CRAWLER_EXTERNAL_CALL_DURATION.labels(
                        service="vector_db"
                    ).observe(vector_db_time)
                    logger.info(
                        f"⏱️  Vector DB upsert completed for {len(items_to_add)} items in {vector_db_time:.2f}s"
                    )
                except Exception as e:
                    error_msg = f"Failed to upsert items to Vector DB: {str(e)}"
                    logger.error(error_msg)
                    import traceback

                    error_details = traceback.format_exc()
                    # Open fresh connection only for error logging
                    try:
                        error_conn = db.get_connection()
                        db.log_processing_error(
                            error_conn,
                            job["file_url"],
                            user_id,
                            "vector_db_upsert_failed",
                            error_msg,
                            error_details,
                        )
                        error_conn.commit()
                        error_conn.close()
                    except Exception as log_err:
                        logger.error(f"Failed to log error to database: {log_err}")
                    logger.warning(
                        f"Vector DB upsert failed - items in Cosmos but not searchable"
                    )
                    return False
            else:
                logger.info(f"No items to upsert (all were BreadcrumbList or invalid)")

            # No deletion tracking - orphaned entities will be cleaned up by batch job

            # Update the site's last_processed timestamp (Note: may need user_id in future)
            logger.info(f"Updating site last_processed timestamp for {job['site']}")
            update_site_last_processed(job["site"])

            # Clear any previous errors for this file since it processed successfully
            # Open fresh connection for this final cleanup operation
            try:
                cleanup_conn = db.get_connection()
                db.clear_file_errors(cleanup_conn, job["file_url"])
                cleanup_conn.commit()
                cleanup_conn.close()
            except Exception as e:
                logger.warning(f"Failed to clear file errors: {e}")

            total_job_time = time.time() - job_start_time
            logger.info(f"⏱️  TOTAL JOB TIME: {total_job_time:.2f}s")
            logger.info(
                f"========== Completed process_file for {job['file_url']} =========="
            )
            return True

        elif job["type"] == "process_removed_file":
            logger.info(f"Processing removal: {job['file_url']}")
            cursor = conn.cursor()

            # Get site_url for domain matching
            cursor.execute(
                "SELECT site_url FROM files WHERE file_url = %s", (job["file_url"],)
            )
            result = cursor.fetchone()
            if not result:
                logger.info(f"File not found in database: {job['file_url']}")
                return True  # Already deleted

            site_url = result[0]
            logger.info(f"Deleting entities for site: {site_url}")

            # Try to download and extract entities from the file
            # Use the same extraction logic as insertion (auto-detects format)
            # If file is dead, we accept orphaned data (cleanup job will handle)
            ids_to_delete = []
            try:
                logger.info(f"Attempting to extract entities from file")
                # Use extract_schema_data_from_url (same as insertion)
                # It auto-detects TSV/JSON/RSS format
                ids, objects = extract_schema_data_from_url(
                    job["file_url"], job.get("content_type")
                )
                logger.info(f"Extracted {len(ids)} entities from file")

                # Filter entities by domain match using simple substring check
                ids_skipped = []
                site_url_lower = site_url.lower()

                for entity_id in ids:
                    entity_id_lower = entity_id.lower()

                    # Check if entity_id contains the site domain with proper URL delimiters
                    # Handles both with and without www prefix
                    if any(
                        [
                            f"://{site_url_lower}/" in entity_id_lower,
                            f"://www.{site_url_lower}/" in entity_id_lower,
                            f"://{site_url_lower}?" in entity_id_lower,
                            f"://www.{site_url_lower}?" in entity_id_lower,
                            f"://{site_url_lower}#" in entity_id_lower,
                            f"://www.{site_url_lower}#" in entity_id_lower,
                        ]
                    ):
                        ids_to_delete.append(entity_id)
                        logger.debug(f"Will delete: {entity_id} (domain match)")
                    else:
                        ids_skipped.append(entity_id)
                        logger.debug(f"Skipping: {entity_id} (different domain)")

                logger.info(
                    f"Will delete {len(ids_to_delete)} entities matching domain {site_url}"
                )
                if ids_skipped:
                    logger.info(
                        f"Skipped {len(ids_skipped)} IDs with different domains"
                    )

            except requests.RequestException as e:
                logger.warning(f"Could not download file (URL dead?): {e}")
                logger.warning(f"Accepting orphaned data - cleanup job will handle")
                # Continue to delete file record even if entities can't be removed
            except Exception as e:
                logger.error(f"Error extracting entities: {e}")
                import traceback

                traceback.print_exc()
                # Continue anyway

            # Delete the file record from files table
            cursor.execute("DELETE FROM files WHERE file_url = %s", (job["file_url"],))

            # Commit SQL changes BEFORE external operations (eventual consistency)
            conn.commit()
            logger.info(f"Committed SQL changes (file record deleted)")

            # Close connection immediately after commit
            conn.close()
            logger.info("Closed database connection after SQL commit")
            conn = None

            # Delete entities from Vector DB and Cosmos DB (best effort)
            if ids_to_delete:
                logger.info(
                    f"Deleting {len(ids_to_delete)} entities from Vector DB and Cosmos DB"
                )

                # Step 1: Delete from Vector DB (make unsearchable)
                from vector_db import vector_db_batch_delete

                try:
                    vector_db_batch_delete(ids_to_delete)
                    logger.info(
                        f"Successfully deleted {len(ids_to_delete)} items from Vector DB"
                    )
                except Exception as e:
                    logger.error(f"Failed to delete from Vector DB: {e}")
                    import traceback

                    traceback.print_exc()
                    # Open fresh connection only for error logging
                    try:
                        error_conn = db.get_connection()
                        db.log_processing_error(
                            error_conn,
                            job["file_url"],
                            user_id,
                            "vector_db_delete_failed",
                            str(e),
                            str(e.__class__.__name__),
                        )
                        error_conn.commit()
                        error_conn.close()
                    except Exception as log_err:
                        logger.error(f"Failed to log error to database: {log_err}")
                    # SQL already committed - cannot rollback
                    logger.warning(
                        f"Vector DB delete failed - orphaned search results may exist"
                    )
                    return False  # Fail the job - cleanup later

                # Step 2: Delete from Cosmos DB (remove storage)
                try:
                    cosmos_db_batch_delete(ids_to_delete)
                    logger.info(
                        f"Successfully deleted {len(ids_to_delete)} items from Cosmos DB"
                    )
                except Exception as e:
                    logger.error(f"Failed to delete from Cosmos DB: {e}")
                    import traceback

                    traceback.print_exc()
                    # Open fresh connection only for error logging
                    try:
                        error_conn = db.get_connection()
                        db.log_processing_error(
                            error_conn,
                            job["file_url"],
                            user_id,
                            "cosmos_db_delete_failed",
                            str(e),
                            str(e.__class__.__name__),
                        )
                        error_conn.commit()
                        error_conn.close()
                    except Exception as log_err:
                        logger.error(f"Failed to log error to database: {log_err}")
                    logger.warning(
                        f"Cosmos DB delete failed - orphaned storage may exist"
                    )
                    return False  # Fail the job - cleanup later

                logger.info(f"Successfully removed {len(ids_to_delete)} entities")
            else:
                logger.info(
                    f"No entities to delete (file was dead or no matching entities)"
                )

            return True

    except Exception as e:
        logger.error(f"Job failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def start_status_server():
    """Start Flask server for worker status in a separate thread"""
    app = Flask(__name__)

    @app.route("/status")
    def status():
        return jsonify(worker_status)

    @app.route("/health")
    def health():
        return jsonify({"status": "healthy"})

    @app.route("/metrics")
    def metrics():
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

    # Run Flask in a separate thread
    port = int(os.getenv("WORKER_STATUS_PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def worker_loop():
    """Main worker loop using queue interface"""
    global worker_status

    # Get queue implementation
    queue = get_queue()

    conn = None

    def get_db_connection():
        """Get a fresh database connection"""
        nonlocal conn
        try:
            if conn:
                try:
                    # Test if connection is still alive
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.close()
                except:
                    # Connection is dead, close it
                    try:
                        conn.close()
                    except:
                        pass
                    conn = None

            if not conn:
                conn = db.get_connection()
                logger.info("Database connection established")

            return conn
        except Exception as e:
            logger.error(f"Error getting database connection: {e}")
            return None

    # Setup signal handlers for graceful shutdown
    # Handles SIGTERM and SIGINT to allow current job to complete before exiting
    shutdown_requested = False

    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        logger.info(f"Received shutdown signal, initiating graceful shutdown...")
        shutdown_requested = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    from metrics import (
        CRAWLER_JOB_DURATION,
        CRAWLER_JOBS_PROCESSED_TOTAL,
        CRAWLER_WORKER_IDLE,
    )

    try:
        logger.info(
            f"Started worker with queue type: {os.getenv('QUEUE_TYPE', 'file')}"
        )
        worker_status["status"] = "running"

        # Track when we last logged queue status
        last_queue_status_time = 0
        queue_status_interval = 30  # Log every 30 seconds

        while not shutdown_requested:
            try:
                # Receive message from queue
                worker_status["status"] = "waiting"
                CRAWLER_WORKER_IDLE.set(1)

                # Log queue status periodically
                current_time = time.time()
                if current_time - last_queue_status_time >= queue_status_interval:
                    if hasattr(queue, "get_message_count"):
                        count = queue.get_message_count()
                        if count >= 0:
                            logger.info(f"Approximate messages in queue: {count}")
                    last_queue_status_time = current_time

                message = queue.receive_message(
                    visibility_timeout=300
                )  # 5 minute timeout

                if not message:
                    time.sleep(5)
                    continue

                job = message.content
                worker_status["status"] = "processing"
                CRAWLER_WORKER_IDLE.set(0)
                job_metric_start = time.time()
                worker_status["current_job"] = job
                logger.info(
                    f"Processing: {job.get('file_url', job.get('type', 'unknown'))}"
                )

                # Get fresh connection for each job
                conn = get_db_connection()
                if not conn:
                    logger.error(f"Cannot connect to database, returning job to queue")
                    if not queue.return_message(message):
                        logger.warning(f"Could not return message to queue")
                    worker_status["current_job"] = None
                    time.sleep(10)  # Wait before retrying
                    continue

                # Process job
                try:
                    success = process_job(conn, job)
                except Exception as e:
                    logger.error(f"Error processing job: {e}")
                    logger.error(f"Full traceback:")
                    import traceback

                    traceback.print_exc()
                    logger.error(f"Job details: {json.dumps(job, indent=2)}")
                    # Check if it's a connection error
                    if "Communication link failure" in str(e) or "08S01" in str(e):
                        logger.warning(
                            f"Database connection lost, will reconnect on next job"
                        )
                        try:
                            conn.close()
                        except:
                            pass
                        conn = None
                    success = False

                # Record metrics
                job_type = job.get("type", "unknown")
                result_label = "success" if success else "failure"
                CRAWLER_JOBS_PROCESSED_TOTAL.labels(
                    job_type=job_type, result=result_label
                ).inc()
                CRAWLER_JOB_DURATION.labels(job_type=job_type).observe(
                    time.time() - job_metric_start
                )

                # Update status
                worker_status["last_job_at"] = datetime.now(timezone.utc).isoformat()
                worker_status["last_job_status"] = "success" if success else "failed"
                worker_status["current_job"] = None

                if success:
                    worker_status["total_jobs_processed"] += 1
                    # Delete message from queue
                    if not queue.delete_message(message):
                        logger.warning(f"Could not delete message from queue")
                else:
                    worker_status["total_jobs_failed"] += 1
                    # Return message to queue for retry
                    if not queue.return_message(message):
                        logger.warning(f"Could not return message to queue")

            except Exception as e:
                logger.error(f"Error in main loop iteration: {e}")
                worker_status["status"] = "error"
                worker_status["current_job"] = None
                # Sleep before retrying to avoid tight error loops
                time.sleep(5)

        logger.info("Worker loop exited gracefully")
        worker_status["status"] = "stopped"
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
        worker_status["status"] = "stopped"
    except Exception as e:
        logger.error(f"Fatal error in worker loop: {e}")
        worker_status["status"] = "crashed"
        import traceback

        traceback.print_exc()
    finally:
        # Cleanup: rollback any uncommitted transactions and close connections
        # This prevents orphaned transactions and database locks
        if conn:
            try:
                conn.rollback()
                logger.info("Rolled back uncommitted transactions")
            except:
                pass
            try:
                conn.close()
                logger.info("Database connection closed")
            except:
                pass


if __name__ == "__main__":
    logger_startup = logging.getLogger("worker.startup")

    # Test database connectivity first
    logger_startup.info("Testing database connection...")
    try:
        test_conn = db.get_connection()
        test_conn.close()
        logger_startup.info("✓ Database connection successful")
    except Exception as e:
        logger_startup.error(f"✗ Database connection failed: {str(e)}")
        sys.exit(1)

    # Test Queue connectivity
    queue_type = os.getenv("QUEUE_TYPE", "file")
    if queue_type == "storage":
        logger_startup.info("Testing Storage Queue connection...")
        try:
            from azure.identity import DefaultAzureCredential
            from azure.storage.queue import QueueServiceClient

            storage_account = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
            queue_name = os.getenv("AZURE_STORAGE_QUEUE_NAME", "crawler-jobs")

            if not storage_account:
                logger_startup.error(
                    "✗ Storage Queue not configured - AZURE_STORAGE_ACCOUNT_NAME not set"
                )
                sys.exit(1)

            account_url = f"https://{storage_account}.queue.core.windows.net"
            credential = DefaultAzureCredential()
            service_client = QueueServiceClient(
                account_url=account_url, credential=credential
            )
            queue_client = service_client.get_queue_client(queue_name)

            # Test connection by checking queue properties
            queue_client.get_queue_properties()
            logger_startup.info(
                f"✓ Storage Queue connection successful (queue: {queue_name})"
            )

            # Ensure queue exists (create if needed)
            from queue_interface_storage import ensure_queue_exists

            ensure_queue_exists(storage_account, queue_name)
        except Exception as e:
            logger_startup.error(f"✗ Storage Queue connection failed: {str(e)}")
            sys.exit(1)

    # Start status server in background thread
    logger_startup.info("Starting status server on port 8080...")
    status_thread = threading.Thread(target=start_status_server, daemon=True)
    status_thread.start()
    logger_startup.info("✓ Status server started")

    # Start worker loop
    worker_loop()
