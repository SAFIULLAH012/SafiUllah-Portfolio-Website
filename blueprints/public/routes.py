"""
Public portfolio routes — homepage, project detail, contact, SEO endpoints.
"""
import json
import logging
import os
import re
from datetime import datetime, timezone
from flask import (
    render_template, request, jsonify, make_response,
    current_app, abort, url_for,
)
from flask_wtf.csrf import validate_csrf
from wtforms.validators import ValidationError

from blueprints.public import public_bp
from extensions import db, mail, limiter
from models import Project, Skill, Education, Experience, Certification, Message, SiteSettings

logger = logging.getLogger(__name__)


def _get_settings():
    """Return the singleton SiteSettings row, creating defaults if absent."""
    s = SiteSettings.query.first()
    if not s:
        s = SiteSettings()
        db.session.add(s)
        db.session.commit()
    return s


def _parse_json_field(text, default):
    """Safely parse a JSON text field from the DB."""
    try:
        return json.loads(text) if text else default
    except (ValueError, TypeError):
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Homepage
# ─────────────────────────────────────────────────────────────────────────────
@public_bp.route("/")
def index():
    settings = _get_settings()
    projects = (
        Project.query.filter_by(published=True)
        .order_by(Project.featured.desc(), Project.display_order.asc(), Project.created_at.desc())
        .all()
    )
    skills = Skill.query.order_by(Skill.display_order.asc()).all()
    education = Education.query.order_by(Education.display_order.asc()).all()
    experience = Experience.query.order_by(Experience.display_order.asc()).all()
    certifications = Certification.query.order_by(Certification.display_order.asc()).all()

    # Parse JSON fields for skills
    for skill in skills:
        skill.tags_list = _parse_json_field(skill.tags, [])

    # Parse technologies in experience
    for exp in experience:
        exp.tech_list = _parse_json_field(exp.technologies, [])

    return render_template(
        "index.html",
        settings=settings,
        projects=projects,
        skills=skills,
        education=education,
        experience=experience,
        certifications=certifications,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Project Detail
# ─────────────────────────────────────────────────────────────────────────────
@public_bp.route("/projects/<slug>")
def project_detail(slug):
    # Validate slug to prevent injection
    if not re.match(r"^[a-z0-9\-]+$", slug):
        abort(404)

    project = Project.query.filter_by(slug=slug, published=True).first_or_404()
    settings = _get_settings()

    project.metrics_dict = _parse_json_field(project.metrics, {})
    project.tech_list = _parse_json_field(project.technologies, [])

    return render_template(
        "project_detail.html",
        project=project,
        settings=settings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Contact Form
# ─────────────────────────────────────────────────────────────────────────────
@public_bp.route("/contact", methods=["POST"])
@limiter.limit("5 per minute;20 per hour")
def contact():
    """
    Accept contact form submission.
    - CSRF validated
    - All fields validated server-side
    - Stored in DB (never in public JSON)
    - Email notification dispatched if SMTP configured
    """
    # ── CSRF check ────────────────────────────────────────────────────────────
    if current_app.config.get("WTF_CSRF_ENABLED", True):
        token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken", "")
        try:
            validate_csrf(token)
        except ValidationError:
            return jsonify({"success": False, "message": "Invalid request. Please refresh and try again."}), 400

    # ── Extract & strip inputs ─────────────────────────────────────────────────
    name = request.form.get("name", "").strip()[:100]
    email = request.form.get("email", "").strip()[:120]
    subject = request.form.get("subject", "").strip()[:200]
    body = request.form.get("message", "").strip()[:3000]

    # ── Validate ──────────────────────────────────────────────────────────────
    errors = []
    if not name:
        errors.append("Name is required.")
    if not email or not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        errors.append("A valid email address is required.")
    if not subject:
        errors.append("Subject is required.")
    if not body:
        errors.append("Message is required.")

    if errors:
        return jsonify({"success": False, "message": " ".join(errors)}), 400

    # ── Store in database ──────────────────────────────────────────────────────
    try:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")[:45]
        msg = Message(
            name=name,
            email=email,
            subject=subject,
            message=body,
            ip_address=ip,
        )
        db.session.add(msg)
        db.session.commit()
    except Exception:
        logger.exception("Failed to save contact message to database")
        return jsonify({"success": False, "message": "An error occurred. Please try again later."}), 500

    # ── Email notification ─────────────────────────────────────────────────────
    recipient = current_app.config.get("CONTACT_RECIPIENT_EMAIL", "safiullah477845@gmail.com")
    resend_api_key = (current_app.config.get("RESEND_API_KEY") or os.environ.get("RESEND_API_KEY", "")).strip()

    email_sent = False
    if resend_api_key and recipient:
        try:
            import requests
            headers = {
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json",
            }
            html_content = (
                f"<div style='font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;'>"
                f"<h2 style='color: #0f172a; border-bottom: 2px solid #5fbcb8; padding-bottom: 10px;'>🚀 New Portfolio Message</h2>"
                f"<p style='margin: 8px 0;'><strong>From:</strong> {name} (&lt;<a href='mailto:{email}'>{email}</a>&gt;)</p>"
                f"<p style='margin: 8px 0;'><strong>Subject:</strong> {subject}</p>"
                f"<p style='margin: 8px 0;'><strong>Date:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>"
                f"<hr style='border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;'>"
                f"<div style='background: #f8fafc; padding: 15px; border-radius: 6px; border-left: 4px solid #5fbcb8;'>"
                f"<p style='margin: 0; white-space: pre-wrap; color: #334155; font-size: 15px; line-height: 1.6;'>{body}</p>"
                f"</div>"
                f"<p style='color: #64748b; font-size: 12px; margin-top: 20px;'>"
                f"Tip: Simply click 'Reply' in your email app to respond directly to {name} ({email})."
                f"</p></div>"
            )
            payload = {
                "from": "Safi Ullah Portfolio <onboarding@resend.dev>",
                "to": [recipient],
                "reply_to": email,
                "subject": f"🚀 New Portfolio Message from {name}: {subject}",
                "html": html_content,
                "text": f"New Portfolio Message\n\nFrom: {name} ({email})\nSubject: {subject}\n\nMessage:\n{body}",
            }
            r = requests.post("https://api.resend.com/emails", json=payload, headers=headers, timeout=10)
            if r.status_code in (200, 201):
                email_sent = True
                logger.info("Resend email dispatched successfully to %s from %s", recipient, email)
            else:
                logger.warning("Resend returned status %s: %s", r.status_code, r.text)
        except Exception:
            logger.exception("Resend API dispatch failed")

    if not email_sent and recipient:
        try:
            from flask_mail import Message as MailMessage
            m = MailMessage(
                subject=f"🚀 New Portfolio Message from {name}: {subject}",
                recipients=[recipient],
                reply_to=email,
                body=(
                    f"You have received a new message from your portfolio website!\n\n"
                    f"Sender Name: {name}\n"
                    f"Sender Email: {email}\n"
                    f"Subject: {subject}\n"
                    f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                    f"Message:\n"
                    f"{body}\n\n"
                    f"---\n"
                    f"Tip: Simply click 'Reply' in your email client to respond directly to {name} ({email})."
                ),
            )
            mail.send(m)
            logger.info("Inquiry email dispatched to %s from %s", recipient, email)
        except Exception:
            # Log but do NOT surface SMTP errors to visitor
            logger.exception("Email dispatch failed (contact form)")

    return jsonify({"success": True, "message": "Thank you! Your message has been received."})


# ─────────────────────────────────────────────────────────────────────────────
# SEO — robots.txt & sitemap.xml
# ─────────────────────────────────────────────────────────────────────────────
@public_bp.route("/robots.txt")
def robots():
    content = "User-agent: *\nAllow: /\nDisallow: /admin/\nSitemap: /sitemap.xml\n"
    resp = make_response(content, 200)
    resp.headers["Content-Type"] = "text/plain"
    return resp


@public_bp.route("/sitemap.xml")
def sitemap():
    import html
    settings = _get_settings()
    projects = Project.query.filter_by(published=True).all()
    base = request.host_url.rstrip("/")
    # Guard: only allow http/https base URLs in the sitemap
    if not base.startswith(("http://", "https://")):
        base = "https://example.com"

    pages = [
        {
            "loc": html.escape(base + "/"),
            "priority": "1.0",
            "changefreq": "weekly",
            "lastmod": (settings.updated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d"),
        },
    ]
    for p in projects:
        pages.append({
            "loc": html.escape(f"{base}/projects/{p.slug}"),
            "priority": "0.8",
            "changefreq": "monthly",
            "lastmod": (p.updated_at or p.created_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d"),
        })

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for page in pages:
        xml += (
            "  <url>\n"
            f"    <loc>{page['loc']}</loc>\n"
            f"    <lastmod>{page['lastmod']}</lastmod>\n"
            f"    <changefreq>{page['changefreq']}</changefreq>\n"
            f"    <priority>{page['priority']}</priority>\n"
            "  </url>\n"
        )
    xml += "</urlset>"
    resp = make_response(xml, 200)
    resp.headers["Content-Type"] = "application/xml"
    return resp
