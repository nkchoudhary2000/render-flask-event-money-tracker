import io
import json
from flask import Blueprint, request, jsonify, send_file
from flask_login import login_required, current_user
from flasgger import swag_from
from extensions import db
from models import User, Event, Category, Transaction, AuditLog
from services.event_service import EventService
from services.drive_service import DriveService
from services.backup_service import BackupService
from services.auth_service import AuthService, admin_required
from logger import app_logger, log_execution

api_bp = Blueprint("api", __name__, url_prefix="/api")

# --------------------------------------------------------------------------
# USER PROFILE & AUTH INFO
# --------------------------------------------------------------------------

@api_bp.route("/auth/me", methods=["GET"])
@login_required
@log_execution
def get_current_user_profile():
    """
    Get Current User Profile
    ---
    tags:
      - Authentication
    summary: Returns the profile and settings of the currently authenticated user
    responses:
      200:
        description: User profile object
        schema:
          type: object
          properties:
            status:
              type: string
              example: success
            user:
              type: object
      401:
        description: Unauthenticated
    """
    return jsonify({
        "status": "success",
        "user": current_user.to_dict()
    }), 200


# --------------------------------------------------------------------------
# EVENT ENDPOINTS
# --------------------------------------------------------------------------

@api_bp.route("/events", methods=["GET"])
@login_required
@log_execution
def list_events():
    """
    List All User Events
    ---
    tags:
      - Events
    summary: Retrieves all events belonging to the current user with aggregated financial stats
    responses:
      200:
        description: Array of event objects
      401:
        description: Unauthorized
    """
    events = EventService.get_user_events(current_user.id, include_stats=True)
    return jsonify({"status": "success", "count": len(events), "events": events}), 200


@api_bp.route("/events", methods=["POST"])
@login_required
@log_execution
def create_event():
    """
    Create a New Event
    ---
    tags:
      - Events
    summary: Creates a new event (e.g. Wedding, Pooja, Birthday) with default categories
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - title
          properties:
            title:
              type: string
              example: "Brother's Grand Marriage"
            description:
              type: string
              example: "Wedding festivities, food, gifts and logistics tracking"
            event_date:
              type: string
              format: date
              example: "2026-11-25"
            currency:
              type: string
              example: "INR"
            budget_limit:
              type: number
              example: 500000.00
    responses:
      201:
        description: Event created successfully
      400:
        description: Validation error
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    title = data.get("title")
    description = data.get("description", "")
    event_date = data.get("event_date")
    currency = data.get("currency", "INR")
    budget_limit = data.get("budget_limit")

    try:
        event = EventService.create_event(
            user_id=current_user.id,
            title=title,
            description=description,
            event_date=event_date,
            currency=currency,
            budget_limit=budget_limit
        )
        return jsonify({
            "status": "success",
            "message": "Event created successfully.",
            "event": event.to_dict(include_stats=True)
        }), 201
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/events/<int:event_id>", methods=["GET"])
@login_required
@log_execution
def get_event(event_id: int):
    """
    Get Single Event Details
    ---
    tags:
      - Events
    summary: Retrieves full details of a specific event
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Event details
      404:
        description: Event not found
    """
    try:
        event = EventService.get_event(event_id, current_user.id, is_admin=current_user.is_admin)
        return jsonify({"status": "success", "event": event.to_dict(include_stats=True)}), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 404


@api_bp.route("/events/<int:event_id>", methods=["PUT"])
@login_required
@log_execution
def update_event(event_id: int):
    """
    Update Event Details
    ---
    tags:
      - Events
    summary: Updates metadata, currency, budget, or status for an event
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
      - in: body
        name: body
        schema:
          type: object
          properties:
            title:
              type: string
            description:
              type: string
            event_date:
              type: string
              format: date
            currency:
              type: string
            budget_limit:
              type: number
            status:
              type: string
              enum: [active, completed, archived]
    responses:
      200:
        description: Event updated successfully
      400:
        description: Bad request
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    try:
        updated = EventService.update_event(event_id, current_user.id, data, is_admin=current_user.is_admin)
        return jsonify({
            "status": "success",
            "message": "Event updated successfully.",
            "event": updated.to_dict(include_stats=True)
        }), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/events/<int:event_id>", methods=["DELETE"])
@login_required
@log_execution
def delete_event(event_id: int):
    """
    Delete an Event
    ---
    tags:
      - Events
    summary: Permanently deletes an event, including its categories and transactions
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Event deleted
      404:
        description: Event not found
    """
    try:
        EventService.delete_event(event_id, current_user.id, is_admin=current_user.is_admin)
        return jsonify({"status": "success", "message": "Event and associated records deleted."}), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 404


# --------------------------------------------------------------------------
# CATEGORY ENDPOINTS
# --------------------------------------------------------------------------

@api_bp.route("/events/<int:event_id>/categories", methods=["GET"])
@login_required
@log_execution
def list_categories(event_id: int):
    """
    List Categories for an Event
    ---
    tags:
      - Categories
    summary: Retrieves all custom categories and financial subtotals for an event
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: List of category items
    """
    try:
        categories = EventService.get_event_categories(event_id, current_user.id, is_admin=current_user.is_admin)
        return jsonify({"status": "success", "count": len(categories), "categories": categories}), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 404


@api_bp.route("/events/<int:event_id>/categories", methods=["POST"])
@login_required
@log_execution
def create_category(event_id: int):
    """
    Create a Custom Category
    ---
    tags:
      - Categories
    summary: Creates a new category within an event (e.g. Decorations, Gifts Received)
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - name
          properties:
            name:
              type: string
              example: "VIP Guest Accommodation"
            type:
              type: string
              enum: [EXPENSE, INCOME, BOTH]
              example: "EXPENSE"
            color:
              type: string
              example: "#ec4899"
            icon:
              type: string
              example: "fa-hotel"
            budget:
              type: number
              example: 50000
    responses:
      201:
        description: Category created
      400:
        description: Validation error
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    name = data.get("name")
    cat_type = data.get("type", "EXPENSE")
    color = data.get("color", "#6366f1")
    icon = data.get("icon", "fa-tag")
    budget = data.get("budget")

    try:
        category = EventService.create_category(
            event_id=event_id,
            user_id=current_user.id,
            name=name,
            type=cat_type,
            color=color,
            icon=icon,
            budget=budget,
            is_admin=current_user.is_admin
        )
        return jsonify({
            "status": "success",
            "message": "Category created successfully.",
            "category": category.to_dict(include_totals=True)
        }), 201
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/categories/<int:category_id>", methods=["PUT", "PATCH"])
@login_required
@log_execution
def update_category(category_id: int):
    """
    Update Category Details & Budget
    ---
    tags:
      - Categories
    summary: Updates category name, budget limit, color, icon, or type
    parameters:
      - name: category_id
        in: path
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            budget:
              type: number
            color:
              type: string
            icon:
              type: string
            type:
              type: string
    responses:
      200:
        description: Category updated
      400:
        description: Validation error
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    try:
        cat = EventService.update_category(category_id, current_user.id, data, is_admin=current_user.is_admin)
        return jsonify({
            "status": "success",
            "message": "Category updated successfully.",
            "category": cat.to_dict(include_totals=True)
        }), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/categories/<int:category_id>", methods=["DELETE"])
@login_required
@log_execution
def delete_category(category_id: int):
    """
    Delete a Category
    ---
    tags:
      - Categories
    summary: Deletes a category
    parameters:
      - name: category_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Category deleted
    """
    try:
        EventService.delete_category(category_id, current_user.id, is_admin=current_user.is_admin)
        return jsonify({"status": "success", "message": "Category deleted."}), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


# --------------------------------------------------------------------------
# TRANSACTION ENDPOINTS
# --------------------------------------------------------------------------

@api_bp.route("/events/<int:event_id>/transactions", methods=["GET"])
@login_required
@log_execution
def list_transactions(event_id: int):
    """
    List Transactions for an Event
    ---
    tags:
      - Transactions
    summary: Queries transactions with live filtering (category, type, payment mode, search text)
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
      - name: category_id
        in: query
        type: integer
      - name: type
        in: query
        type: string
        enum: [EXPENSE, INCOME]
      - name: payment_mode
        in: query
        type: string
      - name: search
        in: query
        type: string
    responses:
      200:
        description: Filtered transactions list
    """
    cat_id = request.args.get("category_id", type=int)
    txn_type = request.args.get("type")
    pay_mode = request.args.get("payment_mode")
    search = request.args.get("search")

    try:
        txns = EventService.get_event_transactions(
            event_id=event_id,
            user_id=current_user.id,
            category_id=cat_id,
            type=txn_type,
            payment_mode=pay_mode,
            search=search,
            is_admin=current_user.is_admin
        )
        return jsonify({"status": "success", "count": len(txns), "transactions": txns}), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/events/<int:event_id>/transactions", methods=["POST"])
@login_required
@log_execution
def create_transaction(event_id: int):
    """
    Create a Transaction (Expense or Income/Gift)
    ---
    tags:
      - Transactions
    summary: Records an incoming gift or outgoing expense, with optional Google Drive receipt upload
    consumes:
      - multipart/form-data
      - application/json
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
      - in: formData
        name: type
        type: string
        required: true
        enum: [EXPENSE, INCOME]
        example: "EXPENSE"
      - in: formData
        name: amount
        type: number
        required: true
        example: 25000.00
      - in: formData
        name: party_name
        type: string
        required: true
        example: "Royal Caterers"
      - in: formData
        name: category_id
        type: integer
        example: 1
      - in: formData
        name: payment_mode
        type: string
        enum: [CASH, UPI, BANK_TRANSFER, CARD, CHEQUE, OTHER]
        example: "UPI"
      - in: formData
        name: reference_no
        type: string
        example: "UPI/TXN984920412"
      - in: formData
        name: description
        type: string
        example: "Initial 50% advance for buffet lunch"
      - in: formData
        name: transaction_date
        type: string
        example: "2026-08-22"
      - in: formData
        name: receipt_file
        type: file
        description: Bill / Receipt image or PDF (saved to Google Drive)
    responses:
      201:
        description: Transaction recorded
      400:
        description: Validation failure
    """
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    receipt_file = request.files.get("receipt_file")

    txn_type = data.get("type", "EXPENSE")
    amount = data.get("amount")
    party_name = data.get("party_name")
    category_id = data.get("category_id")
    payment_mode = data.get("payment_mode", "CASH")
    reference_no = data.get("reference_no")
    description = data.get("description")
    transaction_date = data.get("transaction_date")

    cat_id_int = None
    if category_id and str(category_id).strip().isdigit():
        cat_id_int = int(category_id)

    try:
        txn = EventService.create_transaction(
            event_id=event_id,
            user_id=current_user.id,
            type=txn_type,
            amount=amount,
            party_name=party_name,
            category_id=cat_id_int,
            payment_mode=payment_mode,
            reference_no=reference_no,
            description=description,
            transaction_date=transaction_date,
            receipt_file=receipt_file,
            is_admin=current_user.is_admin
        )
        return jsonify({
            "status": "success",
            "message": "Transaction recorded successfully.",
            "transaction": txn.to_dict()
        }), 201
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/transactions/<int:transaction_id>", methods=["DELETE"])
@login_required
@log_execution
def delete_transaction(transaction_id: int):
    """
    Delete a Transaction
    ---
    tags:
      - Transactions
    summary: Deletes a specific transaction record
    parameters:
      - name: transaction_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Transaction deleted
    """
    try:
        EventService.delete_transaction(transaction_id, current_user.id, is_admin=current_user.is_admin)
        return jsonify({"status": "success", "message": "Transaction deleted successfully."}), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


# --------------------------------------------------------------------------
# ANALYTICS & DASHBOARD METRICS
# --------------------------------------------------------------------------

@api_bp.route("/events/<int:event_id>/analytics", methods=["GET"])
@login_required
@log_execution
def get_event_analytics(event_id: int):
    """
    Get Event Financial Analytics
    ---
    tags:
      - Analytics
    summary: Computes incoming/outgoing cash flows, net balance, category breakdown %, contributor leaderboards, and recent logs
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Comprehensive financial insights object
    """
    try:
        analytics = EventService.get_event_analytics(event_id, current_user.id, is_admin=current_user.is_admin)
        return jsonify({"status": "success", "analytics": analytics}), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


# --------------------------------------------------------------------------
# GOOGLE DRIVE INTEGRATION ENDPOINTS
# --------------------------------------------------------------------------

@api_bp.route("/drive/status", methods=["GET"])
@login_required
@log_execution
def get_drive_status():
    """
    Get Google Drive Connection Status
    ---
    tags:
      - Google Drive
    summary: Checks whether the user's Google Drive is authenticated and verifies the app folder
    responses:
      200:
        description: Drive connection status
    """
@api_bp.route("/drive/folders", methods=["GET"])
@login_required
@log_execution
def list_user_drive_folders():
    """
    List Google Drive Folders & Files
    ---
    tags:
      - Google Drive
    summary: Fetches all available folders and files in the user's Google Drive parent folder for in-panel browsing
    parameters:
      - name: parent_id
        in: query
        type: string
        default: "root"
    responses:
      200:
        description: List of Drive folders and files
      400:
        description: Error querying Google Drive
    """
    parent_id = request.args.get("parent_id", "root")
    try:
        data = DriveService.list_user_drive_folders(current_user, parent_id=parent_id)
        return jsonify({
            "status": "success",
            "current_parent": data.get("current_parent", {}),
            "folders": data.get("folders", []),
            "files": data.get("files", []),
            "count_folders": len(data.get("folders", [])),
            "count_files": len(data.get("files", [])),
            "current_folder_id": current_user.google_drive_folder_id,
            "current_folder_name": current_user.google_drive_folder_name
        }), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/drive/files/<file_id>/download", methods=["GET"])
@login_required
@log_execution
def download_drive_file(file_id: str):
    """
    Download File from Google Drive
    ---
    tags:
      - Google Drive
    summary: Downloads a file stored in the user's Google Drive
    parameters:
      - name: file_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: File binary stream
      400:
        description: Download error
    """
    try:
        content_bytes, filename, mime_type = DriveService.download_file_content(current_user, file_id)
        return send_file(
            io.BytesIO(content_bytes),
            mimetype=mime_type,
            as_attachment=True,
            download_name=filename
        )
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/drive/select-folder", methods=["POST"])
@login_required
@log_execution
def select_drive_folder():
    """
    Set Designated Google Drive Folder
    ---
    tags:
      - Google Drive
    summary: Sets an existing Google Drive folder as the designated destination for all backups and receipts
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - folder_id
          properties:
            folder_id:
              type: string
            folder_name:
              type: string
    responses:
      200:
        description: Designated folder saved
      400:
        description: Error setting folder
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    folder_id = data.get("folder_id")
    folder_name = data.get("folder_name")
    if not folder_id:
        return jsonify({"status": "error", "message": "Folder ID is required."}), 400

    try:
        res = DriveService.set_user_designated_folder(current_user, folder_id=folder_id, folder_name=folder_name)
        return jsonify({
            "status": "success",
            "message": f"Designated backup folder set to '{res['folder_name']}'.",
            "folder": res
        }), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/drive/folder", methods=["POST"])
@api_bp.route("/drive/setup-folder", methods=["POST"])
@login_required
@log_execution
def setup_drive_folder():
    """
    Create & Set Google Drive Destination Folder
    ---
    tags:
      - Google Drive
    summary: Creates a new folder (or links existing by name) and designates it as active backup destination
    parameters:
      - in: body
        name: body
        schema:
          type: object
          properties:
            folder_name:
              type: string
              example: "MyWedding2026_Receipts"
            parent_id:
              type: string
              default: "root"
    responses:
      200:
        description: Folder created and configured successfully
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    folder_name = data.get("folder_name")
    parent_id = data.get("parent_id", "root")

    if not folder_name or not folder_name.strip():
        return jsonify({"status": "error", "message": "Folder name cannot be empty."}), 400

    try:
        res = DriveService.create_and_set_folder(current_user, folder_name=folder_name.strip(), parent_id=parent_id)
        return jsonify({
            "status": "success",
            "message": f"Folder '{res['folder_name']}' created and set as active destination.",
            "folder_id": res["folder_id"],
            "folder_name": res["folder_name"]
        }), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/backup/drive", methods=["POST"])
@api_bp.route("/drive/backup-user-data", methods=["POST"])
@login_required
@log_execution
def backup_to_drive():
    """
    Upload User Data Backup to Google Drive
    ---
    tags:
      - Google Drive
    summary: Dumps all user events, categories, and transactions into a timestamped JSON file directly in the user's Google Drive folder
    responses:
      200:
        description: Backup successfully uploaded to Drive
    """
    try:
        result = BackupService.backup_user_to_google_drive(current_user.id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


# --------------------------------------------------------------------------
# USER DATA EXPORT (DOWNLOAD)
# --------------------------------------------------------------------------

@api_bp.route("/backup/export", methods=["GET"])
@login_required
@log_execution
def export_user_backup():
    """
    Export User Data (Download)
    ---
    tags:
      - Backup & Export
    summary: Generates a downloadable JSON or CSV export of all user events, categories, and transactions
    parameters:
      - name: format
        in: query
        type: string
        enum: [json, csv]
        default: json
    responses:
      200:
        description: File download attachment
    """
    export_format = request.args.get("format", "json")
    try:
        file_bytes, filename, mime_type = BackupService.export_user_data(current_user.id, export_format=export_format)
        return send_file(
            io.BytesIO(file_bytes),
            mimetype=mime_type,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


# --------------------------------------------------------------------------
# ADMIN GLOBAL DATABASE BACKUP & RESTORE
# --------------------------------------------------------------------------

@api_bp.route("/admin/backup", methods=["GET"])
@admin_required
@log_execution
def admin_global_backup():
    """
    Global Database Backup (Admin Only)
    ---
    tags:
      - Admin
    summary: Dumps the entire application database state into a SHA256-checksummed JSON file
    responses:
      200:
        description: Global database JSON download
      403:
        description: Forbidden (Admin only)
    """
    try:
        content_bytes, filename, mime_type = BackupService.export_global_database(current_user.id)
        return send_file(
            io.BytesIO(content_bytes),
            mimetype=mime_type,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route("/admin/restore", methods=["POST"])
@admin_required
@log_execution
def admin_global_restore():
    """
    Global Database Restore (Admin Only)
    ---
    tags:
      - Admin
    summary: Restores the entire database from an uploaded JSON backup in an atomic transaction
    consumes:
      - multipart/form-data
      - application/json
    parameters:
      - in: formData
        name: backup_file
        type: file
        description: The JSON backup file previously exported from the system
    responses:
      200:
        description: Database successfully restored
      400:
        description: Invalid backup file
      403:
        description: Forbidden (Admin only)
    """
    backup_data = None
    if "backup_file" in request.files:
        f = request.files["backup_file"]
        try:
            backup_data = json.loads(f.read().decode("utf-8"))
        except Exception as parse_err:
            return jsonify({"status": "error", "message": f"Failed to parse JSON file: {str(parse_err)}"}), 400
    elif request.is_json:
        backup_data = request.get_json()

    if not backup_data:
        return jsonify({"status": "error", "message": "No backup file or JSON payload provided."}), 400

    try:
        ip_addr = request.headers.get("X-Forwarded-For", request.remote_addr)
        res = BackupService.restore_global_database(current_user.id, backup_data, ip_address=ip_addr)
        return jsonify(res), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/admin/stats", methods=["GET"])
@admin_required
@log_execution
def admin_system_stats():
    """
    Admin System Stats (Admin Only)
    ---
    tags:
      - Admin
    summary: Returns system-wide table statistics and counts
    responses:
      200:
        description: System health and counts data
      403:
        description: Forbidden (Admin only)
    """
    users_count = User.query.count()
    events_count = Event.query.count()
    txns_count = Transaction.query.count()

    return jsonify({
        "status": "success",
        "counts": {
            "users": users_count,
            "events": events_count,
            "transactions": txns_count
        }
    }), 200


@api_bp.route("/admin/users", methods=["GET"])
@admin_required
@log_execution
def admin_list_users():
    """
    List All Registered Users (Admin Only)
    ---
    tags:
      - Admin
    summary: Retrieves list of all registered users with metadata and activity counts
    responses:
      200:
        description: List of user records
      403:
        description: Forbidden (Admin only)
    """
    users = User.query.order_by(User.id.asc()).all()
    user_list = []
    for u in users:
        u_dict = u.to_dict()
        u_dict["events_count"] = u.events.count()
        event_ids = [e.id for e in u.events]
        u_dict["transactions_count"] = Transaction.query.filter(Transaction.event_id.in_(event_ids)).count() if event_ids else 0
        user_list.append(u_dict)
    return jsonify({"status": "success", "count": len(user_list), "users": user_list}), 200


@api_bp.route("/admin/users/<int:user_id>", methods=["DELETE"])
@admin_required
@log_execution
def admin_delete_user(user_id: int):
    """
    Delete User Account Completely (Admin Only)
    ---
    tags:
      - Admin
    summary: Deletes a user account and cascades all their events, categories, and transactions
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: User account deleted
      400:
        description: Validation error or self-deletion attempt
    """
    ip_addr = request.headers.get("X-Forwarded-For", request.remote_addr)
    try:
        AuthService.delete_user(current_user.id, user_id, ip_address=ip_addr)
        return jsonify({"status": "success", "message": "User account and all data deleted."}), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/admin/users/<int:user_id>/purge", methods=["POST"])
@admin_required
@log_execution
def admin_purge_user_data(user_id: int):
    """
    Purge User Financial Data (Admin Only)
    ---
    tags:
      - Admin
    summary: Purges all events, categories, and transactions belonging to a user while preserving login credentials
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: User data purged
      400:
        description: User not found
    """
    ip_addr = request.headers.get("X-Forwarded-For", request.remote_addr)
    try:
        res = AuthService.purge_user_data(current_user.id, user_id, ip_address=ip_addr)
        return jsonify({
            "status": "success",
            "message": f"Successfully purged {res.get('purged_events_count', 0)} events and associated transactions."
        }), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/admin/events", methods=["GET"])
@admin_required
@log_execution
def admin_list_all_events():
    """
    List All System Events (Admin Only)
    ---
    tags:
      - Admin
    summary: Retrieves all events across the entire platform with user ownership and statistics
    responses:
      200:
        description: Array of all events
      403:
        description: Admin only
    """
    events = EventService.get_all_system_events(is_admin=True)
    return jsonify({"status": "success", "count": len(events), "events": events}), 200


@api_bp.route("/admin/events/<int:event_id>", methods=["DELETE"])
@admin_required
@log_execution
def admin_delete_event(event_id: int):
    """
    Delete Any Event (Admin Only)
    ---
    tags:
      - Admin
    summary: Admin deletion of an event and all its associated transactions
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Event deleted
      400:
        description: Event not found
    """
    try:
        EventService.delete_event(event_id, current_user.id, is_admin=True)
        return jsonify({"status": "success", "message": "Event deleted by administrator."}), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/admin/audit", methods=["GET"])
@admin_required
@log_execution
def admin_list_audit_logs():
    """
    List Security & System Audit Logs (Admin Only)
    ---
    tags:
      - Admin
    summary: Retrieves recent system audit and security trail logs
    parameters:
      - name: limit
        in: query
        type: integer
        default: 50
    responses:
      200:
        description: Array of audit log records
      403:
        description: Forbidden (Admin only)
    """
    limit = int(request.args.get("limit", 50))
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    output = []
    for l in logs:
        log_dict = l.to_dict()
        log_dict["user_name"] = l.user.name if l.user else "System / Automated"
        output.append(log_dict)
    return jsonify({"status": "success", "count": len(output), "logs": output}), 200
