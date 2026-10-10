"""
SQLAlchemy database models for Portfolio CMS.
All models include timestamps and appropriate constraints.
"""
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────────────────────────────────────
# Admin User
# ─────────────────────────────────────────────────────────────────────────────
class Admin(db.Model):
    __tablename__ = "admin"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    failed_logins = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)

    def set_password(self, password: str) -> None:
        """Hash and store password — plaintext never persisted."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        return check_password_hash(self.password_hash, password)

    def is_locked(self) -> bool:
        """Check if account is temporarily locked due to failed logins."""
        if self.locked_until and self.locked_until > utcnow():
            return True
        return False

    def record_failed_login(self) -> None:
        """Increment failed logins and lock account if limit exceeded (5 attempts)."""
        self.failed_logins += 1
        if self.failed_logins >= 5:
            from datetime import timedelta
            self.locked_until = utcnow() + timedelta(minutes=15)
        db.session.commit()

    def reset_failed_logins(self) -> None:
        """Reset failed login count upon successful authentication."""
        self.failed_logins = 0
        self.locked_until = None
        db.session.commit()

    def __repr__(self):
        return f"<Admin {self.username}>"


# ─────────────────────────────────────────────────────────────────────────────
# Admin OTP (One-Time Passwords for Security & Verification)
# ─────────────────────────────────────────────────────────────────────────────
import secrets
from datetime import timedelta

class AdminOTP(db.Model):
    __tablename__ = "admin_otp"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admin.id"), nullable=False)
    otp_code = db.Column(db.String(6), nullable=False)
    purpose = db.Column(db.String(32), nullable=False)  # 'change_credentials' or 'forgot_password'
    created_at = db.Column(db.DateTime, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)

    admin = db.relationship("Admin", backref=db.backref("otps", lazy=True))

    @classmethod
    def generate_otp(cls, admin_id: int, purpose: str, valid_minutes: int = 10) -> str:
        """Invalidate existing unused OTPs and generate a fresh 6-digit code."""
        cls.query.filter_by(admin_id=admin_id, purpose=purpose, is_used=False).update({"is_used": True})
        
        code = f"{secrets.randbelow(900000) + 100000}"
        now = utcnow()
        expires = now + timedelta(minutes=valid_minutes)
        otp = cls(
            admin_id=admin_id,
            otp_code=code,
            purpose=purpose,
            created_at=now,
            expires_at=expires,
            is_used=False,
        )
        db.session.add(otp)
        db.session.commit()
        return code

    @classmethod
    def verify_otp(cls, admin_id: int, code: str, purpose: str) -> bool:
        """Verify code against database, checking expiration and single-use flag."""
        now = utcnow()
        otp = cls.query.filter(
            cls.admin_id == admin_id,
            cls.otp_code == str(code).strip(),
            cls.purpose == purpose,
            cls.is_used == False,
            cls.expires_at > now,
        ).first()
        if otp:
            otp.is_used = True
            db.session.commit()
            return True
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Project
# ─────────────────────────────────────────────────────────────────────────────
class Project(db.Model):
    __tablename__ = "project"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
    short_description = db.Column(db.String(400), nullable=False, default="")
    description = db.Column(db.Text, default="")
    problem_statement = db.Column(db.Text, default="")
    category = db.Column(db.String(100), default="Machine Learning")

    # Media
    image = db.Column(db.String(300), default="")
    github_url = db.Column(db.String(300), default="")
    demo_url = db.Column(db.String(300), default="")

    # ML Details (stored as JSON strings)
    dataset = db.Column(db.Text, default="")
    model_architecture = db.Column(db.Text, default="")
    preprocessing = db.Column(db.Text, default="")
    metrics = db.Column(db.Text, default="{}")          # JSON: {"accuracy": ..., "f1": ...}
    technologies = db.Column(db.Text, default="[]")     # JSON: ["TensorFlow", "Flask"]
    results = db.Column(db.Text, default="")
    limitations = db.Column(db.Text, default="")
    future_improvements = db.Column(db.Text, default="")

    # Display control
    featured = db.Column(db.Boolean, default=False, nullable=False)
    published = db.Column(db.Boolean, default=False, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self):
        return f"<Project {self.slug}>"


# ─────────────────────────────────────────────────────────────────────────────
# Skill
# ─────────────────────────────────────────────────────────────────────────────
class Skill(db.Model):
    __tablename__ = "skill"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(100), default="General")   # e.g., "Computer Vision"
    proficiency = db.Column(db.Integer, default=80)            # 0-100 percentage
    icon_class = db.Column(db.String(100), default="fas fa-code")
    tags = db.Column(db.Text, default="[]")                    # JSON list of tag strings
    display_order = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<Skill {self.name}>"


# ─────────────────────────────────────────────────────────────────────────────
# Education
# ─────────────────────────────────────────────────────────────────────────────
class Education(db.Model):
    __tablename__ = "education"

    id = db.Column(db.Integer, primary_key=True)
    institution = db.Column(db.String(200), nullable=False)
    degree = db.Column(db.String(200), nullable=False)
    level = db.Column(db.String(100), default="")         # e.g., "Matric", "ICS", "BSc"
    start_year = db.Column(db.String(10), default="")
    end_year = db.Column(db.String(10), default="")
    score = db.Column(db.String(50), default="")           # CGPA / marks
    score_label = db.Column(db.String(30), default="Score")
    description = db.Column(db.Text, default="")
    display_order = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<Education {self.degree} @ {self.institution}>"


# ─────────────────────────────────────────────────────────────────────────────
# Experience
# ─────────────────────────────────────────────────────────────────────────────
class Experience(db.Model):
    __tablename__ = "experience"

    id = db.Column(db.Integer, primary_key=True)
    company = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.String(20), default="")
    end_date = db.Column(db.String(20), default="Present")
    description = db.Column(db.Text, default="")
    technologies = db.Column(db.Text, default="[]")   # JSON list
    display_order = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<Experience {self.role} @ {self.company}>"


# ─────────────────────────────────────────────────────────────────────────────
# Certification
# ─────────────────────────────────────────────────────────────────────────────
class Certification(db.Model):
    __tablename__ = "certification"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    issuer = db.Column(db.String(200), nullable=False)
    issue_date = db.Column(db.String(30), default="")
    credential_url = db.Column(db.String(300), default="")
    image = db.Column(db.String(300), default="")
    display_order = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<Certification {self.title}>"


# ─────────────────────────────────────────────────────────────────────────────
# Contact Message
# ─────────────────────────────────────────────────────────────────────────────
class Message(db.Model):
    __tablename__ = "message"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    ip_address = db.Column(db.String(45), default="")   # IPv4/IPv6
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    def __repr__(self):
        return f"<Message from {self.email}>"


# ─────────────────────────────────────────────────────────────────────────────
# Site Settings (singleton row — id=1)
# ─────────────────────────────────────────────────────────────────────────────
class SiteSettings(db.Model):
    __tablename__ = "site_settings"

    id = db.Column(db.Integer, primary_key=True)

    # Profile / About
    name = db.Column(db.String(100), default="Safi Ullah")
    headline = db.Column(db.String(200), default="AI & Machine Learning Engineer")
    bio = db.Column(db.Text, default="")
    profile_image = db.Column(db.String(300), default="img/safiullah_profile.jpeg")
    location = db.Column(db.String(100), default="Pakistan")
    contact_email = db.Column(db.String(120), default="")
    availability = db.Column(db.String(100), default="Open for Opportunities")

    # Social Links
    github_url = db.Column(db.String(300), default="")
    linkedin_url = db.Column(db.String(300), default="")
    whatsapp_number = db.Column(db.String(50), default="923477845540")
    resume_url = db.Column(db.String(300), default="cv/safi_ullah_cv.pdf")

    # SEO
    site_title = db.Column(db.String(200), default="Safi Ullah | AI & Machine Learning Engineer")
    meta_description = db.Column(db.Text, default="")

    # Hero Content
    hero_description = db.Column(db.Text, default="")
    # JSON list of strings — the 3 role pills shown in the hero section
    hero_tags = db.Column(db.Text, default='["AI & Machine Learning Engineer", "Computer Vision & MediaPipe", "Deep Learning & CNN"]')

    # About Section
    about_domain = db.Column(db.String(100), default="AI / ML / Computer Vision")
    # JSON list of strings — the "Why Work With Me" capability bullets
    why_work_with_me = db.Column(db.Text, default='["Custom Deep Learning & CNN Architecture Engineering", "Real-Time Computer Vision (ALPR, Hand Tracking, Face Mesh)", "End-to-End Machine Learning & Predictive Analytics Pipelines", "Web API Deployment with Flask & Streamlit"]')
    # The number shown on the projects badge (e.g. "7+")
    projects_badge_count = db.Column(db.String(10), default="7+")
    # The GitHub @handle displayed in the contact section
    github_handle = db.Column(db.String(100), default="@SAFIULLAH012")

    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self):
        return f"<SiteSettings id={self.id}>"


# Alias for backward compatibility
Settings = SiteSettings
