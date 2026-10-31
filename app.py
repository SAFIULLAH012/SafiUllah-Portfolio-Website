"""
Flask Portfolio CMS — Application Factory
"""
import os
import logging
import click
from datetime import datetime, timezone

from flask import Flask, render_template
from dotenv import load_dotenv

from config import config_map
from extensions import db, csrf, mail, limiter
from utils.security import apply_security_headers

_base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_base_dir, ".env"))


def create_app(env: str | None = None) -> Flask:
    """Create and configure the Flask application."""
    if env is None:
        env = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__, instance_relative_config=False)

    # ── Load config ───────────────────────────────────────────────────────────
    cfg = config_map.get(env, config_map["default"])
    app.config.from_object(cfg)

    # ── Production secret key validation ─────────────────────────────────────
    if env == "production":
        try:
            cfg.validate()
        except RuntimeError as e:
            raise RuntimeError(str(e)) from e

    # Ensure upload directory exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ── Init extensions ───────────────────────────────────────────────────────
    db.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)

    # ── Ensure database tables & seed exist ────────────────────────────────────
    with app.app_context():
        try:
            db.create_all()
            _seed_database()
        except Exception as e:
            app.logger.warning("Database auto-init notice: %s", e)

    # ── Jinja Filters & Context Processors ──────────────────────────────────
    import json
    @app.template_filter("from_json")
    def from_json_filter(value):
        try:
            return json.loads(value) if value else []
        except (ValueError, TypeError):
            return []

    @app.context_processor
    def inject_globals():
        return {"now": lambda: datetime.now(timezone.utc)}

    # ── Security headers & ProxyFix ───────────────────────────────────────────
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.after_request(apply_security_headers)

    # ── Register blueprints ───────────────────────────────────────────────────
    from blueprints.public import public_bp
    from blueprints.admin import admin_bp
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    # ── SEO: robots.txt & sitemap.xml ─────────────────────────────────────────
    register_seo_routes(app)

    # ── Error handlers ────────────────────────────────────────────────────────
    register_error_handlers(app)

    # ── CLI commands ──────────────────────────────────────────────────────────
    register_cli_commands(app)

    # ── Logging ───────────────────────────────────────────────────────────────
    configure_logging(app)

    return app


def register_seo_routes(app: Flask) -> None:
    """Register robots.txt, sitemap.xml, and legal pages for SEO."""
    from flask import Response, request as flask_request
    from models import Project

    @app.route("/robots.txt")
    def robots_txt():
        host = flask_request.host_url.rstrip("/")
        content = (
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /admin/\n"
            "Disallow: /admin/login\n"
            "\n"
            f"Sitemap: {host}/sitemap.xml\n"
        )
        return Response(content, mimetype="text/plain")

    @app.route("/sitemap.xml")
    def sitemap_xml():
        from datetime import datetime, timezone
        from models import Project, SiteSettings
        host = flask_request.host_url.rstrip("/")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        settings = None
        try:
            settings = SiteSettings.query.first()
        except Exception:
            pass

        home_mod = settings.updated_at.strftime("%Y-%m-%d") if (settings and settings.updated_at) else today

        pages = [
            {"loc": f"{host}/", "priority": "1.0", "changefreq": "weekly", "lastmod": home_mod},
            {"loc": f"{host}/privacy-policy", "priority": "0.3", "changefreq": "yearly", "lastmod": "2026-10-10"},
            {"loc": f"{host}/terms", "priority": "0.3", "changefreq": "yearly", "lastmod": "2026-10-10"},
        ]

        # Dynamic project pages with authentic lastmod
        try:
            projects = Project.query.filter_by(published=True).order_by(Project.display_order.asc()).all()
            for p in projects:
                p_mod = p.updated_at.strftime("%Y-%m-%d") if p.updated_at else today
                pages.append({
                    "loc": f"{host}/projects/{p.slug}",
                    "priority": "0.8",
                    "changefreq": "monthly",
                    "lastmod": p_mod,
                })
        except Exception:
            pass

        xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        for page in pages:
            xml_lines.append("  <url>")
            xml_lines.append(f"    <loc>{page['loc']}</loc>")
            xml_lines.append(f"    <lastmod>{page['lastmod']}</lastmod>")
            xml_lines.append(f"    <changefreq>{page['changefreq']}</changefreq>")
            xml_lines.append(f"    <priority>{page['priority']}</priority>")
            xml_lines.append("  </url>")
        xml_lines.append("</urlset>")

        return Response("\n".join(xml_lines), mimetype="application/xml")

    @app.route("/privacy-policy")
    def privacy_policy():
        from models import SiteSettings as Settings
        settings = Settings.query.first()
        return render_template("privacy_policy.html", settings=settings)

    @app.route("/terms")
    def terms():
        from models import SiteSettings as Settings
        settings = Settings.query.first()
        return render_template("terms.html", settings=settings)

    @app.route("/thank-you")
    def thank_you():
        from models import SiteSettings as Settings
        settings = Settings.query.first()
        name = flask_request.args.get("name", "")
        email = flask_request.args.get("email", "")
        return render_template("thank_you.html", settings=settings, name=name, email=email)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(400)
    def bad_request(e):
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return render_template("errors/404.html"), 405

    @app.errorhandler(429)
    def too_many_requests(e):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Internal server error")
        return render_template("errors/500.html"), 500


def register_cli_commands(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Create database tables and seed default content."""
        with app.app_context():
            db.create_all()
            _seed_database()
            click.echo("Database initialized and seeded.")

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.argument("email")
    @click.password_option()
    def create_admin(username, email, password):
        """Create an admin account."""
        from models import Admin
        with app.app_context():
            db.create_all()
            if Admin.query.filter_by(username=username).first():
                click.echo(f"Admin '{username}' already exists.")
                return
            admin = Admin(username=username, email=email)
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()
            click.echo(f"Admin account '{username}' created successfully.")

    @app.cli.command("reset-password")
    @click.argument("username")
    def reset_password(username):
        """Reset the password and/or username for an existing admin account."""
        from models import Admin, AdminOTP
        from utils.security import send_otp_email
        import click
        with app.app_context():
            admin = Admin.query.filter_by(username=username).first()
            if not admin:
                click.echo(f"Error: Admin user '{username}' not found.")
                return

            past_password = click.prompt("Past password", hide_input=True)
            if not admin.check_password(past_password):
                click.echo("Error: Incorrect past password.")
                return

            click.echo(f"Generating OTP for {admin.email}...")
            otp_code = AdminOTP.generate_otp(admin.id, purpose="cli_reset", valid_minutes=10)
            sent = send_otp_email(admin.email, otp_code, "CLI credential reset")
            if not sent:
                click.echo(f"Warning: SMTP not configured. Generated OTP is: {otp_code}")

            entered_otp = click.prompt("Enter OTP")
            if not AdminOTP.verify_otp(admin.id, entered_otp, purpose="cli_reset"):
                click.echo("Error: Invalid or expired OTP.")
                return

            new_username = click.prompt("New username (leave blank to keep current)", default=admin.username)
            if new_username and new_username != admin.username:
                existing = Admin.query.filter_by(username=new_username).first()
                if existing:
                    click.echo(f"Error: Username '{new_username}' is already taken.")
                    return
                admin.username = new_username

            new_password = click.prompt("New password (leave blank to keep current)", default="", hide_input=True)
            if new_password:
                admin.set_password(new_password)

            db.session.commit()
            click.echo(f"Credentials for admin '{admin.username}' have been updated successfully.")



def _seed_database() -> None:
    """Seed the database with initial portfolio data."""
    from models import (
        Admin, Project, Skill, Education, SiteSettings,
    )
    import json

    # Auto-migration: ensure newly added columns exist in sqlite table
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE site_settings ADD COLUMN whatsapp_number VARCHAR(50) DEFAULT '923477845540'"))
            conn.commit()
    except Exception:
        pass

    # Settings
    settings_obj = SiteSettings.query.first()
    if not settings_obj:
        s = SiteSettings(
            name="Safi Ullah",
            headline="Computer Science Student & ML Learner",
            bio=(
                "Computer Science student at the University of Layyah with a CGPA of 3.94/4.0. "
                "Passionate about machine learning, computer vision, and Python development. "
                "I enjoy learning through hands-on project building—developing image classification models, "
                "data regression pipelines, and real-time computer vision applications."
            ),
            location="Pakistan",
            contact_email="safiullah477845@gmail.com",
            github_url="https://github.com/SAFIULLAH012",
            linkedin_url="https://www.linkedin.com/in/safiullah012",
            whatsapp_number="923477845540",
            site_title="Safi Ullah | AI & Machine Learning Engineer Portfolio",
            meta_description=(
                "Explore Machine Learning, Computer Vision, and Deep Learning projects built by Safi Ullah, "
                "AI & Machine Learning Engineer from Pakistan."
            ),
            hero_description=(
                "Computer Science student passionate about Machine Learning and Computer Vision. "
                "Dedicated to building practical projects, learning modern AI technologies, and developing clean Python applications."
            ),
            hero_tags=json.dumps(["Computer Science Student", "Machine Learning Learner", "Computer Vision Enthusiast"]),
            about_domain="Computer Science & Machine Learning",
            why_work_with_me=json.dumps([
                "Solid academic foundation in Computer Science & Data Structures (CGPA: 3.94)",
                "Hands-on experience building Computer Vision & Machine Learning projects",
                "Quick learner eager to tackle new challenges and grow technical skills",
                "Experience developing and deploying Python & Flask web applications"
            ]),
            projects_badge_count="7+",
            github_handle="@SAFIULLAH012",
            availability="Open for Opportunities",
            profile_image="img/safiullah_profile.jpeg",
        )
        db.session.add(s)
    else:
        if settings_obj.site_title == "Safi Ullah | Computer Science & Machine Learning Portfolio":
            settings_obj.site_title = "Safi Ullah | AI & Machine Learning Engineer Portfolio"
        if not settings_obj.meta_description:
            settings_obj.meta_description = "Explore Machine Learning, Computer Vision, and Deep Learning projects built by Safi Ullah, AI & Machine Learning Engineer from Pakistan."
        db.session.commit()

    # Skills
    if not Skill.query.first():
        skills_data = [
            {"name": "Python", "category": "Programming", "proficiency": 95,
             "icon_class": "fab fa-python",
             "tags": json.dumps(["Python 3", "OOP", "Data Structures"]), "display_order": 1},
            {"name": "Machine Learning", "category": "Machine Learning", "proficiency": 82,
             "icon_class": "fas fa-chart-line",
             "tags": json.dumps(["Scikit-Learn", "NumPy", "Pandas", "Pipelines"]), "display_order": 2},
            {"name": "Computer Vision", "category": "Computer Vision", "proficiency": 75,
             "icon_class": "fas fa-eye",
             "tags": json.dumps(["OpenCV", "MediaPipe", "ALPR", "Face Mesh"]), "display_order": 3},
            {"name": "Deep Learning & CNNs", "category": "Deep Learning", "proficiency": 75,
             "icon_class": "fas fa-brain",
             "tags": json.dumps(["TensorFlow", "Keras", "CNN", "MobileNetV2"]), "display_order": 4},
            {"name": "Data Analysis", "category": "Data Science", "proficiency": 75,
             "icon_class": "fas fa-database",
             "tags": json.dumps(["Pandas", "Matplotlib", "Seaborn", "EDA"]), "display_order": 5},
            {"name": "Flask & APIs", "category": "Web & Deployment", "proficiency": 60,
             "icon_class": "fas fa-server",
             "tags": json.dumps(["Flask", "REST API", "Streamlit", "Docker"]), "display_order": 6},
        ]
        for sd in skills_data:
            db.session.add(Skill(**sd))
    else:
        # Sync skill proficiencies for accurate default levels
        for s in Skill.query.all():
            nl = s.name.lower()
            if "python" in nl and s.proficiency < 90:
                s.proficiency = 95
            elif ("machine learning" in nl or nl == "ml") and (s.proficiency < 80 or s.proficiency >= 90):
                s.proficiency = 82
            elif ("flask" in nl or "api" in nl) and s.proficiency > 65:
                s.proficiency = 60
            elif ("deep" in nl or "vision" in nl or "analysis" in nl) and s.proficiency > 79:
                s.proficiency = 75
        db.session.commit()

    # Education
    from models import Education
    if not Education.query.first():
        edu_data = [
            {"institution": "D.G Khan Board, Punjab", "degree": "Matriculation (Science)",
             "level": "Matric", "score": "1067/1100", "score_label": "Score",
             "description": "Completed secondary education with distinction in science subjects.",
             "display_order": 1},
            {"institution": "D.G Khan Board, Punjab", "degree": "Intermediate in Computer Science (ICS)",
             "level": "Computer Science", "score": "990/1100", "score_label": "Score",
             "description": "Built strong foundations in programming logic, mathematics, algorithm design, and computer architecture.",
             "display_order": 2},
            {"institution": "University of Layyah, Hafizabad", "degree": "BSc Computer Science",
             "level": "BSc Computer Science", "score": "3.94/4.0", "score_label": "CGPA",
             "description": "3 semesters completed. Focus on algorithms, data structures, and applied AI/ML.",
             "display_order": 3},
            {"institution": "Self-Directed Study", "degree": "Deep Learning & Computer Vision Engineering",
             "level": "Artificial Intelligence & ML", "score": "7+", "score_label": "Projects",
             "description": "Built neural networks, computer vision tools, and ML pipelines across 7+ published GitHub repositories.",
             "display_order": 4},
        ]
        for ed in edu_data:
            db.session.add(Education(**ed))

# Projects with in-depth engineering write-ups to eliminate thin content
    projects_data = [
        {
            "title": "Brain Tumor MRI Classifier (NeuroScan AI)",
            "slug": "brain-tumor-mri-classifier",
            "short_description": "MobileNetV2 transfer learning model classifying brain MRI scans as tumor/no-tumor with Grad-CAM visual explainability.",
            "description": (
                "NeuroScan AI is a research-oriented deep learning application developed to classify brain magnetic "
                "resonance imaging (MRI) scans into Tumor-Detected versus Non-Tumor (Normal) anatomical categories. "
                "Built using transfer learning with a fine-tuned MobileNetV2 convolutional backbone, the system is designed "
                "to explore the efficacy of lightweight neural architectures in biomedical image screening pipelines. "
                "To address the 'black-box' nature of deep neural networks in clinical contexts, the application integrates "
                "Gradient-weighted Class Activation Mapping (Grad-CAM), generating visual activation heatmaps that highlight "
                "the exact spatial regions and tissue anomalies influencing classification decisions. This enables developers "
                "and researchers to verify that model predictions are based on relevant pathological features rather than "
                "spurious background artifacts."
            ),
            "problem_statement": (
                "Accurate manual interpretation of cranial MRI sequences requires extensive radiologist expertise and is "
                "subject to inter-observer variability, particularly in high-volume triage scenarios. This engineering "
                "project explores whether computer vision pipelines can achieve high sensitivity (low false-negative rate) "
                "in binary tumor triage, while maintaining explainability through feature attribution heatmaps. "
                "Note: This software is engineered strictly for research, educational, and bench-testing purposes and is "
                "not a certified diagnostic medical device."
            ),
            "category": "Computer Vision / Deep Learning",
            "github_url": "https://github.com/SAFIULLAH012/Tumor_VS-NON_tumor",
            "dataset": (
                "Evaluated on a comprehensive benchmark of ~26,500 labeled brain MRI scans (13,273 non-tumor and 13,252 "
                "tumor images across axial, sagittal, and coronal planes). Partitioned using a rigorous 70/15/15 stratified "
                "train/validation/test split to prevent data contamination and ensure consistent class distribution across "
                "all evaluation subsets."
            ),
            "model_architecture": (
                "Constructed using MobileNetV2 pre-trained on ImageNet as a feature extraction foundation, with top "
                "convolutional blocks unfreezed for domain-specific fine-tuning. Head architecture incorporates a "
                "GlobalAveragePooling2D layer, BatchNormalization, a Dropout rate of 0.3 for regularization, and a single "
                "Dense unit with Sigmoid activation. Trained via binary cross-entropy loss and the Adam optimizer with cosine decay."
            ),
            "preprocessing": (
                "Input scans are dynamically resized to 224x224x3, scaled to [0, 1] floating-point ranges, and passed through "
                "real-time training augmentations including horizontal flips, small-angle random rotations (+-15 degrees), "
                "shear transformations, and zoom variations to guard against overfitting."
            ),
            "metrics": json.dumps({"accuracy": "95.2%", "precision": "94.8%", "recall": "95.7%", "f1": "95.2%", "roc_auc": "0.98"}),
            "technologies": json.dumps(["TensorFlow", "Keras", "MobileNetV2", "Grad-CAM", "FastAPI", "OpenCV", "Python"]),
            "results": (
                "Achieved a test accuracy of 95.2%, a sensitivity (recall) of 95.7%, precision of 94.8%, and an area under "
                "the ROC curve (ROC-AUC) of 0.98. Grad-CAM visual overlays demonstrated high spatial fidelity with labeled "
                "lesion masks across diverse pathological morphologies."
            ),
            "limitations": (
                "Trained predominantly on public benchmark datasets with homogeneous acquisition protocols. Requires further "
                "validation against heterogeneous multi-center scans with varying MRI magnetic field strengths (1.5T vs 3.0T). "
                "Not cleared for clinical diagnostic workflows."
            ),
            "future_improvements": (
                "Expansion to multi-class histological differentiation (glioma, meningioma, pituitary adenoma), 3D volumetric "
                "segmentation using U-Net architectures, and deployment as an asynchronous DICOM-compatible microservice."
            ),
            "featured": True, "published": True, "display_order": 1,
        },
        {
            "title": "Framingham CHD Risk Prediction",
            "slug": "heart-disease-prediction",
            "short_description": "Binary classification model predicting 10-year coronary heart disease risk from the Framingham Heart Study dataset (4,238 patients).",
            "description": (
                "A clinical machine learning prognostic pipeline designed to forecast 10-year risk of future Coronary "
                "Heart Disease (CHD) based on patient biometric indicators from the Framingham Heart Study. The system "
                "implements a rigorous data science workflow addressing real-world healthcare predictive challenges, including "
                "severe class imbalance (~15% positive incident rate), multi-collinear clinical predictors, and missing "
                "physiological measurements. Multiple classification algorithms—including L2-regularized Logistic Regression, "
                "Random Forest Ensembles, and Histogram-based Gradient Boosting—were benchmarked using stratified cross-validation."
            ),
            "problem_statement": (
                "Cardiovascular disease remains the leading global cause of mortality, making early identification of "
                "asymptomatic individuals critical for preventive intervention. This project investigates whether clinical "
                "biomarkers (blood pressure, lipid profiles, glycemic measures, smoking history, age) can reliably stratify "
                "10-year cardiovascular risk in imbalanced longitudinal cohorts without introducing data leakage."
            ),
            "category": "Machine Learning / Healthcare",
            "github_url": "https://github.com/SAFIULLAH012/heart-disease-prediction",
            "dataset": (
                "The Framingham Heart Study dataset comprising 4,238 clinical observation records across 15 biometric, "
                "demographic, and behavioral features: age, systolic/diastolic blood pressure, total serum cholesterol, "
                "body mass index (BMI), fasting glucose, smoking frequency, hypertension treatment, and cardiovascular event outcomes."
            ),
            "model_architecture": (
                "A comparative evaluation framework assessing Logistic Regression with balanced class weights, Random Forest "
                "Classifiers with cost-sensitive tuning, and Histogram Gradient Boosting. The final deployed pipeline utilizes "
                "calibrated Logistic Regression, which demonstrated superior clinical sensitivity and probabilistic calibration "
                "over complex non-linear ensembles on this feature set."
            ),
            "preprocessing": (
                "Strict train-only median and mode imputation for clinical missing values to eliminate data snooping leakage. "
                "Numerical features transformed using Yeo-Johnson power scaling, continuous features normalized via StandardScaler, "
                "and stratified 70/15/15 cohort partitioning."
            ),
            "metrics": json.dumps({"accuracy": "67%", "precision": "25%", "recall": "58%", "f1": "35%", "roc_auc": "0.70"}),
            "technologies": json.dumps(["Scikit-Learn", "Pandas", "NumPy", "Seaborn", "Matplotlib", "Streamlit", "Python"]),
            "results": (
                "Logistic Regression achieved an optimal balance for screening objectives with a test Recall of 58% and an "
                "ROC-AUC of 0.70. Rather than reporting misleading overall accuracy (which obscures minority class detection "
                "in 85:15 imbalanced data), performance was comprehensively evaluated via precision-recall trade-offs and F1 scores."
            ),
            "limitations": (
                "Observational data reflects epidemiological distributions from a specific geographic cohort. Non-linear "
                "interaction effects were constrained by moderate feature correlation ceilings (maximum single-feature Pearson r=0.225)."
            ),
            "future_improvements": (
                "Integration of cost-sensitive threshold optimization, Bayesian clinical calibration curves, and feature extension "
                "to modern lifestyle biomarkers (dietary, genetic, and wearable heart-rate telemetry)."
            ),
            "featured": True, "published": True, "display_order": 2,
        },
        {
            "title": "OpenCV & MediaPipe Vision Lab",
            "slug": "opencv-mediapipe-lab",
            "short_description": "Real-time vision suite featuring ALPR (license plate detection), 3D hand tracking, face mesh, and gesture recognition.",
            "description": (
                "The Vision Lab is a high-performance, real-time computer vision and perceptual computing suite engineered "
                "using OpenCV, MediaPipe, and Python. The laboratory features multiple integrated perceptual modules: an "
                "Automatic License Plate Recognition (ALPR) pipeline with optical character recognition, a high-fidelity 3D "
                "hand skeleton tracker mapping 21 spatial landmarks per hand, and a real-time 468-point facial landmark mesh "
                "overlay for non-invasive biometric and expression tracking. Engineered to maintain sub-40ms end-to-end latency "
                "and sustained 25+ frames-per-second throughput on commodity hardware."
            ),
            "problem_statement": (
                "Real-time edge computer vision requires balancing deep neural network inference accuracy with stringent computational "
                "constraints. This project explores practical computer vision engineering techniques for image acquisition, spatial "
                "coordinate transformation, temporal smoothing, and optical character extraction without relying on heavyweight cloud GPU clusters."
            ),
            "category": "Computer Vision",
            "github_url": "https://github.com/SAFIULLAH012/opencv_learning",
            "dataset": (
                "Evaluated on continuous 720p/1080p live video capture streams across diverse ambient illuminations, supplemented "
                "by static vehicle and license plate test datasets representing varied viewing angles and alphanumeric character fonts."
            ),
            "model_architecture": (
                "MediaPipe Hands leveraging a two-stage detector-tracker pipeline (BlazePalm detector followed by 2.5D landmark regression), "
                "MediaPipe Face Mesh utilizing 468 3D vertices, and an OpenCV pipeline combining Bilateral Filtering, Canny Edge Detection, "
                "Contour Geometry Filtering, and Tesseract OCR Engine."
            ),
            "preprocessing": (
                "BGR to RGB color-space conversion, adaptive histogram equalization (CLAHE) for illumination variance, bilinear frame "
                "resizing, perspective four-point homography warping, and threshold binarization for plate regions."
            ),
            "metrics": json.dumps({"hand_tracking_fps": "~25 FPS", "face_mesh_landmarks": "468"}),
            "technologies": json.dumps(["OpenCV", "MediaPipe", "Python", "Tesseract", "NumPy"]),
            "results": (
                "Delivers sustained 25+ FPS real-time execution on standard CPU hardware. Hand landmark tracking maintains stable sub-pixel "
                "jitter tolerances, and ALPR demonstrates reliable character segmentation on standard high-contrast vehicle plates."
            ),
            "limitations": (
                "OCR performance degrades in extreme oblique perspective angles, motion blur, or low-light conditions. MediaPipe models "
                "are constrained to single or dual-subject interactions within the camera frame frustum."
            ),
            "future_improvements": (
                "Integration of YOLOv8-based vehicle and license plate localization, custom deep-learning character recognition tailored "
                "for regional plate typography, and WebSocket streaming for browser-based interactive feeds."
            ),
            "featured": True, "published": True, "display_order": 3,
        },
        {
            "title": "Flight Price Prediction",
            "slug": "flight-price-prediction",
            "short_description": "End-to-end ML regression pipeline predicting airline ticket prices from flight features using Scikit-Learn.",
            "description": (
                "An end-to-end predictive analytics and machine learning regression engine developed to model and forecast "
                "domestic airline ticket pricing trends. Commercial aviation employs sophisticated yield management and dynamic "
                "revenue algorithms, resulting in volatile ticket prices influenced by temporal, route, carrier, and operational "
                "factors. This project implements comprehensive exploratory data analysis, domain-specific feature engineering, "
                "and ensemble regression modeling to explain the key economic drivers behind ticket price fluctuations."
            ),
            "problem_statement": (
                "Air travel consumers frequently encounter unpredictable price swings, complicating budget planning. This system "
                "addresses the regression problem of estimating flight fares given booking parameters (departure timing, route complexity, "
                "stop frequency, airline carrier) to provide quantitative transparency into dynamic airline pricing behaviors."
            ),
            "category": "Machine Learning / Regression",
            "github_url": "https://github.com/SAFIULLAH012/Flight-Price-Prediction",
            "dataset": (
                "A comprehensive dataset of 10,683 commercial domestic flight records encompassing multiple airlines (Air India, IndiGo, "
                "Jet Airways, SpiceJet, Multiple Carriers), departure/arrival timestamps, source and destination city pairs, layover stops, "
                "and recorded ticket prices."
            ),
            "model_architecture": (
                "Random Forest Regressor optimized with randomized hyperparameter tuning (n_estimators, max_depth, min_samples_split, "
                "min_samples_leaf) and benchmarked against Linear Regression, Ridge, and Extra Trees Regressors. Validated through 5-fold cross-validation."
            ),
            "preprocessing": (
                "Temporal feature decomposition extracting Journey Day, Journey Month, Departure Hour/Minute, and Arrival Hour/Minute. "
                "Journey duration strings parsed into total numerical minutes. Categorical variables transformed using One-Hot Encoding for "
                "non-ordinal features (Airline, Source, Destination) and ordinal mapping for Total Stops."
            ),
            "metrics": json.dumps({"r2_score": "~0.81", "mae": "~1,200 INR"}),
            "technologies": json.dumps(["Scikit-Learn", "Pandas", "NumPy", "Matplotlib", "Python"]),
            "results": (
                "The tuned Random Forest model attained an R² determination coefficient of 0.81 on the held-out test set with a Mean "
                "Absolute Error (MAE) of ~1,200 INR. Feature importance extraction confirmed that flight duration, total stops, and airline "
                "carrier account for over 70% of pricing variance."
            ),
            "limitations": (
                "Prices reflect historical booking snapshots and do not incorporate real-time seat inventory levels, sudden fuel surcharges, "
                "macroeconomic inflation, or holiday surge demand."
            ),
            "future_improvements": (
                "Incorporation of real-time flight API scrapers, implementation of XGBoost and LightGBM gradient boosting architectures, "
                "and deployment as an interactive fare prediction web application."
            ),
            "featured": False, "published": True, "display_order": 4,
        },
        {
            "title": "House Price Prediction",
            "slug": "house-price-prediction",
            "short_description": "Real estate valuation model using feature engineering and ensemble regression on house attributes.",
            "description": (
                "A data science and regression modeling framework engineered for automated real estate valuation. Residential property "
                "pricing represents a classic multivariate estimation problem characterized by high non-linearities, spatial dependencies, "
                "skewed financial target variables, and multi-collinear architectural features. This project develops an end-to-end "
                "pipeline encompassing statistical hypothesis testing, robust outlier remediation, target variable transformations, "
                "and regularized regression benchmarks."
            ),
            "problem_statement": (
                "Property buyers, appraisers, and financial lenders require accurate, objective valuations based on structural and location "
                "parameters rather than subjective estimates. This engineering solution models residential prices from physical dwelling "
                "characteristics while mitigating statistical bias from skewed distributions."
            ),
            "category": "Machine Learning / Regression",
            "github_url": "https://github.com/SAFIULLAH012/House_Price_Prediction",
            "dataset": (
                "A multi-dimensional residential real estate dataset comprising properties across varied zoning sectors, capturing physical "
                "specifications: above-grade living area, total basement square footage, bedroom counts, full/half bathrooms, garage capacity, "
                "lot size, construction year, and neighborhood classifications."
            ),
            "model_architecture": (
                "A multi-model comparative architecture evaluating L1-regularized Lasso, L2-regularized Ridge Regression, Random Forest Ensembles, "
                "and Gradient Boosting Regressors. Models were evaluated using 10-fold cross-validation and root mean squared error metrics."
            ),
            "preprocessing": (
                "Target variable normalized using natural logarithmic transformation (log1p) to remediate positive skewness. Numerical features "
                "normalized with RobustScaler to insulate against extreme outliers. Missing values treated through neighborhood-grouped median "
                "imputation, and categorical variables converted via target and one-hot encoding."
            ),
            "metrics": json.dumps({"r2_score": "~0.78", "rmse": "0.14 RMSLE"}),
            "technologies": json.dumps(["Scikit-Learn", "Pandas", "NumPy", "Seaborn", "Python"]),
            "results": (
                "Achieved a test R² score of 0.78, with a significantly minimized Root Mean Squared Log Error (RMSLE). Statistical feature "
                "importance confirmed that above-grade living square footage, overall construction quality, and neighborhood tier constitute "
                "the primary valuation drivers."
            ),
            "limitations": (
                "Model is parameterized for specific geographical regions; physical housing attributes vary across different metropolitan "
                "and rural property markets."
            ),
            "future_improvements": (
                "Integration of geospatial GIS coordinates (distance to transit hubs, schools, commercial districts), automated computer vision "
                "appraisal of property photos, and interactive mortgage calculator deployment."
            ),
            "featured": False, "published": True, "display_order": 5,
        },
        {
            "title": "Cat vs Dog CNN Classifier",
            "slug": "cat-dog-cnn-classifier",
            "short_description": "Convolutional Neural Network trained for binary image classification of cats and dogs with training/validation curves.",
            "description": (
                "A deep convolutional neural network (CNN) engineered from scratch for high-accuracy binary visual classification "
                "between felines and canines. Designed as a foundational study in computer vision architecture design, the project "
                "systematically investigates the impact of receptive field sizing, batch normalization placement, spatial pooling "
                "strategies, and aggressive data augmentation on preventing catastrophic overfitting in deep visual classifiers."
            ),
            "problem_statement": (
                "Fine-grained animal classification presents notable computer vision hurdles due to significant intra-class variation "
                "in breed appearance, scale, body posture, lighting conditions, and cluttered background environments. The objective "
                "was to design and train a deep convolutional network achieving robust generalization without relying on pre-trained weights."
            ),
            "category": "Deep Learning / Computer Vision",
            "github_url": "https://github.com/SAFIULLAH012/CAT_DOG_CLASSIFIER",
            "dataset": (
                "The standard Kaggle Dogs vs. Cats benchmark dataset consisting of 25,000 high-resolution color photographs evenly split "
                "(12,500 cats, 12,500 dogs). Structured into a rigorous 20,000 training, 2,500 validation, and 2,500 held-out test split."
            ),
            "model_architecture": (
                "A 4-stage convolutional neural network comprising sequential blocks: Conv2D (32, 64, 128, 256 filters with 3x3 kernels "
                "and ReLU activations), interspersed with BatchNormalization and MaxPooling2D (2x2). Feature maps are flattened through "
                "a Dense layer with 512 units and Dropout(0.5), feeding a final single-neuron Sigmoid output. Compiled with Adam optimizer."
            ),
            "preprocessing": (
                "Images dynamically standardized to 150x150 pixels, pixel intensity normalized to [0, 1]. Training pipeline integrates "
                "on-the-fly data augmentation: 40-degree random rotations, 20% width/height shifts, 20% zoom ranges, shear transformations, "
                "and horizontal flips."
            ),
            "metrics": json.dumps({"test_accuracy": "89.4%", "val_accuracy": "88.7%"}),
            "technologies": json.dumps(["TensorFlow", "Keras", "CNN", "NumPy", "Matplotlib", "Python"]),
            "results": (
                "The scratch convolutional network attained an 89.4% test classification accuracy. Training curves confirmed stable "
                "convergence, with dropout and batch normalization successfully preventing the validation loss divergence typical of "
                "unregularized visual classifiers."
            ),
            "limitations": (
                "Trained strictly for binary domestic pet recognition; does not generalize to exotic feline or wild canine species, "
                "or severely degraded low-resolution imagery."
            ),
            "future_improvements": (
                "Benchmarking against modern transfer-learning architectures (EfficientNet-B0, Vision Transformers), multi-class "
                "domestic breed classification, and ONNX runtime export for edge mobile deployment."
            ),
            "featured": False, "published": True, "display_order": 6,
        },
        {
            "title": "Laptop Price Prediction",
            "slug": "laptop-price-prediction",
            "short_description": "Regression model predicting laptop prices from hardware specifications using feature engineering.",
            "description": (
                "A machine learning predictive analytics pipeline engineered to estimate current consumer retail prices of laptops "
                "based on complex hardware architectures and component specifications. Consumer electronics pricing is driven by "
                "multi-attribute interactions among semiconductor generations, volatile memory bandwidths, display panel technologies, "
                "and form factor manufacturing. This project implements advanced text feature extraction, feature engineering, and ensemble "
                "regression to deliver accurate, automated market price appraisals."
            ),
            "problem_statement": (
                "With hundreds of computing configurations spanning disparate brands and specification tiers, consumers and retailers "
                "struggle to benchmark fair market value. This system formulates an algorithmic pricing model mapping technical specifications "
                "to market prices."
            ),
            "category": "Machine Learning / Regression",
            "github_url": "https://github.com/SAFIULLAH012/Laptop-Price-Prediction",
            "dataset": (
                "A curated dataset of 1,303 laptop configurations from leading manufacturers (Apple, HP, Dell, Lenovo, Asus, Acer, MSI, "
                "Toshiba), tracking 12 technical attributes including company, product type, RAM size, storage media, GPU chipset, "
                "operating system, weight, and retail price."
            ),
            "model_architecture": (
                "Comprehensive regression benchmarking comparing Linear Regression, Ridge, Random Forest Regressor, and Gradient Boosting "
                "Regressors. Optimized using RandomizedSearchCV with 10-fold cross-validation."
            ),
            "preprocessing": (
                "Advanced regular expression parsing extracting resolution dimensions, IPS panel flags, and Touchscreen capabilities from "
                "screen specifications. CPU strings decomposed into manufacturer and tier (Intel Core i5/i7/i9, AMD Ryzen). Hybrid storage "
                "parsed into distinct SSD and HDD capacities (in GB). Target price normalized using logarithmic scaling."
            ),
            "metrics": json.dumps({"r2_score": "0.84", "mape": "11.2%"}),
            "technologies": json.dumps(["Scikit-Learn", "Pandas", "NumPy", "Python"]),
            "results": (
                "Attained an R² determination score of 0.84 on the test partition, with a Mean Absolute Percentage Error (MAPE) of 11.2%. "
                "Feature importance analysis established that dedicated GPU memory, total RAM capacity, and CPU performance tier constitute "
                "the top three determinants of market value."
            ),
            "limitations": (
                "Dataset captures pricing from a specific fiscal quarter and does not reflect sudden supply chain semiconductor shortages "
                "or seasonal promotional discounts."
            ),
            "future_improvements": (
                "Continuous automated web scraping for dynamic catalog updates, integration of benchmark performance scores (Geekbench/3DMark), "
                "and development of an interactive recommendation interface."
            ),
            "featured": False, "published": True, "display_order": 7,
        },
    ]

    # Insert or update projects to ensure rich content is always live
    for pd in projects_data:
        p = Project.query.filter_by(slug=pd["slug"]).first()
        if p:
            # Upgrade existing project if content is thin (< 300 characters)
            if not p.description or len(p.description) < 300:
                p.description = pd["description"]
                p.problem_statement = pd["problem_statement"]
                p.dataset = pd["dataset"]
                p.model_architecture = pd["model_architecture"]
                p.preprocessing = pd["preprocessing"]
                p.results = pd["results"]
                p.limitations = pd["limitations"]
                p.future_improvements = pd["future_improvements"]
                p.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            db.session.add(Project(**pd))

    db.session.commit()


def configure_logging(app: Flask) -> None:
    """Configure structured logging — never log passwords or secrets."""
    os.makedirs("logs", exist_ok=True)
    log_level = logging.DEBUG if app.debug else logging.INFO

    handler = logging.FileHandler("logs/portfolio.log", encoding="utf-8")
    handler.setLevel(log_level)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
    app.logger.setLevel(log_level)

    # Suppress Flask-Limiter verbose output in production
    if not app.debug:
        logging.getLogger("flask_limiter").setLevel(logging.WARNING)


app = create_app()

if __name__ == "__main__":  # pragma: no cover
    # Binding to 0.0.0.0 is intentional for Docker/container deployment
    app.run(debug=app.config.get("DEBUG", False), host="0.0.0.0", port=5000)  # nosec B104
