import logging
import os
import sys
import asyncio
import time
import json # For config file
import signal # For graceful shutdown
from datetime import datetime, timezone, timedelta
from functools import partial # For command parsing convenience

# --- Direct Client Import & Error Handling ---
try:
    from whatsapp_bridge import WhatsappClient
    from whatsapp_bridge import (
        PrerequisitesError, SetupError, BridgeError, DbError, ApiError, WhatsappError
    )
except ImportError:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)
    logger.warning("Could not import specific WhatsappError types.")
    class WhatsappError(Exception): pass
    PrerequisitesError = SetupError = BridgeError = DbError = ApiError = WhatsappError
    if 'WhatsappClient' not in locals():
        logger.critical("Could not import WhatsappClient from whatsapp_bridge")
        raise ImportError("Could not import WhatsappClient from whatsapp_bridge")

# --- Configuration ---
CONFIG_FILE = "config.json"
# --- ADDED DEFINITION BACK ---
EXCLUDE_CHATS = [] # Define the hardcoded exclusion list (can be empty)
POLLING_INTERVAL_SECONDS = 1
# Delays/Messages are now loaded from config

# --- Logging Setup ---
if 'logger' not in locals(): # Ensure logger is defined
     log_level = os.getenv("LOG_LEVEL", "INFO").upper()
     logging.basicConfig(
         level=log_level,
         format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
         handlers=[
             logging.StreamHandler(sys.stdout)
         ]
     )
     logger = logging.getLogger(__name__)

# --- Global State ---
config_data = {} # Holds the loaded config
chat_states = {} # Holds runtime state (pending tasks)
client = None # Global client reference for shutdown handler
main_loop = None # Global loop reference for shutdown handler
shutdown_requested = False # Flag for graceful shutdown

# --- Config Loading/Saving ---
def load_config():
    global config_data
    try:
        with open(CONFIG_FILE, 'r') as f:
            config_data = json.load(f)
        logger.info(f"Configuration loaded successfully from {CONFIG_FILE}")
        config_data.setdefault('defaults', {})
        config_data.setdefault('chats', {})
        config_data['defaults'].setdefault('enabled', True)
        config_data['defaults'].setdefault('delay_seconds', 300)
        config_data['defaults'].setdefault('message', "Default auto-reply.")
        config_data['defaults'].setdefault('rate_limit_minutes', 15)
        if not config_data.get('bot_owner_jid'):
             logger.critical(f"CRITICAL: 'bot_owner_jid' not set in {CONFIG_FILE}")
             sys.exit("Bot owner JID missing in config.")
    except FileNotFoundError:
        logger.error(f"Config file {CONFIG_FILE} not found! Please create it.")
        sys.exit("Config file missing.")
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from {CONFIG_FILE}. Check its format.")
        sys.exit("Invalid config file format.")
    except Exception as e:
        logger.error(f"Error loading config: {e}", exc_info=True)
        sys.exit("Failed to load config.")

def save_config():
    global config_data
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=2)
        logger.info(f"Configuration saved successfully to {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"Failed to save config to {CONFIG_FILE}: {e}", exc_info=True)

def get_chat_config(chat_jid):
    defaults = config_data.get('defaults', {})
    chat_specific = config_data.get('chats', {}).get(chat_jid, {})
    return {
        "enabled": chat_specific.get('enabled', defaults.get('enabled', True)),
        "delay_seconds": chat_specific.get('delay_seconds', defaults.get('delay_seconds', 300)),
        "message": chat_specific.get('message', defaults.get('message', "Default auto-reply.")),
        "rate_limit_minutes": chat_specific.get('rate_limit_minutes', defaults.get('rate_limit_minutes', 15)),
        "last_auto_reply_ts": chat_specific.get('last_auto_reply_ts', 0)
    }

# --- Auto-Reply Core Logic ---
async def send_auto_reply(chat_jid, client):
    logger.info(f"send_auto_reply called for chat {chat_jid}.")
    # --- Prevent sending to broadcast/system JIDs ---
    if chat_jid.endswith("@broadcast"):
        logger.warning(f"Skipping auto-reply to broadcast/system chat: {chat_jid}")
        return

    state = chat_states.get(chat_jid)
    chat_config = get_chat_config(chat_jid)
    logger.info(f"State for {chat_jid} in send_auto_reply: {state}")
    logger.info(f"Config for {chat_jid} in send_auto_reply: {chat_config}")

    if not state or state.get('user_replied_since', True) or not chat_config['enabled']:
        logger.info(f"Send condition not met for {chat_jid} (state invalid, user replied, or disabled). Skipping.")
        return

    now_ts = time.time()
    last_sent_ts = chat_config.get('last_auto_reply_ts', 0)
    rate_limit_seconds = chat_config.get('rate_limit_minutes', 15) * 60
    if now_ts - last_sent_ts < rate_limit_seconds:
        logger.info(f"Rate limit active for {chat_jid}. Last reply was {now_ts - last_sent_ts:.0f}s ago (limit {rate_limit_seconds}s). Skipping.")
        return

    logger.info(f"User has not replied in {chat_jid} and rate limit passed. Preparing to send.")
    try:
        message_to_send = chat_config['message']
        logger.info(f"Calling client.send_message for {chat_jid} with message: '{message_to_send[:50]}...'")
        # Assume sync based on previous findings
        success = client.send_message(
            recipient=chat_jid,
            message=message_to_send
        )

        if success:
             logger.info(f"Auto-reply successfully sent to {chat_jid}.")
             config_data['chats'].setdefault(chat_jid, {})['last_auto_reply_ts'] = now_ts
             config_data['chats'][chat_jid]['enabled'] = chat_config['enabled']
             config_data['chats'][chat_jid]['delay_seconds'] = chat_config['delay_seconds']
             config_data['chats'][chat_jid]['message'] = chat_config['message']
             save_config()
             if chat_jid in chat_states:
                 chat_states[chat_jid]['user_replied_since'] = True
        else:
             logger.warning(f"client.send_message call returned False status for {chat_jid}.")

    except Exception as e:
        logger.error(f"Failed to send auto-reply to {chat_jid}: {e}", exc_info=True)
    finally:
         logger.debug(f"send_auto_reply finished for {chat_jid}")

# --- Timer Task ---
async def _run_auto_reply_after_delay(chat_jid, client, trigger_ts):
    try:
        chat_config = get_chat_config(chat_jid)
        delay = chat_config['delay_seconds']
        logger.info(f"Starting {delay}s sleep for {chat_jid} (triggered at {trigger_ts:.0f})")
        await asyncio.sleep(delay)
        logger.info(f"Finished sleep for {chat_jid}. Checking state...")
        current_task_ref = asyncio.current_task()
        state = chat_states.get(chat_jid)
        condition_met = (
            state and
            state.get('scheduled_task') == current_task_ref and
            state.get('trigger_ts') == trigger_ts and
            not state.get('user_replied_since', True)
        )
        logger.info(f"Condition check result for {chat_jid}: {condition_met}")
        if condition_met:
             chat_config_now = get_chat_config(chat_jid)
             if chat_config_now['enabled']:
                 logger.info(f"Condition check passed for {chat_jid}, calling send_auto_reply")
                 await send_auto_reply(chat_jid, client)
             else:
                 logger.info(f"Send aborted for {chat_jid}: Auto-reply was disabled while timer was running.")
        else:
             logger.info(f"Condition check failed, task mismatch, wrong trigger, or user replied for {chat_jid}. Skipping send.")
    except asyncio.CancelledError:
        logger.info(f"Auto-reply task for {chat_jid} was cancelled.")
    except Exception as e:
        logger.error(f"Exception in auto-reply task for {chat_jid}: {e}", exc_info=True)
    finally:
        state = chat_states.get(chat_jid)
        if state and state.get('scheduled_task') == asyncio.current_task():
             state['scheduled_task'] = None
             logger.debug(f"Cleared task reference in state for {chat_jid}")
        logger.debug(f"Auto-reply task for {chat_jid} finished execution.")

# --- Command Handling ---
async def handle_command(message, client):
    sender_jid = message.get("sender")
    chat_jid = message.get("chat_jid")
    owner_jid = config_data.get("bot_owner_jid")
    content = message.get("content", "").strip()

    if not owner_jid or not sender_jid or sender_jid.split(':')[0] != owner_jid.split(':')[0]:
        logger.warning(f"Command '{content}' received from non-owner {sender_jid} in chat {chat_jid}. Ignoring.")
        return

    parts = content.split(maxsplit=2)
    command = parts[0].lower()
    subcommand = parts[1].lower() if len(parts) > 1 else None
    value = parts[2] if len(parts) > 2 else None
    logger.info(f"Owner command received in {chat_jid}: {command} {subcommand} {value}")

    if command != "/autoreply":
        client.send_message(chat_jid, f"Unknown command base: {command}. Use /autoreply.")
        return

    config_data.setdefault('chats', {})
    chat_config = config_data['chats'].setdefault(chat_jid, {})
    reply_msg = ""
    save_needed = False

    if subcommand == "on":
        chat_config['enabled'] = True
        reply_msg = "Auto-reply ENABLED for this chat."
        save_needed = True
    elif subcommand == "off":
        chat_config['enabled'] = False
        reply_msg = "Auto-reply DISABLED for this chat."
        save_needed = True
    elif subcommand == "delay":
        if value and value.isdigit():
            delay_sec = int(value)
            if delay_sec >= 10:
                chat_config['delay_seconds'] = delay_sec
                reply_msg = f"Auto-reply delay set to {delay_sec} seconds for this chat."
                save_needed = True
            else: reply_msg = "Invalid delay. Must be >= 10 seconds."
        else: reply_msg = "Usage: /autoreply delay <seconds>"
    elif subcommand == "message":
        if value:
            chat_config['message'] = value
            reply_msg = f"Auto-reply message set for this chat:\n'{value}'"
            save_needed = True
        else: reply_msg = "Usage: /autoreply message <your message text>"
    elif subcommand == "status":
        current_chat_config = get_chat_config(chat_jid)
        status_enabled = "ENABLED" if current_chat_config['enabled'] else "DISABLED"
        status_delay = current_chat_config['delay_seconds']
        status_msg = current_chat_config['message']
        last_ts = current_chat_config.get('last_auto_reply_ts', 0)
        status_last = "Never sent" if last_ts == 0 else f"{datetime.fromtimestamp(last_ts).strftime('%Y-%m-%d %H:%M:%S')}"
        reply_msg = (f"Auto-reply status for this chat:\n"
                     f"- Status: {status_enabled}\n"
                     f"- Delay: {status_delay} seconds\n"
                     f"- Message: '{status_msg}'\n"
                     f"- Last Sent: {status_last}")
    elif subcommand == "help":
         reply_msg = ("Available commands:\n"
                      "/autoreply on | off\n"
                      "/autoreply delay <seconds>\n"
                      "/autoreply message <text>\n"
                      "/autoreply status")
    else: reply_msg = f"Unknown subcommand '{subcommand}'. Use /autoreply help."

    try:
        if reply_msg: client.send_message(chat_jid, reply_msg) # Assume sync
        if save_needed: save_config()
    except Exception as e: logger.error(f"Error sending command reply/saving config for {chat_jid}: {e}")

# --- Message Processing Logic ---
# --- CORRECTED FUNCTION (Uses EXCLUDE_CHATS) ---
async def handle_message(message, client):
    processed_chat_jid = "unknown"
    try:
        if not message or not message.get("chat_jid"): return
        chat_jid = message.get("chat_jid")
        processed_chat_jid = chat_jid
        is_from_me = message.get("is_from_me", False)
        content = message.get("content", "")
        sender_jid = message.get("sender")
        owner_jid = config_data.get("bot_owner_jid")

        # Check for owner commands first
        # Command should ideally be sent *to* the bot's number directly
        if sender_jid and owner_jid and sender_jid.split(':')[0] == owner_jid.split(':')[0] and content.startswith("/autoreply"):
             logger.info("Processing command...")
             await handle_command(message, client)
             return # Stop processing after command

        # --- Auto-Reply Logic ---
        logger.debug(f"Processing message: ID={message.get('id')}, Chat={chat_jid}, FromMe={is_from_me}, Content='{content[:50]}...'")

        chat_config = get_chat_config(chat_jid) # Get effective config

        # --- Use EXCLUDE_CHATS here ---
        # Ignore if disabled via config OR if in hardcoded EXCLUDE_CHATS (unless it's from me)
        if not chat_config['enabled'] or (chat_jid in EXCLUDE_CHATS and not is_from_me):
             logger.debug(f"Auto-reply disabled or chat excluded: {chat_jid}")
             return

        # Get runtime state
        if chat_jid not in chat_states:
            chat_states[chat_jid] = {"user_replied_since": True, "scheduled_task": None, "trigger_ts": 0}
        state = chat_states[chat_jid]
        existing_task = state.get("scheduled_task")

        if is_from_me:
            logger.debug(f"User message detected in chat {chat_jid}.")
            state['user_replied_since'] = True
            if existing_task:
                logger.info(f"User replied in {chat_jid}. Cancelling scheduled auto-reply task.")
                try: existing_task.cancel()
                except Exception: pass
                state['scheduled_task'] = None
        else:
            # Incoming message
            logger.debug(f"Incoming message detected in chat {chat_jid}.")
            now_ts = time.time()
            state['user_replied_since'] = False

            last_sent_ts = chat_config.get('last_auto_reply_ts', 0)
            rate_limit_seconds = chat_config.get('rate_limit_minutes', 15) * 60
            if now_ts - last_sent_ts < rate_limit_seconds:
                logger.info(f"Rate limit active for {chat_jid}. Not scheduling new auto-reply.")
                if existing_task:
                    try: existing_task.cancel()
                    except Exception: pass
                    state['scheduled_task'] = None
                return

            if existing_task:
                logger.info(f"New incoming message in {chat_jid}. Resetting timer (cancelling old task).")
                try: existing_task.cancel()
                except Exception: pass
                state['scheduled_task'] = None

            delay = chat_config['delay_seconds']
            logger.info(f"Scheduling auto-reply task for {chat_jid} with {delay}s delay.")
            state['trigger_ts'] = now_ts
            try:
                 new_task = asyncio.create_task(_run_auto_reply_after_delay(chat_jid, client, now_ts))
                 state['scheduled_task'] = new_task
            except Exception as e_task_create:
                 logger.error(f"Error creating auto-reply task for {chat_jid}: {e_task_create}")
                 state['scheduled_task'] = None
                 state['trigger_ts'] = 0

    except Exception as e:
        logger.error(f"Error processing message in handle_message for chat {processed_chat_jid}: {e}", exc_info=True)


# --- Main Async Function ---
async def main_async():
    global client, main_loop, shutdown_requested
    running = True
    main_loop = asyncio.get_running_loop()
    load_config() # Load config at the start

    try:
        logger.info("Initializing WhatsApp Client directly...")
        client = WhatsappClient(auto_setup=True, auto_connect=True)
        logger.info("WhatsApp Client initialized successfully.")
        logger.info("Starting manual polling loop...")
        while running and not shutdown_requested:
            try:
                new_messages = client.get_new_messages(download_media=False) # Assume sync
                if new_messages:
                    logger.info(f"Received {len(new_messages)} new messages.")
                    for msg in new_messages:
                        asyncio.create_task(handle_message(msg, client))
                await asyncio.sleep(POLLING_INTERVAL_SECONDS)
            except (DbError, ApiError, BridgeError, WhatsappError) as e:
                logger.error(f"WhatsApp Bridge error during polling loop: {e}. Continuing...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error during polling loop: {e}", exc_info=True)
                await asyncio.sleep(5)
    except (PrerequisitesError, SetupError, BridgeError, WhatsappError) as e:
         logger.critical(f"FATAL ERROR during client initialization: {e}", exc_info=True)
    except Exception as e:
         logger.critical(f"FATAL UNEXPECTED ERROR during startup: {e}", exc_info=True)
    finally:
        logger.info("Initiating shutdown sequence (called from main_async finally)...")
        await shutdown_tasks()

async def shutdown_tasks():
    global client, shutdown_requested
    if shutdown_requested and client is None: # Avoid double execution if already called by signal
         logger.info("Shutdown already in progress or client not set.")
         return

    logger.info("Running shutdown tasks...")
    shutdown_requested = True

    if client:
        try:
            logger.info("Disconnecting client...")
            client.disconnect() # Assume sync
            logger.info("Client disconnected.")
        except Exception as e_disc:
            logger.error(f"Error during client disconnect: {e_disc}", exc_info=True)
    else: logger.info("Client object not initialized, skipping disconnect.")

    logger.info("Cancelling pending auto-reply tasks...")
    all_tasks_to_cancel = []
    for chat_jid, state in list(chat_states.items()):
         task = state.get('scheduled_task')
         if task and not task.done():
              logger.debug(f"Marking task for {chat_jid} for cancellation.")
              task.cancel()
              all_tasks_to_cancel.append(task)
    if all_tasks_to_cancel:
         logger.info(f"Waiting briefly for {len(all_tasks_to_cancel)} tasks to cancel...")
         try:
             await asyncio.wait(all_tasks_to_cancel, timeout=2.0, return_when=asyncio.ALL_COMPLETED)
         except asyncio.TimeoutError: logger.warning("Timeout waiting for tasks to cancel.")
         except Exception as e_wait: logger.error(f"Error awaiting task cancellation: {e_wait}")
         logger.info("Finished waiting for task cancellation.")
    else: logger.info("No pending auto-reply tasks to cancel.")

    save_config() # Save config on shutdown
    logger.info("Shutdown complete.")

def handle_signal(sig, frame):
    logger.warning(f"Received signal {sig}. Initiating graceful shutdown...")
    global shutdown_requested, main_loop
    if not shutdown_requested and main_loop and main_loop.is_running():
         # Schedule the async shutdown task from the signal handler
         asyncio.run_coroutine_threadsafe(shutdown_tasks(), main_loop)
         # Set flag immediately to help stop polling loop
         shutdown_requested = True
    elif shutdown_requested:
         logger.warning("Shutdown already requested.")
    else:
         logger.warning("Loop not available for scheduling shutdown task.")

# --- Script Entry Point ---
if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_signal)
    try: signal.signal(signal.SIGTERM, handle_signal)
    except AttributeError: logger.warning("SIGTERM not available on this platform.")

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt: logger.info("KeyboardInterrupt caught at top level.")
    except Exception as e_run: logger.critical(f"Unhandled exception at top level: {e_run}", exc_info=True)
    finally:
        # Fallback save if shutdown wasn't clean
        if not shutdown_requested:
            logger.warning("Script exiting unexpectedly. Attempting final config save.")
            save_config()