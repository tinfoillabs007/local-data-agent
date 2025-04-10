import os
import json
import time
import logging
from typing import Optional, Dict, Any
import sys

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Now we can use absolute imports
import config

logger = logging.getLogger(__name__)

# Define the path for the token file within the user's home directory
TOKEN_DIR = os.path.expanduser("~/.mcp-helper")
TOKEN_FILE_PATH = os.path.join(TOKEN_DIR, "tokens.json")

class TokenStorage:
    """Handles secure storage and retrieval of OAuth tokens."""

    def __init__(self, token_file: str = TOKEN_FILE_PATH):
        self.token_file = token_file
        self._ensure_dir_exists()

    def _ensure_dir_exists(self):
        """Ensures the directory for storing the token file exists."""
        try:
            os.makedirs(TOKEN_DIR, exist_ok=True)
            # Set directory permissions to be readable/writable only by the user
            # os.chmod(TOKEN_DIR, 0o700)
        except OSError as e:
            logger.error(f"Error creating token directory {TOKEN_DIR}: {e}")
            # Depending on the error, might want to raise it or handle differently

    def save_tokens(self, tokens: Dict[str, Any]):
        """Saves the tokens securely to a file."""
        try:
            # Add 'expires_at' timestamp based on 'expires_in'
            if 'expires_in' in tokens and isinstance(tokens['expires_in'], (int, float)):
                tokens['expires_at'] = time.time() + tokens['expires_in']
            else:
                # Set a default expiry if not provided, e.g., 1 hour
                logger.warning("Token response missing or has invalid 'expires_in', setting default expiry.")
                tokens['expires_at'] = time.time() + 3600

            with open(self.token_file, 'w') as f:
                json.dump(tokens, f, indent=4)
            # Set file permissions to be readable/writable only by the user
            # os.chmod(self.token_file, 0o600)
            logger.info(f"Tokens saved successfully to {self.token_file}")
        except IOError as e:
            logger.error(f"Error saving tokens to {self.token_file}: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred while saving tokens: {e}")

    def load_tokens(self) -> Optional[Dict[str, Any]]:
        """Loads the tokens from the file."""
        if not os.path.exists(self.token_file):
            logger.info("Token file does not exist.")
            return None

        try:
            with open(self.token_file, 'r') as f:
                tokens = json.load(f)
            logger.info("Tokens loaded successfully.")
            return tokens
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading or parsing tokens from {self.token_file}: {e}")
            # Optionally: Corrupted file handling - rename/delete?
            return None
        except Exception as e:
            logger.exception(f"An unexpected error occurred while loading tokens: {e}")
            return None

    def clear_tokens(self):
        """Deletes the token file."""
        try:
            if os.path.exists(self.token_file):
                os.remove(self.token_file)
                logger.info("Tokens cleared successfully.")
        except OSError as e:
            logger.error(f"Error deleting token file {self.token_file}: {e}")

    def is_token_expired(self, tokens: Optional[Dict[str, Any]] = None, buffer_seconds: int = 60) -> bool:
        """Checks if the access token is expired or close to expiring.

        Args:
            tokens: The token dictionary. If None, tries to load from storage.
            buffer_seconds: A buffer time in seconds before actual expiry to consider it expired.

        Returns:
            True if the token is considered expired, False otherwise.
        """
        if tokens is None:
            tokens = self.load_tokens()

        if not tokens or 'expires_at' not in tokens:
            logger.info("No tokens or expiry information found, considering expired.")
            return True # No token or expiry info means we need a new one

        expires_at = tokens['expires_at']
        if not isinstance(expires_at, (int, float)):
            logger.warning("Invalid 'expires_at' value found in stored tokens, considering expired.")
            return True

        # Check if the token is expired or within the buffer period
        is_expired = time.time() >= (expires_at - buffer_seconds)
        if is_expired:
            logger.info(f"Token expired or expires within {buffer_seconds} seconds.")
        else:
            logger.debug("Token is still valid.")
        return is_expired 