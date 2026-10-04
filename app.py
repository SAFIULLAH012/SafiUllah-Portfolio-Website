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
        host = flask_request.host_url.rstrip("/")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Static pages
        pages = [
            {"loc": f"{host}/", "priority": "1.0", "changefreq": "weekly"},
            {"loc": f"{host}/#about", "priority": "0.8", "changefreq": "monthly"},
            {"loc": f"{host}/#skills", "priority": "0.8", "changefreq": "monthly"},
            {"loc": f"{host}/#projects", "priority": "0.9", "changefreq": "weekly"},
            {"loc": f"{host}/#education", "priority": "0.7", "changefreq": "monthly"},
            {"loc": f"{host}/#contact", "priority": "0.7", "changefreq": "monthly"},
            {"loc": f"{host}/privacy-policy", "priority": "0.4", "changefreq": "yearly"},
            {"loc": f"{host}/terms", "priority": "0.4", "changefreq": "yearly"},
        ]

        # Dynamic project pages
        try:
            projects = Project.query.filter_by(published=True).all()
            for p in projects:
                pages.append({
                    "loc": f"{host}/projects/{p.slug}",
                    "priority": "0.8",
                    "changefreq": "monthly",
                })
        except Exception:
            pass


        xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        for page in pages:
            xml_lines.append("  <url>")
            xml_lines.append(f"    <loc>{page['loc']}</loc>")
            xml_lines.append(f"    <lastmod>{today}</lastmod>")
            xml_lines.append(f"    <changefreq>{page['changefreq']}</changefreq>")
            xml_lines.append(f"    <priority>{page['priority']}</priority>")
            xml_lines.append("  </url>")
        xml_lines.append("</urlset>")

        return Response("\n".join(xml_lines), mimetype="application/xml")

    @app.route("/privacy-policy")
    def privacy_policy():
        from models import Settings
        settings = Settings.query.first()
        return render_template("privacy_policy.html", settings=settings)

    @app.route("/terms")
    def terms():
        from models import Settings
        settings = Settings.query.first()
        return render_template("terms.html", settings=settings)

    @app.route("/thank-you")
    def thank_you():
        from models import Settings
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

    # Projects
    if not Project.query.first():
        projects_data = [
            {
                "title": "Brain Tumor MRI Classifier (NeuroScan AI)",
                "slug": "brain-tumor-mri-classifier",
                "short_description": "MobileNetV2 transfer learning model classifying brain MRI scans as tumor/no-tumor with Grad-CAM visual explainability.",
                "description": (
                    "NeuroScan AI is a research-grade deep learning application that classifies brain MRI scans "
                    "as Tumor Detected or No Tumor (Normal). Built for educational and research purposes only — "
                    "not a clinical diagnostic tool."
                ),
                "problem_statement": (
                    "Brain tumor detection from MRI scans is a time-intensive task requiring specialist review. "
                    "This project explores whether a CNN trained on labeled MRI data can aid educational "
                    "understanding of classification pipelines. Not intended for clinical use."
                ),
                "category": "Computer Vision / Deep Learning",
                "github_url": "https://github.com/SAFIULLAH012/Tumor_VS-NON_tumor",
                "dataset": "~13,273 No-Tumor and ~13,252 Tumor (Augmented) brain MRI images. 70/15/15 train/val/test stratified split.",
                "model_architecture": "ImageNet pre-trained MobileNetV2 as feature extractor with fine-tuning. Added GlobalAveragePooling2D, Dropout(0.3), Dense(1, sigmoid). Data augmentation: random flips, rotations, zooms.",
                "preprocessing": "Resize to 224×224, normalize [0,1], balanced 1:1 class ratio, augmentation on training set only.",
                "metrics": json.dumps({"accuracy": "95.2%", "precision": "94.8%", "recall": "95.7%", "f1": "95.2%", "roc_auc": "0.98"}),
                "technologies": json.dumps(["TensorFlow", "Keras", "MobileNetV2", "Grad-CAM", "FastAPI", "OpenCV", "Python"]),
                "results": "Model achieves 95.2% test accuracy, 95.7% recall (sensitivity), and 0.98 ROC-AUC. Grad-CAM heatmaps successfully highlight tumor regions for interpretability.",
                "limitations": "Research/educational project only. Not validated for clinical use. Trained on a single dataset from a specific demographic. Results should not be used for medical decisions.",
                "future_improvements": "Multi-class classification (glioma, meningioma, pituitary). Threshold tuning for clinical sensitivity. External dataset validation.",
                "featured": True, "published": True, "display_order": 1,
            },
            {
                "title": "Framingham CHD Risk Prediction",
                "slug": "heart-disease-prediction",
                "short_description": "Binary classification model predicting 10-year coronary heart disease risk from the Framingham Heart Study dataset (4,238 patients).",
                "description": (
                    "A thorough binary classification project predicting 10-year CHD risk. "
                    "Trained Logistic Regression, Random Forest, and HistGradientBoosting on the Framingham dataset. "
                    "Logistic Regression wins on Recall (0.58) and ROC-AUC (0.70) — a deliberately documented "
                    "finding, not a flaw."
                ),
                "problem_statement": "Predict whether a patient will develop coronary heart disease in the next 10 years using clinical features including age, blood pressure, smoking status, and cholesterol.",
                "category": "Machine Learning / Healthcare",
                "github_url": "https://github.com/SAFIULLAH012/heart-disease-prediction",
                "dataset": "Framingham Heart Study dataset: 4,238 patients, 15 clinical features, ~15% positive class (class-imbalanced).",
                "model_architecture": "Three models compared: Logistic Regression (deployed), Random Forest, HistGradientBoosting. 5-fold stratified cross-validation. Leakage-safe train-only imputation.",
                "preprocessing": "Missing value imputation using train-only fill values (no data leakage). Feature engineering on clinical variables. Stratified 70/15/15 split.",
                "metrics": json.dumps({"accuracy": "67%", "precision": "25%", "recall": "58%", "f1": "35%", "roc_auc": "0.70"}),
                "technologies": json.dumps(["Scikit-Learn", "Pandas", "NumPy", "Seaborn", "Matplotlib", "Streamlit", "Python"]),
                "results": "Logistic Regression selected as deployed model: highest recall (0.58) and ROC-AUC (0.70). Accuracy alone is misleading for imbalanced data — reporting precision/recall/F1/AUC instead.",
                "limitations": "Weak classifier by absolute standards (25% precision, max feature correlation r=0.225). This reflects the known ceiling of the Framingham feature set, not a modeling error. Not a diagnostic tool.",
                "future_improvements": "Threshold tuning for recall optimization. Calibration check (reliability diagrams). Cost-sensitive classification.",
                "featured": True, "published": True, "display_order": 2,
            },
            {
                "title": "OpenCV & MediaPipe Vision Lab",
                "slug": "opencv-mediapipe-lab",
                "short_description": "Real-time vision suite featuring ALPR (license plate detection), 3D hand tracking, face mesh, and gesture recognition.",
                "description": "A multi-module computer vision laboratory exploring OpenCV and MediaPipe capabilities for real-time tracking, detection, and analysis.",
                "problem_statement": "Demonstrate real-time computer vision applications including automatic license plate recognition, 3D hand skeleton tracking, and facial landmark mesh overlay.",
                "category": "Computer Vision",
                "github_url": "https://github.com/SAFIULLAH012/opencv_learning",
                "dataset": "Real-time webcam feeds and static test images.",
                "model_architecture": "MediaPipe Hands (21 3D landmarks per hand), MediaPipe Face Mesh (468 landmarks), OpenCV contour detection + Tesseract OCR for ALPR.",
                "preprocessing": "Frame resize, BGR→RGB conversion, background segmentation.",
                "metrics": json.dumps({"hand_tracking_fps": "~25 FPS", "face_mesh_landmarks": "468"}),
                "technologies": json.dumps(["OpenCV", "MediaPipe", "Python", "Tesseract", "NumPy"]),
                "results": "Real-time 25+ FPS hand tracking with 21 3D landmarks. Functional ALPR pipeline on test license plates. Stable face mesh with 468-point overlay.",
                "limitations": "ALPR accuracy varies by lighting and plate font. MediaPipe models are pre-trained; not fine-tuned for custom scenarios.",
                "future_improvements": "Fine-tune ALPR for Pakistan license plate formats. Add gesture command recognition. Deploy as a FastAPI service.",
                "featured": True, "published": True, "display_order": 3,
            },
            {
                "title": "Flight Price Prediction",
                "slug": "flight-price-prediction",
                "short_description": "End-to-end ML regression pipeline predicting airline ticket prices from flight features using Scikit-Learn.",
                "description": "Regression pipeline predicting flight prices using feature engineering on route, stops, duration, airline, and timing features.",
                "problem_statement": "Predict airline ticket prices based on structured flight features to understand pricing dynamics.",
                "category": "Machine Learning / Regression",
                "github_url": "https://github.com/SAFIULLAH012/Flight-Price-Prediction",
                "dataset": "Flight price dataset with features: airline, source, destination, stops, departure time, duration, arrival time.",
                "model_architecture": "Random Forest Regressor with feature engineering. OneHotEncoding for categorical, label encoding for ordinal.",
                "preprocessing": "Date/time feature extraction, duration parsing, missing value handling, encoding.",
                "metrics": json.dumps({"r2_score": "~0.81", "mae": "~1,200 INR"}),
                "technologies": json.dumps(["Scikit-Learn", "Pandas", "NumPy", "Matplotlib", "Python"]),
                "results": "R² ≈ 0.81 on test set. Feature importance shows stops, duration, and airline as top price predictors.",
                "limitations": "Dataset limited to specific routes and time periods. Price volatility and dynamic pricing not modeled.",
                "future_improvements": "Real-time price scraping. Time-series modeling for seasonal trends. Gradient boosting for improved accuracy.",
                "featured": False, "published": True, "display_order": 4,
            },
            {
                "title": "House Price Prediction",
                "slug": "house-price-prediction",
                "short_description": "Real estate valuation model using feature engineering and ensemble regression on house attributes.",
                "description": "End-to-end house price regression model with EDA, feature engineering, and multiple model comparison.",
                "problem_statement": "Predict house sale prices from structural and location features using regression modeling.",
                "category": "Machine Learning / Regression",
                "github_url": "https://github.com/SAFIULLAH012/House_Price_Prediction",
                "dataset": "House price dataset with features: square footage, bedrooms, bathrooms, location, year built, renovation status.",
                "model_architecture": "Multiple regression models compared: Linear Regression, Ridge, Random Forest Regressor.",
                "preprocessing": "Missing value imputation, outlier handling, log-transform of target variable, feature encoding.",
                "metrics": json.dumps({"r2_score": "~0.78", "rmse": "Varies by dataset"}),
                "technologies": json.dumps(["Scikit-Learn", "Pandas", "NumPy", "Seaborn", "Python"]),
                "results": "R² ≈ 0.78 on test set. Square footage and location identified as dominant price predictors.",
                "limitations": "Dataset-specific results. Real estate pricing is highly location and market-dependent.",
                "future_improvements": "Geospatial feature engineering. XGBoost/LightGBM ensemble. Web deployment with Flask form input.",
                "featured": False, "published": True, "display_order": 5,
            },
            {
                "title": "Cat vs Dog CNN Classifier",
                "slug": "cat-dog-cnn-classifier",
                "short_description": "Convolutional Neural Network trained for binary image classification of cats and dogs with training/validation curves.",
                "description": "CNN binary classifier trained on the classic Cats vs Dogs dataset with full training pipeline and evaluation metrics.",
                "problem_statement": "Train a CNN from scratch (or with transfer learning) to classify images as cat or dog.",
                "category": "Deep Learning / Computer Vision",
                "github_url": "https://github.com/SAFIULLAH012/CAT_DOG_CLASSIFIER",
                "dataset": "Cats and Dogs dataset: standard binary classification benchmark.",
                "model_architecture": "Custom CNN with Conv2D, MaxPooling, BatchNormalization, Dropout layers. Binary crossentropy loss, Adam optimizer.",
                "preprocessing": "Resize to 128×128, normalize [0,1], data augmentation (flip, rotation, zoom).",
                "metrics": json.dumps({"test_accuracy": "~90%", "val_accuracy": "~88%"}),
                "technologies": json.dumps(["TensorFlow", "Keras", "CNN", "NumPy", "Matplotlib", "Python"]),
                "results": "~90% test accuracy. Training/validation curves show healthy convergence with minimal overfitting using dropout and augmentation.",
                "limitations": "Binary classifier only. Limited generalization to other animal species or unusual images.",
                "future_improvements": "Multi-class pet classification. Transfer learning with EfficientNet. Mobile deployment.",
                "featured": False, "published": True, "display_order": 6,
            },
            {
                "title": "Laptop Price Prediction",
                "slug": "laptop-price-prediction",
                "short_description": "Regression model predicting laptop prices from hardware specifications using feature engineering.",
                "description": "Predicts laptop market prices from hardware specs: processor, RAM, storage, display, GPU, and brand.",
                "problem_statement": "Predict laptop prices from specifications to assist in price estimation and comparison.",
                "category": "Machine Learning / Regression",
                "github_url": "https://github.com/SAFIULLAH012/Laptop-Price-Prediction",
                "dataset": "Laptop specifications and price dataset with features: CPU brand/type, RAM, SSD/HDD storage, GPU, screen size, resolution, OS.",
                "model_architecture": "Random Forest Regressor with pipeline including encoding and feature engineering.",
                "preprocessing": "Text parsing of specifications, categorical encoding, feature extraction from combined spec strings.",
                "metrics": json.dumps({"r2_score": "~0.85", "mae": "Varies by currency/dataset"}),
                "technologies": json.dumps(["Scikit-Learn", "Pandas", "NumPy", "Python"]),
                "results": "R² ≈ 0.85. RAM, CPU brand, and SSD storage are top price predictors.",
                "limitations": "Dataset from a specific time period; prices evolve rapidly with hardware releases.",
                "future_improvements": "Web scraping for live price updates. Streamlit interactive demo. GPU-brand price impact analysis.",
                "featured": False, "published": True, "display_order": 7,
            },
        ]
        for pd in projects_data:
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
