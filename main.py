#!/usr/bin/env python3
"""
Local Agent Helper: Runs as a local HTTP server to handle tasks from the frontend.
"""

import logging
import sys
import os
from urllib.parse import urlencode
import webbrowser
from queue import Queue, Empty
from threading import Thread
from typing import Optional
import asyncio
from datetime import datetime
from flask_cors import CORS # Import CORS
import json
import re

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Use absolute imports
import config
import oauth_utils
# No longer need separate callback_server module
# from callback_server import CallbackServer, set_code_queue
from api_client import McpApiClient, introspect_token # Import introspect if needed elsewhere
from token_storage import TokenStorage
# Import necessary functions from oauth_flow, renaming to avoid conflicts if necessary
from oauth_flow import (
    set_global_token_storage,
    get_valid_token as get_valid_oauth_token, # Rename to be specific
    exchange_code_for_token,
    initiate_authorization as initiate_oauth_authorization, # Rename to be specific
    set_auth_code_queue
)
from agent_runner import run_agent_task

from flask import Flask, request, jsonify, redirect

# --- Global Variables ---
_auth_code_queue: Queue[Optional[str]] = Queue()

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}}) # Apply CORS globally for origin 3000

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('mcp_helper_server')

# Suppress overly verbose Flask/Werkzeug logs if desired
# logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Pass the queue reference to the oauth_flow module *once* at startup
set_auth_code_queue(_auth_code_queue)

# --- OAuth Callback Route ---
@app.route('/callback')
def oauth_callback():
    """Handles the redirect from the OAuth authorization server."""
    global _auth_code_queue
    auth_code = request.args.get('code')
    error = request.args.get('error')
    error_description = request.args.get('error_description', 'No description provided.')

    if auth_code:
        logger.info("OAuth callback received authorization code.")
        _auth_code_queue.put(auth_code)
        # Simple success page for the browser tab
        return "<h1>Authorization Successful</h1><p>You can close this window.</p>", 200
    elif error:
        logger.error(f"OAuth callback received error: {error} - {error_description}")
        _auth_code_queue.put(None) # Signal error
        return f"<h1>Authorization Failed</h1><p>Error: {error}</p><p>{error_description}</p>", 400
    else:
        logger.warning("OAuth callback received without code or error parameters.")
        _auth_code_queue.put(None) # Signal unexpected state
        return "<h1>Invalid Request</h1><p>Callback received without expected parameters.</p>", 400

# --- Task Execution Route ---
@app.route('/run-task')
def run_task():
    """Handles requests from the frontend to perform tasks."""
    task = request.args.get('task')
    if not task:
        logger.error("'/run-task' endpoint called without 'task' parameter.")
        return jsonify({"success": False, "error": "Missing 'task' parameter"}), 400

    logger.info(f"Received task request: '{task}'")

    try:
        # --- Authentication ---
        token_storage = TokenStorage()
        set_global_token_storage(token_storage) # Set global storage
        api_client = McpApiClient(token_storage)

        # NOTE: Queue is already set globally, no need to pass it here again
        logger.info("Attempting to get valid OAuth token...")
        access_token = get_valid_oauth_token()

        if not access_token:
            logger.error("Failed to obtain valid access token.")
            return jsonify({"success": False, "error": "Authentication failed or user cancelled."}), 401

        logger.info("Successfully obtained access token.")

        # --- Task Dispatch ---
        if task == "Update vault data":
            logger.info("Executing 'Update vault data' task...")
            vault_data = api_client.get_vault_data()
            if vault_data is not None:
                logger.info(f"Current vault data fetched successfully.")

                sensitive_data = {
                    "x_name": "tinfoillabs@gmail.com",
                    "x_password": "gupta@0365",
                    
                }
                # --- Run Agent ---
                # run_agent_task now returns the extracted content directly
                save_content = asyncio.run(run_agent_task(
                    task="Open gmail.com and login with x_name and x_password then get the 2 latest emails in the inbox",
                    sensitive_data=sensitive_data
                ))

                # Check if agent task failed
                agent_failed = False
                error_message = "Agent task failed or returned no content."
                if save_content is None:
                    agent_failed = True
                elif isinstance(save_content, dict) and 'error' in save_content:
                    agent_failed = True
                    error_message = save_content['error']

                if agent_failed:
                    logger.error(error_message)
                    return jsonify({"success": False, "error": error_message}), 500

                logger.info(f"Agent task completed and returned content.")

                # --- Merge and Save ---
                merged_data = vault_data.copy()
                merged_data['last_agent_update'] = {
                    'timestamp': datetime.now().isoformat(),
                    'task_trigger': task,
                    'result': save_content
                }

                logger.info(f"Attempting to save merged vault data...")
                # Call API client to save the *merged* data back to the backend
                save_success = api_client.save_vault_data(merged_data)

                if save_success:
                    logger.info("Vault data updated successfully.")
                    return jsonify({"success": True, "message": "Vault data updated by agent.", "updatedVaultData": merged_data}), 200
                else:
                    logger.error("Failed to save updated vault data.")
                    return jsonify({"success": False, "error": "Failed to save updated vault data"}), 500
            else:
                logger.error("Failed to fetch vault data before update.")
                return jsonify({"success": False, "error": "Failed to fetch vault data"}), 500
        else:
            logger.warning(f"Received unknown task: '{task}'")
            return jsonify({"success": False, "error": f"Unknown task: {task}"}), 400

    except Exception as e:
        logger.exception(f"An unexpected error occurred while processing task '{task}': {e}")
        return jsonify({"success": False, "error": "An internal server error occurred."}), 500

# --- Get Vault Route ---
@app.route('/get-vault') # GET is default, but explicit is fine
def get_vault():
    """Handles requests to fetch the current vault data."""
    logger.info("Received request to get vault data.")

    try:
        # --- Authentication (same as run_task) ---
        token_storage = TokenStorage()
        set_global_token_storage(token_storage)
        api_client = McpApiClient(token_storage)

        logger.info("Attempting to get valid OAuth token for getting vault...")
        access_token = get_valid_oauth_token()

        if not access_token:
            logger.error("Failed to obtain valid access token for getting vault.")
            return jsonify({"success": False, "error": "Authentication failed or user cancelled."}), 401

        logger.info("Successfully obtained access token for getting vault.")

        # --- Fetch Data ---
        logger.info("Attempting to fetch vault data via API client...")
        vault_data_response = api_client.get_vault_data() # This should return the full API response structure

        if vault_data_response is not None and vault_data_response.get('success'):
            logger.info("Vault data fetched successfully via API.")
            # Return the actual vault data nested within the response
            return jsonify({"success": True, "vaultData": vault_data_response.get('vaultData', {})}), 200
        else:
            logger.error("Failed to fetch vault data via API.")
            error_message = "Failed to fetch vault data"
            if vault_data_response and 'error' in vault_data_response:
                 error_message = vault_data_response['error'] # Pass along error from worker if available
            return jsonify({"success": False, "error": error_message}), 500

    except Exception as e:
        logger.exception(f"An unexpected error occurred while getting vault data: {e}")
        return jsonify({"success": False, "error": "An internal server error occurred."}), 500

# --- Clear Vault Route ---
@app.route('/clear-vault', methods=['POST']) # Use POST for actions that modify data
def clear_vault():
    """Handles requests to clear the vault data."""
    logger.info("Received request to clear vault data.")

    try:
        # --- Authentication (same as run_task) ---
        token_storage = TokenStorage()
        set_global_token_storage(token_storage)
        api_client = McpApiClient(token_storage)

        logger.info("Attempting to get valid OAuth token for clearing vault...")
        access_token = get_valid_oauth_token() # Reuse the existing auth logic

        if not access_token:
            logger.error("Failed to obtain valid access token for clearing vault.")
            return jsonify({"success": False, "error": "Authentication failed or user cancelled."}), 401

        logger.info("Successfully obtained access token for clearing vault.")

        # --- Clear Data ---
        logger.info("Attempting to clear vault data via API client...")
        # Use the new dedicated clear method
        clear_success = api_client.clear_vault_data() 

        if clear_success:
            logger.info("Vault data cleared successfully via API.")
            return jsonify({"success": True, "message": "Vault data cleared."}), 200
        else:
            logger.error("Failed to clear vault data via API.")
            return jsonify({"success": False, "error": "Failed to clear vault data"}), 500

    except Exception as e:
        logger.exception(f"An unexpected error occurred while clearing vault data: {e}")
        return jsonify({"success": False, "error": "An internal server error occurred."}), 500

# --- Server Startup ---
if __name__ == "__main__":
    logger.info("Starting MCP Helper local server...")
    # Use a different port than the callback port if they were separate
    server_port = config.CALLBACK_PORT # Or choose a dedicated port like 8991
    logger.info(f"Server will listen on http://localhost:{server_port}")
    # Set debug=False for production/stable use
    # Use threaded=True if initiate_authorization needs to run in parallel
    app.run(host='localhost', port=server_port, debug=False, threaded=True) 