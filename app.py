import os
import datetime
from flask import Flask, jsonify, render_template, request
from config import config_by_name
from extensions import db, login_manager, cors, swagger, migrate
from routes import ui_bp, api_bp, auth_bp
from logger import setup_logger, app_logger

def create_app(config_name: str = None) -> Flask:
    """Application factory for Event Money Tracker."""
    if config_name is None:
        env_mode = os.getenv("FLASK_ENV", "development").lower()
        config_name = "production" if env_mode == "production" else "development"

    app = Flask(__name__)
    config_class = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(config_class)

    # Dynamic refresh of DB URL from environment if provided (for development/production)
    if config_name != "testing":
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
            app.config["SQLALCHEMY_DATABASE_URI"] = db_url
            if not db_url.startswith("sqlite"):
                app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
                    "pool_pre_ping": True,
                    "pool_recycle": 300,
                }

    # Initialize logger
    setup_logger("event_tracker", log_level=app.config.get("LOG_LEVEL", "DEBUG"))
    app_logger.info(f"[BOOTSTRAP] Initializing Event Money Tracker in [{config_name.upper()}] mode.")

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})
    swagger.init_app(app)
    migrate.init_app(app, db)

    # Register Blueprints
    app.register_blueprint(ui_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(auth_bp)
    app_logger.info("[BOOTSTRAP] Registered UI, API, and Auth Blueprints successfully.")

    # Context processors
    @app.context_processor
    def inject_globals():
        return {
            "now": datetime.datetime.utcnow(),
            "app_name": "Event Money Tracker"
        }

    # Global Error Handlers
    @app.errorhandler(404)
    def handle_404(e):
        app_logger.warning(f"[ROUTING 404] Resource not found: {request.path}")
        if request.path.startswith("/api/"):
            return jsonify({"status": "error", "message": "API endpoint or resource not found"}), 404
        return render_template("base.html"), 404

    @app.errorhandler(413)
    def handle_413(e):
        app_logger.error(f"[UPLOAD 413] File size exceeds limit on: {request.path}")
        if request.path.startswith("/api/"):
            return jsonify({"status": "error", "message": "Uploaded file is too large (max 16 MB)."}), 413
        return render_template("base.html"), 413

    @app.errorhandler(500)
    def handle_500(e):
        app_logger.error(f"[SERVER 500] Internal server error on: {request.path} | Error: {str(e)}")
        if request.path.startswith("/api/"):
            return jsonify({"status": "error", "message": "Internal server error"}), 500
        return render_template("base.html"), 500

    # Auto-initialize database tables in development
    with app.app_context():
        try:
            db.create_all()
            app_logger.info("[BOOTSTRAP] Database tables verified / created.")
        except Exception as db_err:
            app_logger.error(f"[BOOTSTRAP] Database table initialization warning: {str(db_err)}")

    # CLI Management Commands
    @app.cli.command("init-db")
    def init_db_command():
        """Initializes database schema."""
        db.create_all()
        print("Initialized the database tables.")

    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PORT", 5000))
    app_logger.info(f"[LAUNCH] Starting development server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=True)
