import os

import psycopg2
from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/")
def index():
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "db-service"),
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.getenv("POSTGRES_DB", "appdb"),
            user=os.getenv("POSTGRES_USER", "postgres_user"),
            password=os.getenv("POSTGRES_PASSWORD", "password"),
            connect_timeout=3,
        )
        with conn, conn.cursor() as cur:
            cur.execute("SELECT value FROM message WHERE id = 1;")
            value = cur.fetchone()[0]
        conn.close()
        return jsonify({"value": value}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
