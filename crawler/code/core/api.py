import sys
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import db
from master import process_site
import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
import json
from get_queue import get_queue
import logging
import log

# Default user_id for all operations (auth handled at higher level)
DEFAULT_USER_ID = "system"

app = Flask(__name__, static_folder="static")
CORS(app)

# Global scheduler task
scheduler_task = None
scheduler_running = False
event_loop = None

# Track when master started
master_started_at = datetime.now(timezone.utc)

log.configure(os.environ)
# This is simply the API setup around the master, so use same logger.
logger = logging.getLogger("master")
logger_api = logging.getLogger("master.api")
logger_scheduler = logging.getLogger("master.scheduler")


# ========== Static Pages ==========


@app.route("/faq")
def faq_page():
    """Show FAQ page"""
    return send_from_directory("static", "faq.html")


@app.route("/api-docs")
def api_docs_page():
    """Show API documentation page"""
    return send_from_directory("static", "api-docs.html")


# Serve the frontend
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


# API Routes


@app.route("/api/sites", methods=["GET"])
def get_sites():
    """Get all sites with their status"""
    conn = db.get_connection()
    try:
        sites = db.get_all_sites(conn, DEFAULT_USER_ID)
        return jsonify(sites)
    finally:
        # Rollback any uncommitted transactions before closing
        try:
            conn.rollback()
        except:
            pass
        conn.close()


@app.route("/api/sites", methods=["POST"])
def add_site():
    """Add a new site to monitor"""
    try:
        data = request.json
        site_url = data.get("site_url")
        interval_hours = data.get("interval_hours", 720)
        refresh_mode = data.get("refresh_mode", "diff")

        if not site_url:
            return jsonify({"error": "site_url is required"}), 400

        # Validate refresh_mode
        if refresh_mode not in ["diff", "full"]:
            return jsonify({"error": "refresh_mode must be 'diff' or 'full'"}), 400

        # Normalize site URL
        site_url = db.normalize_site_url(site_url)

        conn = db.get_connection()
        try:
            db.add_site(conn, site_url, DEFAULT_USER_ID, interval_hours, refresh_mode=refresh_mode)
            # Process site immediately in background
            if event_loop:
                try:
                    asyncio.run_coroutine_threadsafe(
                        process_site_async(site_url, DEFAULT_USER_ID), event_loop
                    )
                except Exception as e:
                    logger_api.warning(
                        f"Could not start async processing for {site_url}: {e}"
                    )
            return jsonify({"success": True, "site_url": site_url})
        finally:
            conn.close()
    except Exception as e:
        logger_api.error(f"Error in add_site: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/sites/<path:site_url>", methods=["GET"])
def get_site_details(site_url):
    """Get detailed information about a specific site including files and vector DB count"""
    # Normalize site URL
    site_url = db.normalize_site_url(site_url)

    conn = db.get_connection()
    try:
        cursor = conn.cursor(as_dict=True)

        # Get all files for this site with their item counts
        cursor.execute(
            """
            SELECT
                f.url,
                f.last_read,
                f.status,
                COUNT(i.id) as item_count
            FROM files f
            LEFT JOIN ids i ON f.url = i.file_url
            WHERE f.site_url = %s
            GROUP BY f.url, f.last_read, f.status
            ORDER BY f.url
        """,
            (site_url,),
        )

        files = cursor.fetchall()

        # Get total vector DB count for this site
        try:
            from azure.search.documents import SearchClient
            from azure.core.credentials import AzureKeyCredential

            search_client = SearchClient(
                endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
                index_name=os.getenv("AZURE_SEARCH_INDEX_NAME", "crawler-vectors"),
                credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_KEY")),
            )

            results = search_client.search(
                "*", filter=f"site eq '{site_url}'", top=0, include_total_count=True
            )
            vector_db_count = results.get_count()
        except Exception as e:
            logger_api.error(f"Error getting vector DB count: {e}")
            vector_db_count = 0

        return jsonify(
            {"site_url": site_url, "files": files, "vector_db_count": vector_db_count}
        )
    finally:
        # Rollback any uncommitted transactions before closing
        try:
            conn.rollback()
        except:
            pass
        conn.close()


@app.route("/api/sites/<path:site_url>", methods=["DELETE"])
def delete_site(site_url):
    """Remove a site from monitoring by deleting all its schema_maps"""
    # Normalize site URL
    site_url = db.normalize_site_url(site_url)

    conn = db.get_connection()
    try:
        cursor = conn.cursor()

        # Get all unique schema_maps for this site (across all users)
        cursor.execute(
            """
            SELECT DISTINCT schema_map FROM files
            WHERE site_url = %s
        """,
            (site_url,),
        )
        schema_maps = [row[0] for row in cursor.fetchall()]

        # Delete each schema_map (queues removal jobs and deletes from DB)
        total_files_removed = 0
        for schema_map_url in schema_maps:
            files_removed = _delete_schema_map_internal(conn, site_url, schema_map_url)
            total_files_removed += files_removed

        # Finally delete the site itself (across all users)
        cursor.execute("DELETE FROM sites WHERE site_url = %s", (site_url,))
        conn.commit()
        conn.close()

        return jsonify(
            {
                "success": True,
                "schema_maps_removed": len(schema_maps),
                "files_queued_for_removal": total_files_removed,
            }
        )
    except Exception as e:
        # Rollback on error
        try:
            conn.rollback()
        except:
            pass
        conn.close()
        raise


def _delete_schema_map_internal(conn, site_url, schema_map_url):
    """Internal function to delete files for a schema_map and queue removal jobs (across all users)"""
    cursor = conn.cursor()

    # Get all files for this schema_map before deleting (include content_type)
    cursor.execute(
        """
        SELECT file_url, content_type FROM files
        WHERE site_url = %s AND schema_map = %s
    """,
        (site_url, schema_map_url),
    )
    files = cursor.fetchall()

    # Queue removal jobs for each file so workers can:
    # 1. Remove IDs from ids table
    # 2. Remove from vector DB
    # 3. Delete from files table
    queue = get_queue()
    for file_url, content_type in files:
        job = {
            "type": "process_removed_file",
            "site": site_url,
            "file_url": file_url,
            "user_id": DEFAULT_USER_ID,
        }
        if content_type:
            job["content_type"] = content_type
        queue.send_message(job)

    # NOTE: Do NOT delete from files or ids tables here - workers will do that when they process the jobs
    # This ensures proper ordering: ids deleted first, then vector DB cleaned, then files table cleaned

    return len(files)


@app.route("/api/sites/<path:site_url>/schema-files", methods=["POST"])
def add_schema_file(site_url):
    """Add a manual schema map to a specific site and extract all files from it"""
    from master import add_schema_map_to_site

    # Normalize site URL
    site_url = db.normalize_site_url(site_url)

    data = request.json
    schema_map_url = data.get("schema_map_url")
    refresh_mode = data.get("refresh_mode", "diff")  # Default to 'diff' mode

    if not schema_map_url:
        return jsonify({"error": "schema_map_url is required"}), 400

    # Validate refresh_mode
    if refresh_mode not in ["diff", "full"]:
        return jsonify({"error": "refresh_mode must be 'diff' or 'full'"}), 400

    try:
        # Use the Level 2 logic from master.py
        files_added, files_queued = add_schema_map_to_site(
            site_url, DEFAULT_USER_ID, schema_map_url, refresh_mode=refresh_mode
        )

        if files_queued == 0:
            return (
                jsonify(
                    {"error": "No schema files found or failed to fetch schema_map"}
                ),
                400,
            )

        return jsonify(
            {
                "success": True,
                "site_url": site_url,
                "schema_map_url": schema_map_url,
                "files_discovered": files_added,  # New files discovered
                "files_queued": files_queued,  # Total files queued for processing
                "files_queued": files_queued,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sites/<path:site_url>/schema-files", methods=["DELETE"])
def delete_schema_file(site_url):
    """Remove a schema map and all its files from a site"""
    # Normalize site URL
    site_url = db.normalize_site_url(site_url)

    data = request.json
    schema_map_url = data.get("schema_map_url")

    if not schema_map_url:
        return jsonify({"error": "schema_map_url is required"}), 400

    conn = db.get_connection()
    try:
        # Use the internal function to delete files and queue removal jobs
        files_removed = _delete_schema_map_internal(conn, site_url, schema_map_url)
        conn.commit()
        conn.close()

        return jsonify(
            {
                "success": True,
                "deleted_count": files_removed,
                "files_queued_for_removal": files_removed,
            }
        )
    except Exception as e:
        # Rollback on error
        try:
            conn.rollback()
        except:
            pass
        conn.close()
        raise


@app.route("/api/sites/<path:site_url>/vector-count", methods=["GET"])
def get_site_vector_count(site_url):
    """Get vector DB count for a site"""
    import urllib.parse

    site_url = urllib.parse.unquote(site_url)

    # Normalize site URL
    site_url = db.normalize_site_url(site_url)

    # Verify site exists
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT site_url FROM sites WHERE site_url = %s", (site_url,))
        if not cursor.fetchone():
            return jsonify({"error": "Site not found"}), 404
    finally:
        # Rollback any uncommitted transactions before closing
        try:
            conn.rollback()
        except:
            pass
        conn.close()

    # Get count from vector DB
    from vector_db import vector_db_count_by_site

    count = vector_db_count_by_site(site_url)

    return jsonify({"site_url": site_url, "count": count})


@app.route("/api/status", methods=["GET"])
def get_status():
    """Get overall system status"""
    conn = db.get_connection()
    try:
        sites_status = db.get_site_status(conn, DEFAULT_USER_ID)
        # Return object with master info and sites array
        return jsonify(
            {
                "master_started_at": master_started_at.isoformat(),
                "master_uptime_seconds": (
                    datetime.now(timezone.utc) - master_started_at
                ).total_seconds(),
                "sites": sites_status,
            }
        )
    finally:
        # Rollback any uncommitted transactions before closing
        try:
            conn.rollback()
        except:
            pass
        conn.close()


@app.route("/api/queue/status", methods=["GET"])
def get_queue_status():
    """Get queue processing status"""
    queue_type = os.getenv("QUEUE_TYPE", "file")

    status = {
        "queue_type": queue_type,
        "pending_jobs": 0,
        "processing_jobs": 0,
        "failed_jobs": 0,
        "jobs": [],
        "error": None,
    }

    try:
        if queue_type == "file":
            # File-based queue status
            queue_dir = os.getenv("QUEUE_DIR", "queue")
            status["queue_dir"] = queue_dir

            if os.path.exists(queue_dir):
                # Count pending jobs
                for filename in sorted(os.listdir(queue_dir), reverse=True):
                    if filename.startswith("job-") and filename.endswith(".json"):
                        status["pending_jobs"] += 1
                        # Read job details (limit to 20 most recent)
                        if (
                            len([j for j in status["jobs"] if j["status"] == "pending"])
                            < 20
                        ):
                            try:
                                with open(os.path.join(queue_dir, filename)) as f:
                                    job = json.load(f)
                                    status["jobs"].append(
                                        {
                                            "id": filename,
                                            "status": "pending",
                                            "type": job.get("type"),
                                            "site": job.get("site"),
                                            "file_url": job.get("file_url"),
                                            "queued_at": job.get("queued_at"),
                                        }
                                    )
                            except:
                                pass
                    elif filename.endswith(".processing"):
                        status["processing_jobs"] += 1
                        # Read job details
                        try:
                            filepath = os.path.join(queue_dir, filename)
                            mtime = os.path.getmtime(filepath)
                            age_seconds = int(time.time() - mtime)

                            with open(filepath) as f:
                                job = json.load(f)
                                status["jobs"].append(
                                    {
                                        "id": filename,
                                        "status": "processing",
                                        "type": job.get("type"),
                                        "site": job.get("site"),
                                        "file_url": job.get("file_url"),
                                        "queued_at": job.get("queued_at"),
                                        "processing_time": age_seconds,
                                    }
                                )
                        except:
                            pass

                # Count failed jobs
                error_dir = os.path.join(queue_dir, "errors")
                if os.path.exists(error_dir):
                    for filename in os.listdir(error_dir):
                        if filename.startswith("job-") or filename.startswith(
                            "failed-"
                        ):
                            status["failed_jobs"] += 1

        elif queue_type == "storage":
            # Azure Storage Queue status
            try:
                from azure.storage.queue import QueueServiceClient
                from azure.identity import DefaultAzureCredential

                storage_account = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
                queue_name = os.getenv("AZURE_STORAGE_QUEUE_NAME", "crawler-jobs")

                if not storage_account:
                    status["error"] = (
                        "Azure Storage Queue not configured (AZURE_STORAGE_ACCOUNT_NAME not set)"
                    )
                    return jsonify(status)

                # Use Azure AD authentication
                account_url = f"https://{storage_account}.queue.core.windows.net"
                credential = DefaultAzureCredential()
                service_client = QueueServiceClient(
                    account_url=account_url, credential=credential
                )
                queue_client = service_client.get_queue_client(queue_name)

                properties = queue_client.get_queue_properties()
                status["pending_jobs"] = properties.get("approximate_message_count", 0)

                # Peek at messages
                messages = queue_client.peek_messages(max_messages=20)
                for msg in messages:
                    try:
                        content = json.loads(msg.content)
                        status["jobs"].append(
                            {
                                "id": msg.id,
                                "status": "pending",
                                "type": content.get("type"),
                                "site": content.get("site"),
                                "file_url": content.get("file_url"),
                                "queued_at": content.get("queued_at"),
                                "inserted_on": (
                                    str(msg.inserted_on) if msg.inserted_on else None
                                ),
                            }
                        )
                    except:
                        pass
            except Exception as e:
                status["error"] = f"Error connecting to Storage Queue: {str(e)}"

    except Exception as e:
        status["error"] = f"Error getting queue status: {str(e)}"

    status["total_jobs"] = (
        status["pending_jobs"] + status["processing_jobs"] + status["failed_jobs"]
    )

    # Sort jobs by status (processing first, then pending)
    status["jobs"].sort(
        key=lambda x: (x["status"] != "processing", x.get("queued_at") or ""),
        reverse=True,
    )

    return jsonify(status)


@app.route("/api/process/<path:site_url>", methods=["POST"])
def trigger_process(site_url):
    """Manually trigger processing for a site"""
    # Normalize site URL
    site_url = db.normalize_site_url(site_url)

    try:
        # Process in background using asyncio
        if event_loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    process_site_async(site_url, DEFAULT_USER_ID), event_loop
                )
            except Exception as e:
                logger_api.warning(f"Could not trigger processing for {site_url}: {e}")
        else:
            logger_api.warning("Event loop not initialized")
        return jsonify(
            {"success": True, "message": f"Processing started for {site_url}"}
        )
    except Exception as e:
        logger_api.error(f"Error in trigger_process: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/scheduler/status", methods=["GET"])
def get_scheduler_status():
    """Get scheduler status"""
    global scheduler_task, scheduler_running

    is_running = scheduler_running and scheduler_task and not scheduler_task.done()

    return jsonify({"running": is_running, "check_interval_seconds": 300})


@app.route("/api/scheduler/start", methods=["POST"])
def start_scheduler_endpoint():
    """Start the scheduler"""
    start_scheduler()
    return jsonify({"success": True, "message": "Scheduler started"})


@app.route("/api/scheduler/stop", methods=["POST"])
def stop_scheduler_endpoint():
    """Stop the scheduler"""
    stop_scheduler()
    return jsonify({"success": True, "message": "Scheduler stopped"})


@app.route("/api/sites/<path:site_url>/files", methods=["GET"])
def get_site_files(site_url):
    """Get all files for a specific site"""
    # Normalize site URL
    site_url = db.normalize_site_url(site_url)

    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT file_url, schema_map, last_read_time, number_of_items, is_manual, is_active
            FROM files
            WHERE site_url = %s AND is_active = 1
            ORDER BY file_url
        """,
            (site_url,),
        )

        files = [
            {
                "file_url": row[0],
                "schema_map": row[1],
                "last_read_time": row[2].isoformat() if row[2] else None,
                "number_of_items": row[3],
                "is_manual": bool(row[4]),
                "is_active": bool(row[5]),
            }
            for row in cursor.fetchall()
        ]
        return jsonify(files)
    finally:
        # Rollback any uncommitted transactions before closing
        try:
            conn.rollback()
        except:
            pass
        conn.close()


@app.route("/api/files", methods=["GET"])
def get_all_files():
    """Get all files from the database with their IDs"""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT f.site_url, f.file_url, f.schema_map, f.is_active, f.is_manual,
                   f.number_of_items, f.last_read_time,
                   COUNT(DISTINCT i.id) as id_count
            FROM files f
            LEFT JOIN ids i ON f.file_url = i.file_url
            GROUP BY f.site_url, f.file_url, f.schema_map, f.is_active, f.is_manual,
                     f.number_of_items, f.last_read_time
            ORDER BY f.site_url, f.file_url
        """
        )

        files = [
            {
                "site_url": row[0],
                "file_url": row[1],
                "schema_map": row[2],
                "is_active": bool(row[3]),
                "is_manual": bool(row[4]),
                "number_of_items": row[5],
                "last_read_time": row[6].isoformat() if row[6] else None,
                "id_count": row[7],
            }
            for row in cursor.fetchall()
        ]
        return jsonify(files)
    finally:
        # Rollback any uncommitted transactions before closing
        try:
            conn.rollback()
        except:
            pass
        conn.close()


@app.route("/api/files/<path:file_url>/ids", methods=["GET"])
def get_file_ids(file_url):
    """Get all IDs for a specific file"""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id
            FROM ids
            WHERE file_url = %s
            ORDER BY id
        """,
            (file_url,),
        )

        ids = [row[0] for row in cursor.fetchall()]
        return jsonify({"file_url": file_url, "ids": ids, "count": len(ids)})
    finally:
        # Rollback any uncommitted transactions before closing
        try:
            conn.rollback()
        except:
            pass
        conn.close()


@app.route("/api/files/<path:file_url>/details", methods=["GET"])
def get_file_details(file_url):
    """Get detailed information about a file including errors"""
    conn = db.get_connection()
    try:
        cursor = conn.cursor(as_dict=True)

        # Get file info
        cursor.execute(
            """
            SELECT file_url, site_url, schema_map, last_read_time, number_of_items, is_active
            FROM files
            WHERE file_url = %s
        """,
            (file_url,),
        )
        file_info = cursor.fetchone()

        if not file_info:
            return jsonify({"error": "File not found"}), 404

        # Get error history
        errors = db.get_file_errors(conn, file_url, limit=50)

        # Get ID count
        cursor.execute(
            """
            SELECT COUNT(*) as id_count
            FROM ids
            WHERE file_url = %s
        """,
            (file_url,),
        )
        id_count = cursor.fetchone()["id_count"]

        return jsonify(
            {
                "file_url": file_url,
                "site_url": file_info["site_url"],
                "schema_map": file_info["schema_map"],
                "last_read_time": (
                    file_info["last_read_time"].isoformat()
                    if file_info["last_read_time"]
                    else None
                ),
                "number_of_items": file_info["number_of_items"] or id_count,
                "id_count": id_count,
                "is_active": file_info["is_active"],
                "errors": errors,
            }
        )
    finally:
        # Rollback any uncommitted transactions before closing
        try:
            conn.rollback()
        except:
            pass
        conn.close()


@app.route("/api/queue/history", methods=["GET"])
def get_queue_history():
    """Get queue history from log file"""
    import os

    QUEUE_LOG_FILE = "/app/data/queue_history.jsonl"

    try:
        if not os.path.exists(QUEUE_LOG_FILE):
            return jsonify([])

        # Read last 1000 lines
        history = []
        with open(QUEUE_LOG_FILE, "r") as f:
            lines = f.readlines()
            for line in lines[-1000:]:
                try:
                    history.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue

        # Return in reverse chronological order (newest first)
        return jsonify(list(reversed(history)))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/fetch-log", methods=["GET"])
def get_fetch_log():
    """Get URL fetch log from workers"""
    import os

    FETCH_LOG_FILE = "/app/data/fetch_log.jsonl"

    try:
        if not os.path.exists(FETCH_LOG_FILE):
            return jsonify([])

        # Read last 1000 lines
        log_entries = []
        with open(FETCH_LOG_FILE, "r") as f:
            lines = f.readlines()
            for line in lines[-1000:]:
                try:
                    log_entries.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue

        # Return in reverse chronological order (newest first)
        return jsonify(list(reversed(log_entries)))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _can_resolve_host(hostname):
    """Check if a hostname resolves (for Docker DNS detection)"""
    import socket

    try:
        socket.gethostbyname(hostname)
        return True
    except socket.gaierror:
        return False


def _detect_worker_environment():
    """Detect which environment we're running in for worker discovery"""
    # Kubernetes: service account token exists
    if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token"):
        return "kubernetes"
    # Docker Compose: DOCKER_COMPOSE env var or can resolve 'worker' hostname
    if os.getenv("DOCKER_COMPOSE") or _can_resolve_host("worker"):
        return "docker-compose"
    # Local dev
    return "local"


def _get_workers_kubernetes():
    """Discover workers in Kubernetes environment"""
    import requests as req

    # Use Kubernetes API from within the cluster
    # Service account token and CA cert are automatically mounted
    k8s_host = os.getenv("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
    k8s_port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
    namespace = "crawler"

    # Read service account token
    with open("/var/run/secrets/kubernetes.io/serviceaccount/token", "r") as f:
        token = f.read()

    # API endpoint to list pods with label selector
    url = f"https://{k8s_host}:{k8s_port}/api/v1/namespaces/{namespace}/pods?labelSelector=app=crawler-worker"

    headers = {"Authorization": f"Bearer {token}"}

    # Get pods from Kubernetes API
    response = req.get(
        url,
        headers=headers,
        verify="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
        timeout=10,
    )

    if response.status_code != 200:
        return (
            jsonify(
                {
                    "error": "Failed to get worker pods from Kubernetes API",
                    "status": response.status_code,
                }
            ),
            500,
        )

    pods_data = response.json()
    workers = []

    for pod in pods_data.get("items", []):
        pod_name = pod["metadata"]["name"]
        pod_ip = pod["status"].get("podIP", "N/A")
        phase = pod["status"].get("phase", "Unknown")

        worker_info = {
            "name": pod_name,
            "ip": pod_ip,
            "phase": phase,
            "status": None,
            "error": None,
        }

        # Try to fetch status from worker if it's running
        if phase == "Running" and pod_ip and pod_ip != "N/A":
            try:
                status_response = req.get(f"http://{pod_ip}:8080/status", timeout=2)
                if status_response.status_code == 200:
                    worker_info["status"] = status_response.json()
            except Exception as e:
                worker_info["error"] = str(e)

        workers.append(worker_info)

    return jsonify({"workers": workers, "environment": "kubernetes"})


def _get_workers_docker_compose():
    """Discover workers in Docker Compose environment"""
    import requests as req

    workers = []
    seen_worker_ids = set()

    # Docker Compose with deploy.replicas creates containers like:
    # crawler-worker-1, crawler-worker-2, etc. (project name prefix)
    # Or just worker-1, worker-2 depending on configuration

    # Try the base 'worker' service first (handles single replica or round-robin)
    try:
        response = req.get("http://worker:8080/status", timeout=2)
        if response.status_code == 200:
            worker_status = response.json()
            worker_id = worker_status.get("worker_id", "worker")
            if worker_id not in seen_worker_ids:
                seen_worker_ids.add(worker_id)
                workers.append(
                    {
                        "name": worker_id,
                        "ip": "worker",
                        "phase": "Running",
                        "status": worker_status,
                        "error": None,
                    }
                )
    except Exception:
        pass

    # Try numbered workers (for scaled deployments)
    for i in range(1, 11):  # Try up to 10 workers
        for hostname in [f"crawler-worker-{i}", f"worker-{i}"]:
            try:
                response = req.get(f"http://{hostname}:8080/status", timeout=1)
                if response.status_code == 200:
                    worker_status = response.json()
                    worker_id = worker_status.get("worker_id", hostname)
                    if worker_id not in seen_worker_ids:
                        seen_worker_ids.add(worker_id)
                        workers.append(
                            {
                                "name": worker_id,
                                "ip": hostname,
                                "phase": "Running",
                                "status": worker_status,
                                "error": None,
                            }
                        )
                    break  # Found this index, move to next
            except Exception:
                continue

    return jsonify({"workers": workers, "environment": "docker-compose"})


@app.route("/api/workers", methods=["GET"])
def get_workers():
    """Get all worker pods/containers and their status"""
    try:
        env = _detect_worker_environment()

        if env == "kubernetes":
            return _get_workers_kubernetes()
        elif env == "docker-compose":
            return _get_workers_docker_compose()
        else:
            return jsonify(
                {
                    "workers": [],
                    "environment": "local",
                    "message": "Worker discovery not available in local dev mode. Run workers manually with make dev-worker.",
                }
            )
    except Exception as e:
        import traceback

        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


async def process_site_async(site_url, user_id):
    """Async wrapper for process_site function

    Returns: Number of files queued (int), or None on error
    """
    try:
        # Run process_site in a thread pool to avoid blocking the event loop
        files_queued = await asyncio.get_event_loop().run_in_executor(
            None, process_site, site_url, user_id
        )
        return files_queued
    except Exception as e:
        logger.error(f"Error processing site {site_url}: {e}")
        return None


async def scheduler_loop():
    """Background scheduler that periodically checks sites for reprocessing"""
    global scheduler_running

    logger_scheduler.info("Started background scheduler")

    while scheduler_running:
        try:
            conn = db.get_connection()
            cursor = conn.cursor()

            # Get sites that need reprocessing (with user_id)
            # Check sites where last_processed + interval_hours < now OR never processed
            cursor.execute(
                """
                SELECT site_url, user_id, process_interval_hours, last_processed
                FROM sites
                WHERE is_active = 1
                  AND (
                    last_processed IS NULL
                    OR DATEADD(hour, process_interval_hours, last_processed) <= GETUTCDATE()
                  )
            """
            )

            sites_to_process = cursor.fetchall()

            # Close connection immediately after query - don't hold during async processing
            conn.close()
            logger_scheduler.debug("Closed scheduler database connection")

            if sites_to_process:
                logger_scheduler.info(f"Found {len(sites_to_process)} sites to process")

                # Create tasks for all sites to process concurrently
                tasks = []
                for (
                    site_url,
                    user_id,
                    interval_hours,
                    last_processed,
                ) in sites_to_process:
                    if last_processed:
                        time_since = datetime.now(timezone.utc) - last_processed
                        logger_scheduler.info(
                            f"Processing {site_url} for user {user_id} (last processed {time_since} ago)"
                        )
                    else:
                        logger_scheduler.info(
                            f"Processing {site_url} for user {user_id} (never processed before)"
                        )

                    # Add to task list for concurrent processing
                    tasks.append(process_site_async(site_url, user_id))

                # Process all sites concurrently
                if tasks:
                    # Use return_exceptions=True to prevent one site error from killing all
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for i, result in enumerate(results):
                        site_url, user_id = sites_to_process[i][0], sites_to_process[i][1]
                        if isinstance(result, Exception):
                            logger_scheduler.error(
                                f"Error processing site {site_url}: {result}"
                            )
                        elif result is None:
                            # Error occurred (process_site returned None)
                            logger_scheduler.error(
                                f"Failed to process site {site_url}"
                            )
                        elif result == 0:
                            # Successfully processed but 0 files queued
                            # Update last_processed since no workers will run
                            try:
                                update_conn = db.get_connection()
                                update_cursor = update_conn.cursor()
                                update_cursor.execute(
                                    "UPDATE sites SET last_processed = GETUTCDATE() WHERE site_url = %s AND user_id = %s",
                                    (site_url, user_id)
                                )
                                update_conn.commit()
                                update_conn.close()
                                logger_scheduler.info(f"Updated last_processed for {site_url} (0 files queued, no workers will run)")
                            except Exception as e:
                                logger_scheduler.error(f"Failed to update last_processed for {site_url}: {e}")
                        else:
                            # Successfully queued files (result > 0)
                            # Workers will update last_processed as they process files
                            logger_scheduler.info(f"Queued {result} files for {site_url} - workers will update last_processed")

        except Exception as e:
            logger_scheduler.error(f"Error in scheduler loop: {e}")
            # Try to close connection if it exists and wasn't closed yet
            try:
                if "conn" in locals() and conn:
                    conn.close()
            except:
                pass

        # Sleep for 5 minutes between checks
        await asyncio.sleep(300)

    logger_scheduler.info("Scheduler stopped")


def start_scheduler():
    """Start the background scheduler task"""
    global scheduler_task, scheduler_running, event_loop

    if scheduler_task and not scheduler_task.done():
        logger_scheduler.warning("Already running")
        return

    scheduler_running = True
    if event_loop:
        scheduler_task = asyncio.run_coroutine_threadsafe(scheduler_loop(), event_loop)
        logger_scheduler.info("Starting background scheduler task")


def stop_scheduler():
    """Stop the background scheduler task"""
    global scheduler_running, scheduler_task
    scheduler_running = False
    logger_scheduler.info("Stopping scheduler...")
    if scheduler_task:
        scheduler_task.cancel()


def run_event_loop():
    """Run the asyncio event loop in a separate thread"""
    global event_loop
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    event_loop.run_forever()


if __name__ == "__main__":
    logger_startup = logging.getLogger("master.startup")
    logger_startup.setLevel(log.level(os.environ))

    # Ensure database tables exist
    logger_startup.info("Testing database connection...")
    conn = db.get_connection()
    try:
        db.create_tables(conn)
        logger_startup.info("✓ Database tables verified")
    except Exception as e:
        logger_startup.warning(
            f"Note: Table creation skipped (tables likely exist): {e}"
        )

    # Ensure system user exists for default operations
    try:
        db.ensure_system_user(conn)
        logger_startup.info("✓ System user verified")
    except Exception as e:
        logger_startup.warning(f"Warning: Could not ensure system user: {e}")

    conn.close()
    logger_startup.info("✓ Database connection successful")

    # Test Queue connectivity
    queue_type = os.getenv("QUEUE_TYPE", "file")
    if queue_type == "storage":
        print("[STARTUP] Testing Storage Queue connection...")
        try:
            from azure.storage.queue import QueueServiceClient
            from azure.identity import DefaultAzureCredential

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

    # Start asyncio event loop in background
    import threading

    loop_thread = threading.Thread(target=run_event_loop, daemon=True)
    loop_thread.start()

    # Wait a moment for the event loop to start
    time.sleep(0.5)

    # Start the scheduler
    start_scheduler()

    # Run the Flask app (use 5001 to avoid macOS AirPlay conflict)
    port = int(os.getenv("API_PORT", 5001))

    try:
        app.run(
            host="0.0.0.0", port=port, debug=False
        )  # debug=False to avoid duplicate scheduler
    finally:
        stop_scheduler()
        if event_loop:
            event_loop.call_soon_threadsafe(event_loop.stop)
