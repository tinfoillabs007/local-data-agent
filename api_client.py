import requests
import logging
from typing import Dict, Any, Optional
import sys
import os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Now we can use absolute imports
import config
from token_storage import TokenStorage # Assuming TokenStorage is needed

logger = logging.getLogger(__name__)

class McpApiClient:
    """Client for interacting with the MCP Worker API."""
    def __init__(self, token_storage: TokenStorage):
        self.token_storage = token_storage
        self.config = config

    def _make_request(self, method: str, path: str, access_token: Optional[str] = None, **kwargs) -> requests.Response:
        """Helper function to make requests to the MCP API."""
        if not self.config.MCP_WORKER_API_URL:
            raise ValueError("MCP_WORKER_API_URL not configured.")
        url = f"{self.config.MCP_WORKER_API_URL}{path}"
        logger.debug(f"Making request to URL: {url}")

        headers = kwargs.pop("headers", {})
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        try:
            response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            return response
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error occurred: {e.response.status_code} {e.response.reason} for URL: {url}")
            try:
                error_details = e.response.json()
                logger.error(f"Error details: {error_details}")
            except ValueError:
                logger.error(f"Error response body: {e.response.text[:500]}...")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Network or request error for URL {url}: {e}")
            raise
        except Exception as e:
            logger.exception(f"An unexpected error occurred during the request to {url}: {e}")
            raise

    def _get_access_token(self) -> Optional[str]:
         """Retrieves a valid access token from storage. Assumes OAuthFlow handled refresh/new token."""
         tokens = self.token_storage.load_tokens()
         if tokens and not self.token_storage.is_token_expired(tokens):
             return tokens.get('access_token')
         # Ideally, OAuthFlow should be called before API client methods if token is missing/expired
         # This client doesn't handle the auth flow itself.
         logger.warning("No valid access token found in storage.")
         return None

    def get_vault_data(self) -> Optional[Dict[str, Any]]:
        """Fetches data from the /api/vault endpoint."""
        access_token = self._get_access_token()
        if not access_token:
            logger.error("Cannot fetch vault data without a valid access token.")
            return None

        try:
            logger.info(f"Fetching vault data from /api/vault...")
            response = self._make_request("GET", "/api/vault", access_token=access_token)
            vault_data = response.json()
            logger.info("Successfully fetched vault data.")
            return vault_data
        except (requests.exceptions.RequestException, ValueError, Exception) as e:
            logger.error(f"Failed to fetch vault data: {e}")
            return None

    def save_vault_data(self, data_to_save: Dict[str, Any]) -> bool:
        """Saves data to the /api/vault endpoint."""
        access_token = self._get_access_token()
        if not access_token:
            logger.error("Cannot save vault data without a valid access token.")
            return False

        try:
            logger.info(f"Saving vault data to /api/vault...")
            response = self._make_request("POST", "/api/vault", access_token=access_token, json=data_to_save)
            logger.info(f"Vault data saved successfully. Status code: {response.status_code}")
            return True
        except (requests.exceptions.RequestException, ValueError, Exception) as e:
            logger.error(f"Failed to save vault data: {e}")
            return False

    def clear_vault_data(self) -> bool:
        """Deletes vault data via the DELETE /api/vault endpoint."""
        access_token = self._get_access_token()
        if not access_token:
            logger.error("Cannot clear vault data without a valid access token.")
            return False

        try:
            logger.info(f"Sending request to clear vault data via DELETE /api/vault...")
            response = self._make_request("DELETE", "/api/vault", access_token=access_token)
            # DELETE typically returns 200 OK or 204 No Content on success
            logger.info(f"Vault data cleared successfully. Status code: {response.status_code}")
            return True
        except (requests.exceptions.RequestException, ValueError, Exception) as e:
            logger.error(f"Failed to clear vault data: {e}")
            return False

# The introspect_token function might belong better in oauth_flow.py or a dedicated auth_client.py
# Keeping it here for now, but making it a standalone function as it calls the AUTH_WORKER_URL
def introspect_token(access_token: str) -> Optional[Dict[str, Any]]:
    """Calls the auth-worker's /introspect endpoint."""
    if not config.AUTH_WORKER_URL:
        raise ValueError("AUTH_WORKER_URL not configured.")
    introspect_url = f"{config.AUTH_WORKER_URL}/introspect"
    payload = {"token": access_token}
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }
    try:
        logger.info(f"Introspecting token via {introspect_url}...")
        # Using requests directly here as it's not calling MCP_WORKER_API_URL
        response = requests.post(introspect_url, data=payload, headers=headers, timeout=30)
        response.raise_for_status()
        introspection_data = response.json()
        logger.info(f"Token introspection successful. Active: {introspection_data.get('active')}")
        return introspection_data
    except (requests.exceptions.RequestException, ValueError, Exception) as e:
        logger.error(f"Token introspection failed: {e}")
        return None 