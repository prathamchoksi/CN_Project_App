import logging
import os
import socket
import sys
import time
from flask import Flask, jsonify
import psycopg2
from psycopg2 import OperationalError, DatabaseError

# Configure unbuffered, standardized logging to stdout for container log collectors
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("k8s-self-healing-api")

app = Flask(__name__)

# Environment configuration with production-ready defaults
DB_HOST = os.getenv("DB_HOST", "db-service")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "appdb")
DB_USER = os.getenv("POSTGRES_USER", "postgres_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "rpi_secure_password_123")
POD_NAME = os.getenv("HOSTNAME", socket.gethostname())
NODE_NAME = os.getenv("NODE_NAME", "unknown-node")


def get_resilient_db_connection(
    max_retries: int = 5,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    connect_timeout: int = 3
):
    """
    Establishes a PostgreSQL connection wrapped in exponential backoff retry logic.
    Survives transient network blips and database restarts without terminating the app.
    """
    delay = initial_delay
    last_err = None

    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connect_timeout=connect_timeout
            )
            conn.autocommit = True
            return conn
        except (OperationalError, DatabaseError, Exception) as err:
            last_err = err
            if attempt < max_retries:
                logger.warning(
                    f"[NET-WARN] Database connection failed (attempt {attempt}/{max_retries}): {err}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                delay *= backoff_factor
            else:
                logger.error(
                    f"[NET-ERR] Database connection permanently failed after {max_retries} attempts: {err}"
                )

    raise last_err


def init_schema(conn):
    """
    Ensures the 'visits' counter table is initialized idempotently.
    Uses atomic counter row pattern for high performance and zero SD card bloat.
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS visits (
                id INT PRIMARY KEY,
                count BIGINT NOT NULL
            );
            INSERT INTO visits (id, count)
            VALUES (1, 0)
            ON CONFLICT (id) DO NOTHING;
        """)


@app.route("/", methods=["GET"])
def index():
    """
    Main endpoint:
    - Increments visits counter in PostgreSQL.
    - Captures query execution latency.
    - Returns pod identification and node location for visual proof of load balancing.
    """
    start_time = time.perf_counter()

    try:
        conn = get_resilient_db_connection(
            max_retries=5,
            initial_delay=1.0,
            backoff_factor=2.0,
            connect_timeout=3
        )
        try:
            init_schema(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE visits
                    SET count = count + 1
                    WHERE id = 1
                    RETURNING count;
                """)
                row = cur.fetchone()
                visit_count = int(row[0]) if row else 1
        finally:
            conn.close()

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return jsonify({
            "status": "success",
            "message": "Raspberry Pi K8s Self-Healing Test API",
            "pod_name": os.environ.get("HOSTNAME", POD_NAME),
            "node_name": os.environ.get("NODE_NAME", NODE_NAME),
            "total_database_visits": visit_count,
            "db_latency_ms": elapsed_ms
        }), 200

    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(f"[REQ-ERR] Error processing request on {POD_NAME}: {exc}")
        return jsonify({
            "status": "error",
            "message": "Database request failed after exponential retries",
            "pod_name": os.environ.get("HOSTNAME", POD_NAME),
            "node_name": os.environ.get("NODE_NAME", NODE_NAME),
            "error": str(exc),
            "db_latency_ms": elapsed_ms
        }), 503


@app.route("/healthz", methods=["GET"])
def liveness_probe():
    """
    Kubernetes Liveness Probe:
    Verifies that the web server process is responsive.
    External dependencies like the database are deliberately excluded here
    to prevent cascading restart storms when only the network is flapping.
    """
    return jsonify({"status": "alive"}), 200


@app.route("/ready", methods=["GET"])
def readiness_probe():
    """
    Kubernetes Readiness Probe:
    Executes a fast probe query ('SELECT 1;') against PostgreSQL.
    Returns HTTP 200 if connected.
    Returns HTTP 503 if unreachable so Kube-Proxy instantly stops routing traffic.
    """
    try:
        # Fast connection timeout (2s) to fail quickly without holding kubelet threads
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            connect_timeout=2
        )
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        conn.close()
        return jsonify({"status": "ready", "db": "connected"}), 200
    except Exception as exc:
        logger.warning(f"[PROBE-WARN] Readiness probe failed: {exc}")
        return jsonify({"status": "not_ready", "db": "unreachable"}), 503


if __name__ == "__main__":
    # Local development runner
    app.run(host="0.0.0.0", port=5000)

