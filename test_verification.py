import os
import json
from app import create_app
from extensions import db
from models import User, Event, Category, Transaction, AuditLog
from services.auth_service import AuthService
from services.event_service import EventService
from services.backup_service import BackupService

def run_tests():
    print("=================================================================")
    print("RUNNING COMPREHENSIVE VERIFICATION SUITE")
    print("=================================================================")

    app = create_app("testing")

    with app.app_context():
        # 1. Verify DB table creation
        db.create_all()
        print("[TEST 1/8] Database Schema Initialization: SUCCESS")

        # 2. Verify First-User Admin logic
        admin_user = AuthService.register_local_user(
            email="admin@eventtracker.com",
            password="adminpassword123",
            name="Admin User",
            ip_address="127.0.0.1"
        )
        assert admin_user.is_admin is True, "First user should be admin"
        print(f"[TEST 2/8] First User Admin Elevation: SUCCESS -> User {admin_user.email} (is_admin={admin_user.is_admin})")

        # Second user should NOT be admin
        normal_user = AuthService.register_local_user(
            email="guest@eventtracker.com",
            password="guestpassword123",
            name="Guest User",
            ip_address="127.0.0.1"
        )
        assert normal_user.is_admin is False, "Subsequent users should not be admin by default"
        print(f"[TEST 2/8 (b)] Second User Non-Admin Check: SUCCESS -> User {normal_user.email} (is_admin={normal_user.is_admin})")

        # 3. Verify Account Merging (Google OAuth + Local Auth)
        fake_google_info = {
            "sub": "google-109283746",
            "email": "guest@eventtracker.com",
            "name": "Guest User Merged",
            "picture": "https://lh3.googleusercontent.com/a/sample"
        }
        fake_tokens = {
            "access_token": "fake-access-token-12345",
            "refresh_token": "fake-refresh-token-67890",
            "expires_in": 3600
        }
        merged_user = AuthService.handle_google_oauth_user(fake_google_info, fake_tokens, ip_address="127.0.0.1")
        assert merged_user.id == normal_user.id, "User IDs must match upon email merge"
        assert merged_user.google_id == "google-109283746", "Google ID must be linked"
        assert merged_user.has_google_drive_linked() is True, "Drive tokens must be recognized"
        print(f"[TEST 3/8] Account Merging (Google + Local): SUCCESS -> Linked Google ID for User {merged_user.email}")

        # 4. Verify Event & Default Category Creation (Wedding & Career/Business)
        event = EventService.create_event(
            user_id=normal_user.id,
            title="Arjun & Sneha Wedding",
            description="Wedding celebrations & rituals",
            event_type="WEDDING",
            currency="INR",
            budget_limit=500000.0
        )
        assert event.id is not None
        assert event.categories.count() > 0, "Default categories should be seeded automatically"
        print(f"[TEST 4/8] Wedding Event & Category Creation: SUCCESS -> Created Event '{event.title}' with {event.categories.count()} categories")

        # 4b. Verify Career, Freelance & Business Event Creation with Carrier Payments & Proportional Budgets
        career_event = EventService.create_event(
            user_id=normal_user.id,
            title="Q4 Freelance & Carrier Logistics",
            description="Client retainers, shipping & software tools",
            event_type="CAREER_BUSINESS",
            currency="INR",
            budget_limit=200000.0
        )
        assert career_event.id is not None
        assert career_event.event_type == "CAREER_BUSINESS"
        
        carrier_cat = career_event.categories.filter_by(name="Carrier, Freight & Shipping Payments").first()
        contractor_cat = career_event.categories.filter_by(name="Contractor & Freelancer Wages").first()
        client_inc_cat = career_event.categories.filter_by(name="Client Payments & Invoices").first()

        assert carrier_cat is not None, "Carrier category must be created"
        assert contractor_cat is not None, "Contractor category must be created"
        assert client_inc_cat is not None, "Client income category must be created"
        
        # Verify 10% carrier budget = 20,000 and 25% contractor budget = 50,000
        assert carrier_cat.budget == 20000.0, f"Expected 20,000 carrier budget, got {carrier_cat.budget}"
        assert contractor_cat.budget == 50000.0, f"Expected 50,000 contractor budget, got {contractor_cat.budget}"
        print(f"[TEST 4/8 (b)] Career & Business Event with Carrier Budgets: SUCCESS -> Carrier Budget: INR {carrier_cat.budget}, Contractor Budget: INR {contractor_cat.budget}")

        # 4c. Verify Carrier Payment Mode Transaction
        txn_carrier = EventService.create_transaction(
            event_id=career_event.id,
            user_id=normal_user.id,
            type="EXPENSE",
            amount=6500.0,
            party_name="BlueDart Freight Logistics",
            category_id=carrier_cat.id,
            payment_mode="CARRIER_PAY",
            reference_no="BLUEDART/987123654",
            description="Express package shipping for client hardware"
        )
        assert txn_carrier.id is not None and txn_carrier.payment_mode == "CARRIER_PAY"
        print(f"[TEST 4/8 (c)] Carrier Payment Mode Transaction: SUCCESS -> INR {txn_carrier.amount} to '{txn_carrier.party_name}' via {txn_carrier.payment_mode}")

        # 4d. Verify Template Application to Existing Event
        applied_cats = EventService.apply_template_to_event(
            event_id=event.id,
            user_id=normal_user.id,
            template_id="TRAVEL_TRIP",
            overwrite=False,
            auto_budget=True
        )
        assert len(applied_cats) > 0
        print(f"[TEST 4/8 (d)] Apply Template to Existing Event: SUCCESS -> Applied TRAVEL_TRIP template ({len(applied_cats)} total categories)")

        # 5. Verify Transaction Management (Expenses & Incoming Gifts)
        catering_cat = event.categories.filter_by(name="Catering & Food").first()
        gifts_cat = event.categories.filter_by(name="Gifts & Shagun Received").first()

        # Add an outgoing expense
        txn_exp = EventService.create_transaction(
            event_id=event.id,
            user_id=normal_user.id,
            type="EXPENSE",
            amount=45000.0,
            party_name="Royal Catering Services",
            category_id=catering_cat.id if catering_cat else None,
            payment_mode="UPI",
            reference_no="UPI/109283019",
            description="Advance payment for wedding feast"
        )
        assert txn_exp.id is not None

        # Add an incoming gift
        txn_inc = EventService.create_transaction(
            event_id=event.id,
            user_id=normal_user.id,
            type="INCOME",
            amount=21000.0,
            party_name="Uncle Ramesh Sharma",
            category_id=gifts_cat.id if gifts_cat else None,
            payment_mode="CASH",
            description="Shagun envelope with blessings"
        )
        assert txn_inc.id is not None

        # Check analytics
        analytics = EventService.get_event_analytics(event.id, normal_user.id)
        assert analytics["summary"]["total_expense"] == 45000.0
        assert analytics["summary"]["total_income"] == 21000.0
        assert analytics["summary"]["net_balance"] == (21000.0 - 45000.0)
        assert analytics["summary"]["budget_limit"] == 500000.0
        print(f"[TEST 5/8] Transactions & Financial Analytics: SUCCESS -> Income: INR {analytics['summary']['total_income']}, Expense: INR {analytics['summary']['total_expense']}, Net: INR {analytics['summary']['net_balance']}")

        # 6. Verify User-Level Backup (JSON & CSV)
        json_bytes, json_fn, _ = BackupService.export_user_data(normal_user.id, "json")
        csv_bytes, csv_fn, _ = BackupService.export_user_data(normal_user.id, "csv")
        assert len(json_bytes) > 0 and json_fn.endswith(".json")
        assert len(csv_bytes) > 0 and csv_fn.endswith(".csv")
        print(f"[TEST 6/8] User Backup Export (JSON & CSV): SUCCESS -> Generated {json_fn} ({len(json_bytes)} bytes) and {csv_fn} ({len(csv_bytes)} bytes)")

        # 7. Verify Admin Global Database Backup & Restore Engine
        backup_bytes, backup_fn, _ = BackupService.export_global_database(admin_user.id)
        backup_obj = json.loads(backup_bytes.decode("utf-8"))
        assert "metadata" in backup_obj and "sha256_checksum" in backup_obj["metadata"]
        assert len(backup_obj["tables"]["users"]) == 2
        print(f"[TEST 7/8] Admin Global DB Backup: SUCCESS -> Dumped DB with Checksum {backup_obj['metadata']['sha256_checksum'][:16]}...")

        # Test restore
        restore_result = BackupService.restore_global_database(admin_user.id, backup_obj, ip_address="127.0.0.1")
        assert restore_result["status"] == "success"
        assert User.query.count() == 2
        assert Event.query.count() == 2
        assert Transaction.query.count() == 3
        print(f"[TEST 7/8 (b)] Admin Global DB Restore with Transaction Safety: SUCCESS -> Restored {User.query.count()} users, {Event.query.count()} events & {Transaction.query.count()} transactions")

        # 8. Test HTTP Endpoints via Flask Test Client
        client = app.test_client()

        # Login page
        res_login = client.get("/login")
        assert res_login.status_code == 200

        # Register page
        res_reg = client.get("/register")
        assert res_reg.status_code == 200

        # Swagger Docs
        res_swagger = client.get("/apidocs/")
        assert res_swagger.status_code == 200

        # Login as Admin via /auth/local/login
        res_login_post = client.post("/auth/local/login", data={"email": "admin@eventtracker.com", "password": "adminpassword123"})
        assert res_login_post.status_code in [200, 302]

        # Test Templates API Endpoint
        res_tpl = client.get("/api/events/templates")
        assert res_tpl.status_code == 200
        tpl_data = res_tpl.get_json()
        assert tpl_data["status"] == "success" and "templates" in tpl_data
        assert "CAREER_BUSINESS" in tpl_data["templates"]
        assert "WEDDING" in tpl_data["templates"]

        # Test creating event via API with CAREER_BUSINESS template
        res_create_ev = client.post("/api/events", json={
            "title": "Corporate Annual Offsite",
            "event_type": "CAREER_BUSINESS",
            "budget_limit": 150000.0,
            "currency": "INR"
        })
        assert res_create_ev.status_code == 201
        new_ev = res_create_ev.get_json()["event"]
        ev_id = new_ev["id"]

        # Test Apply Template endpoint
        res_apply_tpl = client.post(f"/api/events/{ev_id}/categories/apply-template", json={
            "template_id": "CONFERENCE",
            "overwrite": False,
            "auto_budget": True
        })
        assert res_apply_tpl.status_code == 200
        assert res_apply_tpl.get_json()["status"] == "success"

        # Test Auto-Budget endpoint
        res_auto_bgt = client.post(f"/api/events/{ev_id}/categories/auto-budget")
        assert res_auto_bgt.status_code == 200
        assert res_auto_bgt.get_json()["status"] == "success"

        # Admin stats endpoint
        res_admin_stats = client.get("/api/admin/stats")
        assert res_admin_stats.status_code == 200
        stats_json = res_admin_stats.get_json()
        assert stats_json["status"] == "success" and "counts" in stats_json
        assert stats_json["counts"]["users"] >= 2

        # Admin users endpoint
        res_admin_users = client.get("/api/admin/users")
        assert res_admin_users.status_code == 200
        users_json = res_admin_users.get_json()
        assert users_json["status"] == "success" and len(users_json["users"]) >= 2
        assert any(u["email"] == "admin@eventtracker.com" and u["is_admin"] is True for u in users_json["users"])

        # Admin audit endpoint
        res_admin_audit = client.get("/api/admin/audit")
        assert res_admin_audit.status_code == 200
        audit_json = res_admin_audit.get_json()
        assert audit_json["status"] == "success" and len(audit_json["logs"]) >= 1

        # Admin platform events endpoint
        res_admin_events = client.get("/api/admin/events")
        assert res_admin_events.status_code == 200
        events_json = res_admin_events.get_json()
        assert events_json["status"] == "success" and len(events_json["events"]) >= 1

        # Admin purge user data
        guest_user = User.query.filter_by(email="guest@eventtracker.com").first()
        assert guest_user is not None
        res_purge = client.post(f"/api/admin/users/{guest_user.id}/purge")
        assert res_purge.status_code == 200
        assert guest_user.events.count() == 0

        # Admin delete user
        res_del_user = client.delete(f"/api/admin/users/{guest_user.id}")
        assert res_del_user.status_code == 200
        assert User.query.filter_by(email="guest@eventtracker.com").first() is None

        print(f"[TEST 8/8] Flask Test Client & Admin/Template Endpoints: SUCCESS -> HTTP 200 on /login, /register, /apidocs/, /api/events/templates, /api/events, /api/events/<id>/categories/apply-template, /api/events/<id>/categories/auto-budget, /api/admin/stats, /api/admin/users, /api/admin/events, /api/admin/users/<id>/purge, /api/admin/users/<id>")

    print("=================================================================")
    print("ALL 8 VERIFICATION SUITES PASSED FLAWLESSLY!")
    print("=================================================================")

if __name__ == "__main__":
    run_tests()

