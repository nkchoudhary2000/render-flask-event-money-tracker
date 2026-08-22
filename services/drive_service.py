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
    def list_user_drive_folders(cls, user: User, parent_id: str = "root") -> dict:
        """
        Lists folders inside a specific parent (defaults to 'root') with metadata and web links.
        """
        drive = cls.get_drive_client(user)
        target_parent = parent_id.strip() if (parent_id and parent_id.strip()) else "root"

        query = f"mimeType = 'application/vnd.google-apps.folder' and trashed = false and '{target_parent}' in parents"
        try:
            results = drive.files().list(
                q=query,
                spaces="drive",
                fields="files(id, name, modifiedTime, webViewLink, parents)",
                orderBy="name asc",
                pageSize=100
            ).execute()
            log_external_api("GoogleDrive", "files().list (Folders)", "GET", payload={"q": query}, response=results)

            current_folder_info = {"id": target_parent, "name": "Google Drive (Root)", "is_root": True, "parents": []}
            if target_parent != "root":
                try:
                    f_info = drive.files().get(fileId=target_parent, fields="id, name, webViewLink, parents").execute()
                    current_folder_info = {
                        "id": f_info.get("id"),
                        "name": f_info.get("name"),
                        "webViewLink": f_info.get("webViewLink", f"https://drive.google.com/drive/folders/{target_parent}"),
                        "parents": f_info.get("parents", []),
                        "is_root": False
                    }
                except Exception as ex:
                    app_logger.warning(f"[DRIVE] Could not get metadata for parent folder {target_parent}: {str(ex)}")

            return {
                "current_parent": current_folder_info,
                "folders": results.get("files", [])
            }
        except Exception as e:
            app_logger.error(f"[DRIVE] Error listing user Drive folders under parent '{target_parent}': {str(e)}")
            raise ValueError(f"Could not load Google Drive folders: {str(e)}")

    @classmethod
    @log_execution
    def set_user_designated_folder(cls, user: User, folder_id: str, folder_name: str = None) -> dict:
        """
        Sets an existing Google Drive folder as the designated destination for backups & receipts.
        """
        drive = cls.get_drive_client(user)
        try:
            res = drive.files().get(fileId=folder_id, fields="id, name, trashed, mimeType").execute()
            if not res or res.get("trashed"):
                raise ValueError("Selected folder is invalid or in trash.")
            if res.get("mimeType") != "application/vnd.google-apps.folder":
                raise ValueError("Selected item is not a Google Drive folder.")

            actual_name = res.get("name", folder_name or "Custom Folder")
            user.google_drive_folder_id = folder_id
            user.google_drive_folder_name = actual_name
            db.session.commit()
            app_logger.info(f"[DRIVE] Designated Drive folder set to '{actual_name}' (ID: {folder_id}) for User ID: {user.id}")
            return {
                "folder_id": folder_id,
                "folder_name": actual_name
            }
        except Exception as e:
            app_logger.error(f"[DRIVE] Failed to set designated folder: {str(e)}")
            raise ValueError(f"Failed to set designated Google Drive folder: {str(e)}")

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
