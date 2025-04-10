import logging
import asyncio
from typing import Dict, Any, Optional
import os
import sys
import re
import json
from datetime import datetime

from dotenv import load_dotenv # Keep load_dotenv if testing standalone
from langchain_openai import ChatOpenAI
from browser_use import Agent, Browser, BrowserConfig

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Now we can use absolute imports
import config

logger = logging.getLogger(__name__)

async def run_agent_task(task: str, sensitive_data: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """Sets up and runs the browser-use agent for a given task description,
       following the specific initialization pattern provided.

    Args:
        task: The natural language description of the task for the agent.
        sensitive_data: Optional dictionary containing sensitive data keys and values
                        to be masked and used by the agent.

    Returns:
        The result from the agent's execution, or None if an error occurs.
    """
    logger.info(f"Preparing agent for task: {task[:100]}...")

    if not config.OPENAI_API_KEY:
        logger.error("OpenAI API key not configured. Cannot run agent.")
        return None

    try:
        # 1. Configure the LLM (using settings from config.py)
        llm = ChatOpenAI(
            model=config.LLM_MODEL,
            openai_api_key=config.OPENAI_API_KEY,
            temperature=0.0, # Set temperature as desired
            # max_tokens=2048 # Set max tokens if needed
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

        # 3. Initialize the agent with LLM, browser, task, and sensitive data
        agent = Agent(
            task=task,
            llm=llm,
            sensitive_data=sensitive_data or {}, # Pass sensitive data if provided
            # browser=browser
        )
        logger.info("Browser-use agent initialized.")

        # 4. Run the agent
        logger.info("Starting agent execution...")
        # Assuming agent.run() is the correct async method
        result = await agent.run()
        logger.info("Agent execution completed.")
        logger.debug(f"Agent result: {result}")

        # Ensure browser is closed after execution if needed.
        # agent.run() or browser might handle this, check browser-use docs.
        # Explicitly closing might be safer:
        # await browser.close()
        # logger.info("Browser closed.")

        logger.info(f"Agent task completed with result: {result}")

        # --- Extract Final Result (Attempting Structured Data First) ---
        save_content = None
        task_successful = False
        is_done = False

        # Check basic structure and done status
        if result and hasattr(result, 'is_done') and callable(result.is_done):
            is_done = result.is_done()
            if is_done:
                 task_successful = hasattr(result, 'is_successful') and callable(result.is_successful) and result.is_successful()

        if is_done and task_successful:
            logger.info("Agent task marked as done and successful. Attempting to find structured data...")
            found_json_content = None # Store the last valid JSON found
            if hasattr(result, 'history') and result.history: # Assuming 'history' holds AgentHistory items
                 # Iterate backwards from the second-to-last history item
                 for history_item in reversed(result.history[:-1]): # Skip the last 'done' item
                     if hasattr(history_item, 'result') and history_item.result:
                         for action_result in reversed(history_item.result): # Check results within the step
                             if hasattr(action_result, 'extracted_content') and action_result.extracted_content:
                                 content_str = action_result.extracted_content
                                 potential_json = None
                                 # Try extracting from ```json ... ``` block
                                 match_block = re.search(r'```json\n(\{.*?\})\n```', content_str, re.DOTALL)
                                 if match_block:
                                     try:
                                         json_str = match_block.group(1)
                                         potential_json = json.loads(json_str)
                                         logger.debug(f"Found potential JSON in block: {json.dumps(potential_json)}")
                                     except json.JSONDecodeError as json_err:
                                         logger.warning(f"Found JSON block but failed to parse: {json_err}.")
                                 # Try extracting direct JSON object
                                 elif content_str.strip().startswith('{') and content_str.strip().endswith('}'):
                                      try:
                                          potential_json = json.loads(content_str)
                                          logger.debug(f"Found potential direct JSON: {json.dumps(potential_json)}")
                                      except json.JSONDecodeError as json_err:
                                          logger.warning(f"Found direct JSON but failed to parse: {json_err}.")

                                 # If we found valid JSON, store it and continue searching backwards
                                 # This prioritizes results from later steps if multiple JSON results exist
                                 if potential_json is not None:
                                     # Optional: Add a check to ensure it's not trivially empty if desired
                                     # if isinstance(potential_json, dict) and potential_json: # Or more specific checks
                                     found_json_content = potential_json
                                     # Don't break here, keep searching backwards for potentially better/later JSON

            # After checking all history, use the last valid JSON found
            if found_json_content is not None:
                save_content = found_json_content
                logger.info(f"Using last found structured JSON data from previous steps: {json.dumps(save_content)}")
            else:
                 logger.warning("Structured JSON data not found in previous steps.")

            # Fallback to the final result string if no structured data found
            if save_content is None:
                logger.info("Falling back to final_result() content from the 'done' action.")
                if hasattr(result, 'final_result') and callable(result.final_result):
                    save_content = result.final_result()
                    if not save_content:
                        save_content = "Task completed successfully (no specific content)."
                else:
                     save_content = "Task completed successfully (result retrieval method missing)."

        elif is_done and not task_successful:
            # Task finished but was not successful
            logger.warning("Agent task marked as done but not successful.")
            if hasattr(result, 'final_result') and callable(result.final_result):
                save_content = result.final_result() # Still try to get content from 'done' action
            if not save_content:
                save_content = "Task finished unsuccessfully (no specific content)."
        else:
             # Task not marked as done, potentially stopped early or error
             logger.warning("Agent task not marked as done or agent_result structure unexpected.")
             # Fallback: Try to get content from the last action's result if available
             if hasattr(result, 'history') and result.history:
                 last_history_item = result.history[-1]
                 if hasattr(last_history_item, 'result') and last_history_item.result:
                     last_action_result = last_history_item.result[-1]
                     if hasattr(last_action_result, 'extracted_content') and last_action_result.extracted_content:
                         save_content = last_action_result.extracted_content
                         logger.warning("Using extracted content from the last action as fallback.")
                     elif hasattr(last_action_result, 'error') and last_action_result.error:
                         save_content = f"Agent stopped with error: {last_action_result.error}"
                         logger.error(f"Agent task stopped with error: {last_action_result.error}")

        if save_content is None:
            logger.warning("Could not extract relevant final content from agent result. Saving raw string representation instead.")
            save_content = f"Agent task did not complete or provide a final result. Raw: {str(result)[:500]}..." # Limit length

        # Return the extracted content instead of the raw agent result object
        return save_content
 
    except ImportError as e:
        logger.error(f"Import error, likely missing dependencies (langchain-openai or browser-use): {e}")
        logger.error("Please ensure all dependencies in requirements.txt are installed.")
        return None
    except Exception as e:
        # Log the exception traceback for detailed debugging
        logger.exception(f"An unexpected error occurred during agent execution: {e}")
        # Ensure browser is closed even if an error occurs mid-run
        if 'browser' in locals() and browser and not browser.is_closed():
             try:
                #  await browser.close()
                 logger.info("Browser closed after exception.")
             except Exception as close_err:
                 logger.error(f"Error closing browser after exception: {close_err}")
        return None

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