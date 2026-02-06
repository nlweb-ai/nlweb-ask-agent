import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import config  # Load environment variables
import db
import log
import requests
from get_queue import get_queue

log.configure(os.environ)
logger = logging.getLogger("master")
logger.setLevel(log.level(os.environ))


def parse_schema_map_xml(xml_content, base_url):
    """Parse schema_map.xml content and extract schema.org file URLs"""
    try:
        root = ET.fromstring(xml_content)

        logger.debug(f"Root tag: {root.tag}")
        logger.debug(f"Root attrib: {root.attrib}")

        # Handle namespace if present
        namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        ns_uri = "http://www.sitemaps.org/schemas/sitemap/0.9"

        schema_urls = []

        # ROBUST APPROACH: Find ALL <url> elements at any depth, with any namespace
        # This handles various sitemap structures without hard-coding specific patterns
        urls = []

        # Try with namespace first (most common)
        urls.extend(root.findall(".//sitemap:url", namespace))
        urls.extend(root.findall(".//{%s}url" % ns_uri))

        # Also try without namespace (fallback)
        urls.extend(root.findall(".//url"))

        # Remove duplicates (in case same element matched multiple ways)
        urls = list(set(urls))

        logger.debug(f"Found {len(urls)} url elements (at any depth)")

        for url_elem in urls:
            # Check if this URL has structuredData/schema.org or RSS content type
            content_type = url_elem.get("contentType", "")
            logger.debug(f"URL element contentType: {content_type}")

            # Accept both schema.org and RSS content types
            if "schema.org" in content_type.lower() or "rss" in content_type.lower():
                # Get the location - try multiple namespace formats
                loc = url_elem.find("sitemap:loc", namespace)
                if loc is None:
                    loc = url_elem.find("{%s}loc" % ns_uri)
                if loc is None:
                    loc = url_elem.find("loc")

                if loc is not None and loc.text:
                    # Make URL absolute if needed
                    url = urljoin(base_url, loc.text.strip())
                    logger.debug(f"Adding URL: {url} with content_type: {content_type}")
                    # Return tuple of (url, content_type) to pass format info to worker
                    schema_urls.append((url, content_type))

        logger.debug(f"Total schema URLs extracted: {len(schema_urls)}")
        return schema_urls
    except ET.ParseError as e:
        logger.error(f"Error parsing XML: {e}. For site: {base_url}")
        return []


def get_schema_urls_from_robots(site_url):
    """
    Fetch robots.txt or schema_map.xml and extract schema file URLs.
    Returns triples: (site_url, schema_map_url, json_file_url)
    First tries robots.txt for schemaMap directives.
    If not found, tries schema_map.xml directly.
    """

    # First, try robots.txt
    parsed_site = urlparse(site_url)
    site_url_normalized = site_url if parsed_site.scheme else f"https://{site_url}"
    robots_url = urljoin(site_url_normalized, "/robots.txt")

    try:
        response = requests.get(robots_url, timeout=10)
        if response.status_code == 200:
            schema_map_urls = []
            for line in response.text.splitlines():
                if line.lower().startswith("schemamap:"):
                    url = line.split(":", 1)[1].strip()
                    schema_map_urls.append(urljoin(site_url_normalized, url))

            # If we found schemaMap directives, fetch and parse those XML files
            if schema_map_urls:
                all_schema_files = []
                for map_url in schema_map_urls:
                    try:
                        map_response = requests.get(map_url, timeout=10)
                        if map_response.status_code == 200:
                            url_tuples = parse_schema_map_xml(
                                map_response.text, site_url_normalized
                            )
                            # Return triples of (site_url, schema_map_url, (json_file_url, content_type))
                            all_schema_files.extend(
                                [
                                    (site_url, map_url, url_tuple)
                                    for url_tuple in url_tuples
                                ]
                            )
                    except requests.RequestException as e:
                        logger.error(f"Error fetching schema map from {map_url}: {e}")
                return all_schema_files
    except requests.RequestException:
        pass  # Try schema_map.xml next

    # If no robots.txt or no schemaMap directives, try schema_map.xml directly
    schema_map_url = urljoin(site_url_normalized, "/schema_map.xml")
    try:
        response = requests.get(schema_map_url, timeout=10)
        if response.status_code == 200:
            url_tuples = parse_schema_map_xml(response.text, site_url_normalized)
            # Return triples of (site_url, schema_map_url, (json_file_url, content_type))
            return [(site_url, schema_map_url, url_tuple) for url_tuple in url_tuples]
    except requests.RequestException:
        pass

    # As a last resort, if the site_url itself ends with schema_map.xml, fetch it
    if site_url_normalized.endswith("schema_map.xml"):
        try:
            response = requests.get(site_url_normalized, timeout=10)
            if response.status_code == 200:
                base = site_url_normalized.rsplit("/", 1)[0] + "/"
                url_tuples = parse_schema_map_xml(response.text, base)
                # Return triples of (site_url, schema_map_url, (json_file_url, content_type))
                return [(site_url, site_url, url_tuple) for url_tuple in url_tuples]
        except requests.RequestException as e:
            logger.error(f"Error fetching schema map from {site_url}: {e}")

    logger.debug(f"No schema files found for {site_url}")
    return []


def is_aajtak_recent_file(url):
    """
    Check if a URL should be processed for aajtak.in.
    Returns True if the URL matches:
    - "latest" in URL (latest news feed)
    - Any date within the last 7 days (for backfilling)
    """
    from datetime import date, timedelta

    if "latest" in url.lower():
        return True

    LAST_X_DAYS = 2
    today = date.today()
    for days_ago in range(LAST_X_DAYS):
        check_date = today - timedelta(days=days_ago)
        date_pattern = (
            f"yyyy={check_date.year}&mm={check_date.month:02d}&dd={check_date.day:02d}"
        )
        if date_pattern in url:
            return True

    return False


def filter_aajtak_recent_files(file_url_tuples):
    """
    Hack: Only process recent files for aajtak.in to avoid checking 1,500+ historical files.
    Keeps files matching recent date criteria.

    Result: ~3 files instead of 1,500
    """
    recent_files = [
        url_tuple
        for url_tuple in file_url_tuples
        if is_aajtak_recent_file(url_tuple[0])
    ]
    logger.info(
        f"aajtak.in filter: {len(file_url_tuples)} files → {len(recent_files)} recent files"
    )
    return recent_files


def add_schema_map_to_site(
    site_url, user_id="system", schema_map_url=None, refresh_mode="diff"
):
    """
    Add a schema map to a site (Level 2 logic):
    1. Fetch and parse the schema_map XML
    2. Add all JSON files to database
    3. Queue files for processing based on refresh_mode

    Args:
        site_url: Site URL
        user_id: User ID
        schema_map_url: URL to schema map XML
        refresh_mode: "diff" (only queue new files) or "full" (queue all files)

    Returns: (files_added_count, files_queued_count)
    """
    conn = None
    try:
        conn = db.get_connection()

        # Check if site exists, if not create it
        cursor = conn.cursor()
        cursor.execute(
            "SELECT site_url FROM sites WHERE site_url = %s AND user_id = %s",
            (site_url, user_id),
        )
        if not cursor.fetchone():
            db.add_site(
                conn,
                site_url,
                user_id,
                schema_map_url=schema_map_url,
                refresh_mode=refresh_mode,
            )
        else:
            # Site exists - update schema_map_url and refresh_mode
            cursor.execute(
                "UPDATE sites SET schema_map_url = %s, refresh_mode = %s WHERE site_url = %s AND user_id = %s",
                (schema_map_url, refresh_mode, site_url, user_id),
            )

        # Fetch and parse the schema_map to get all JSON file URLs
        response = requests.get(schema_map_url, timeout=10)
        if response.status_code != 200:
            logger.warning(
                f"Failed to fetch schema_map {schema_map_url}: HTTP {response.status_code}"
            )
            return (0, 0)

        logger.info(f"Fetched schema_map, parsing with base_url: {site_url}")
        json_file_url_tuples = parse_schema_map_xml(response.text, site_url)
        logger.info(f"Parsed {len(json_file_url_tuples)} files from schema_map")

        if not json_file_url_tuples:
            logger.debug(
                f"No schema files found in {schema_map_url}; response preview: {response.text[:500]}"
            )
            return (0, 0)

        # Create triples: (site_url, schema_map_url, file_url) for database
        # Keep content_type separately for job creation
        files_to_add = [
            (site_url, schema_map_url, url_tuple[0])
            for url_tuple in json_file_url_tuples
        ]

        # Add all files to the database
        added_files, removed_files = db.update_site_files(
            conn, site_url, user_id, files_to_add
        )
        logger.info(
            f"Database update: {len(added_files)} files added, {len(removed_files)} removed"
        )
        logger.debug(f"Added files: {added_files}")

        # Create a lookup dict for content_type by file_url
        content_type_map = {
            url_tuple[0]: url_tuple[1] for url_tuple in json_file_url_tuples
        }
        logger.debug(f"Content type map: {content_type_map}")

        # Determine which files to queue based on refresh_mode
        if refresh_mode == "full":
            # Queue ALL files from XML (current behavior)
            # Worker will check file_hash and skip if unchanged
            files_to_queue = [url_tuple[0] for url_tuple in json_file_url_tuples]
            logger.info(
                f"Refresh mode: FULL - queuing {len(files_to_queue)} files (worker will check hashes)"
            )
        else:
            # Queue only NEW files (diff mode)
            # Workers won't encounter existing files at all
            files_to_queue = added_files
            logger.info(
                f"Refresh mode: DIFF - queuing {len(files_to_queue)} new files only"
            )

        # HACK: For aajtak.in, override files_to_queue to only recent files
        # This avoids checking 1,500+ historical files that never change
        # We do this AFTER all normal logic, so database has all files but we only queue recent ones
        if site_url == "aajtak.in":
            recent_tuples = filter_aajtak_recent_files(json_file_url_tuples)
            files_to_queue = [url_tuple[0] for url_tuple in recent_tuples]
            logger.info(
                f"aajtak.in override: queuing {len(files_to_queue)} recent files (ignoring mode)"
            )

        queue = get_queue()
        queued_count = 0

        for file_url in files_to_queue:
            try:
                content_type = content_type_map.get(file_url)

                job = {
                    "type": "process_file",
                    "user_id": user_id,
                    "site": site_url,
                    "file_url": file_url,
                    "schema_map": schema_map_url,
                    "queued_at": datetime.now(timezone.utc).isoformat(),
                }

                # Add content_type if available
                if content_type:
                    job["content_type"] = content_type
                success = queue.send_message(job)
                if success:
                    queued_count += 1
            except Exception as e:
                logger.error(f"Error queuing file {file_url}: {e}")

        if refresh_mode == "full":
            logger.info(
                f"Queued {queued_count} process_file jobs in FULL mode (worker will skip unchanged via hash)"
            )
        else:
            logger.info(
                f"Queued {queued_count} new files in DIFF mode (existing files not queued)"
            )

        # Queue jobs for REMOVED files
        for file_url in removed_files:
            try:
                job = {
                    "type": "process_removed_file",
                    "user_id": user_id,  # Add user_id to job
                    "site": site_url,
                    "file_url": file_url,
                    "queued_at": datetime.now(timezone.utc).isoformat(),
                }
                queue.send_message(job)
            except Exception as e:
                logger.error(f"Error queuing removal for {file_url}: {e}")

        # Return: (new files discovered, total jobs queued)
        # Note: queued_count may be greater than len(added_files) because we queue ALL files
        # for hash-based change detection, not just new ones
        return (len(added_files), queued_count)

    except Exception as e:
        logger.error(
            f"Error adding schema map {schema_map_url} to site {site_url}: {e}"
        )
        return (0, 0)
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


def process_site(site_url, user_id="system"):
    """
    Process a site (Level 1 logic):
    1. Check database for stored schema_map_url first
    2. If not found, discover schema maps from robots.txt
    3. For each schema map, call add_schema_map_to_site (Level 2)

    Returns: Number of files queued (int), or None on error
    """
    try:
        logger.debug(f"Processing site: {site_url}")

        # First, check if site has a stored schema_map_url and refresh_mode in database
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT schema_map_url, refresh_mode FROM sites WHERE site_url = %s AND user_id = %s",
            (site_url, user_id),
        )
        result = cursor.fetchone()
        conn.close()

        schema_map_urls = []
        refresh_mode = "diff"  # Default

        if result and result[0]:
            # Use stored schema_map_url and refresh_mode from database
            stored_schema_map = result[0]
            stored_refresh_mode = result[1] if result[1] else "diff"
            refresh_mode = stored_refresh_mode
            logger.info(
                f"Using stored schema_map: {stored_schema_map}, refresh_mode: {refresh_mode}"
            )
            schema_map_urls = [stored_schema_map]
        else:
            # No stored schema_map, try discovery from robots.txt
            logger.debug(f"No stored schema_map, attempting discovery...")
            triples = get_schema_urls_from_robots(site_url)

            # Extract unique schema_map URLs
            schema_map_urls = list(set(schema_map for _, schema_map, _ in triples))

        if not schema_map_urls:
            logger.debug(f"No schema maps found for {site_url}")
            return 0  # No schema maps = no files queued

        logger.debug(f"Found {len(schema_map_urls)} schema map(s) for {site_url}")

        # For each schema map, use Level 2 logic to add it
        total_files = 0
        total_queued = 0
        for schema_map_url in schema_map_urls:
            logger.debug(f"Processing schema map: {schema_map_url}")
            files_added, files_queued = add_schema_map_to_site(
                site_url, user_id, schema_map_url, refresh_mode=refresh_mode
            )
            total_files += files_added
            total_queued += files_queued

        logger.info(
            f"Processed {site_url}: {total_files} files added, {total_queued} queued"
        )
        return total_queued

    except Exception as e:
        logger.exception(f"Unexpected error processing {site_url}: {e}")
        return None


# write_job function removed - now using queue interface

if __name__ == "__main__":
    # Simple command line interface
    import sys

    if len(sys.argv) != 2:
        print("Usage: python master.py <site_url>")
        sys.exit(1)
    process_site(sys.argv[1])
