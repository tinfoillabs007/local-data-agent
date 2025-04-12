import logging
import asyncio
from typing import Dict, Any, Optional
import os
import sys
# No need for re or json here anymore for extraction
# import re
import json # Keep json for parsing final_result if it's a string
from datetime import datetime

from dotenv import load_dotenv # Keep load_dotenv if testing standalone
from langchain_openai import ChatOpenAI
from browser_use import Agent, AgentHistoryList
# No longer need ActionResult or extract_json_from_model_output here
# from browser_use.agent.views import ActionResult
# from browser_use.browser import Browser
# from browser_use.agent.message_manager.utils import extract_json_from_model_output

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Now we can use absolute imports
import config

logger = logging.getLogger(__name__)

async def run_agent_task(task: str, sensitive_data: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """Sets up and runs the browser-use agent for a given task description.

    Args:
        task: The natural language description of the task for the agent.
        sensitive_data: Optional dictionary containing sensitive data keys and values.

    Returns:
        The final result content string from the agent's execution,
        or an error dictionary if something went wrong.
    """
    logger.info(f"Preparing agent for task: {task[:100]}...")

    if not config.OPENAI_API_KEY:
        logger.error("OpenAI API key not configured. Cannot run agent.")
        return {"error": "OpenAI API key not configured."} # Return error dict

    try:
        # 1. Configure the LLM
        llm = ChatOpenAI(
            model=config.LLM_MODEL,
            openai_api_key=config.OPENAI_API_KEY,
            temperature=0.0,
        )
        logger.info(f"LLM configured with model: {config.LLM_MODEL}")

        # 2. Configure and initialize the browser
        # Allow overriding headless mode via config or keep it True as per example?
        # Let's make it configurable, defaulting to True.
        # headless_mode = os.getenv("AGENT_HEADLESS", "True").lower() == "true"
        # logger.info(f"Browser headless mode: {headless_mode}")

        # browser_config_args = {"headless": headless_mode}
        # if config.CHROME_PATH:
        #     browser_config_args['executable_path'] = config.CHROME_PATH
        #     logger.info(f"Using custom browser path: {config.CHROME_PATH}")
        # if config.CHROME_USER_DATA:
        #     browser_config_args['user_data_dir'] = config.CHROME_USER_DATA
        #     logger.info(f"Using custom user data dir: {config.CHROME_USER_DATA}")

        # browser_config = BrowserConfig(**browser_config_args)
        # browser = Browser(config=browser_config)
        # logger.info("Browser object initialized.")

        # 3. Initialize the agent
        agent = Agent(
            task=task,
            llm=llm,
            sensitive_data=sensitive_data or {},
            # browser=browser # Pass browser if initialized
        )
        logger.info("Browser-use agent initialized.")

        # 4. Run the agent
        logger.info("Starting agent execution...")
        history: AgentHistoryList = await agent.run()
        logger.info("Agent execution completed.")

        # --- Use history.final_result() directly ---
        save_content = None
        if history:
            final_summary = history.final_result() # Get the content logged as "📄 Result:"
            is_done = history.is_done()
            is_successful = history.is_successful() # Returns None if not done

            if is_done:
                if is_successful:
                    logger.info("Agent task completed successfully.")
                    # Use the final summary string directly
                    save_content = final_summary if final_summary else "Task successful but no final summary content."
                else:
                    logger.warning("Agent task done but unsuccessful.")
                    # Return the summary string if available, otherwise an error message
                    save_content = final_summary if final_summary else "Task unsuccessful and no final summary content."
                    # Optionally wrap in error dict if main.py needs differentiation
                    # save_content = {"error": "Task finished unsuccessfully", "summary": save_content}
            else: # Not done
                 logger.warning("Agent task did not complete (not marked as done).")
                 # Return the final summary if it exists (might be from last step before stop)
                 save_content = final_summary if final_summary else "Task did not complete."
                 # Optionally wrap in error dict
                 # save_content = {"error": "Task did not complete", "summary": save_content}

        else: # Agent run failed entirely or returned None
            logger.error("Agent run returned None or an unexpected result.")
            save_content = {"error": "Agent run failed entirely."}

        logger.info(f"Agent task completed with result: {history}")

        return save_content

    except ImportError as e:
        logger.error(f"Import error: {e}")
        return {"error": f"Import error: {e}"}
    except Exception as e:
        logger.exception(f"An unexpected error occurred during agent execution: {e}")
        # Ensure browser is closed even if an error occurs mid-run
        if 'browser' in locals() and browser and not browser.is_closed():
             try:
                #  await browser.close()
                 logger.info("Browser closed after exception.")
             except Exception as close_err:
                 logger.error(f"Error closing browser after exception: {close_err}")
        return {"error": f"Agent execution failed: {e}"}

# Keep the example usage commented out for when running the module directly
# import os
# async def test_agent():
#     # Load .env directly if running standalone for testing
#     load_dotenv()
#     # Example task and sensitive data
#     test_task = "go to example.com and find the main heading"
#     # test_sensitive = {'login_user': 'test@example.com', 'login_pass': 'password123'}
#     result = await run_agent_task(test_task)
#     if result:
#         print(f"Agent Result:\n{result}")
#     else:
#         print("Agent task failed.")
#
# if __name__ == '__main__':
#     # Ensure config module can be found if run directly
#     import sys
#     sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
#     from local_agent_helper import config # Now this should work
#     asyncio.run(test_agent()) 