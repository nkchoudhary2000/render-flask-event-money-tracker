import io
import datetime
from flask import current_app
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from extensions import db
from models import User
from logger import app_logger, log_execution, log_external_api

class DriveService:
    """Per-user Google Drive API v3 integration service."""

    @staticmethod
    @log_execution
    def get_credentials(user: User) -> Credentials:
        """Constructs and auto-refreshes Google OAuth Credentials for a given user."""
        if not user.google_access_token and not user.google_refresh_token:
            app_logger.warning(f"[DRIVE] User ID: {user.id} does not have Google Drive credentials linked.")
            raise ValueError("Google Drive is not linked. Please sign in with Google to enable Drive features.")

        client_id = current_app.config.get("GOOGLE_CLIENT_ID")
        client_secret = current_app.config.get("GOOGLE_CLIENT_SECRET")
        scopes = current_app.config.get("GOOGLE_OAUTH_SCOPES")

        creds = Credentials(
            token=user.google_access_token,
            refresh_token=user.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
            expiry=user.google_token_expiry
        )

        # Refresh token if expired
        if creds.expired or (user.google_token_expiry and user.google_token_expiry <= datetime.datetime.utcnow()):
            app_logger.info(f"[DRIVE] Token expired for User ID: {user.id}. Refreshing access token via Google OAuth.")
            try:
                creds.refresh(Request())
                user.google_access_token = creds.token
                if creds.expiry:
                    user.google_token_expiry = creds.expiry
                db.session.commit()
                app_logger.info(f"[DRIVE] Token successfully refreshed and persisted for User ID: {user.id}")
            except Exception as e:
                app_logger.error(f"[DRIVE] Token refresh failed for User ID: {user.id}: {str(e)}")
                raise ValueError(f"Failed to refresh Google Drive access: {str(e)}")

        return creds

    @classmethod
    @log_execution
    def get_drive_client(cls, user: User):
        """Initializes and returns the Google Drive API v3 discovery client."""
        creds = cls.get_credentials(user)
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    @classmethod
    @log_execution
    def get_or_create_app_folder(cls, user: User, folder_name: str = None) -> str:
        """
        Retrieves existing designated Drive folder or creates a new one in the user's Drive.
        """
        drive = cls.get_drive_client(user)
        target_name = folder_name or user.google_drive_folder_name or current_app.config.get("GOOGLE_DRIVE_FOLDER_NAME", "EventMoneyTracker_Receipts")

        # 1. Check if existing folder_id is still valid
        if user.google_drive_folder_id:
            try:
                res = drive.files().get(fileId=user.google_drive_folder_id, fields="id, name, trashed").execute()
                log_external_api("GoogleDrive", f"files().get({user.google_drive_folder_id})", "GET", response=res)
                if res and not res.get("trashed"):
                    return user.google_drive_folder_id
            except Exception as e:
                app_logger.warning(f"[DRIVE] Existing folder ID {user.google_drive_folder_id} invalid or inaccessible: {str(e)}. Will search or recreate.")

        # 2. Search for folder by name in user's root Drive
        query = f"mimeType = 'application/vnd.google-apps.folder' and name = '{target_name}' and trashed = false"
        try:
            results = drive.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
            log_external_api("GoogleDrive", "files().list", "GET", payload={"q": query}, response=results)
            files = results.get("files", [])
            if files:
                folder_id = files[0]["id"]
                user.google_drive_folder_id = folder_id
                user.google_drive_folder_name = target_name
                db.session.commit()
                app_logger.info(f"[DRIVE] Found existing folder '{target_name}' with ID: {folder_id}")
                return folder_id
        except Exception as e:
            app_logger.error(f"[DRIVE] Error querying Drive folders: {str(e)}")

        # 3. Create folder if not found
        try:
            file_metadata = {
                "name": target_name,
                "mimeType": "application/vnd.google-apps.folder"
            }
            folder = drive.files().create(body=file_metadata, fields="id, name").execute()
            log_external_api("GoogleDrive", "files().create (Folder)", "POST", payload=file_metadata, response=folder)
            
            folder_id = folder.get("id")
            user.google_drive_folder_id = folder_id
            user.google_drive_folder_name = target_name
            db.session.commit()
            app_logger.info(f"[DRIVE] Created designated folder '{target_name}' with ID: {folder_id} for User ID: {user.id}")
            return folder_id
        except Exception as e:
            app_logger.error(f"[DRIVE] Failed to create folder in Drive: {str(e)}")
            raise ValueError(f"Failed to create Google Drive folder: {str(e)}")

    @classmethod
    @log_execution
    def upload_file(cls, user: User, file_stream, filename: str, mime_type: str, folder_id: str = None) -> dict:
        """
        Uploads an image, document or receipt directly to the user's designated Google Drive folder.
        """
        drive = cls.get_drive_client(user)
        target_folder_id = folder_id or cls.get_or_create_app_folder(user)

        file_metadata = {
            "name": filename,
            "parents": [target_folder_id]
        }

        # Wrap stream in MediaIoBaseUpload
        media = MediaIoBaseUpload(file_stream, mimetype=mime_type, resumable=True)

        try:
            app_logger.info(f"[DRIVE] Uploading file '{filename}' ({mime_type}) to folder: {target_folder_id}")
            uploaded_file = drive.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink, webContentLink, thumbnailLink"
            ).execute()

            log_external_api("GoogleDrive", "files().create (File Upload)", "POST", payload=file_metadata, response=uploaded_file)
            
            # Make file accessible via link (reader permissions)
            try:
                permission = {"type": "anyone", "role": "reader"}
                drive.permissions().create(fileId=uploaded_file.get("id"), body=permission).execute()
            except Exception as perm_err:
                app_logger.warning(f"[DRIVE] Note: Could not set public view permission: {str(perm_err)}")

            result = {
                "file_id": uploaded_file.get("id"),
                "file_name": uploaded_file.get("name"),
                "web_view_link": uploaded_file.get("webViewLink"),
                "web_content_link": uploaded_file.get("webContentLink"),
                "thumbnail_link": uploaded_file.get("thumbnailLink")
            }
            app_logger.info(f"[DRIVE] Successfully uploaded file '{filename}' -> ID: {result['file_id']}")
            return result
        except Exception as e:
            app_logger.error(f"[DRIVE] File upload to Google Drive failed: {str(e)}")
            raise ValueError(f"Failed to upload file to Google Drive: {str(e)}")

    @classmethod
    @log_execution
    def upload_backup_content(cls, user: User, content_bytes: bytes, filename: str, mime_type: str = "application/json") -> dict:
        """Uploads a user data backup directly to Google Drive."""
        stream = io.BytesIO(content_bytes)
        return cls.upload_file(user, stream, filename, mime_type)

    @classmethod
    @log_execution
    def check_drive_status(cls, user: User) -> dict:
        """Checks connection status to Google Drive."""
        if not user.has_google_drive_linked():
            return {
                "connected": False,
                "folder_id": None,
                "folder_name": user.google_drive_folder_name,
                "message": "Google Drive not linked."
            }

        try:
            folder_id = cls.get_or_create_app_folder(user)
            return {
                "connected": True,
                "folder_id": folder_id,
                "folder_name": user.google_drive_folder_name,
                "message": "Google Drive connected and folder verified."
            }
        except Exception as e:
            return {
                "connected": False,
                "folder_id": user.google_drive_folder_id,
                "folder_name": user.google_drive_folder_name,
                "message": f"Connection error: {str(e)}"
            }
