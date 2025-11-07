# Python Nifty 50 Watcher and Telegram Notifier
#
# Requirements (Install these using pip):
# pip install requests yfinance schedule pytz
#
# Before running:
# 1. Levels File: Ensure 'weekly_range.csv' exists with SPOT_PRICE, CALL_LTP, PUT_LTP.
# 2. Telegram: Get your BOT_TOKEN and CHANNEL_ID (or chat ID).

import requests
import yfinance as yf
import schedule
import time
import datetime
import pytz
import math
import csv 

# --- 1. CONFIGURATION: FILL THESE IN ---

# Local File Configuration
LEVELS_FILE = 'weekly_range.csv' # The local file where the input levels are stored

# Telegram Configuration
# >>> IMPORTANT: Replace these placeholders with your actual values! <<<
BOT_TOKEN = '6377307246:AAEuJAlBiQgDQEa03yNmKQJmZbXyQ0WINOk'
CHANNEL_ID = '-996001230' # Your Telegram Channel ID (e.g., '@MyNiftyChannel' or '-1234567890')

# Trading Configuration
NIFTY_TICKER = '^NSEI'  # Ticker for Nifty 50 Index (check yfinance documentation)
PROXIMITY_THRESHOLD = 25  # Nifty points (e.g., 25 points near an R/S level)
STRIKE_INTERVAL = 50      # Nifty options trade in 50-point intervals

# Global storage for R/S levels
WEEKLY_LEVELS = {} # Will store {'R1': 20100, 'S1': 20000, ...}
# These are the final calculated R/S keys used by downstream functions
LEVEL_KEYS = ['R1', 'S1', 'R2', 'S2', 'R3', 'S3'] 
# These are the input keys expected in the CSV
INPUT_KEYS = ['SPOT_PRICE', 'CALL_LTP', 'PUT_LTP'] 

# Timezone setup
IST = pytz.timezone('Asia/Kolkata')

# --- 2. TELEGRAM HELPER FUNCTIONS ---

def send_telegram_message(message):
    """Sends a message to the configured Telegram channel."""
    if not BOT_TOKEN or not CHANNEL_ID:
        print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] ERROR: Telegram credentials missing. Message not sent.")
        return
        
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHANNEL_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Telegram message sent successfully.")
    except requests.exceptions.HTTPError as e:
        print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Error sending Telegram message (HTTP Error): {e.response.text}")
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Error sending Telegram message: {e}")

# --- 3. LOCAL CSV INTERACTION (UPDATED LOGIC) ---

def fetch_levels():
    """Reads SPOT, CALL_LTP, PUT_LTP from CSV (skipping header), calculates R/S levels, and updates WEEKLY_LEVELS."""
    global WEEKLY_LEVELS
    print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Attempting to fetch input levels from local file '{LEVELS_FILE}'...")
    try:
        with open(LEVELS_FILE, 'r') as file:
            reader = csv.reader(file)
            
            # 1. Skip Header Row (This is the fix for the reported error)
            try:
                next(reader) 
            except StopIteration:
                print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Error: CSV file is empty, cannot find header.")
                send_telegram_message(f"⚠️ *CSV Read Error:* File '{LEVELS_FILE}' is empty. Cannot load input values.")
                return

            # 2. Get Data Row
            try:
                values = next(reader)
            except StopIteration:
                print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Error: CSV file contains only a header, no data row found.")
                send_telegram_message(f"⚠️ *CSV Read Error:* File '{LEVELS_FILE}' missing data row.")
                return

            if len(values) >= len(INPUT_KEYS):
                input_values = {}
                for i in range(len(INPUT_KEYS)):
                    try:
                        # Attempt to convert to float
                        # We use INPUT_KEYS[i] in the error message for clarity
                        input_values[INPUT_KEYS[i]] = float(values[i].strip()) 
                    except ValueError:
                        print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Error: Value '{values[i]}' for {INPUT_KEYS[i]} is not a valid number.")
                        send_telegram_message(f"⚠️ *CSV Data Error:* Value for {INPUT_KEYS[i]} ('{values[i]}') is not a valid number.")
                        return 
                
                # --- CALCULATION LOGIC ---
                
                spot_price = input_values['SPOT_PRICE']
                call_ltp = input_values['CALL_LTP']
                put_ltp = input_values['PUT_LTP']
                print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Successfully read input values from '{LEVELS_FILE}': SPOT={spot_price}, CALL_LTP={call_ltp}, PUT_LTP={put_ltp}")
                # Calculation Steps
                total_ltp1 = call_ltp + put_ltp
                total_ltp2 = total_ltp1 * 2
                total_ltp3 = total_ltp1 * 3
                print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Calculated total LTPs: LTP1={total_ltp1}, LTP2={total_ltp2}, LTP3={total_ltp3}")
                # Set R/S Levels based on the spot price and volatility bands
                new_levels = {
                    'R1': spot_price + total_ltp1,
                    'S1': spot_price - total_ltp1,
                    'R2': spot_price + total_ltp2,
                    'S2': spot_price - total_ltp2,
                    'R3': spot_price + total_ltp3,
                    'S3': spot_price - total_ltp3, # Support 3
                }
                
                WEEKLY_LEVELS = new_levels
                print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Input values: SPOT={spot_price:.2f}, CLTP={call_ltp:.2f}, PLTP={put_ltp:.2f}")
                print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Calculated R/S levels: {WEEKLY_LEVELS}")
                
            else:
                print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Error: Not enough values found in the data row of '{LEVELS_FILE}'. Expected {len(INPUT_KEYS)} values.")
                send_telegram_message(f"⚠️ *CSV Format Error:* Expected 3 input values in data row of '{LEVELS_FILE}', found {len(values)}. Check file format.")

    except FileNotFoundError:
        print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Critical Error: File '{LEVELS_FILE}' not found. Please create it in the same directory.")
        send_telegram_message(f"🚨 *Critical Error:* Weekly levels file ('{LEVELS_FILE}') not found. Please create it.")
    except Exception as e:
        print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] An unexpected error occurred during file reading: {e}")
        send_telegram_message(f"🚨 *Critical Error:* Failed to read and calculate levels. Details: {e}")

# --- 4. DAILY LEVEL NOTIFICATION JOB ---

def notify_weekly_levels():
    """Notifies the channel of the weekly R/S levels."""
    if not WEEKLY_LEVELS:
        fetch_levels() # Try to fetch just in case

    if WEEKLY_LEVELS:
        message = (
            "🎯 *WEEKLY NIFTY LEVELS - RANGES (09:25 AM IST)*\n\n"
            
            "**📈 R E S I S T A N C E S**\n"
            "---------------------------\n"
            # Use monospaced font blocks and padding for alignment
            f"`R3: {WEEKLY_LEVELS.get('R3', 'N/A'):>10.2f}`\n"
            f"`R2: {WEEKLY_LEVELS.get('R2', 'N/A'):>10.2f}`\n"
            f"`R1: {WEEKLY_LEVELS.get('R1', 'N/A'):>10.2f}`\n\n"
            
            "**📉 S U P P O R T S**\n"
            "---------------------------\n"
            f"`S1: {WEEKLY_LEVELS.get('S1', 'N/A'):>10.2f}`\n"
            f"`S2: {WEEKLY_LEVELS.get('S2', 'N/A'):>10.2f}`\n"
            f"`S3: {WEEKLY_LEVELS.get('S3', 'N/A'):>10.2f}`\n\n"
            
            "Watch for price action near these zones."
        )
        send_telegram_message(message)
    else:
        send_telegram_message("❌ *Daily Levels Notification Failed:* Levels are not yet loaded.")

# --- 5. MARKET CHECK LOGIC ---

def get_nifty_spot():
    """Fetches the current Nifty spot price using yfinance."""
    try:
        ticker = yf.Ticker(NIFTY_TICKER)
        # Fetch the last 1 day of data at 1-minute interval for the latest price
        data = ticker.history(period="1d", interval="1m")
        if data.empty:
            print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] No data found for {NIFTY_TICKER}")
            return None
        
        # Get the last closing price
        spot_price = data['Close'].iloc[-1]
        return round(spot_price, 2)
    except Exception as e:
        print(f"[{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Error fetching Nifty data: {e}")
        return None

def find_nearest_strike(price, interval):
    """Calculates the nearest strike price based on a fixed interval (e.g., 50)."""
    return round(price / interval) * interval

def check_proximity_and_notify():
    """
    The main market monitoring function.
    Runs every 5 minutes during market hours.
    """
    now = datetime.datetime.now(IST)
    current_time_str = now.strftime('%H:%M:%S')

    # Check if the time is within market hours (9:25 AM to 3:15 PM IST)
    start_time = now.replace(hour=9, minute=25, second=0, microsecond=0)
    end_time = now.replace(hour=15, minute=15, second=0, microsecond=0)

    if not (start_time <= now <= end_time):
        # This check is mostly redundant if the scheduler is set correctly, 
        # but serves as a safety guard.
        print(f"[{current_time_str}] Outside trading hours. Skipping check.")
        return

    print(f"[{current_time_str}] Running 5-min check...")
    
    # 1. Ensure levels are loaded
    if not WEEKLY_LEVELS:
        # Only try to fetch if market is open and levels are missing
        fetch_levels()
        if not WEEKLY_LEVELS:
            print(f"[{current_time_str}] Levels not loaded. Skipping market check.")
            return

    # 2. Get Nifty Spot Price
    nifty_spot = get_nifty_spot()
    if nifty_spot is None:
        print(f"[{current_time_str}] Failed to get spot price. Skipping check.")
        return

    # 3. Check Proximity to Levels
    for level_key, level_value in WEEKLY_LEVELS.items():
        if abs(nifty_spot - level_value) <= PROXIMITY_THRESHOLD:
            # Nifty is near a key level!
            
            level_type = level_key[0] # 'R' for Resistance, 'S' for Support
            
            # 4. Determine Trade Probability and Strike
            if level_type == 'R':
                # Near Resistance: Probability of PE trade (if selling starts)
                trade_direction = "PE (Put)"
                trade_strike = find_nearest_strike(level_value, STRIKE_INTERVAL)
                message_action = "PE (Put Option) trade if reversal/rejection occurs"
                
            elif level_type == 'S':
                # Near Support: Probability of CE trade (if buying starts)
                trade_direction = "CE (Call)"
                trade_strike = find_nearest_strike(level_value, STRIKE_INTERVAL)
                message_action = "CE (Call Option) trade if bounce/support holds"

            # 5. Construct Notification Message
            message = (
                f"🔔 *NIFTY WEEKLY ALERT* - {current_time_str} IST\n"
                f"Nifty Spot Value: *{nifty_spot:.2f}*\n"
                f"Near Key Level: *{level_key}* at {level_value:.2f}\n"
                f"(Within {PROXIMITY_THRESHOLD} points)\n\n"
                
                f"✨ *Trade Probability:* High chance of {message_action}.\n"
                
                f"Suggested Nearest Strike: **{trade_strike}** ({trade_direction})\n\n"
            
                "NOTE: NOT SEBI REG. Only For Education purpose."
            )
            
            send_telegram_message(message)
            # Notify only once per 5-min interval if a level is hit
            break 
            
# --- 6. SCHEDULING AND MAIN LOOP ---

def main():
     while True:
        IST = pytz.timezone("Asia/Kolkata")
        current_time = datetime.datetime.now(IST).time()
        if current_time >= datetime.datetime.strptime("09:25", "%H:%M").time() and current_time <= datetime.datetime.strptime("09:45", "%H:%M").time():
            print("Notifying Weekly Levels : ", current_time)
            # Run the initial level fetch once immediately
            fetch_levels()
            notify_weekly_levels()

        if current_time >= datetime.datetime.strptime("09:30", "%H:%M").time() and current_time <= datetime.datetime.strptime("15:15", "%H:%M").time():
            print("Market is open in IST timezone : ", current_time)
            # Run the initial level fetch once immediately
            check_proximity_and_notify()
            time.sleep(300)
            print("5 min wait complete...!",current_time)
            
        else:
            print("Market closed for the day. Exiting program.")
            break

if __name__ == "__main__":
    main()
    