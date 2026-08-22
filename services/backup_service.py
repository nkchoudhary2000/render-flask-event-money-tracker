import io
import csv
import json
import hashlib
import datetime
from extensions import db
from models import User, Event, Category, Transaction, AuditLog
from services.drive_service import DriveService
from logger import app_logger, log_execution, log_db_transaction

class BackupService:
    """Service for User-level data exports/cloud backups and Admin Global Database Backup/Restore."""

    @staticmethod
    @log_execution
    def export_user_data(user_id: int, export_format: str = "json") -> tuple:
        """
        Exports all events, categories, and transactions for a single user in JSON or CSV format.
        Returns: (file_bytes: bytes, filename: str, mime_type: str)
        """
        user = User.query.get(user_id)
        if not user:
            raise ValueError("User not found.")

        events = Event.query.filter_by(user_id=user.id).all()
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        if export_format.lower() == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Event Title", "Event Date", "Currency", "Transaction Type", "Category",
                "Amount", "Party Name (Payee/Contributor)", "Payment Mode", "Reference No",
                "Transaction Date", "Description", "Receipt Drive Link"
            ])

            for ev in events:
                for txn in ev.transactions.all():
                    writer.writerow([
                        ev.title,
                        ev.event_date.isoformat() if ev.event_date else "",
                        ev.currency,
                        txn.type,
                        txn.category.name if txn.category else "Uncategorized",
                        txn.amount,
                        txn.party_name,
                        txn.payment_mode,
                        txn.reference_no or "",
                        txn.transaction_date.isoformat() if txn.transaction_date else "",
                        txn.description or "",
                        txn.drive_web_view_link or ""
                    ])

            content_bytes = output.getvalue().encode("utf-8")
            filename = f"EventMoneyTracker_{user.name.replace(' ', '_')}_{timestamp}.csv"
            return content_bytes, filename, "text/csv"

        # Default JSON format
        data = {
            "version": "1.0",
            "exported_at": datetime.datetime.utcnow().isoformat(),
            "user": {
                "email": user.email,
                "name": user.name
            },
            "events": []
        }

        for ev in events:
            ev_data = ev.to_dict()
            ev_data["categories"] = [c.to_dict() for c in ev.categories.all()]
            ev_data["transactions"] = [t.to_dict() for t in ev.transactions.all()]
            data["events"].append(ev_data)

        content_bytes = json.dumps(data, indent=2, default=str).encode("utf-8")
        filename = f"EventMoneyTracker_Backup_{user.name.replace(' ', '_')}_{timestamp}.json"
        return content_bytes, filename, "application/json"

    @staticmethod
    @log_execution
    def backup_user_to_google_drive(user_id: int) -> dict:
        """Exports user event data and saves it directly to their designated Google Drive folder."""
        user = User.query.get(user_id)
        if not user or not user.has_google_drive_linked():
            raise ValueError("Google Drive is not connected. Please connect your Google account first.")

        content_bytes, filename, mime_type = BackupService.export_user_data(user_id, export_format="json")
        upload_result = DriveService.upload_backup_content(user, content_bytes, filename, mime_type)

        audit = AuditLog(
            user_id=user.id,
            action="USER_DRIVE_BACKUP",
            details=json.dumps({"filename": filename, "file_id": upload_result.get("file_id")})
        )
        db.session.add(audit)
        db.session.commit()

        app_logger.info(f"[BACKUP] Successfully backed up User ID: {user_id} data to Google Drive -> File: {filename}")
        return {
            "status": "success",
            "message": "Event data successfully backed up to your Google Drive folder.",
            "file": upload_result
        }

    # ------------------ ADMIN GLOBAL BACKUP & RESTORE ------------------

    @staticmethod
    @log_execution
    def export_global_database(admin_user_id: int) -> tuple:
        """
        Dumps entire database state (Users, Events, Categories, Transactions, AuditLogs)
        into a structured, versioned, and checksummed JSON payload.
        """
        admin = User.query.get(admin_user_id)
        if not admin or not admin.is_admin:
            raise PermissionError("Administrator privileges required.")

        app_logger.info(f"[ADMIN BACKUP] Initiating complete database state dump by Admin ID: {admin_user_id}")

        users = User.query.all()
        events = Event.query.all()
        categories = Category.query.all()
        transactions = Transaction.query.all()
        audit_logs = AuditLog.query.all()

        db_dump = {
            "metadata": {
                "schema_version": "1.0",
                "application": "Event Money Tracker",
                "exported_at": datetime.datetime.utcnow().isoformat(),
                "exported_by": admin.email,
                "counts": {
                    "users": len(users),
                    "events": len(events),
                    "categories": len(categories),
                    "transactions": len(transactions),
                    "audit_logs": len(audit_logs)
                }
            },
            "tables": {
                "users": [
                    {
                        "id": u.id,
                        "email": u.email,
                        "password_hash": u.password_hash,
                        "name": u.name,
                        "avatar_url": u.avatar_url,
                        "google_id": u.google_id,
                        "google_drive_folder_id": u.google_drive_folder_id,
                        "google_drive_folder_name": u.google_drive_folder_name,
                        "is_admin": u.is_admin,
                        "created_at": u.created_at.isoformat() if u.created_at else None,
                        "updated_at": u.updated_at.isoformat() if u.updated_at else None
                    } for u in users
                ],
                "events": [
                    {
                        "id": e.id,
                        "user_id": e.user_id,
                        "title": e.title,
                        "description": e.description,
                        "event_date": e.event_date.isoformat() if e.event_date else None,
                        "currency": e.currency,
                        "budget_limit": e.budget_limit,
                        "status": e.status,
                        "created_at": e.created_at.isoformat() if e.created_at else None,
                        "updated_at": e.updated_at.isoformat() if e.updated_at else None
                    } for e in events
                ],
                "categories": [
                    {
                        "id": c.id,
                        "event_id": c.event_id,
                        "name": c.name,
                        "type": c.type,
                        "color": c.color,
                        "icon": c.icon,
                        "budget": c.budget,
                        "created_at": c.created_at.isoformat() if c.created_at else None
                    } for c in categories
                ],
                "transactions": [
                    {
                        "id": t.id,
                        "event_id": t.event_id,
                        "category_id": t.category_id,
                        "type": t.type,
                        "amount": t.amount,
                        "party_name": t.party_name,
                        "payment_mode": t.payment_mode,
                        "reference_no": t.reference_no,
                        "description": t.description,
                        "transaction_date": t.transaction_date.isoformat() if t.transaction_date else None,
                        "drive_file_id": t.drive_file_id,
                        "drive_web_view_link": t.drive_web_view_link,
                        "drive_file_name": t.drive_file_name,
                        "drive_thumbnail_link": t.drive_thumbnail_link,
                        "created_at": t.created_at.isoformat() if t.created_at else None,
                        "updated_at": t.updated_at.isoformat() if t.updated_at else None
                    } for t in transactions
                ],
                "audit_logs": [
                    {
                        "id": a.id,
                        "user_id": a.user_id,
                        "action": a.action,
                        "details": a.details,
                        "ip_address": a.ip_address,
                        "timestamp": a.timestamp.isoformat() if a.timestamp else None
                    } for a in audit_logs
                ]
            }
        }

        content_json = json.dumps(db_dump, indent=2, default=str)
        checksum = hashlib.sha256(content_json.encode("utf-8")).hexdigest()
        db_dump["metadata"]["sha256_checksum"] = checksum
        
        final_content = json.dumps(db_dump, indent=2, default=str).encode("utf-8")
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"EventMoneyTracker_GLOBAL_BACKUP_{timestamp}.json"

        # Log admin audit
        audit = AuditLog(
            user_id=admin.id,
            action="GLOBAL_DATABASE_BACKUP_EXPORT",
            details=json.dumps({"filename": filename, "checksum": checksum, "counts": db_dump["metadata"]["counts"]})
        )
        db.session.add(audit)
        db.session.commit()

        app_logger.info(f"[ADMIN BACKUP] Export completed. Checksum: {checksum}")
        return final_content, filename, "application/json"

    @staticmethod
    @log_execution
    def restore_global_database(admin_user_id: int, backup_data: dict, ip_address: str = None) -> dict:
        """
        Restores entire database state from a validated JSON backup in an atomic transaction.
        """
        admin = User.query.get(admin_user_id)
        if not admin or not admin.is_admin:
            raise PermissionError("Administrator privileges required.")

        app_logger.info(f"[ADMIN RESTORE] Starting Global Database restore requested by Admin ID: {admin_user_id}")

        if not isinstance(backup_data, dict) or "tables" not in backup_data:
            raise ValueError("Invalid backup format: Missing 'tables' root key.")

        tables = backup_data.get("tables", {})
        raw_users = tables.get("users", [])
        raw_events = tables.get("events", [])
        raw_categories = tables.get("categories", [])
        raw_transactions = tables.get("transactions", [])
        raw_audit_logs = tables.get("audit_logs", [])

        try:
            # Wipe and restore within transaction
            # Delete in reverse foreign key order
            Transaction.query.delete()
            Category.query.delete()
            Event.query.delete()
            AuditLog.query.delete()
            User.query.delete()
            db.session.flush()

            # 1. Restore Users
            for u in raw_users:
                user = User(
                    id=u.get("id"),
                    email=u.get("email"),
                    password_hash=u.get("password_hash"),
                    name=u.get("name", "User"),
                    avatar_url=u.get("avatar_url"),
                    google_id=u.get("google_id"),
                    google_drive_folder_id=u.get("google_drive_folder_id"),
                    google_drive_folder_name=u.get("google_drive_folder_name", "EventMoneyTracker_Receipts"),
                    is_admin=u.get("is_admin", False)
                )
                if u.get("created_at"):
                    try:
                        user.created_at = datetime.datetime.fromisoformat(u["created_at"])
                    except Exception:
                        pass
                db.session.add(user)
            db.session.flush()

            # 2. Restore Events
            for e in raw_events:
                ev = Event(
                    id=e.get("id"),
                    user_id=e.get("user_id"),
                    title=e.get("title"),
                    description=e.get("description"),
                    currency=e.get("currency", "INR"),
                    budget_limit=e.get("budget_limit"),
                    status=e.get("status", "active")
                )
                if e.get("event_date"):
                    try:
                        ev.event_date = datetime.date.fromisoformat(e["event_date"])
                    except Exception:
                        pass
                if e.get("created_at"):
                    try:
                        ev.created_at = datetime.datetime.fromisoformat(e["created_at"])
                    except Exception:
                        pass
                db.session.add(ev)
            db.session.flush()

            # 3. Restore Categories
            for c in raw_categories:
                cat = Category(
                    id=c.get("id"),
                    event_id=c.get("event_id"),
                    name=c.get("name"),
                    type=c.get("type", "EXPENSE"),
                    color=c.get("color", "#6366f1"),
                    icon=c.get("icon", "fa-tag"),
                    budget=c.get("budget")
                )
                if c.get("created_at"):
                    try:
                        cat.created_at = datetime.datetime.fromisoformat(c["created_at"])
                    except Exception:
                        pass
                db.session.add(cat)
            db.session.flush()

            # 4. Restore Transactions
            for t in raw_transactions:
                txn = Transaction(
                    id=t.get("id"),
                    event_id=t.get("event_id"),
                    category_id=t.get("category_id"),
                    type=t.get("type", "EXPENSE"),
                    amount=float(t.get("amount", 0)),
                    party_name=t.get("party_name", "Unknown"),
                    payment_mode=t.get("payment_mode", "CASH"),
                    reference_no=t.get("reference_no"),
                    description=t.get("description"),
                    drive_file_id=t.get("drive_file_id"),
                    drive_web_view_link=t.get("drive_web_view_link"),
                    drive_file_name=t.get("drive_file_name"),
                    drive_thumbnail_link=t.get("drive_thumbnail_link")
                )
                if t.get("transaction_date"):
                    try:
                        txn.transaction_date = datetime.datetime.fromisoformat(t["transaction_date"])
                    except Exception:
                        pass
                if t.get("created_at"):
                    try:
                        txn.created_at = datetime.datetime.fromisoformat(t["created_at"])
                    except Exception:
                        pass
                db.session.add(txn)
            db.session.flush()

            # 5. Restore Audit Logs
            for a in raw_audit_logs:
                alog = AuditLog(
                    id=a.get("id"),
                    user_id=a.get("user_id"),
                    action=a.get("action", "RESTORED_LOG"),
                    details=a.get("details") if isinstance(a.get("details"), str) else json.dumps(a.get("details")),
                    ip_address=a.get("ip_address")
                )
                if a.get("timestamp"):
                    try:
                        alog.timestamp = datetime.datetime.fromisoformat(a["timestamp"])
                    except Exception:
                        pass
                db.session.add(alog)

            # Record final restore audit action
            restore_audit = AuditLog(
                user_id=admin_user_id,
                action="GLOBAL_DATABASE_RESTORE_COMPLETED",
                details=json.dumps({
                    "restored_counts": {
                        "users": len(raw_users),
                        "events": len(raw_events),
                        "categories": len(raw_categories),
                        "transactions": len(raw_transactions)
                    }
                }),
                ip_address=ip_address
            )
            db.session.add(restore_audit)
            db.session.commit()

            app_logger.info(f"[ADMIN RESTORE] Database restore successfully committed. Restored {len(raw_users)} users, {len(raw_events)} events, {len(raw_transactions)} transactions.")
            return {
                "status": "success",
                "message": "Database successfully restored from backup.",
                "restored_counts": {
                    "users": len(raw_users),
                    "events": len(raw_events),
                    "categories": len(raw_categories),
                    "transactions": len(raw_transactions)
                }
            }

        except Exception as e:
            db.session.rollback()
            app_logger.error(f"[ADMIN RESTORE] Failed to restore database: {str(e)}. Transaction rolled back.")
            raise ValueError(f"Database restore failed: {str(e)}")
