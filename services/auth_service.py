import datetime
import functools
from flask import request, jsonify, abort, redirect, url_for
from flask_login import current_user
from extensions import db
from models import User, AuditLog
from logger import app_logger, log_execution, log_db_transaction

def admin_required(func):
    """Decorator to ensure route is only accessed by administrators."""
    @functools.wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated:
            app_logger.warning("[AUTH] Unauthorized access attempt to admin resource by unauthenticated user.")
            if request.path.startswith("/api/"):
                return jsonify({"status": "error", "message": "Authentication required"}), 401
            return redirect(url_for("ui.login", next=request.url))
        
        if not current_user.is_admin:
            app_logger.warning(f"[AUTH] Forbidden access attempt to admin resource by User ID: {current_user.id} ({current_user.email})")
            if request.path.startswith("/api/"):
                return jsonify({"status": "error", "message": "Admin privileges required"}), 403
            abort(403)
            
        return func(*args, **kwargs)
    return decorated_view


class AuthService:
    """Authentication and User Lifecycle Service."""

    @staticmethod
    @log_execution
    def delete_user(admin_user_id: int, target_user_id: int, ip_address: str = None) -> bool:
        """Deletes a user account and cascades all associated data."""
        if admin_user_id == target_user_id:
            raise ValueError("You cannot delete your own active administrator account.")

        target = User.query.get(target_user_id)
        if not target:
            raise ValueError("User account not found.")

        target_email = target.email
        db.session.delete(target)

        audit = AuditLog(
            user_id=admin_user_id,
            action="USER_DELETED_BY_ADMIN",
            details=f"Admin ID {admin_user_id} deleted user account ID {target_user_id} ({target_email})",
            ip_address=ip_address
        )
        db.session.add(audit)
        db.session.commit()
        log_db_transaction("DELETE", "User", target_user_id)
        app_logger.info(f"[ADMIN] User ID {target_user_id} ({target_email}) deleted by Admin ID {admin_user_id}")
        return True

    @staticmethod
    @log_execution
    def purge_user_data(admin_user_id: int, target_user_id: int, ip_address: str = None) -> dict:
        """Purges all events, categories, and transactions for a user while keeping account intact."""
        target = User.query.get(target_user_id)
        if not target:
            raise ValueError("User account not found.")

        event_count = target.events.count()
        for ev in target.events.all():
            db.session.delete(ev)

        audit = AuditLog(
            user_id=admin_user_id,
            action="USER_DATA_PURGED",
            details=f"Admin ID {admin_user_id} purged {event_count} events and all transactions for User {target.email}",
            ip_address=ip_address
        )
        db.session.add(audit)
        db.session.commit()
        app_logger.info(f"[ADMIN] Purged {event_count} events for User ID {target_user_id} ({target.email})")
        return {"purged_events_count": event_count}

    @staticmethod
    @log_execution
    def register_local_user(email: str, password: str, name: str, ip_address: str = None) -> User:
        """
        Registers a new user or sets a password for an existing OAuth user without one.
        The very first user registered in the system is automatically granted Admin privileges.
        """
        email_clean = email.strip().lower()
        existing_user = User.query.filter_by(email=email_clean).first()

        # Check if first user in system
        user_count = User.query.count()
        is_first_user = (user_count == 0)

        if existing_user:
            if existing_user.password_hash:
                app_logger.warning(f"[AUTH] Registration failed: Email '{email_clean}' is already registered.")
                raise ValueError("An account with this email already exists.")
            
            # Account merge: User originally registered with Google OAuth is now adding a password
            app_logger.info(f"[AUTH] Merging account for User ID: {existing_user.id} with local password.")
            existing_user.set_password(password)
            if name and not existing_user.name:
                existing_user.name = name.strip()
            
            audit = AuditLog(
                user_id=existing_user.id,
                action="LOCAL_PASSWORD_ADDED",
                details=f"Local password linked to Google OAuth account ({email_clean})",
                ip_address=ip_address
            )
            db.session.add(audit)
            db.session.commit()
            log_db_transaction("UPDATE", "User", existing_user.id, {"email": email_clean, "merged": True})
            return existing_user

        # Create new user
        new_user = User(
            email=email_clean,
            name=name.strip() if name else email_clean.split("@")[0],
            is_admin=is_first_user
        )
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.flush()  # Generate user.id

        if is_first_user:
            app_logger.info(f"[AUTH] FIRST USER DETECTED -> User ID: {new_user.id} ({email_clean}) granted ADMIN role.")

        audit = AuditLog(
            user_id=new_user.id,
            action="USER_REGISTERED_LOCAL",
            details=f"User registered with email ({email_clean}). Admin: {is_first_user}",
            ip_address=ip_address
        )
        db.session.add(audit)
        db.session.commit()

        log_db_transaction("CREATE", "User", new_user.id, {"email": email_clean, "is_admin": is_first_user})
        return new_user

    @staticmethod
    @log_execution
    def authenticate_local_user(email: str, password: str, ip_address: str = None) -> User:
        """Validates credentials for local email/password login."""
        email_clean = email.strip().lower()
        user = User.query.filter_by(email=email_clean).first()

        if not user or not user.check_password(password):
            app_logger.warning(f"[AUTH] Failed login attempt for email: '{email_clean}' from IP: {ip_address}")
            raise ValueError("Invalid email or password.")

        audit = AuditLog(
            user_id=user.id,
            action="USER_LOGIN_LOCAL",
            details="Successful local login",
            ip_address=ip_address
        )
        db.session.add(audit)
        db.session.commit()
        app_logger.info(f"[AUTH] User ID: {user.id} ({email_clean}) successfully logged in locally.")
        return user

    @staticmethod
    @log_execution
    def handle_google_oauth_user(user_info: dict, tokens: dict, ip_address: str = None) -> User:
        """
        Handles user creation and account merging after successful Google OAuth 2.0 handshake.
        Seamlessly links Google ID and Drive tokens with existing local accounts.
        """
        email = user_info.get("email", "").strip().lower()
        google_id = user_info.get("sub")
        name = user_info.get("name", email.split("@")[0])
        avatar_url = user_info.get("picture")

        if not email or not google_id:
            app_logger.error(f"[AUTH] Invalid Google OAuth user info payload: {user_info}")
            raise ValueError("Google OAuth payload is missing essential email or user identifier.")

        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in", 3600)
        token_expiry = datetime.datetime.utcnow() + datetime.timedelta(seconds=int(expires_in)) if expires_in else None

        user = User.query.filter((User.google_id == google_id) | (User.email == email)).first()

        if user:
            app_logger.info(f"[AUTH] Existing user found during Google OAuth (ID: {user.id}, Email: {user.email}). Merging credentials.")
            user.google_id = google_id
            if avatar_url:
                user.avatar_url = avatar_url
            if name and not user.name:
                user.name = name
            
            # Update tokens
            user.google_access_token = access_token
            if refresh_token:
                user.google_refresh_token = refresh_token
            user.google_token_expiry = token_expiry

            audit = AuditLog(
                user_id=user.id,
                action="USER_LOGIN_GOOGLE_MERGED",
                details=f"Google OAuth login & tokens refreshed for {email}",
                ip_address=ip_address
            )
            db.session.add(audit)
            db.session.commit()
            log_db_transaction("UPDATE", "User", user.id, {"google_id": google_id, "tokens_updated": True})
            return user

        # Create new user via Google
        user_count = User.query.count()
        is_first_user = (user_count == 0)

        new_user = User(
            email=email,
            name=name,
            avatar_url=avatar_url,
            google_id=google_id,
            google_access_token=access_token,
            google_refresh_token=refresh_token,
            google_token_expiry=token_expiry,
            is_admin=is_first_user
        )

        db.session.add(new_user)
        db.session.flush()

        if is_first_user:
            app_logger.info(f"[AUTH] FIRST USER DETECTED via Google OAuth -> User ID: {new_user.id} ({email}) granted ADMIN role.")

        audit = AuditLog(
            user_id=new_user.id,
            action="USER_REGISTERED_GOOGLE",
            details=f"New user registered via Google OAuth ({email}). Admin: {is_first_user}",
            ip_address=ip_address
        )
        db.session.add(audit)
        db.session.commit()

        log_db_transaction("CREATE", "User", new_user.id, {"email": email, "google_id": google_id, "is_admin": is_first_user})
        return new_user
