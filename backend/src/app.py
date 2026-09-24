from flask import Flask, jsonify
from flask_cors import CORS

# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------
from src.config.db import init_db, get_db


# ---------------------------------------------------------
# TASK BLUEPRINTS
# ---------------------------------------------------------
from src.modules.tasks.repeat_until_done.routes import (
    repeat_until_done_task_bp
)
from src.modules.tasks.recurring.routes import (
    recurring_task_bp
)


# ---------------------------------------------------------
# DASHBOARD BLUEPRINT
# ---------------------------------------------------------
from src.modules.dashboard.routes import (
    dashboard_bp
)


# ---------------------------------------------------------
# ASSISTANT BLUEPRINT - Google Gemini
# ---------------------------------------------------------
from src.modules.assistant.routes import (
    assistant_bp
)


# ---------------------------------------------------------
# RECURRING BACKGROUND SCHEDULER
# ---------------------------------------------------------
from src.modules.tasks.recurring.scheduler import (
    start_recurring_scheduler
)


def create_app():
    """
    Flask application factory.

    Responsibilities:
        1. Create Flask app.
        2. Enable CORS.
        3. Initialize MongoDB.
        4. Register task APIs.
        5. Register Dashboard API.
        6. Register Assistant/LLM API.
        7. Start recurring lifecycle scheduler.
        8. Register health endpoints.
    """

    app = Flask(__name__)

    # Allow Flutter/web development clients to call Flask.
    CORS(app)

    # Initialize MongoDB using existing environment configuration.
    init_db()

    # -----------------------------------------------------
    # REGISTER FEATURE BLUEPRINTS
    # -----------------------------------------------------

    # /api/tasks/repeat-until-done
    app.register_blueprint(
        repeat_until_done_task_bp
    )

    # /api/tasks/recurring
    app.register_blueprint(
        recurring_task_bp
    )

    # /api/dashboard
    app.register_blueprint(
        dashboard_bp
    )

    # /api/assistant/providers
    # /api/assistant/health
    # /api/assistant/chat
    app.register_blueprint(
        assistant_bp
    )

    # Keep recurring lifecycle synchronization running.
    # Tests monkeypatch this so no real scheduler is started in pytest.
    start_recurring_scheduler()

    @app.route("/", methods=["GET"])
    def home():
        return jsonify({
            "success": True,
            "message": "AI Task Manager API is running."
        }), 200

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "success": True,
            "status": "healthy"
        }), 200

    @app.route("/health/database", methods=["GET"])
    def database_health():
        try:
            db = get_db()
            db.client.admin.command("ping")

            return jsonify({
                "success": True,
                "database": "connected"
            }), 200
        except Exception as error:
            return jsonify({
                "success": False,
                "database": "disconnected",
                "error": str(error)
            }), 500

    return app
