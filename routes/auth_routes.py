import os
import secrets
import requests
from flask import Blueprint, request, redirect, url_for, session, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from services.auth_service import AuthService
from logger import app_logger, log_execution, log_external_api

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# --------------------------------------------------------------------------
# LOCAL AUTHENTICATION
# --------------------------------------------------------------------------

@auth_bp.route("/local/login", methods=["POST"])
@log_execution
def local_login():
    """Handles local email/password login submission."""
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    email = data.get("email", "").strip()
    password = data.get("password", "")
    remember = data.get("remember") in [True, "true", "on", "1"]

    ip_addr = request.headers.get("X-Forwarded-For", request.remote_addr)

    try:
        user = AuthService.authenticate_local_user(email, password, ip_address=ip_addr)
        login_user(user, remember=remember)
        app_logger.info(f"[AUTH] User {user.email} (ID: {user.id}) logged in successfully.")

        if request.is_json:
            return jsonify({
                "status": "success",
                "message": "Login successful",
                "user": user.to_dict(),
                "redirect_url": url_for("ui.dashboard")
            }), 200
        
        flash("Welcome back!", "success")
        next_url = request.args.get("next") or url_for("ui.dashboard")
        return redirect(next_url)
    except ValueError as e:
        if request.is_json:
            return jsonify({"status": "error", "message": str(e)}), 401
        flash(str(e), "danger")
        return redirect(url_for("ui.login"))


@auth_bp.route("/local/register", methods=["POST"])
@log_execution
def local_register():
    """Handles local user registration."""
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if len(password) < 6:
        msg = "Password must be at least 6 characters long."
        if request.is_json:
            return jsonify({"status": "error", "message": msg}), 400
        flash(msg, "warning")
        return redirect(url_for("ui.register"))

    ip_addr = request.headers.get("X-Forwarded-For", request.remote_addr)

    try:
        user = AuthService.register_local_user(email, password, name, ip_address=ip_addr)
        login_user(user, remember=True)
        app_logger.info(f"[AUTH] New user {user.email} (ID: {user.id}) registered & logged in.")

        if request.is_json:
            return jsonify({
                "status": "success",
                "message": "Registration successful",
                "user": user.to_dict(),
                "redirect_url": url_for("ui.dashboard")
            }), 201
        
        flash(f"Welcome to Event Money Tracker, {user.name}!", "success")
        return redirect(url_for("ui.dashboard"))
    except ValueError as e:
        if request.is_json:
            return jsonify({"status": "error", "message": str(e)}), 400
        flash(str(e), "danger")
        return redirect(url_for("ui.register"))


# --------------------------------------------------------------------------
# GOOGLE OAUTH 2.0
# --------------------------------------------------------------------------

@auth_bp.route("/google/login", methods=["GET"])
@log_execution
def google_login():
    """Initiates Google OAuth 2.0 authorization request."""
    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    if not client_id:
        app_logger.error("[AUTH] Google OAuth is not configured (missing GOOGLE_CLIENT_ID).")
        flash("Google OAuth is not configured on this server. Please use local login or provide credentials.", "warning")
        return redirect(url_for("ui.login"))

    # Generate state token to protect against CSRF
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    # Force HTTPS redirect URI if in production or behind proxy
    redirect_uri = url_for("auth.google_callback", _external=True)
    if request.headers.get("X-Forwarded-Proto") == "https":
        redirect_uri = redirect_uri.replace("http://", "https://", 1)

    scopes = " ".join(current_app.config.get("GOOGLE_OAUTH_SCOPES", []))

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        "response_type=code&"
        f"scope={scopes}&"
        "access_type=offline&"
        "prompt=consent&"
        f"state={state}"
    )

    app_logger.info(f"[AUTH] Redirecting user to Google OAuth consent screen. State: {state[:8]}...")
    return redirect(auth_url)


@auth_bp.route("/google/callback", methods=["GET"])
@log_execution
def google_callback():
    """Handles Google OAuth 2.0 redirect callback."""
    code = request.args.get("code")
    state = request.args.get("state")
    saved_state = session.pop("oauth_state", None)

    if not code:
        err = request.args.get("error", "Unknown error")
        app_logger.warning(f"[AUTH] Google OAuth callback error: {err}")
        flash(f"Google authorization failed: {err}", "danger")
        return redirect(url_for("ui.login"))

    if not state or state != saved_state:
        app_logger.warning("[AUTH] Invalid OAuth state token in Google callback.")
        flash("Session validation failed during Google sign-in. Please try again.", "warning")
        return redirect(url_for("ui.login"))

    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    client_secret = current_app.config.get("GOOGLE_CLIENT_SECRET")
    redirect_uri = url_for("auth.google_callback", _external=True)
    if request.headers.get("X-Forwarded-Proto") == "https":
        redirect_uri = redirect_uri.replace("http://", "https://", 1)

    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }

    try:
        # Exchange code for tokens
        token_res = requests.post(token_url, data=token_data, timeout=10)
        log_external_api("GoogleOAuth", "oauth2/token", "POST", payload={"code": "******"}, response=token_res.json(), status_code=token_res.status_code)
        
        if token_res.status_code != 200:
            app_logger.error(f"[AUTH] Failed to exchange authorization code for tokens: {token_res.text}")
            flash("Failed to obtain access tokens from Google.", "danger")
            return redirect(url_for("ui.login"))

        tokens = token_res.json()

        # Fetch user profile info
        userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        userinfo_res = requests.get(userinfo_url, headers={"Authorization": f"Bearer {tokens['access_token']}"}, timeout=10)
        
        if userinfo_res.status_code != 200:
            app_logger.error(f"[AUTH] Failed to fetch Google user profile: {userinfo_res.text}")
            flash("Failed to retrieve Google profile info.", "danger")
            return redirect(url_for("ui.login"))

        user_info = userinfo_res.json()
        ip_addr = request.headers.get("X-Forwarded-For", request.remote_addr)

        user = AuthService.handle_google_oauth_user(user_info, tokens, ip_address=ip_addr)
        login_user(user, remember=True)

        app_logger.info(f"[AUTH] Google OAuth user logged in: {user.email} (Admin: {user.is_admin})")
        flash(f"Successfully signed in with Google as {user.name}!", "success")
        return redirect(url_for("ui.dashboard"))

    except Exception as e:
        app_logger.error(f"[AUTH] Google OAuth processing failed: {str(e)}")
        flash(f"Google sign in failed: {str(e)}", "danger")
        return redirect(url_for("ui.login"))


# --------------------------------------------------------------------------
# LOGOUT
# --------------------------------------------------------------------------

@auth_bp.route("/logout", methods=["GET", "POST"])
@log_execution
def logout():
    """Logs out the current user session and clears all authentication cookies."""
    user_email = current_user.email if current_user.is_authenticated else "Anonymous"
    try:
        logout_user()
    except Exception:
        pass
    session.clear()
    app_logger.info(f"[AUTH] User {user_email} logged out.")
    flash("You have been signed out.", "info")

    resp = redirect(url_for("ui.login"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0, post-check=0, pre-check=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.delete_cookie("session")
    resp.delete_cookie("remember_token")
    return resp
