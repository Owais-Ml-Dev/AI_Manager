"""
HTTP controller for the Dashboard feature.
"""

from flask import jsonify

from src.modules.dashboard.service import (
    get_dashboard,
)


def get_dashboard_controller():
    """
    Return all data required by the Dashboard screen.
    """

    data = get_dashboard()

    return jsonify({
        "success": True,
        "data": data
    }), 200
