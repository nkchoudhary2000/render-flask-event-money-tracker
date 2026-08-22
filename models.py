import datetime
import json
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db, login_manager
from logger import log_db_transaction

class User(UserMixin, db.Model):
    """User account model with local password and Google OAuth support."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    name = db.Column(db.String(150), nullable=False)
    avatar_url = db.Column(db.String(512), nullable=True)
    
    # Google OAuth fields
    google_id = db.Column(db.String(255), unique=True, nullable=True, index=True)
    google_access_token = db.Column(db.Text, nullable=True)
    google_refresh_token = db.Column(db.Text, nullable=True)
    google_token_expiry = db.Column(db.DateTime, nullable=True)
    
    # Google Drive configuration per user
    google_drive_folder_id = db.Column(db.String(255), nullable=True)
    google_drive_folder_name = db.Column(db.String(255), default="EventMoneyTracker_Receipts")
    
    # Privileges
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    events = db.relationship("Event", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    audit_logs = db.relationship("AuditLog", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password: str):
        """Hashes and sets user password."""
        self.password_hash = generate_password_hash(password)
        log_db_transaction("SET_PASSWORD", "User", self.id)

    def check_password(self, password: str) -> bool:
        """Verifies given password against stored hash."""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def has_google_drive_linked(self) -> bool:
        """Check if user has valid Google OAuth tokens for Drive."""
        return bool(self.google_access_token or self.google_refresh_token)

    def to_dict(self, include_tokens: bool = False) -> dict:
        """Serializes user to dictionary."""
        data = {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "is_admin": self.is_admin,
            "google_linked": bool(self.google_id),
            "google_drive_linked": self.has_google_drive_linked(),
            "google_drive_folder_id": self.google_drive_folder_id,
            "google_drive_folder_name": self.google_drive_folder_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_tokens:
            data["google_access_token"] = self.google_access_token
            data["google_refresh_token"] = self.google_refresh_token
            data["google_token_expiry"] = self.google_token_expiry.isoformat() if self.google_token_expiry else None
        return data

    def __repr__(self):
        return f"<User {self.id}: {self.email} (Admin: {self.is_admin})>"


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login user loader callback."""
    return User.query.get(int(user_id))


class Event(db.Model):
    """Event model (e.g. Wedding, Pooja, Birthday, Gathering)."""
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    event_date = db.Column(db.Date, default=datetime.date.today, nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    event_type = db.Column(db.String(50), default="WEDDING", nullable=True)  # WEDDING, CAREER_BUSINESS, BIRTHDAY, POOJA_RELIGIOUS, TRAVEL_TRIP, HOUSEHOLD_BUDGET, CONFERENCE, GENERAL_CUSTOM
    budget_limit = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(50), default="active", nullable=False)  # active, completed, archived
    
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    categories = db.relationship("Category", backref="event", lazy="dynamic", cascade="all, delete-orphan")
    transactions = db.relationship("Transaction", backref="event", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self, include_stats: bool = False) -> dict:
        """Serializes event to dictionary."""
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "event_type": self.event_type or "WEDDING",
            "event_date": self.event_date.isoformat() if self.event_date else None,
            "currency": self.currency,
            "budget_limit": self.budget_limit,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_stats:
            total_income = sum(t.amount for t in self.transactions.filter_by(type="INCOME").all())
            total_expense = sum(t.amount for t in self.transactions.filter_by(type="EXPENSE").all())
            data["stats"] = {
                "total_income": total_income,
                "total_expense": total_expense,
                "net_balance": total_income - total_expense,
                "transaction_count": self.transactions.count(),
                "category_count": self.categories.count()
            }
        return data

    def __repr__(self):
        return f"<Event {self.id}: {self.title} ({self.event_type})>"


class Category(db.Model):
    """Category model within an event (e.g. Decorations, Catering, Gifts Received)."""
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), default="EXPENSE", nullable=False)  # EXPENSE, INCOME, BOTH
    color = db.Column(db.String(20), default="#6366f1", nullable=False)
    icon = db.Column(db.String(50), default="fa-tag", nullable=False)
    budget = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # Relationships
    transactions = db.relationship("Transaction", backref="category", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self, include_totals: bool = False) -> dict:
        """Serializes category to dictionary."""
        data = {
            "id": self.id,
            "event_id": self.event_id,
            "name": self.name,
            "type": self.type,
            "color": self.color,
            "icon": self.icon,
            "budget": self.budget,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_totals:
            total_spent = sum(t.amount for t in self.transactions.filter_by(type="EXPENSE").all())
            total_received = sum(t.amount for t in self.transactions.filter_by(type="INCOME").all())
            data["total_spent"] = total_spent
            data["total_received"] = total_received
            data["transaction_count"] = self.transactions.count()
        return data

    def __repr__(self):
        return f"<Category {self.id}: {self.name} ({self.type})>"


class Transaction(db.Model):
    """Financial transaction (Expense or Income/Gift) record."""
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    
    type = db.Column(db.String(20), nullable=False)  # EXPENSE (Outgoing) or INCOME (Incoming / Gift)
    amount = db.Column(db.Float, nullable=False)
    party_name = db.Column(db.String(255), nullable=False)  # Payee (e.g. Vendor) or Contributor (e.g. Guest)
    payment_mode = db.Column(db.String(50), default="CASH", nullable=False)  # CASH, UPI, BANK_TRANSFER, CARD, CHEQUE, OTHER
    reference_no = db.Column(db.String(100), nullable=True)  # UPI Ref / Cheque No / Bill No
    description = db.Column(db.Text, nullable=True)
    transaction_date = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Google Drive receipt linkage
    drive_file_id = db.Column(db.String(255), nullable=True)
    drive_web_view_link = db.Column(db.String(1024), nullable=True)
    drive_file_name = db.Column(db.String(255), nullable=True)
    drive_thumbnail_link = db.Column(db.String(1024), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    def to_dict(self) -> dict:
        """Serializes transaction to dictionary."""
        return {
            "id": self.id,
            "event_id": self.event_id,
            "category_id": self.category_id,
            "category_name": self.category.name if self.category else "Uncategorized",
            "category_color": self.category.color if self.category else "#94a3b8",
            "category_icon": self.category.icon if self.category else "fa-tag",
            "type": self.type,
            "amount": self.amount,
            "party_name": self.party_name,
            "payment_mode": self.payment_mode,
            "reference_no": self.reference_no,
            "description": self.description,
            "transaction_date": self.transaction_date.isoformat() if self.transaction_date else None,
            "drive_file_id": self.drive_file_id,
            "drive_web_view_link": self.drive_web_view_link,
            "drive_file_name": self.drive_file_name,
            "drive_thumbnail_link": self.drive_thumbnail_link,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Transaction {self.id}: {self.type} {self.amount} ({self.party_name})>"


class AuditLog(db.Model):
    """System & Security Audit Log."""
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = db.Column(db.String(100), nullable=False)  # e.g. "USER_REGISTER", "ADMIN_RESTORE_DB", "DRIVE_BACKUP"
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        """Serializes audit log to dictionary."""
        details_parsed = self.details
        try:
            if self.details:
                details_parsed = json.loads(self.details)
        except Exception:
            pass

        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_email": self.user.email if self.user else "System/Deleted",
            "action": self.action,
            "details": details_parsed,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def __repr__(self):
        return f"<AuditLog {self.id}: {self.action} by User {self.user_id}>"
