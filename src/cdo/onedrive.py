"""
OneDrive File Storage via Microsoft Graph API

Uploads pattern files, AI sketches, and tech pack documents to OneDrive
so they're accessible in OneDrive/Teams. Uses MSAL client credentials
(app-only auth, no user login needed).
"""
import logging
from typing import Optional, Dict

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Folder structure in OneDrive
FOLDERS = {
    "patterns": "Patterns",
    "sketches": "Sketches",
    "techpacks": "TechPacks",
    "reports": "Reports",
}


class OneDriveStorage:
    """Manages file uploads to OneDrive via Microsoft Graph API."""

    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expires = 0

    @property
    def is_configured(self) -> bool:
        """Check if OneDrive credentials are configured."""
        return bool(
            settings.onedrive_client_id and
            settings.onedrive_client_secret and
            settings.onedrive_tenant_id and
            settings.onedrive_user_id
        )

    def _get_access_token(self) -> Optional[str]:
        """Get access token using MSAL client credentials flow."""
        import time

        if self._access_token and time.time() < self._token_expires - 60:
            return self._access_token

        if not self.is_configured:
            logger.warning("OneDrive not configured - missing credentials")
            return None

        try:
            import msal

            app = msal.ConfidentialClientApplication(
                settings.onedrive_client_id,
                authority=f"https://login.microsoftonline.com/{settings.onedrive_tenant_id}",
                client_credential=settings.onedrive_client_secret,
            )

            result = app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )

            if "access_token" in result:
                self._access_token = result["access_token"]
                self._token_expires = time.time() + result.get("expires_in", 3600)
                return self._access_token
            else:
                logger.error(f"Token acquisition failed: {result.get('error_description')}")
                return None

        except ImportError:
            logger.error("msal package not installed")
            return None
        except Exception as e:
            logger.error(f"Token acquisition error: {e}")
            return None

    def _ensure_folder(self, folder_path: str) -> Optional[str]:
        """Ensure folder exists in OneDrive, create if needed.

        Returns the folder's item ID.
        """
        import httpx

        token = self._get_access_token()
        if not token:
            return None

        headers = {"Authorization": f"Bearer {token}"}
        user_id = settings.onedrive_user_id
        base = f"https://graph.microsoft.com/v1.0/users/{user_id}/drive"

        # Try to get the folder
        try:
            response = httpx.get(
                f"{base}/root:/{folder_path}",
                headers=headers,
                timeout=10.0,
            )

            if response.status_code == 200:
                return response.json().get("id")

            # Folder doesn't exist - create it recursively
            parts = folder_path.split("/")
            current_path = ""
            current_id = None

            for part in parts:
                parent = f"root:/{current_path}:" if current_path else "root"
                create_response = httpx.post(
                    f"{base}/{parent}/children",
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "name": part,
                        "folder": {},
                        "@microsoft.graph.conflictBehavior": "replace",
                    },
                    timeout=10.0,
                )

                if create_response.status_code in (200, 201):
                    current_id = create_response.json().get("id")
                    current_path = f"{current_path}/{part}" if current_path else part
                elif create_response.status_code == 409:
                    # Already exists, get its ID
                    get_response = httpx.get(
                        f"{base}/root:/{current_path}/{part}" if current_path else f"{base}/root:/{part}",
                        headers=headers,
                        timeout=10.0,
                    )
                    if get_response.status_code == 200:
                        current_id = get_response.json().get("id")
                        current_path = f"{current_path}/{part}" if current_path else part
                    else:
                        logger.error(f"Failed to get existing folder {part}")
                        return None
                else:
                    logger.error(f"Failed to create folder {part}: {create_response.status_code}")
                    return None

            return current_id

        except Exception as e:
            logger.error(f"Folder ensure error: {e}")
            return None

    def upload_file(
        self,
        folder_type: str,
        filename: str,
        content: bytes,
        subfolder: str = None,
    ) -> Optional[Dict]:
        """Upload a file to OneDrive.

        Args:
            folder_type: One of 'patterns', 'sketches', 'techpacks', 'reports'
            filename: Name for the file
            content: File content as bytes
            subfolder: Optional subfolder within the type folder

        Returns:
            Dict with file_id, share_link, web_url or None on failure
        """
        if not self.is_configured:
            logger.warning("OneDrive not configured - file not uploaded")
            return None

        import httpx

        token = self._get_access_token()
        if not token:
            return None

        # Build folder path
        base_path = settings.onedrive_folder_path
        type_folder = FOLDERS.get(folder_type, folder_type)
        folder_path = f"{base_path}/{type_folder}"
        if subfolder:
            folder_path = f"{folder_path}/{subfolder}"

        # Ensure folder exists
        self._ensure_folder(folder_path)

        # Upload file
        user_id = settings.onedrive_user_id
        upload_url = (
            f"https://graph.microsoft.com/v1.0/users/{user_id}/drive"
            f"/root:/{folder_path}/{filename}:/content"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        }

        try:
            response = httpx.put(
                upload_url,
                headers=headers,
                content=content,
                timeout=30.0,
            )

            if response.status_code in (200, 201):
                data = response.json()
                file_id = data.get("id")
                web_url = data.get("webUrl")

                # Create share link
                share_link = self.create_share_link(file_id)

                logger.info(f"Uploaded {filename} to OneDrive: {folder_path}")

                return {
                    "file_id": file_id,
                    "web_url": web_url,
                    "share_link": share_link,
                    "folder_path": folder_path,
                    "filename": filename,
                    "size_bytes": len(content),
                }
            else:
                logger.error(f"Upload failed: {response.status_code} {response.text}")
                return None

        except Exception as e:
            logger.error(f"Upload error: {e}")
            return None

    def create_share_link(self, file_id: str) -> Optional[str]:
        """Create a shareable link for a file.

        Returns the share URL or None.
        """
        if not file_id:
            return None

        import httpx

        token = self._get_access_token()
        if not token:
            return None

        user_id = settings.onedrive_user_id
        url = (
            f"https://graph.microsoft.com/v1.0/users/{user_id}/drive"
            f"/items/{file_id}/createLink"
        )

        try:
            response = httpx.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "type": "view",
                    "scope": "organization",
                },
                timeout=10.0,
            )

            if response.status_code in (200, 201):
                return response.json().get("link", {}).get("webUrl")
            else:
                logger.warning(f"Share link creation failed: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Share link error: {e}")
            return None

    def download_file(self, file_id: str) -> Optional[bytes]:
        """Download a file from OneDrive by its item ID."""
        import httpx

        token = self._get_access_token()
        if not token:
            return None

        user_id = settings.onedrive_user_id
        url = (
            f"https://graph.microsoft.com/v1.0/users/{user_id}/drive"
            f"/items/{file_id}/content"
        )

        try:
            response = httpx.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
                follow_redirects=True,
            )

            if response.status_code == 200:
                return response.content
            else:
                logger.error(f"Download failed: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Download error: {e}")
            return None


# Singleton instance
onedrive = OneDriveStorage()
