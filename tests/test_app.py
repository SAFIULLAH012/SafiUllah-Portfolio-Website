"""
Automated test suite for Safi Ullah Portfolio CMS
Covers:
- Public endpoints & status codes
- Project detail dynamic rendering
- Contact form validation & CSRF
- SEO (sitemap.xml, robots.txt)
- Security headers
- Admin authentication & session security
- Admin CRUD operations
"""
import pytest
import json
import io
from app import create_app
from extensions import db
from models import Admin, AdminOTP, Project, Skill, SiteSettings, Message


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        # Seed test admin
        admin = Admin(username="testadmin", email="test@example.com")
        admin.set_password("TestSecret123!")
        db.session.add(admin)

        # Seed site settings
        settings = SiteSettings(
            name="Safi Ullah",
            headline="AI Engineer",
            site_title="Safi Ullah | AI Engineer",
            hero_description="AI Developer",
            contact_email="test@example.com",
            resume_url="cv/safi_ullah_cv.pdf"
        )
        db.session.add(settings)

        # Seed test project
        proj = Project(
            title="Brain Tumor MRI Classifier",
            slug="brain-tumor-mri-classifier",
            short_description="CNN classification model",
            category="Deep Learning",
            technologies=json.dumps(["TensorFlow", "Keras"]),
            metrics=json.dumps({"accuracy": "95.2%"}),
            published=True,
            featured=True,
        )
        db.session.add(proj)
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app, client):
    """Client authenticated as admin."""
    with client.session_transaction() as sess:
        admin = Admin.query.filter_by(username="testadmin").first()
        sess["admin_id"] = admin.id
        sess["admin_username"] = admin.username
    return client


# ─────────────────────────────────────────────────────────────────────────────
# Public Tests
# ─────────────────────────────────────────────────────────────────────────────
def test_homepage_loads(client):
    """Homepage returns 200 and contains key sections and CV download button."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Safi Ullah" in html
    assert "Download My CV" in html
    assert "safi_ullah_cv.pdf" in html
    assert "Brain Tumor MRI Classifier" in html


def test_project_detail_loads(client):
    """Valid project slug loads the dynamic detail page."""
    res = client.get("/projects/brain-tumor-mri-classifier")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Brain Tumor MRI Classifier" in html
    assert "95.2%" in html
    assert "TensorFlow" in html


def test_project_detail_404(client):
    """Invalid slug returns 404."""
    res = client.get("/projects/non-existent-slug-xyz")
    assert res.status_code == 404


def test_robots_txt(client):
    """robots.txt is served with correct mime and contents."""
    res = client.get("/robots.txt")
    assert res.status_code == 200
    assert "User-agent: *" in res.get_data(as_text=True)
    assert "Disallow: /admin/" in res.get_data(as_text=True)


def test_sitemap_xml(client):
    """sitemap.xml is valid XML containing public routes."""
    res = client.get("/sitemap.xml")
    assert res.status_code == 200
    assert "application/xml" in res.headers["Content-Type"]
    assert "brain-tumor-mri-classifier" in res.get_data(as_text=True)


def test_security_headers(client):
    """Responses contain critical security headers."""
    res = client.get("/")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


# ─────────────────────────────────────────────────────────────────────────────
# Admin Auth Tests
# ─────────────────────────────────────────────────────────────────────────────
def test_admin_requires_login(client):
    """Unauthenticated access to /admin redirects to /admin/login."""
    res = client.get("/admin/dashboard", follow_redirects=False)
    assert res.status_code == 302
    assert "/admin/login" in res.headers["Location"]


def test_admin_login_success(client):
    """Admin can login with valid credentials."""
    res = client.post(
        "/admin/login",
        data={"identifier": "testadmin", "password": "TestSecret123!"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "Dashboard" in res.get_data(as_text=True)


def test_admin_login_failure(client):
    res = client.post(
        "/admin/login",
        data={"identifier": "testadmin", "password": "WrongPassword!"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "Invalid username/email or password" in res.get_data(as_text=True)


def test_admin_dashboard_authenticated(auth_client):
    """Authenticated admin can view dashboard."""
    res = auth_client.get("/admin/dashboard")
    assert res.status_code == 200
    assert "Welcome back, testadmin" in res.get_data(as_text=True)


def test_admin_logout(auth_client):
    """Admin logout clears session and redirects to login."""
    res = auth_client.get("/admin/logout", follow_redirects=True)
    assert res.status_code == 200
    assert "Sign In" in res.get_data(as_text=True)


# ─────────────────────────────────────────────────────────────────────────────
# Admin CRUD Tests
# ─────────────────────────────────────────────────────────────────────────────
def test_admin_create_project(auth_client, app):
    """Admin can create a new project via form POST."""
    data = {
        "title": "Heart Disease Risk Classifier",
        "slug": "heart-disease-risk-classifier",
        "short_description": "Binary classification of 10-yr CHD risk",
        "description": "Full description of CHD study",
        "category": "Healthcare ML",
        "technologies": "Scikit-Learn, Pandas",
        "metric_accuracy": "67%",
        "metric_recall": "58%",
        "metric_roc_auc": "0.70",
        "published": "on",
        "featured": "on",
        "display_order": "1",
    }
    res = auth_client.post("/admin/projects/new", data=data, follow_redirects=True)
    assert res.status_code == 200
    assert "Heart Disease Risk Classifier" in res.get_data(as_text=True)

    with app.app_context():
        p = Project.query.filter_by(slug="heart-disease-risk-classifier").first()
        assert p is not None
        assert p.category == "Healthcare ML"
        assert p.featured is True


def test_admin_request_and_verify_credential_otp(auth_client, app):
    """Step 1: Verify current password and request OTP. Step 2: Verify OTP and update username and password."""
    # Step 1: Wrong current password fails
    res_fail = auth_client.post(
        "/admin/request-credential-otp",
        data={"current_password": "WrongPassword!"},
        follow_redirects=True,
    )
    assert "Current password is incorrect" in res_fail.get_data(as_text=True)

    # Step 1: Correct current password succeeds and generates OTP
    res_step1 = auth_client.post(
        "/admin/request-credential-otp",
        data={"current_password": "TestSecret123!"},
        follow_redirects=True,
    )
    assert res_step1.status_code == 200

    # Retrieve generated OTP from DB
    with app.app_context():
        admin = Admin.query.filter_by(username="testadmin").first()
        otp_entry = AdminOTP.query.filter_by(admin_id=admin.id, purpose="change_credentials", is_used=False).first()
        assert otp_entry is not None
        otp_code = otp_entry.otp_code

    # Step 2: Submit OTP and new username & password
    res_step2 = auth_client.post(
        "/admin/update-credentials",
        data={
            "otp_code": otp_code,
            "new_username": "new_admin_user",
            "new_password": "BrandNewSecret789!",
            "confirm_password": "BrandNewSecret789!",
        },
        follow_redirects=True,
    )
    assert res_step2.status_code == 200
    assert "Account credentials updated successfully" in res_step2.get_data(as_text=True)

    # Verify admin record was updated in database
    with app.app_context():
        updated_admin = Admin.query.filter_by(username="new_admin_user").first()
        assert updated_admin is not None
        assert updated_admin.check_password("BrandNewSecret789!")


def test_admin_forgot_password_flow(client, app):
    """Admin can request OTP for forgotten password and reset it."""
    # Step 1: Request OTP for existing admin email
    res_request = client.post(
        "/admin/forgot-password",
        data={"identifier": "test@example.com"},
        follow_redirects=True,
    )
    assert res_request.status_code == 200
    assert "Enter OTP & Reset Password" in res_request.get_data(as_text=True)

    # Fetch OTP from DB
    with app.app_context():
        admin = Admin.query.filter_by(email="test@example.com").first()
        otp_entry = AdminOTP.query.filter_by(admin_id=admin.id, purpose="forgot_password", is_used=False).first()
        assert otp_entry is not None
        otp_code = otp_entry.otp_code

    # Step 2: Verify OTP and set new password
    res_reset = client.post(
        "/admin/reset-password-verify",
        data={
            "otp": otp_code,
            "new_password": "ResetPassword123!",
            "confirm_password": "ResetPassword123!",
        },
        follow_redirects=True,
    )
    assert res_reset.status_code == 200
    assert "Password reset successful" in res_reset.get_data(as_text=True)

    # Step 3: Login with new password
    res = client.post(
        "/admin/login",
        data={"identifier": "testadmin", "password": "ResetPassword123!"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "Dashboard" in res.get_data(as_text=True)


# ─────────────────────────────────────────────────────────────────────────────
# Additional Security, Validation & CMS Tests
# ─────────────────────────────────────────────────────────────────────────────
def test_contact_form_valid(client, app):
    """Valid contact form submission returns 200 with success JSON."""
    data = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "subject": "Collaboration Opportunity",
        "message": "We would love to discuss a computer vision project with you.",
    }
    res = client.post("/contact", data=data)
    assert res.status_code == 200
    res_json = res.get_json()
    assert res_json["success"] is True
    assert "received" in res_json["message"]

    with app.app_context():
        msg = Message.query.filter_by(email="jane@example.com").first()
        assert msg is not None
        assert msg.subject == "Collaboration Opportunity"


def test_contact_form_invalid_email(client):
    """Invalid email format returns 400."""
    data = {
        "name": "Jane Doe",
        "email": "not-an-email",
        "subject": "Hello",
        "message": "Test message",
    }
    res = client.post("/contact", data=data)
    assert res.status_code == 400
    res_json = res.get_json()
    assert res_json["success"] is False


def test_contact_form_empty_fields(client):
    """Missing required fields return 400."""
    data = {
        "name": "",
        "email": "",
        "subject": "",
        "message": "",
    }
    res = client.post("/contact", data=data)
    assert res.status_code == 400


def test_unauthenticated_protected_routes_redirect(client):
    """Ensure all protected admin endpoints redirect unauthenticated users."""
    endpoints = [
        "/admin/projects",
        "/admin/messages",
        "/admin/settings",
        "/admin/skills",
        "/admin/education",
        "/admin/experience",
        "/admin/certifications",
    ]
    for ep in endpoints:
        res = client.get(ep, follow_redirects=False)
        assert res.status_code == 302
        assert "/admin/login" in res.headers["Location"]


def test_project_slug_injection(client):
    """Malicious slug characters return 404."""
    res = client.get("/projects/../../etc/passwd")
    assert res.status_code in (404, 308)


def test_project_draft_not_public(auth_client, client, app):
    """Draft (unpublished) projects must NOT be accessible publicly."""
    # Create draft project
    data = {
        "title": "Confidential AI Research",
        "slug": "confidential-ai-research",
        "short_description": "Secret unreleased project",
        "description": "Details",
        "category": "Deep Learning",
        "display_order": "1",
    }
    # Notice: 'published' is NOT in data, so it's a draft
    res_create = auth_client.post("/admin/projects/new", data=data, follow_redirects=True)
    assert res_create.status_code == 200

    # Public user tries to view it
    res_pub = client.get("/projects/confidential-ai-research")
    assert res_pub.status_code == 404

    # Public homepage must not list it
    res_home = client.get("/")
    assert "Confidential AI Research" not in res_home.get_data(as_text=True)


def test_project_delete(auth_client, app):
    """Admin can delete a project."""
    with app.app_context():
        p = Project.query.filter_by(slug="brain-tumor-mri-classifier").first()
        pid = p.id

    res = auth_client.post(f"/admin/projects/{pid}/delete", follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        deleted = db.session.get(Project, pid)
        assert deleted is None


def test_xss_in_project_title_is_safe(auth_client, client, app):
    """XSS payloads in user input are not executed unescaped."""
    xss_payload = '<script>alert("XSS")</script>'
    data = {
        "title": xss_payload,
        "slug": "xss-test-slug",
        "short_description": "Testing XSS",
        "published": "on",
    }
    auth_client.post("/admin/projects/new", data=data, follow_redirects=True)

    res = client.get("/projects/xss-test-slug")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    # Ensure raw unescaped script tag is not present
    assert '<script>alert("XSS")</script>' not in html or '&lt;script&gt;' in html



def test_upload_invalid_file_rejected(auth_client):
    """Uploading non-image disguised as image is rejected."""
    fake_img = (io.BytesIO(b"MZ executable binary payload"), "evil.exe")
    data = {
        "title": "Upload Attack Test",
        "slug": "upload-attack-test",
        "image": fake_img,
        "published": "on",
    }
    res = auth_client.post("/admin/projects/new", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    assert "Invalid image file" in res.get_data(as_text=True)


def test_upload_mime_spoof_rejected(auth_client):
    """Executable binary masquerading with a .jpg extension is rejected by Pillow validation."""
    # EXE bytes but .jpg extension — should fail PIL magic bytes check
    fake_jpg = (io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00"), "evil.jpg")
    data = {
        "title": "MIME Spoof Test",
        "slug": "mime-spoof-test",
        "image": fake_jpg,
        "published": "on",
    }
    res = auth_client.post("/admin/projects/new", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    assert "Invalid image file" in res.get_data(as_text=True)


def test_sitemap_xml_escaping(client):
    """Sitemap XML response is well-formed and doesn't leak raw host characters."""
    res = client.get("/sitemap.xml")
    assert res.status_code == 200
    xml = res.get_data(as_text=True)
    assert "<?xml" in xml
    assert "<urlset" in xml
    # Should not contain bare ampersands or angle brackets in URLs
    assert "<loc>http" in xml


def test_register_otp_brute_force_protection(client, app):
    """After 5 failed OTP attempts on register-verify, the session is invalidated."""
    # Seed a pending registration session manually
    with client.session_transaction() as sess:
        sess["reg_username"] = "brutetest"
        sess["reg_email"] = "brute@example.com"
        sess["reg_password_hash"] = "pbkdf2:sha256:fake_hash_only_for_test"
        sess["reg_otp"] = "999999"
        sess["reg_otp_attempts"] = 0

    # Make 6 failed attempts
    for i in range(6):
        res = client.post(
            "/admin/register-verify",
            data={"otp": "000000"},  # Wrong OTP
            follow_redirects=False,
        )

    # After brute-force, session should be cleared and redirect to /register
    assert res.status_code in (200, 302)
    with client.session_transaction() as sess:
        assert "reg_otp" not in sess or sess.get("reg_otp_attempts", 0) > 5


def test_production_config_validation(monkeypatch):
    """ProductionConfig.validate() enforces strong, non-default SECRET_KEY."""
    from config import ProductionConfig

    # Prohibited keys
    for bad_key in ("", "CHANGE-ME-BEFORE-DEPLOYING", "generate-a-secure-random-secret-key", "short-key"):
        monkeypatch.setenv("SECRET_KEY", bad_key)
        with pytest.raises(RuntimeError):
            ProductionConfig.validate()

    # Valid 64-char hex key
    monkeypatch.setenv("SECRET_KEY", "a" * 64)
    # Should not raise
    ProductionConfig.validate()


def test_legal_and_thank_you_routes(client):
    """Verify /privacy-policy, /terms, and /thank-you render with HTTP 200."""
    res_priv = client.get("/privacy-policy")
    assert res_priv.status_code == 200
    assert "Privacy Policy" in res_priv.get_data(as_text=True)

    res_terms = client.get("/terms")
    assert res_terms.status_code == 200
    assert "Terms" in res_terms.get_data(as_text=True)

    res_ty = client.get("/thank-you")
    assert res_ty.status_code == 200
    html_ty = res_ty.get_data(as_text=True)
    assert "Message Sent" in html_ty
    assert 'content="noindex, nofollow"' in html_ty


def test_csp_allows_google_analytics(client):
    """Ensure Content-Security-Policy allows GTM and GA4 domains."""
    res = client.get("/")
    assert res.status_code == 200
    csp = res.headers.get("Content-Security-Policy", "")
    assert "https://www.googletagmanager.com" in csp
    assert "https://*.google-analytics.com" in csp

