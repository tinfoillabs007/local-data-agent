import logging
import requests
import json
import time
import webbrowser
import sys
import os
from typing import Optional, Dict, Any
from urllib.parse import urlencode
from queue import Queue, Empty

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Now we can use absolute imports
import config
import oauth_utils
from token_storage import TokenStorage

logger = logging.getLogger(__name__)

# Global variable for token storage
_global_token_storage: Optional[TokenStorage] = None

# Queue reference for auth code
_auth_code_queue_ref: Optional[Queue] = None

def set_auth_code_queue(queue: Queue):
    """Sets the queue reference for initiate_authorization to use."""
    global _auth_code_queue_ref
    logger.debug("Setting auth code queue reference.")
    _auth_code_queue_ref = queue

def set_global_token_storage(storage: TokenStorage):
    """Sets the global token storage instance."""
    global _global_token_storage
    _global_token_storage = storage

def exchange_code_for_token(code: str, verifier: str) -> Optional[Dict[str, Any]]:
    """Exchanges the authorization code and verifier for access and refresh tokens."""
    if _global_token_storage is None:
        logger.error("Global token storage not set before calling exchange_code_for_token")
        return None

    token_url = f"{config.AUTH_WORKER_URL}/token"
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': config.REDIRECT_URI,
        'client_id': config.CLIENT_ID,
        'code_verifier': verifier,
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    try:
        logger.info(f"Requesting tokens from {token_url}...")
        response = requests.post(token_url, data=payload, headers=headers, timeout=30)
        response.raise_for_status()

        tokens = response.json()
        logger.info("Successfully received tokens from auth server.")

        # Save the tokens using the global storage
        _global_token_storage.save_tokens(tokens)

        return tokens

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during token exchange: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            except Exception:
                logger.error("Could not parse error response body.")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON response from token endpoint: {e}")
        logger.error(f"Raw response text: {response.text if 'response' in locals() else 'N/A'}")
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred during token exchange: {e}")
        return None

def refresh_access_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Refreshes the access token using the refresh token."""
    if _global_token_storage is None:
        logger.error("Global token storage not set before calling refresh_access_token")
        return None

    token_url = f"{config.AUTH_WORKER_URL}/token"
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': config.CLIENT_ID,
        'scope': config.SCOPES,
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    try:
        logger.info(f"Requesting token refresh from {token_url}...")
        response = requests.post(token_url, data=payload, headers=headers, timeout=30)

        if not response.ok:
            try:
                error_data = response.json()
                error = error_data.get('error')
                error_description = error_data.get('error_description', '')
                if error == 'invalid_grant':
                    logger.warning(f"Refresh token is invalid or revoked: {error_description}")
                    _global_token_storage.clear_tokens()
                    logger.info("Cleared stored tokens due to invalid refresh token.")
                    return None
                else:
                    logger.error(f"OAuth error during token refresh: {error} - {error_description}")
            except json.JSONDecodeError:
                logger.error(f"Non-JSON error response during token refresh. Status: {response.status_code}, Body: {response.text[:200]}...")
            response.raise_for_status()

        new_tokens = response.json()
        logger.info("Successfully refreshed tokens.")

        # Save the new tokens using the global storage
        _global_token_storage.save_tokens(new_tokens)

        return new_tokens

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during token refresh: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            except Exception:
                logger.error("Could not parse error response body.")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON response from token endpoint during refresh: {e}")
        logger.error(f"Raw response text: {response.text if 'response' in locals() else 'N/A'}")
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred during token refresh: {e}")
        return None

def initiate_authorization() -> Optional[Dict[str, Any]]:
    """Initiates the PKCE OAuth flow, opens browser, waits for callback via queue."""
    if _global_token_storage is None:
        logger.error("Global token storage not set before calling initiate_authorization")
        return None
    if _auth_code_queue_ref is None:
        logger.error("Auth code queue reference not set before initiating authorization.")
        return None

    logger.info("Initiating OAuth 2.1 PKCE flow...")
    verifier = oauth_utils.generate_pkce_verifier()
    challenge = oauth_utils.calculate_pkce_challenge(verifier)
    logger.info("Generated PKCE verifier and challenge.")

    auth_url_base = f"{config.AUTH_WORKER_URL}/authorize"
    params = {
        'response_type': 'code',
        'client_id': config.CLIENT_ID,
        'redirect_uri': config.REDIRECT_URI, # This MUST match the port Flask is running on
        'scope': config.SCOPES,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    auth_url = f"{auth_url_base}?{urlencode(params)}"
    logger.debug(f"Constructed authorization URL: {auth_url}")

    # No need to start a separate server here, Flask server is already running

    logger.info(f"Opening browser to: {auth_url_base}...")
    opened = webbrowser.open(auth_url)
    if not opened:
        logger.warning("Could not automatically open browser. Please open the URL manually.")
        print("-" * 40)
        print("Please open the following URL in your browser to authorize:")
        print(auth_url)
        print("-" * 40)

    # Wait for the code from the queue populated by the Flask callback route
    code: Optional[str] = None
    try:
        logger.info("Waiting for authorization code from callback queue...")
        code = _auth_code_queue_ref.get(timeout=300) # 5 minutes timeout
        if code:
            logger.info("Authorization code received from queue.")
        else:
            logger.error("Received error signal (None) from callback queue.")
            return None # Callback indicated an error
    except Empty:
        logger.error("Timeout waiting for authorization code from queue.")
        return None
    except Exception as e:
        logger.exception(f"An error occurred while waiting for the code queue: {e}")
        return None
    # No finally block needed to shut down server here

    if code:
        logger.info("Exchanging authorization code for tokens...")
        tokens = exchange_code_for_token(code, verifier)
        if tokens:
            logger.info("Successfully exchanged code for tokens.")
            return tokens
        else:
            logger.error("Failed to exchange code for tokens.")
            return None
    else:
        # This case should technically be handled by the error signal check above
        logger.warning("Proceeding without authorization code (should not happen).")
        return None

def get_valid_token() -> Optional[str]:
    """Orchestrates loading, refreshing, or initiating auth to get a valid access token.

    Attempts to load existing tokens. If present and valid, returns the access token.
    If expired but a refresh token exists, attempts to refresh.
    If no tokens exist, they are expired and cannot be refreshed, or refresh fails,
    initiates the full PKCE authorization flow.

    Returns:
        A valid access token string, or None if unable to obtain one.
    """
    global _auth_code_queue_ref # Ensure we can modify the global queue reference if needed
    if _global_token_storage is None:
        logger.error("Global token storage not set before calling get_valid_token")
        return None

    logger.info("Attempting to get a valid access token...")
    tokens = _global_token_storage.load_tokens()

    if tokens:
        logger.info("Found existing tokens.")
        if not _global_token_storage.is_token_expired(tokens):
            logger.info("Existing access token is still valid.")
            return tokens.get('access_token')
        else:
            logger.info("Existing access token has expired.")
            refresh_token = tokens.get('refresh_token')
            if refresh_token:
                logger.info("Attempting to refresh token...")
                refreshed_tokens = refresh_access_token(refresh_token)
                if refreshed_tokens:
                    logger.info("Token refresh successful.")
                    return refreshed_tokens.get('access_token')
                else:
                    logger.warning("Token refresh failed. Need to re-authenticate.")
            else:
                logger.warning("Token expired and no refresh token found. Need to re-authenticate.")
                _global_token_storage.clear_tokens()
    else:
        logger.info("No existing tokens found.")

    # ---- Initiate Full Auth Flow ----
    logger.info("Initiating full OAuth authorization flow...")
    # If the queue reference wasn't passed (e.g. from main server), it won't work
    if _auth_code_queue_ref is None:
        # This should ideally not happen if called from the server context
        # where the queue is passed via set_auth_code_queue
        logger.error("Auth code queue was not set before needing full auth flow. Cannot proceed automatically.")
        # If we absolutely must proceed, we might create one here, but it's disconnected
        # from the server's callback route. Let's error out instead.
        # _auth_code_queue_ref = Queue() # Temporary queue, but won't get populated
        # set_auth_code_queue(_auth_code_queue_ref) # Set it just for initiate_authorization call
        return None # Fail if queue wasn't setup correctly by the calling context

    new_tokens = initiate_authorization() # initiate_authorization now uses the existing _auth_code_queue_ref
    if new_tokens:
        logger.info("Full authorization flow successful.")
        return new_tokens.get('access_token')
    else:
        logger.error("Failed to obtain tokens via authorization flow.")
        return None

# Example usage or testing block (can be removed or kept)
# if __name__ == '__main__':
#     print("Testing OAuth Flow...")
#     # Need to initialize storage and queue for testing
#     test_storage = TokenStorage()
#     set_global_token_storage(test_storage)
#     test_queue = Queue()
#     set_auth_code_queue(test_queue)
#
#     # Example: Force re-authentication
#     test_storage.clear_tokens()
#     token = get_valid_token()
#     if token:
#         print(f"Successfully obtained token: {token[:10]}...")
#     else:
#         print("Failed to obtain token.") 