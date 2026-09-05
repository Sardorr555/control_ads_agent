"""
Isolated High-Throughput Flask Ingestion Service for Traffic Attribution (Track 3).
Listens on 127.0.0.1:5001, isolated from core payment processing (port 5000).
"""
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Union
from flask import Flask, request, jsonify, make_response
from pydantic import ValidationError

from .models.events import RawTrafficEventDTO
from .storage.sqlite_events_repo import SQLiteEventsRepo
from .core.anonymizer import anonymize_request

logger = logging.getLogger("swipies.tracker_service")


def create_app(db_path: str = None, base_salt: str = None) -> Flask:
    app = Flask(__name__)

    actual_db_path = db_path or os.getenv("ATTRIBUTION_DB_PATH", "./data/attribution_events.db")
    actual_salt = base_salt or os.getenv(
        "ATTRIBUTION_SALT",
        "default_track3_salt_min_32_chars_long_entropy_value_2026"
    )

    repo = SQLiteEventsRepo(actual_db_path)
    app.config["REPO"] = repo
    app.config["BASE_SALT"] = actual_salt

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    @app.route("/api/v1/track/health", methods=["GET"])
    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({
            "status": "healthy",
            "service": "swipies-tracker",
            "port": 5001,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200

    @app.route("/api/v1/track/event", methods=["OPTIONS"])
    @app.route("/event", methods=["OPTIONS"])
    def options_track_event():
        resp = make_response("", 204)
        return resp

    @app.route("/api/v1/track/event", methods=["POST"])
    @app.route("/event", methods=["POST"])
    def track_event():
        """
        Ingestion endpoint for client events (pageview, heartbeat, leave, conversion).
        Supports single JSON object or batch array of events.
        """
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({"error": "Invalid or missing JSON payload"}), 400

        # Anonymize client IP on the fly
        anon = anonymize_request(
            headers=dict(request.headers),
            remote_addr=request.remote_addr or "127.0.0.1",
            base_salt=app.config["BASE_SALT"]
        )

        events_data: List[Dict[str, Any]] = payload if isinstance(payload, list) else [payload]
        saved_count = 0
        validation_errors = []

        for item in events_data:
            if not isinstance(item, dict):
                validation_errors.append("Event must be a JSON object")
                continue
            try:
                dto = RawTrafficEventDTO(
                    ip_hash=anon["ip_hash"],
                    country=anon["country"],
                    city=anon["city"],
                    **item
                )
                repo.save_raw_event(dto)
                saved_count += 1
            except ValidationError as ve:
                validation_errors.append(str(ve))
            except Exception as e:
                logger.error(f"[TrackerService] Storage error: {e}", exc_info=True)
                validation_errors.append(str(e))

        if saved_count == 0 and validation_errors:
            return jsonify({
                "success": False,
                "saved": 0,
                "errors": validation_errors
            }), 400

        return jsonify({
            "success": True,
            "saved": saved_count,
            "errors_count": len(validation_errors)
        }), 200

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5001, debug=False)
