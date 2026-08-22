import datetime
from sqlalchemy import func, case
from extensions import db
from models import Event, Category, Transaction, User
from services.drive_service import DriveService
from logger import app_logger, log_execution, log_db_transaction

DEFAULT_CATEGORIES = [
    {"name": "Gifts & Shagun Received", "type": "INCOME", "color": "#10b981", "icon": "fa-gift"},
    {"name": "Catering & Food", "type": "EXPENSE", "color": "#f59e0b", "icon": "fa-utensils"},
    {"name": "Decorations & Stage", "type": "EXPENSE", "color": "#8b5cf6", "icon": "fa-holly-berry"},
    {"name": "Venue & Accommodation", "type": "EXPENSE", "color": "#3b82f6", "icon": "fa-hotel"},
    {"name": "Photography & Video", "type": "EXPENSE", "color": "#ec4899", "icon": "fa-camera"},
    {"name": "Entertainment & DJ", "type": "EXPENSE", "color": "#6366f1", "icon": "fa-music"},
    {"name": "Clothing & Jewelry", "type": "EXPENSE", "color": "#14b8a6", "icon": "fa-gem"},
    {"name": "Travel & Logistics", "type": "EXPENSE", "color": "#f97316", "icon": "fa-car"},
    {"name": "Miscellaneous Expenses", "type": "EXPENSE", "color": "#64748b", "icon": "fa-receipt"}
]

class EventService:
    """Business logic for Events, Categories, Transactions, and Financial Analytics."""

    @staticmethod
    @log_execution
    def create_event(user_id: int, title: str, description: str = "", event_date = None, 
                     currency: str = "INR", budget_limit: float = None, auto_seed_categories: bool = True) -> Event:
        """Creates a new event and optionally seeds default event categories."""
        if not title or not title.strip():
            raise ValueError("Event title is required.")

        parsed_date = event_date
        if isinstance(event_date, str) and event_date:
            try:
                parsed_date = datetime.datetime.strptime(event_date, "%Y-%m-%d").date()
            except ValueError:
                parsed_date = datetime.date.today()
        elif not parsed_date:
            parsed_date = datetime.date.today()

        event = Event(
            user_id=user_id,
            title=title.strip(),
            description=description.strip() if description else None,
            event_date=parsed_date,
            currency=currency.upper() if currency else "INR",
            budget_limit=float(budget_limit) if budget_limit is not None and str(budget_limit).strip() != "" else None
        )

        db.session.add(event)
        db.session.flush()

        if auto_seed_categories:
            for cat_def in DEFAULT_CATEGORIES:
                cat = Category(
                    event_id=event.id,
                    name=cat_def["name"],
                    type=cat_def["type"],
                    color=cat_def["color"],
                    icon=cat_def["icon"]
                )
                db.session.add(cat)

        db.session.commit()
        log_db_transaction("CREATE", "Event", event.id, {"title": event.title, "user_id": user_id})
        app_logger.info(f"[EVENT] Created Event ID: {event.id} ('{event.title}') for User ID: {user_id}")
        return event

    @staticmethod
    @log_execution
    def get_user_events(user_id: int, include_stats: bool = True) -> list:
        """Fetches all events belonging to a user."""
        events = Event.query.filter_by(user_id=user_id).order_by(Event.event_date.desc(), Event.created_at.desc()).all()
        return [e.to_dict(include_stats=include_stats) for e in events]

    @staticmethod
    @log_execution
    def get_all_system_events(is_admin: bool = True) -> list:
        """Fetches all events across the entire system with owner information."""
        if not is_admin:
            raise ValueError("Admin privileges required.")
        events = Event.query.order_by(Event.created_at.desc()).all()
        result = []
        for e in events:
            d = e.to_dict(include_stats=True)
            d["owner_email"] = e.user.email if e.user else "Deleted User"
            d["owner_name"] = e.user.name if e.user else "Deleted User"
            result.append(d)
        return result

    @staticmethod
    @log_execution
    def get_event(event_id: int, user_id: int, is_admin: bool = False) -> Event:
        """Fetches an event by ID verifying ownership or admin status."""
        query = Event.query.filter_by(id=event_id)
        if not is_admin:
            query = query.filter_by(user_id=user_id)
        event = query.first()
        if not event:
            app_logger.warning(f"[EVENT] Event ID: {event_id} not found or access denied for User ID: {user_id}")
            raise ValueError("Event not found or unauthorized.")
        return event

    @staticmethod
    @log_execution
    def update_event(event_id: int, user_id: int, data: dict, is_admin: bool = False) -> Event:
        """Updates event metadata."""
        event = EventService.get_event(event_id, user_id, is_admin)
        
        if "title" in data and data["title"]:
            event.title = data["title"].strip()
        if "description" in data:
            event.description = data["description"].strip() if data["description"] else None
        if "currency" in data and data["currency"]:
            event.currency = data["currency"].upper()
        if "budget_limit" in data:
            val = data["budget_limit"]
            event.budget_limit = float(val) if val is not None and str(val).strip() != "" else None
        if "status" in data and data["status"]:
            event.status = data["status"]
        if "event_date" in data and data["event_date"]:
            try:
                event.event_date = datetime.datetime.strptime(data["event_date"], "%Y-%m-%d").date()
            except Exception:
                pass

        db.session.commit()
        log_db_transaction("UPDATE", "Event", event.id, data)
        return event

    @staticmethod
    @log_execution
    def delete_event(event_id: int, user_id: int, is_admin: bool = False) -> bool:
        """Deletes an event and all associated categories and transactions."""
        event = EventService.get_event(event_id, user_id, is_admin)
        db.session.delete(event)
        db.session.commit()
        log_db_transaction("DELETE", "Event", event_id)
        app_logger.info(f"[EVENT] Deleted Event ID: {event_id} for User ID: {user_id}")
        return True

    # ------------------ CATEGORY OPERATIONS ------------------

    @staticmethod
    @log_execution
    def create_category(event_id: int, user_id: int, name: str, type: str = "EXPENSE",
                        color: str = "#6366f1", icon: str = "fa-tag", budget: float = None, is_admin: bool = False) -> Category:
        """Creates a custom category within an event."""
        event = EventService.get_event(event_id, user_id, is_admin)
        if not name or not name.strip():
            raise ValueError("Category name is required.")

        category = Category(
            event_id=event.id,
            name=name.strip(),
            type=type.upper() if type in ["EXPENSE", "INCOME", "BOTH"] else "EXPENSE",
            color=color or "#6366f1",
            icon=icon or "fa-tag",
            budget=float(budget) if budget is not None and str(budget).strip() != "" else None
        )
        db.session.add(category)
        db.session.commit()
        log_db_transaction("CREATE", "Category", category.id, {"event_id": event.id, "name": category.name})
        return category

    @staticmethod
    @log_execution
    def get_event_categories(event_id: int, user_id: int, include_totals: bool = True, is_admin: bool = False) -> list:
        """Fetches categories belonging to an event with ultra-fast aggregated totals."""
        event = EventService.get_event(event_id, user_id, is_admin)
        
        categories = Category.query.filter_by(event_id=event.id).order_by(Category.name.asc()).all()
        if not include_totals or not categories:
            return [c.to_dict(include_totals=False) for c in categories]

        cat_stats = db.session.query(
            Transaction.category_id,
            func.coalesce(func.sum(case((Transaction.type == 'EXPENSE', Transaction.amount), else_=0)), 0).label('spent'),
            func.coalesce(func.sum(case((Transaction.type == 'INCOME', Transaction.amount), else_=0)), 0).label('received'),
            func.count(Transaction.id).label('count')
        ).filter(
            Transaction.event_id == event.id,
            Transaction.category_id.isnot(None)
        ).group_by(
            Transaction.category_id
        ).all()

        stats_map = {row[0]: (float(row[1] or 0), float(row[2] or 0), int(row[3] or 0)) for row in cat_stats}

        output = []
        for cat in categories:
            d = cat.to_dict(include_totals=False)
            spent, received, count = stats_map.get(cat.id, (0.0, 0.0, 0))
            d["total_spent"] = spent
            d["total_received"] = received
            d["transaction_count"] = count
            output.append(d)
        return output

    @staticmethod
    @log_execution
    def update_category(category_id: int, user_id: int, data: dict, is_admin: bool = False) -> Category:
        """Updates category name, budget, color, icon, or type."""
        category = Category.query.get(category_id)
        if not category:
            raise ValueError("Category not found.")
        EventService.get_event(category.event_id, user_id, is_admin)

        if "name" in data and data["name"]:
            category.name = data["name"].strip()
        if "type" in data and data["type"] in ["EXPENSE", "INCOME", "BOTH"]:
            category.type = data["type"]
        if "color" in data and data["color"]:
            category.color = data["color"].strip()
        if "icon" in data and data["icon"]:
            category.icon = data["icon"].strip()
        if "budget" in data:
            val = data["budget"]
            category.budget = float(val) if val is not None and str(val).strip() != "" else None

        db.session.commit()
        log_db_transaction("UPDATE", "Category", category.id, data)
        return category

    @staticmethod
    @log_execution
    def delete_category(category_id: int, user_id: int, is_admin: bool = False) -> bool:
        """Deletes a category."""
        category = Category.query.get(category_id)
        if not category:
            raise ValueError("Category not found.")
        # Verify event ownership
        EventService.get_event(category.event_id, user_id, is_admin)
        
        db.session.delete(category)
        db.session.commit()
        log_db_transaction("DELETE", "Category", category_id)
        return True

    # ------------------ TRANSACTION OPERATIONS ------------------

    @staticmethod
    @log_execution
    def create_transaction(event_id: int, user_id: int, type: str, amount: float,
                           party_name: str, category_id: int = None, payment_mode: str = "CASH",
                           reference_no: str = None, description: str = None,
                           transaction_date = None, receipt_file = None, is_admin: bool = False) -> Transaction:
        """
        Creates a new transaction (Expense or Income) with optional Google Drive receipt upload.
        """
        event = EventService.get_event(event_id, user_id, is_admin)
        user = User.query.get(user_id)

        try:
            amt = float(amount)
            if amt <= 0:
                raise ValueError("Amount must be greater than zero.")
        except (ValueError, TypeError):
            raise ValueError("Invalid monetary amount.")

        if not party_name or not party_name.strip():
            raise ValueError("Payee or Contributor name is required.")

        txn_type = type.upper()
        if txn_type not in ["EXPENSE", "INCOME"]:
            txn_type = "EXPENSE"

        parsed_date = datetime.datetime.utcnow()
        if transaction_date:
            if isinstance(transaction_date, str):
                try:
                    parsed_date = datetime.datetime.fromisoformat(transaction_date.replace("Z", "+00:00"))
                except ValueError:
                    try:
                        parsed_date = datetime.datetime.strptime(transaction_date, "%Y-%m-%d")
                    except ValueError:
                        parsed_date = datetime.datetime.utcnow()
            elif isinstance(transaction_date, datetime.datetime):
                parsed_date = transaction_date

        drive_file_id = None
        drive_web_view_link = None
        drive_file_name = None
        drive_thumbnail_link = None

        # Process receipt upload to Google Drive if file provided
        if receipt_file and hasattr(receipt_file, "filename") and receipt_file.filename:
            app_logger.info(f"[TRANSACTION] Receipt file attached: '{receipt_file.filename}'. Checking Google Drive integration.")
            if user and user.has_google_drive_linked():
                try:
                    upload_res = DriveService.upload_file(
                        user=user,
                        file_stream=receipt_file.stream,
                        filename=f"Receipt_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{receipt_file.filename}",
                        mime_type=receipt_file.mimetype or "application/octet-stream"
                    )
                    drive_file_id = upload_res.get("file_id")
                    drive_file_name = upload_res.get("file_name")
                    drive_web_view_link = upload_res.get("web_view_link")
                    drive_thumbnail_link = upload_res.get("thumbnail_link")
                    app_logger.info(f"[TRANSACTION] Receipt uploaded to Drive -> ID: {drive_file_id}")
                except Exception as drive_err:
                    app_logger.error(f"[TRANSACTION] Failed to upload receipt to Drive: {str(drive_err)}. Proceeding without drive link.")
            else:
                app_logger.warning("[TRANSACTION] User does not have Google Drive linked. Skipping cloud receipt upload.")

        txn = Transaction(
            event_id=event.id,
            category_id=category_id if category_id and category_id > 0 else None,
            type=txn_type,
            amount=amt,
            party_name=party_name.strip(),
            payment_mode=payment_mode.upper() if payment_mode else "CASH",
            reference_no=reference_no.strip() if reference_no else None,
            description=description.strip() if description else None,
            transaction_date=parsed_date,
            drive_file_id=drive_file_id,
            drive_web_view_link=drive_web_view_link,
            drive_file_name=drive_file_name,
            drive_thumbnail_link=drive_thumbnail_link
        )

        db.session.add(txn)
        db.session.commit()
        log_db_transaction("CREATE", "Transaction", txn.id, {"event_id": event.id, "amount": amt, "type": txn_type})
        app_logger.info(f"[TRANSACTION] Created {txn_type} transaction ID: {txn.id} ({amt}) for Event ID: {event.id}")
        return txn

    @staticmethod
    @log_execution
    def get_event_transactions(event_id: int, user_id: int, category_id: int = None,
                               type: str = None, payment_mode: str = None, search: str = None,
                               is_admin: bool = False) -> list:
        """Queries transactions with dynamic filtering."""
        event = EventService.get_event(event_id, user_id, is_admin)
        query = Transaction.query.filter_by(event_id=event.id)

        if category_id and category_id > 0:
            query = query.filter_by(category_id=category_id)
        if type and type.upper() in ["EXPENSE", "INCOME"]:
            query = query.filter_by(type=type.upper())
        if payment_mode and payment_mode.upper() != "ALL":
            query = query.filter_by(payment_mode=payment_mode.upper())
        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.filter(
                (Transaction.party_name.ilike(term)) |
                (Transaction.description.ilike(term)) |
                (Transaction.reference_no.ilike(term))
            )

        transactions = query.order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).all()
        return [t.to_dict() for t in transactions]

    @staticmethod
    @log_execution
    def delete_transaction(transaction_id: int, user_id: int, is_admin: bool = False) -> bool:
        """Deletes a transaction."""
        txn = Transaction.query.get(transaction_id)
        if not txn:
            raise ValueError("Transaction not found.")
        EventService.get_event(txn.event_id, user_id, is_admin)

        db.session.delete(txn)
        db.session.commit()
        log_db_transaction("DELETE", "Transaction", transaction_id)
        return True

    # ------------------ COMPREHENSIVE ANALYTICS ------------------

    @staticmethod
    @log_execution
    def get_event_analytics(event_id: int, user_id: int, is_admin: bool = False) -> dict:
        """
        Calculates complete financial aggregates, cash flows, category percentages,
        contributor/payee summaries, and timeline series for high-speed dashboard visualization.
        """
        event = EventService.get_event(event_id, user_id, is_admin)
        all_txns = Transaction.query.filter_by(event_id=event.id).all()

        total_income = sum(t.amount for t in all_txns if t.type == "INCOME")
        total_expense = sum(t.amount for t in all_txns if t.type == "EXPENSE")
        net_balance = total_income - total_expense

        budget_limit = event.budget_limit or 0.0
        budget_remaining = budget_limit - total_expense if budget_limit > 0 else None
        budget_utilization = round((total_expense / budget_limit) * 100, 1) if budget_limit > 0 else 0.0

        # Category Breakdown
        categories = event.categories.all()
        cat_map = {c.id: {"id": c.id, "name": c.name, "color": c.color, "icon": c.icon, "type": c.type, "total_expense": 0.0, "total_income": 0.0, "count": 0} for c in categories}
        uncategorized_expense = 0.0
        uncategorized_income = 0.0

        for t in all_txns:
            if t.category_id in cat_map:
                cat_data = cat_map[t.category_id]
                if t.type == "EXPENSE":
                    cat_data["total_expense"] += t.amount
                else:
                    cat_data["total_income"] += t.amount
                cat_data["count"] += 1
            else:
                if t.type == "EXPENSE":
                    uncategorized_expense += t.amount
                else:
                    uncategorized_income += t.amount

        category_breakdown = list(cat_map.values())
        if uncategorized_expense > 0 or uncategorized_income > 0:
            category_breakdown.append({
                "id": None,
                "name": "Uncategorized",
                "color": "#94a3b8",
                "icon": "fa-question-circle",
                "type": "BOTH",
                "total_expense": uncategorized_expense,
                "total_income": uncategorized_income,
                "count": 0
            })

        # Calculate percentages of total expense for categories
        for cat in category_breakdown:
            cat["expense_percentage"] = round((cat["total_expense"] / total_expense * 100), 1) if total_expense > 0 else 0.0

        # Payment Mode Distribution
        payment_modes = {}
        for t in all_txns:
            pm = t.payment_mode or "OTHER"
            if pm not in payment_modes:
                payment_modes[pm] = {"mode": pm, "total_expense": 0.0, "total_income": 0.0, "count": 0}
            if t.type == "EXPENSE":
                payment_modes[pm]["total_expense"] += t.amount
            else:
                payment_modes[pm]["total_income"] += t.amount
            payment_modes[pm]["count"] += 1

        # Top Contributors (Incoming Gifts)
        contributors = {}
        payees = {}
        for t in all_txns:
            if t.type == "INCOME":
                contributors[t.party_name] = contributors.get(t.party_name, 0.0) + t.amount
            elif t.type == "EXPENSE":
                payees[t.party_name] = payees.get(t.party_name, 0.0) + t.amount

        top_contributors = sorted([{"name": k, "amount": v} for k, v in contributors.items()], key=lambda x: x["amount"], reverse=True)[:5]
        top_payees = sorted([{"name": k, "amount": v} for k, v in payees.items()], key=lambda x: x["amount"], reverse=True)[:5]

        # Recent Transactions
        recent = [t.to_dict() for t in sorted(all_txns, key=lambda x: x.transaction_date or datetime.datetime.min, reverse=True)[:10]]

        return {
            "event": event.to_dict(),
            "summary": {
                "total_income": total_income,
                "total_expense": total_expense,
                "net_balance": net_balance,
                "transaction_count": len(all_txns),
                "budget_limit": budget_limit,
                "budget_remaining": budget_remaining,
                "budget_utilization": budget_utilization
            },
            "category_breakdown": category_breakdown,
            "payment_modes": list(payment_modes.values()),
            "top_contributors": top_contributors,
            "top_payees": top_payees,
            "recent_transactions": recent
        }
