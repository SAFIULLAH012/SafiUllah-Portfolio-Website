"""
Admin blueprint — CMS routes for authenticated admin users.
Every route is protected by the @login_required decorator.
"""
from flask import Blueprint

admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="../../templates/admin",
)

from blueprints.admin import routes  # noqa: E402, F401
