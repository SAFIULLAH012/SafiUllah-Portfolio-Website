"""
Public blueprint — public-facing portfolio routes.
"""
from flask import Blueprint

public_bp = Blueprint(
    "public",
    __name__,
    template_folder="../../templates",
)

from blueprints.public import routes  # noqa: E402, F401
