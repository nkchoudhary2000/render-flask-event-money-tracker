from flask import Blueprint, render_template, redirect, url_for, make_response
from flask_login import login_required, current_user
from services.event_service import EventService
from services.drive_service import DriveService
from services.auth_service import admin_required
from logger import app_logger, log_execution

ui_bp = Blueprint("ui", __name__)

@ui_bp.route("/")
@log_execution
def index():
    """Landing route - redirects to dashboard or login."""
    if current_user.is_authenticated:
        return redirect(url_for("ui.dashboard"))
    return redirect(url_for("ui.login"))


@ui_bp.route("/login")
@log_execution
def login():
    """Renders the login view."""
    if current_user.is_authenticated:
        return redirect(url_for("ui.dashboard"))
    resp = make_response(render_template("login.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    return resp


@ui_bp.route("/register")
@log_execution
def register():
    """Renders the registration view."""
    if current_user.is_authenticated:
        return redirect(url_for("ui.dashboard"))
    resp = make_response(render_template("register.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    return resp


@ui_bp.route("/logout")
def logout_redirect():
    """Convenience alias to auth logout."""
    return redirect(url_for("auth.logout"))


@ui_bp.route("/dashboard")
@login_required
@log_execution
def dashboard():
    """
    Renders the central Single Page Application (SPA) Dashboard.
    Pre-populates initial event data, categories, and transactions for 0ms instant rendering.
    """
    events = EventService.get_user_events(current_user.id, include_stats=True)
    drive_status = DriveService.check_drive_status(current_user)

    active_event_id = events[0]["id"] if events else None
    active_event_data = None
    initial_categories = []
    initial_transactions = []

    if active_event_id:
        try:
            active_event_data = EventService.get_event_analytics(active_event_id, current_user.id, is_admin=current_user.is_admin)
            initial_categories = EventService.get_event_categories(active_event_id, current_user.id, include_totals=True, is_admin=current_user.is_admin)
            raw_txns = EventService.get_event_transactions(active_event_id, current_user.id, is_admin=current_user.is_admin)
            initial_transactions = [t.to_dict() for t in raw_txns]
        except Exception as e:
            app_logger.warning(f"[UI] Could not load initial analytics/categories for event {active_event_id}: {str(e)}")

    rendered_html = render_template(
        "dashboard.html",
        user=current_user,
        events=events,
        active_event=active_event_data,
        initial_categories=initial_categories,
        initial_transactions=initial_transactions,
        drive_status=drive_status
    )
    resp = make_response(rendered_html)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0, post-check=0, pre-check=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@ui_bp.route("/admin")
@admin_required
@log_execution
def admin():
    """Admin portal shortcut - redirects directly into dashboard admin tab."""
    return redirect(url_for("ui.dashboard") + "#admin")
