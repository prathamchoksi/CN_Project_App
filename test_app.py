"""
Unit tests for the resilient 2-tier Kubernetes API service.
Validates:
1. /healthz Liveness Probe
2. /ready Readiness Probe (success and failure modes)
3. / Main Endpoint (counter increment, exponential backoff retries, and permanent failure)
"""

import os
import unittest
from unittest.mock import patch, MagicMock
from psycopg2 import OperationalError

# Set test environment variables before importing app
os.environ["DB_HOST"] = "test-db"
os.environ["DB_PORT"] = "5432"
os.environ["POSTGRES_DB"] = "testdb"
os.environ["POSTGRES_USER"] = "testuser"
os.environ["POSTGRES_PASSWORD"] = "testpass"
os.environ["HOSTNAME"] = "backend-test-pod-123"
os.environ["NODE_NAME"] = "rpi-worker-node-1"

import app as api_module


class TestResilientK8sApp(unittest.TestCase):

    def setUp(self):
        self.app = api_module.app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    # --------------------------------------------------------------------------
    # 1. Liveness Probe Test
    # --------------------------------------------------------------------------
    def test_liveness_probe_always_alive(self):
        """Liveness probe must return 200 without touching external dependencies."""
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {"status": "alive"})

    # --------------------------------------------------------------------------
    # 2. Readiness Probe Tests
    # --------------------------------------------------------------------------
    @patch("psycopg2.connect")
    def test_readiness_probe_success(self, mock_connect):
        """Readiness probe must return 200 when SELECT 1 succeeds."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {"status": "ready", "db": "connected"})
        mock_connect.assert_called_once()

    @patch("psycopg2.connect")
    def test_readiness_probe_failure_stops_traffic(self, mock_connect):
        """Readiness probe must return 503 when DB network fails."""
        mock_connect.side_effect = OperationalError("connection refused")

        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 503)
        data = response.get_json()
        self.assertEqual(data, {"status": "not_ready", "db": "unreachable"})

    # --------------------------------------------------------------------------
    # 3. Main Endpoint Tests & Reconnection Logic
    # --------------------------------------------------------------------------
    @patch("app.get_resilient_db_connection")
    def test_index_endpoint_success(self, mock_get_conn):
        """Main endpoint increments counter and reports pod/node metadata."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (42,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["pod_name"], "backend-test-pod-123")
        self.assertEqual(data["node_name"], "rpi-worker-node-1")
        self.assertEqual(data["total_database_visits"], 42)
        self.assertIn("db_latency_ms", data)
        self.assertIsInstance(data["db_latency_ms"], float)

    @patch("time.sleep")
    @patch("psycopg2.connect")
    def test_exponential_backoff_transient_recovery(self, mock_connect, mock_sleep):
        """
        Simulate 2 transient network failures followed by a successful 3rd attempt.
        Verifies exponential backoff delays and successful recovery.
        """
        mock_conn = MagicMock()
        # Fail twice with network error, succeed on 3rd attempt
        mock_connect.side_effect = [
            OperationalError("network glitch 1"),
            OperationalError("network glitch 2"),
            mock_conn
        ]

        conn = api_module.get_resilient_db_connection(
            max_retries=5,
            initial_delay=0.1,
            backoff_factor=2.0
        )

        self.assertEqual(conn, mock_conn)
        self.assertEqual(mock_connect.call_count, 3)
        # Verify exponential backoff intervals
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_any_call(0.1)
        mock_sleep.assert_any_call(0.2)

    @patch("time.sleep")
    @patch("psycopg2.connect")
    def test_permanent_network_failure_handling(self, mock_connect, mock_sleep):
        """Simulate permanent network failure exhausting all retries."""
        mock_connect.side_effect = OperationalError("host unreachable")

        with self.assertRaises(OperationalError):
            api_module.get_resilient_db_connection(
                max_retries=3,
                initial_delay=0.01,
                backoff_factor=2.0
            )

        self.assertEqual(mock_connect.call_count, 3)


if __name__ == "__main__":
    unittest.main()

