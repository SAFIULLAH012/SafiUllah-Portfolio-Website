"""
Flask extensions — instantiated here and imported from app factory.
This avoids circular imports between app, models, and blueprints.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
csrf = CSRFProtect()
mail = Mail()
limiter = Limiter(key_func=get_remote_address)
