# Local Agent Helper

This Python application acts as a local helper to:
1.  Authenticate with an OAuth 2.0 provider (like `auth-worker`) using the secure PKCE flow for native applications.
2.  Interact with a backend API (like `mcp-worker`) to fetch and store data (e.g., in a vault).
3.  Run automated browser tasks using the `browser-use` library and an LLM (like OpenAI).
4.  Combine the results of the agent task with the fetched data and save it back.

## Setup

1.  **Clone/Download:** Get the code for this application.
2.  **Python Environment:** Create and activate a virtual environment (recommended):
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```
3.  **Install Dependencies:** Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    # Or using uv:
    # uv pip install -r requirements.txt
    ```
4.  **Install Playwright Browsers:** The `browser-use` library relies on Playwright. Install the necessary browser binaries (e.g., Chromium):
    ```bash
    playwright install --with-deps chromium
    ```
    *(See Playwright documentation for installing other browsers or troubleshooting.)*

## Configuration

1.  **Copy Example Env File:**
    ```bash
    cp .env.example .env
    ```
2.  **Edit `.env` File:** Open the `.env` file and fill in the required values:
    *   `HELPER_APP_CLIENT_ID`: The unique Client ID registered for *this* native application in your OAuth provider (`auth-worker`).
    *   `AUTH_WORKER_URL`: The base URL of your running `auth-worker` instance (e.g., `http://localhost:8080`).
    *   `MCP_WORKER_API_URL`: The base URL of your running `mcp-worker` instance (e.g., `http://localhost:8081`).
    *   `OPENAI_API_KEY`: Your API key from OpenAI for the agent's LLM.
    *   *(Optional)* `LLM_MODEL`: Override the default OpenAI model (e.g., `gpt-4o`).
    *   *(Optional)* `CHROME_PATH`: Specify the exact path to your Chrome/Chromium executable if Playwright can't find it.
    *   *(Optional)* `CHROME_USER_DATA`: Specify a Chrome user data directory for Playwright to use (e.g., for persistent logins within the agent session).
    *   *(Optional)* `CALLBACK_PORT`: The local port the helper will listen on for the OAuth redirect. Defaults to `8990`. **Ensure this matches the redirect URI registered in `auth-worker`**. The full redirect URI will be `http://localhost:PORT/callback`.

3.  **Register Native Client in Auth Worker:**
    *   You **must** manually register this helper application as a native client within your `auth-worker` configuration.
    *   Typically, this involves editing the `oauth-config.ts` (or similar) file in your `auth-worker` project.
    *   Add a new client configuration entry with:
        *   `client_id`: The **exact** value you put in `HELPER_APP_CLIENT_ID` in the `.env` file.
        *   `client_name`: A descriptive name (e.g., "Local Agent Helper").
        *   `redirect_uris`: An array containing the specific redirect URI: `["http://localhost:8990/callback"]` (adjust port if changed).
        *   `grant_types`: Must include `authorization_code` and `refresh_token`.
        *   `response_types`: Must include `code`.
        *   `token_endpoint_auth_method`: `none` (PKCE uses no client secret).
        *   `scopes`: Ensure the allowed scopes include those requested by the helper (default: `openid profile email offline_access vault_api`). Adjust `SCOPES` in `local_agent_helper/config.py` if needed.
        *   Application Type: `native`.
    *   **Restart** your `auth-worker` after updating its configuration.

## Running the Application

Ensure your `auth-worker` and `mcp-worker` services are running and accessible at the configured URLs.

Execute the main script from the `local_agent_helper` directory, providing the task description as a command-line argument:

```bash
python main.py "Your detailed task description for the agent goes here. For example, find the price of AAPL stock and add it to my notes."
```

The first time you run it (or after tokens expire/are cleared), it will:
1.  Open your web browser to the `auth-worker`'s authorization page.
2.  Ask you to log in and grant permission.
3.  Redirect back to `http://localhost:PORT/callback`.
4.  Capture the authorization code.
5.  Exchange the code for tokens and store them securely using `keyring`.

Subsequent runs (while tokens are valid) will use the stored tokens.

The application will then proceed to run the agent task, fetch vault data, merge results, and save the updated data back to the vault via the `mcp-worker` API.

## Token Storage

*   OAuth tokens (including sensitive refresh tokens) are stored securely using the `keyring` library, which interfaces with your operating system's native credential store (e.g., macOS Keychain, Windows Credential Manager, Freedesktop Secret Service).
*   You may need to grant permission the first time `keyring` accesses the store.
*   If you encounter issues saving or loading tokens, ensure `keyring` is installed correctly and its backend is functional (`pip install keyring`, potentially `pip install dbus-python` on Linux).

## Packaging (Optional)

For easier distribution, you could consider packaging the application into a standalone executable using tools like:
*   **PyInstaller:** Creates executables for Windows, macOS, and Linux.
*   **py2app:** macOS specific.
*   **Briefcase:** Part of the BeeWare suite, aims for cross-platform native packaging.

Consult the documentation for these tools for specific usage instructions. 