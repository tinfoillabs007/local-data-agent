import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- OAuth Configuration ---
CLIENT_ID = os.getenv("HELPER_APP_CLIENT_ID")
if not CLIENT_ID:
    logger.warning("HELPER_APP_CLIENT_ID not set in environment variables.")

# Scopes required by the application
# Adjust these scopes based on the actual requirements of the auth server and APIs
SCOPES = "openid profile email offline_access vault_api"

# --- Service URLs ---
AUTH_WORKER_URL = os.getenv("AUTH_WORKER_URL")
if not AUTH_WORKER_URL:
    logger.warning("AUTH_WORKER_URL not set in environment variables.")

MCP_WORKER_API_URL = os.getenv("MCP_WORKER_API_URL")
if not MCP_WORKER_API_URL:
    logger.warning("MCP_WORKER_API_URL not set in environment variables.")

# --- Local Callback Server Configuration ---
# Ensure this matches the Redirect URI registered for the native client
CALLBACK_PORT = int(os.getenv("CALLBACK_PORT", "8990"))
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"

# --- Token Storage ---
# Simple file-based storage for demo purposes. Use keyring for production.
TOKEN_FILE = os.getenv("TOKEN_FILE", "auth_tokens.json")

# --- LLM/Agent Configuration ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY not set. Agent functionality will be limited.")

# Optional LLM model override
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini") # Or whatever default browser-use prefers

# --- Browser Configuration (for browser-use) ---
# Optional paths for Playwright
CHROME_PATH = os.getenv("CHROME_PATH")
CHROME_USER_DATA = os.getenv("CHROME_USER_DATA")


# Helper function to get required config values, raising an error if missing
def get_required_config(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        raise ValueError(f"Missing required environment variable: {var_name}")
    return value

# Example of ensuring critical variables are present before proceeding
try:
    CLIENT_ID = get_required_config("HELPER_APP_CLIENT_ID")
    AUTH_WORKER_URL = get_required_config("AUTH_WORKER_URL")
    MCP_WORKER_API_URL = get_required_config("MCP_WORKER_API_URL")
    OPENAI_API_KEY = get_required_config("OPENAI_API_KEY")
except ValueError as e:
    logger.error(f"Configuration Error: {e}")
    # Depending on the application structure, you might exit here or handle it differently
    # For now, we just log the error, as some parts might function without all keys during development.

logger.info("Configuration loaded.")
logger.info(f"Redirect URI: {REDIRECT_URI}") 