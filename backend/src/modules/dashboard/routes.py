"""
Dashboard routes.
"""

from flask import Blueprint

from src.modules.dashboard.controller import (
    get_dashboard_controller,
)


dashboard_bp = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/api/dashboard"
)


dashboard_bp.route(
    "",
    methods=["GET"]
)(
    get_dashboard_controller
)
