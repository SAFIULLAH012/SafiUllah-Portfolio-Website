"""
Admin CMS blueprint routes.
All routes except /admin/login require an authenticated session.
"""
import json
import logging
import re
from datetime import datetime, timezone
from functools import wraps

from flask import (
    render_template, request, redirect, url_for,
    session, flash, jsonify, abort, current_app,
)
from werkzeug.utils import secure_filename

from blueprints.admin import admin_bp
from extensions import db, limiter
from models import (
    Admin, AdminOTP, Project, Skill, Education, Experience,
    Certification, Message, SiteSettings,
)
from utils.security import validate_and_save_image, validate_and_save_pdf, send_otp_email

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Auth Helpers
# ─────────────────────────────────────────────────────────────────────────────
def login_required(f):
    """Decorator: redirect unauthenticated requests to admin login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_id"):
            flash("Please log in to access the admin panel.", "warning")
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated


def _slugify(text: str) -> str:
    """Convert a title to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text


def _unique_slug(base_slug: str, exclude_id: int = None) -> str:
    """Ensure slug is unique, appending a counter if needed."""
    slug = base_slug
    counter = 1
    while True:
        q = Project.query.filter_by(slug=slug)
        if exclude_id:
            q = q.filter(Project.id != exclude_id)
        if not q.first():
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


def _get_settings():
    s = SiteSettings.query.first()
    if not s:
        s = SiteSettings()
        db.session.add(s)
        db.session.commit()
    return s


def _parse_json(text, default):
    try:
        return json.loads(text) if text else default
    except (ValueError, TypeError):
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Login / Logout
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if session.get("admin_id"):
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        remember_me = request.form.get("remember_me") in ("on", "true", "1")

        admin = Admin.query.filter(
            (Admin.username == identifier) | (Admin.email == identifier)
        ).first()

        if admin:
            if admin.is_locked():
                logger.warning("Attempted login on locked account: %s", identifier)
                flash("This account is temporarily locked due to too many failed attempts. Please try again in 15 minutes.", "danger")
                return render_template("admin/login.html")

            if admin.check_password(password):
                from datetime import timedelta
                if remember_me:
                    current_app.permanent_session_lifetime = timedelta(days=30)
                else:
                    current_app.permanent_session_lifetime = timedelta(hours=8)

                session.clear()
                session.permanent = True
                session["admin_id"] = admin.id
                session["admin_username"] = admin.username
                admin.reset_failed_logins()
                admin.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
                db.session.commit()
                logger.info("Admin login successful: %s", admin.username)
                flash(f"Welcome back, {admin.username}!", "success")
                return redirect(url_for("admin.dashboard"))
            else:
                admin.record_failed_login()
                remaining = max(0, 5 - admin.failed_logins)
                if remaining == 0:
                    flash("Account locked for 15 minutes due to 5 consecutive failed attempts.", "danger")
                else:
                    flash(f"Invalid username/email or password. ({remaining} attempt{'s' if remaining != 1 else ''} remaining before lockout)", "danger")
        else:
            logger.warning("Failed admin login attempt for unknown identifier: %s", identifier)
            flash("Invalid username/email or password.", "danger")

    return render_template("admin/login.html")


@admin_bp.route("/logout")
@login_required
def logout():
    username = session.get("admin_username", "unknown")
    session.clear()
    logger.info("Admin logout: %s", username)
    flash("You have been logged out.", "info")
    return redirect(url_for("admin.login"))


@admin_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if session.get("admin_id"):
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        
        # Check if email is in ALLOWED_ADMIN_EMAILS
        allowed_emails = current_app.config.get("ALLOWED_ADMIN_EMAILS", [])
        if email not in allowed_emails:
            logger.warning("Unauthorized registration attempt for email: %s", email)
            flash("You are not authorized to register an admin account with this email.", "danger")
            return redirect(url_for("admin.register"))

        if Admin.query.filter_by(username=username).first() or Admin.query.filter_by(email=email).first():
            flash("Username or email already exists.", "danger")
            return redirect(url_for("admin.register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            return redirect(url_for("admin.register"))

        # We can't use AdminOTP since the admin isn't created yet.
        # Store temporary OTP and password hash in session.
        import secrets
        from werkzeug.security import generate_password_hash
        otp_code = f"{secrets.randbelow(900000) + 100000}"
        
        session["reg_username"] = username
        session["reg_email"] = email
        session["reg_password_hash"] = generate_password_hash(password)
        session["reg_otp"] = otp_code

        from utils.security import send_otp_email
        sent = send_otp_email(email, otp_code, "admin account registration")
        if not sent:
            if current_app.config.get("DEBUG") or current_app.config.get("TESTING"):
                flash(f"Verification OTP code for {email} is: {otp_code} (SMTP not active).", "warning")
            else:
                flash("A verification code was generated. Please check server logs or configure SMTP.", "info")
        else:
            flash(f"A 6-digit verification code has been sent to {email}.", "info")

        return redirect(url_for("admin.register_verify"))

    return render_template("admin/register.html")


@admin_bp.route("/register-verify", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register_verify():
    if not session.get("reg_email") or not session.get("reg_password_hash"):
        flash("Registration session expired. Please start again.", "warning")
        return redirect(url_for("admin.register"))

    if request.method == "POST":
        otp = request.form.get("otp", "").strip()

        # Increment attempt counter to prevent brute-force of 6-digit OTP
        attempts = session.get("reg_otp_attempts", 0) + 1
        session["reg_otp_attempts"] = attempts
        if attempts > 5:
            # Too many failed attempts — invalidate the registration session
            session.pop("reg_username", None)
            session.pop("reg_email", None)
            session.pop("reg_password_hash", None)
            session.pop("reg_otp", None)
            session.pop("reg_otp_attempts", None)
            logger.warning("Registration OTP brute-force detected; session cleared.")
            flash("Too many invalid attempts. Please start registration again.", "danger")
            return redirect(url_for("admin.register"))

        if otp != session.get("reg_otp"):
            flash("Invalid OTP verification code. Please check and try again.", "danger")
            return render_template("admin/register_verify.html", email=session.get("reg_email"))

        # OTP verified — create admin using stored password hash
        admin = Admin(
            username=session.get("reg_username"),
            email=session.get("reg_email"),
            password_hash=session.get("reg_password_hash")
        )
        db.session.add(admin)
        db.session.commit()

        logger.info("New admin registered: %s", admin.username)

        # Clear registration session data
        for key in ("reg_username", "reg_email", "reg_password_hash", "reg_otp", "reg_otp_attempts"):
            session.pop(key, None)

        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for("admin.login"))

    return render_template("admin/register_verify.html", email=session.get("reg_email"))


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/")
@admin_bp.route("/dashboard")
@login_required
def dashboard():
    stats = {
        "total_projects": Project.query.count(),
        "published_projects": Project.query.filter_by(published=True).count(),
        "draft_projects": Project.query.filter_by(published=False).count(),
        "featured_projects": Project.query.filter_by(featured=True).count(),
        "total_skills": Skill.query.count(),
        "total_certifications": Certification.query.count(),
        "total_messages": Message.query.count(),
        "unread_messages": Message.query.filter_by(is_read=False, is_archived=False).count(),
    }
    recent_messages = (
        Message.query.filter_by(is_archived=False)
        .order_by(Message.created_at.desc())
        .limit(5)
        .all()
    )
    return render_template("admin/dashboard.html", stats=stats, recent_messages=recent_messages)


# ─────────────────────────────────────────────────────────────────────────────
# Projects CRUD
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/projects")
@login_required
def projects_list():
    projects = Project.query.order_by(Project.display_order.asc(), Project.created_at.desc()).all()
    return render_template("admin/projects_list.html", projects=projects)


@admin_bp.route("/projects/new", methods=["GET", "POST"])
@login_required
def project_new():
    if request.method == "POST":
        return _save_project(None)
    return render_template("admin/project_form.html", project=None, action="new")


@admin_bp.route("/projects/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def project_edit(pid):
    project = Project.query.get_or_404(pid)
    if request.method == "POST":
        return _save_project(project)
    project.tech_list = _parse_json(project.technologies, [])
    project.metrics_dict = _parse_json(project.metrics, {})
    return render_template("admin/project_form.html", project=project, action="edit")


def _save_project(project):
    """Create or update a project from POST form data."""
    f = request.form
    is_new = project is None
    if is_new:
        project = Project()

    project.title = f.get("title", "").strip()[:200]
    project.short_description = f.get("short_description", "").strip()[:400]
    project.description = f.get("description", "").strip()
    project.problem_statement = f.get("problem_statement", "").strip()
    project.category = f.get("category", "Machine Learning").strip()[:100]
    project.github_url = f.get("github_url", "").strip()[:300]
    project.demo_url = f.get("demo_url", "").strip()[:300]
    project.dataset = f.get("dataset", "").strip()
    project.model_architecture = f.get("model_architecture", "").strip()
    project.preprocessing = f.get("preprocessing", "").strip()
    project.results = f.get("results", "").strip()
    project.limitations = f.get("limitations", "").strip()
    project.future_improvements = f.get("future_improvements", "").strip()
    project.featured = f.get("featured") == "on"
    project.published = f.get("published") == "on"
    try:
        project.display_order = int(f.get("display_order", 0))
    except ValueError:
        project.display_order = 0

    # Slug
    raw_slug = f.get("slug", "").strip() or _slugify(project.title)
    raw_slug = _slugify(raw_slug)
    project.slug = _unique_slug(raw_slug, exclude_id=project.id if not is_new else None)

    # Technologies JSON
    techs = [t.strip() for t in f.get("technologies", "").split(",") if t.strip()]
    project.technologies = json.dumps(techs)

    # Metrics JSON
    metrics = {}
    for key in ["accuracy", "precision", "recall", "f1", "roc_auc"]:
        val = f.get(f"metric_{key}", "").strip()
        if val:
            metrics[key] = val
    project.metrics = json.dumps(metrics)

    # Image upload
    if "image" in request.files:
        img_file = request.files["image"]
        if img_file and img_file.filename:
            saved = validate_and_save_image(img_file, subfolder="projects")
            if saved:
                project.image = saved
            else:
                project.tech_list = _parse_json(project.technologies, [])
                project.metrics_dict = _parse_json(project.metrics, {})
                flash("Invalid image file. Please upload PNG, JPG, or WebP under 5MB.", "danger")
                return render_template(
                    "admin/project_form.html",
                    project=project,
                    action="new" if is_new else "edit",
                )

    if is_new:
        db.session.add(project)

    db.session.commit()
    logger.info("Project saved: %s (id=%s)", project.slug, project.id)
    flash(f"Project '{project.title}' saved successfully.", "success")
    return redirect(url_for("admin.projects_list"))


@admin_bp.route("/projects/<int:pid>/delete", methods=["POST"])
@login_required
def project_delete(pid):
    project = db.session.get(Project, pid)
    if not project:
        abort(404)
    title = project.title
    db.session.delete(project)
    db.session.commit()
    logger.info("Project deleted: id=%s title=%s", pid, title)
    flash(f"Project '{title}' deleted.", "info")
    return redirect(url_for("admin.projects_list"))


@admin_bp.route("/projects/<int:pid>/toggle-publish", methods=["POST"])
@login_required
def project_toggle_publish(pid):
    project = db.session.get(Project, pid)
    if not project:
        abort(404)
    project.published = not project.published
    db.session.commit()
    state = "published" if project.published else "unpublished"
    return jsonify({"success": True, "published": project.published, "state": state})


@admin_bp.route("/projects/<int:pid>/toggle-featured", methods=["POST"])
@login_required
def project_toggle_featured(pid):
    project = db.session.get(Project, pid)
    if not project:
        abort(404)
    project.featured = not project.featured
    db.session.commit()
    return jsonify({"success": True, "featured": project.featured})


# ─────────────────────────────────────────────────────────────────────────────
# Skills CRUD
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/skills")
@login_required
def skills():
    all_skills = Skill.query.order_by(Skill.display_order.asc()).all()
    for s in all_skills:
        s.tags_list = _parse_json(s.tags, [])
    return render_template("admin/skills.html", skills=all_skills)


@admin_bp.route("/skills/save", methods=["POST"])
@login_required
def skill_save():
    sid = request.form.get("id")
    if sid:
        skill = Skill.query.get_or_404(int(sid))
    else:
        skill = Skill()
        db.session.add(skill)

    skill.name = request.form.get("name", "").strip()[:100]
    skill.category = request.form.get("category", "").strip()[:100]
    skill.icon_class = request.form.get("icon_class", "fas fa-code").strip()[:100]
    try:
        skill.proficiency = max(0, min(100, int(request.form.get("proficiency", 80))))
    except ValueError:
        skill.proficiency = 80
    try:
        skill.display_order = int(request.form.get("display_order", 0))
    except ValueError:
        skill.display_order = 0
    tags = [t.strip() for t in request.form.get("tags", "").split(",") if t.strip()]
    skill.tags = json.dumps(tags)

    db.session.commit()
    flash("Skill saved.", "success")
    return redirect(url_for("admin.skills"))


@admin_bp.route("/skills/<int:sid>/delete", methods=["POST"])
@login_required
def skill_delete(sid):
    skill = Skill.query.get_or_404(sid)
    db.session.delete(skill)
    db.session.commit()
    flash("Skill deleted.", "info")
    return redirect(url_for("admin.skills"))


# ─────────────────────────────────────────────────────────────────────────────
# Education CRUD
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/education")
@login_required
def education():
    items = Education.query.order_by(Education.display_order.asc()).all()
    return render_template("admin/education.html", education=items)


@admin_bp.route("/education/save", methods=["POST"])
@login_required
def education_save():
    eid = request.form.get("id")
    if eid:
        edu = Education.query.get_or_404(int(eid))
    else:
        edu = Education()
        db.session.add(edu)

    edu.institution = request.form.get("institution", "").strip()[:200]
    edu.degree = request.form.get("degree", "").strip()[:200]
    edu.level = request.form.get("level", "").strip()[:100]
    edu.start_year = request.form.get("start_year", "").strip()[:10]
    edu.end_year = request.form.get("end_year", "").strip()[:10]
    edu.score = request.form.get("score", "").strip()[:50]
    edu.score_label = request.form.get("score_label", "Score").strip()[:30]
    edu.description = request.form.get("description", "").strip()
    try:
        edu.display_order = int(request.form.get("display_order", 0))
    except ValueError:
        edu.display_order = 0

    db.session.commit()
    flash("Education record saved.", "success")
    return redirect(url_for("admin.education"))


@admin_bp.route("/education/<int:eid>/delete", methods=["POST"])
@login_required
def education_delete(eid):
    edu = Education.query.get_or_404(eid)
    db.session.delete(edu)
    db.session.commit()
    flash("Education record deleted.", "info")
    return redirect(url_for("admin.education"))


# ─────────────────────────────────────────────────────────────────────────────
# Experience CRUD
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/experience")
@login_required
def experience():
    items = Experience.query.order_by(Experience.display_order.asc()).all()
    for item in items:
        item.tech_list = _parse_json(item.technologies, [])
    return render_template("admin/experience.html", experience=items)


@admin_bp.route("/experience/save", methods=["POST"])
@login_required
def experience_save():
    eid = request.form.get("id")
    if eid:
        exp = Experience.query.get_or_404(int(eid))
    else:
        exp = Experience()
        db.session.add(exp)

    exp.company = request.form.get("company", "").strip()[:200]
    exp.role = request.form.get("role", "").strip()[:200]
    exp.start_date = request.form.get("start_date", "").strip()[:20]
    exp.end_date = request.form.get("end_date", "Present").strip()[:20]
    exp.description = request.form.get("description", "").strip()
    techs = [t.strip() for t in request.form.get("technologies", "").split(",") if t.strip()]
    exp.technologies = json.dumps(techs)
    try:
        exp.display_order = int(request.form.get("display_order", 0))
    except ValueError:
        exp.display_order = 0

    db.session.commit()
    flash("Experience record saved.", "success")
    return redirect(url_for("admin.experience"))


@admin_bp.route("/experience/<int:eid>/delete", methods=["POST"])
@login_required
def experience_delete(eid):
    exp = Experience.query.get_or_404(eid)
    db.session.delete(exp)
    db.session.commit()
    flash("Experience record deleted.", "info")
    return redirect(url_for("admin.experience"))


# ─────────────────────────────────────────────────────────────────────────────
# Certifications CRUD
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/certifications")
@login_required
def certifications():
    certs = Certification.query.order_by(Certification.display_order.asc()).all()
    return render_template("admin/certifications.html", certifications=certs)


@admin_bp.route("/certifications/save", methods=["POST"])
@login_required
def certification_save():
    cid = request.form.get("id")
    if cid:
        cert = Certification.query.get_or_404(int(cid))
    else:
        cert = Certification()
        db.session.add(cert)

    cert.title = request.form.get("title", "").strip()[:200]
    cert.issuer = request.form.get("issuer", "").strip()[:200]
    cert.issue_date = request.form.get("issue_date", "").strip()[:30]
    cert.credential_url = request.form.get("credential_url", "").strip()[:300]
    try:
        cert.display_order = int(request.form.get("display_order", 0))
    except ValueError:
        cert.display_order = 0

    if "image" in request.files:
        img_file = request.files["image"]
        if img_file and img_file.filename:
            saved = validate_and_save_image(img_file, subfolder="certs")
            if saved:
                cert.image = saved

    db.session.commit()
    flash("Certification saved.", "success")
    return redirect(url_for("admin.certifications"))


@admin_bp.route("/certifications/<int:cid>/delete", methods=["POST"])
@login_required
def certification_delete(cid):
    cert = Certification.query.get_or_404(cid)
    db.session.delete(cert)
    db.session.commit()
    flash("Certification deleted.", "info")
    return redirect(url_for("admin.certifications"))


# ─────────────────────────────────────────────────────────────────────────────
# Messages (Admin-only, no public endpoint)
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/messages")
@login_required
def messages():
    show = request.args.get("show", "inbox")
    if show == "archived":
        msgs = Message.query.filter_by(is_archived=True).order_by(Message.created_at.desc()).all()
    else:
        msgs = Message.query.filter_by(is_archived=False).order_by(Message.created_at.desc()).all()
    return render_template("admin/messages.html", messages=msgs, show=show)


@admin_bp.route("/messages/<int:mid>/read", methods=["POST"])
@login_required
def message_mark_read(mid):
    msg = Message.query.get_or_404(mid)
    msg.is_read = not msg.is_read
    db.session.commit()
    return jsonify({"success": True, "is_read": msg.is_read})


@admin_bp.route("/messages/<int:mid>/archive", methods=["POST"])
@login_required
def message_archive(mid):
    msg = Message.query.get_or_404(mid)
    msg.is_archived = not msg.is_archived
    db.session.commit()
    return jsonify({"success": True, "is_archived": msg.is_archived})


@admin_bp.route("/messages/<int:mid>/delete", methods=["POST"])
@login_required
def message_delete(mid):
    msg = Message.query.get_or_404(mid)
    db.session.delete(msg)
    db.session.commit()
    flash("Message deleted.", "info")
    return redirect(url_for("admin.messages"))


# ─────────────────────────────────────────────────────────────────────────────
# Site Settings / Profile
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    s = _get_settings()

    if request.method == "POST":
        s.name = request.form.get("name", "").strip()[:100]
        s.headline = request.form.get("headline", "").strip()[:200]
        s.bio = request.form.get("bio", "").strip()
        s.location = request.form.get("location", "").strip()[:100]
        s.contact_email = request.form.get("contact_email", "").strip()[:120]
        s.availability = request.form.get("availability", "").strip()[:100]
        s.github_url = request.form.get("github_url", "").strip()[:300]
        s.linkedin_url = request.form.get("linkedin_url", "").strip()[:300]
        s.whatsapp_number = request.form.get("whatsapp_number", "").strip()[:50]
        s.resume_url = request.form.get("resume_url", "").strip()[:300]
        s.site_title = request.form.get("site_title", "").strip()[:200]
        s.meta_description = request.form.get("meta_description", "").strip()[:300]
        s.hero_description = request.form.get("hero_description", "").strip()
        s.about_domain = request.form.get("about_domain", "AI / ML / Computer Vision").strip()[:100]
        s.projects_badge_count = request.form.get("projects_badge_count", "7+").strip()[:10]
        s.github_handle = request.form.get("github_handle", "@SAFIULLAH012").strip()[:100]

        # Hero tags (comma-separated or JSON)
        raw_hero_tags = request.form.get("hero_tags", "")
        if raw_hero_tags:
            hero_tags_list = [t.strip() for t in raw_hero_tags.split(",") if t.strip()]
            s.hero_tags = json.dumps(hero_tags_list)

        # Why work with me (multiline or comma-separated)
        raw_why = request.form.get("why_work_with_me", "")
        if raw_why:
            why_list = [w.strip() for w in raw_why.split("\n") if w.strip()]
            s.why_work_with_me = json.dumps(why_list)

        # Profile image upload
        if "profile_image" in request.files:
            img_file = request.files["profile_image"]
            if img_file and img_file.filename:
                saved = validate_and_save_image(img_file, subfolder="profile")
                if saved:
                    s.profile_image = saved
                else:
                    flash("Invalid image file.", "danger")

        # Resume / CV PDF upload
        if "resume_pdf" in request.files:
            pdf_file = request.files["resume_pdf"]
            if pdf_file and pdf_file.filename:
                saved_pdf = validate_and_save_pdf(pdf_file, subfolder="cv")
                if saved_pdf:
                    s.resume_url = saved_pdf
                else:
                    flash("Invalid PDF file. Please upload a valid .pdf document under 10MB.", "danger")

        db.session.commit()
        flash("Settings saved successfully.", "success")
        return redirect(url_for("admin.settings"))

    # Parse JSON lists for rendering in edit form
    s.hero_tags_list = _parse_json(s.hero_tags, [])
    s.why_work_with_me_list = _parse_json(s.why_work_with_me, [])
    return render_template("admin/settings.html", settings=s)


# ─────────────────────────────────────────────────────────────────────────────
# Forgot Password Flow (Login Page)
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def forgot_password():
    if session.get("admin_id"):
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        admin = Admin.query.filter(
            (Admin.username == identifier) | (Admin.email == identifier)
        ).first()

        if not admin:
            # Generic message to prevent username enumeration
            flash("If an admin account matches that username or email, an OTP code has been sent.", "info")
            return render_template("admin/forgot_password.html")

        otp_code = AdminOTP.generate_otp(admin.id, purpose="forgot_password", valid_minutes=10)
        sent = send_otp_email(admin.email, otp_code, "admin password reset")

        session["reset_admin_id"] = admin.id
        session["reset_admin_email"] = admin.email

        if not sent:
            if current_app.config.get("DEBUG") or current_app.config.get("TESTING"):
                flash(
                    f"Verification OTP generated for {admin.email}: {otp_code} (SMTP not active in local environment).",
                    "warning"
                )
            else:
                flash(
                    "A verification code has been dispatched. Please check your email (or server logs if SMTP is not configured).",
                    "info"
                )
        else:
            flash(f"A 6-digit verification code has been sent to {admin.email}.", "info")

        return redirect(url_for("admin.reset_password_verify"))

    return render_template("admin/forgot_password.html")


@admin_bp.route("/reset-password-verify", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def reset_password_verify():
    admin_id = session.get("reset_admin_id")
    if not admin_id:
        flash("Password reset session expired. Please start again.", "warning")
        return redirect(url_for("admin.forgot_password"))

    admin = db.session.get(Admin, admin_id)
    if not admin:
        session.pop("reset_admin_id", None)
        return redirect(url_for("admin.forgot_password"))

    if request.method == "POST":
        otp = request.form.get("otp", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not AdminOTP.verify_otp(admin.id, otp, purpose="forgot_password"):
            flash("Invalid or expired OTP verification code. Please check and try again.", "danger")
            return render_template("admin/reset_password_verify.html", email=admin.email)

        if len(new_password) < 8:
            flash("New password must be at least 8 characters long.", "danger")
            return render_template("admin/reset_password_verify.html", email=admin.email)

        if new_password != confirm_password:
            flash("New passwords do not match.", "danger")
            return render_template("admin/reset_password_verify.html", email=admin.email)

        admin.set_password(new_password)
        db.session.commit()
        session.pop("reset_admin_id", None)
        session.pop("reset_admin_email", None)

        logger.info("Admin password reset successfully for user: %s", admin.username)
        flash("Password reset successful! You can now log in with your new password.", "success")
        return redirect(url_for("admin.login"))

    return render_template("admin/reset_password_verify.html", email=admin.email)


# ─────────────────────────────────────────────────────────────────────────────
# Credential & Password Change (Past Password Check + Email OTP Verification)
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/request-credential-otp", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def request_credential_otp():
    """Step 1: Verify current password, then generate and send OTP to admin's email."""
    admin_id = session.get("admin_id")
    admin = db.session.get(Admin, admin_id)
    if not admin:
        abort(404)

    current_pw = request.form.get("current_password", "")

    if not admin.check_password(current_pw):
        flash("Current password is incorrect. Please enter your existing password to request an OTP.", "danger")
        return redirect(url_for("admin.settings"))

    otp_code = AdminOTP.generate_otp(admin.id, purpose="change_credentials", valid_minutes=10)
    sent = send_otp_email(admin.email, otp_code, "updating admin username/password")

    session["credential_step"] = "verify"

    if not sent:
        if current_app.config.get("DEBUG") or current_app.config.get("TESTING"):
            flash(
                f"Verification OTP code for {admin.email} is: {otp_code} (SMTP not active in local environment).",
                "warning"
            )
        else:
            flash(
                "A verification code has been dispatched. Please check your email (or server logs if SMTP is not configured).",
                "info"
            )
    else:
        flash(f"A 6-digit verification code was sent to your registered email ({admin.email}).", "info")

    return redirect(url_for("admin.settings") + "#security-credentials")


@admin_bp.route("/update-credentials", methods=["POST"])
@login_required
def update_credentials():
    """Step 2: Verify OTP code, then apply changes to username and/or password."""
    admin_id = session.get("admin_id")
    admin = db.session.get(Admin, admin_id)
    if not admin:
        abort(404)

    otp = request.form.get("otp_code", "").strip()
    new_username = request.form.get("new_username", "").strip()
    new_password = request.form.get("new_password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    if not AdminOTP.verify_otp(admin.id, otp, purpose="change_credentials"):
        flash("Invalid or expired OTP code. Please request a new verification code.", "danger")
        return redirect(url_for("admin.settings") + "#security-credentials")

    changes_made = []

    # 1. Username change
    if new_username and new_username != admin.username:
        if not re.match(r"^[a-zA-Z0-9_\-\.]{3,32}$", new_username):
            flash("Username must be between 3 and 32 alphanumeric characters.", "danger")
            return redirect(url_for("admin.settings") + "#security-credentials")

        existing = Admin.query.filter_by(username=new_username).first()
        if existing and existing.id != admin.id:
            flash(f"Username '{new_username}' is already taken.", "danger")
            return redirect(url_for("admin.settings") + "#security-credentials")

        old_user = admin.username
        admin.username = new_username
        session["admin_username"] = new_username
        changes_made.append(f"username updated from '{old_user}' to '{new_username}'")

    # 2. Password change
    if new_password:
        if len(new_password) < 8:
            flash("New password must be at least 8 characters long.", "danger")
            return redirect(url_for("admin.settings") + "#security-credentials")

        if new_password != confirm_password:
            flash("New password and confirmation do not match.", "danger")
            return redirect(url_for("admin.settings") + "#security-credentials")

        admin.set_password(new_password)
        changes_made.append("password updated")

    if not changes_made:
        flash("No changes were submitted.", "info")
        return redirect(url_for("admin.settings"))

    db.session.commit()
    session.pop("credential_step", None)
    logger.info("Admin credentials updated for id %d: %s", admin.id, ", ".join(changes_made))
    flash("Account credentials updated successfully! " + ", ".join(changes_made).capitalize() + ".", "success")
    return redirect(url_for("admin.settings"))
