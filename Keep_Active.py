# Installation instructions for required packages:
# pip install pywin32 pyautogui pynput pyWinhook pythoncom

import time
import random
import threading
import ctypes
import sys
import os
import math
import logging
from pynput.keyboard import Controller as KeyboardController
import win32com.client
import win32gui
import win32con
import pyautogui
from datetime import datetime
from ctypes import wintypes
import pythoncom
import pyWinhook as pyHook

# Initialize keyboard controller
keyboard = KeyboardController()

# Constants
MIN_IDLE_TIME = 180  # seconds (3 minutes) before considering the system idle
CHECK_INTERVAL = 10  # seconds between idle checks
ACTIVITY_INTERVAL_MIN = 30  # minimum seconds between simulated activities
ACTIVITY_INTERVAL_MAX = 120  # maximum seconds between simulated activities
LOG_FILE = "keep_active_log.txt"  # log file name

# Finance-related keywords for realistic typing
FINANCE_KEYWORDS = [
    "Risk Assessment Report",
    "Control Testing Procedures",
    "Account Verification Process",
    "Quality Assurance Review",
    "Management Information Report",
    "EUC Testing Guidelines",
    "Internal Control Framework",
    "Compliance Monitoring",
    "Risk Mitigation Strategy",
    "Control Self Assessment",
    "Audit Findings Review",
    "Regulatory Compliance Check",
    "Transaction Verification",
    "Reconciliation Process",
    "Risk Register Update",
    "Control Effectiveness Testing",
    "Documentation Review Process",
    "Incident Management Workflow",
    "Financial Control Metrics",
    "Operational Risk Assessment"
]

# Set up logging
def setup_logging():
    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(log_dir, LOG_FILE)
    
    # Create a logger
    logger = logging.getLogger('KeepActiveLogger')
    logger.setLevel(logging.INFO)
    
    # Create file handler
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.INFO)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add the handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Initialize logger
logger = setup_logging()

# Windows API functions
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.c_uint),
        ('dwTime', ctypes.c_uint),
    ]
    
# Windows API constants
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
KEYEVENTF_KEYUP = 0x0002

# Setup for input simulation
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

# Function to get system idle time
def get_idle_time():
    last_input_info = LASTINPUTINFO()
    last_input_info.cbSize = ctypes.sizeof(last_input_info)
    user32.GetLastInputInfo(ctypes.byref(last_input_info))
    millis = kernel32.GetTickCount() - last_input_info.dwTime
    return millis / 1000.0  # convert to seconds

# Function to simulate human-like typing with natural variations in speed
def simulate_human_typing(text):
    # Base typing speed (words per minute)
    base_wpm = random.uniform(45, 70)
    # Convert to seconds per character
    base_spc = 60 / (base_wpm * 5)
    
    logger.info(f"Simulating typing text: '{text}'")
    
    for char in text:
        # Add natural variation to typing speed
        if random.random() < 0.1:  # Occasional longer pause (like thinking)
            time.sleep(random.uniform(0.5, 1.2))
        elif random.random() < 0.3:  # Frequent slight variations
            time.sleep(base_spc * random.uniform(0.8, 1.5))
        else:
            time.sleep(base_spc)
            
        # Type the character
        keyboard.press(char)
        keyboard.release(char)
        
    # Add a pause at the end
    time.sleep(random.uniform(0.5, 1.0))

# Function to open a new Outlook email
def open_new_outlook_email():
    try:
        logger.info("Opening new Outlook email")
        
        # Use win32com to interact with Outlook
        pythoncom.CoInitialize()  # Initialize COM for this thread
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # 0 = olMailItem
        mail.Display()
        
        # Give Outlook a moment to open the window
        time.sleep(1.5)
        
        logger.info("New Outlook email window opened")
        return True
    except Exception as e:
        logger.error(f"Error opening Outlook: {e}")
        return False

# Function to close the current email window
def close_email_window():
    try:
        logger.info("Closing email window")
        
        # Find the Outlook window
        window = win32gui.GetForegroundWindow()
        
        # Try to close it properly
        try:
            win32gui.PostMessage(window, win32con.WM_CLOSE, 0, 0)
            time.sleep(0.5)
            
            # Handle potential "save draft" dialog
            # Use tab and enter to select "Don't Save"
            keyboard.press_and_release('tab')
            time.sleep(0.2)
            keyboard.press_and_release('tab')
            time.sleep(0.2)
            keyboard.press_and_release('enter')
            
            logger.info("Email window closed")
        except Exception as e:
            logger.error(f"Error closing window gracefully: {e}")
            # Force close as a fallback
            try:
                keyboard.press_and_release('alt+f4')
                time.sleep(0.5)
                keyboard.press_and_release('tab')
                time.sleep(0.2)
                keyboard.press_and_release('enter')  # Don't save
            except:
                pass
            
        return True
    except Exception as e:
        logger.error(f"Error in close_email_window: {e}")
        return False

# Function to simulate typing in Outlook
def simulate_outlook_email_typing():
    try:
        logger.info("Starting Outlook email typing simulation")
        
        # Open a new email
        if not open_new_outlook_email():
            logger.error("Failed to open Outlook - trying alternative method")
            # Alternative: try pyautogui approach
            pyautogui.hotkey('ctrl', 'shift', 'm')
            time.sleep(2)
        
        # Tab to the subject field
        keyboard.press_and_release('tab')
        time.sleep(0.5)
        
        # Type a subject
        subject = f"Draft - {random.choice(FINANCE_KEYWORDS)}"
        simulate_human_typing(subject)
        time.sleep(0.8)
        
        # Tab to the body
        keyboard.press_and_release('tab')
        time.sleep(0.5)
        
        # Type some content in the body
        # Create a paragraph with 3-5 sentences using finance keywords
        num_sentences = random.randint(3, 5)
        for _ in range(num_sentences):
            # Build a sentence with a finance keyword
            sentence = f"The {random.choice(FINANCE_KEYWORDS).lower()} "
            
            # Add some common phrases
            phrases = [
                "needs to be completed by end of week.",
                "was discussed in yesterday's meeting.",
                "requires additional documentation.",
                "has been updated with new requirements.",
                "should be reviewed by the team.",
                "will be included in the quarterly report.",
                "needs sign-off from compliance.",
                "has been flagged for additional review.",
                "shows promising improvement in metrics.",
                "indicates potential areas of concern."
            ]
            
            sentence += random.choice(phrases)
            simulate_human_typing(sentence + " ")
            
            # Add random pauses between sentences
            time.sleep(random.uniform(0.8, 2.0))
        
        # Let the email sit open for a bit (as if reading/reviewing)
        time.sleep(random.uniform(5, 10))
        
        # Close without saving
        close_email_window()
        
        logger.info("Email typing simulation completed")
        return True
    except Exception as e:
        logger.error(f"Error in email simulation: {e}")
        # Try to recover by closing any open windows
        try:
            keyboard.press_and_release('alt+f4')
            time.sleep(0.5)
            keyboard.press_and_release('tab')
            time.sleep(0.2)
            keyboard.press_and_release('enter')  # Don't save
        except:
            pass
        return False

# Function to simulate realistic human mouse movement
def simulate_human_mouse_movement():
    # Get current mouse position
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    current_x, current_y = point.x, point.y
    
    # Get screen dimensions for bounds checking
    screen_width = user32.GetSystemMetrics(0)
    screen_height = user32.GetSystemMetrics(1)
    
    # Generate a natural destination within screen bounds
    # Typically humans move mouse 100-500 pixels in a single motion
    move_distance = random.randint(100, 400)
    angle = random.uniform(0, 2 * 3.14159)  # Random direction in radians
    
    # Calculate destination with bounds checking
    dest_x = min(max(int(current_x + move_distance * math.cos(angle)), 10), screen_width - 10)
    dest_y = min(max(int(current_y + move_distance * math.sin(angle)), 10), screen_height - 10)
    
    logger.info(f"Moving mouse from ({current_x}, {current_y}) to ({dest_x}, {dest_y})")
    
    # Number of steps for the movement (higher = smoother)
    steps = random.randint(10, 25)
    
    # Human mouse movements typically follow a slight curve and have variable speed
    # (acceleration and deceleration at start/end)
    for i in range(0, steps + 1):
        # Ease in/out function for natural acceleration/deceleration
        t = i / steps
        ease = 3 * (t ** 2) - 2 * (t ** 3)  # Smooth step function
        
        # Add a slight curve to the movement
        curve_x = random.randint(-10, 10) * math.sin(math.pi * t)
        curve_y = random.randint(-10, 10) * math.sin(math.pi * t)
        
        # Calculate intermediate position
        x = int(current_x + (dest_x - current_x) * ease + curve_x)
        y = int(current_y + (dest_y - current_y) * ease + curve_y)
        
        # Keep within screen bounds
        x = min(max(x, 0), screen_width)
        y = min(max(y, 0), screen_height)
        
        # Move mouse
        user32.SetCursorPos(x, y)
        
        # Random sleep between steps (variability in movement speed)
        step_sleep = random.uniform(0.005, 0.015)
        time.sleep(step_sleep)
    
    # Small pause at destination (as humans often do)
    time.sleep(random.uniform(0.1, 0.3))
    
    # Log the activity
    logger.info(f"Mouse movement completed to position ({dest_x}, {dest_y})")

# Function to simulate human activity
def simulate_activity():
    # First, always include a mouse movement regardless of other activities
    logger.info("Simulating human mouse movement")
    simulate_human_mouse_movement()
    
    # Then, decide if we should also do email typing
    activity_choice = random.random()
    
    # 70% chance for realistic email typing
    if activity_choice < 0.7:
        logger.info("Starting email typing simulation")
        simulate_outlook_email_typing()
    
    # Add a slight pause between activities if we did both
    time.sleep(random.uniform(1.0, 2.0))
    
    # Log completion
    logger.info(f"Activity simulation completed at {time.strftime('%H:%M:%S')}")

# Variables for tracking user activity
user_active = True
last_user_activity = time.time()

# Callback function for mouse events
def on_mouse_event(event):
    global user_active, last_user_activity
    user_active = True
    last_user_activity = time.time()
    logger.debug(f"User mouse activity detected: {event.MessageName}")
    return True

# Callback function for keyboard events
def on_keyboard_event(event):
    global user_active, last_user_activity
    user_active = True
    last_user_activity = time.time()
    logger.debug(f"User keyboard activity detected: Key {event.Key}")
    return True

# Function to monitor user activity
def monitor_user_activity():
    # Initialize hook manager
    hook_manager = pyHook.HookManager()
    
    # Register callbacks
    hook_manager.MouseAll = on_mouse_event
    hook_manager.KeyDown = on_keyboard_event
    
    # Hook into mouse and keyboard events
    hook_manager.HookMouse()
    hook_manager.HookKeyboard()
    
    # Enter message loop
    pythoncom.PumpMessages()

# Main function for the keep-active logic
def keep_active():
    global user_active, last_user_activity
    
    logger.info("=== Keep-active service started ===")
    logger.info(f"Will activate after {MIN_IDLE_TIME} seconds of inactivity")
    logger.info(f"Logging to console and {os.path.abspath(LOG_FILE)}")
    logger.info(f"Activity interval: {ACTIVITY_INTERVAL_MIN}-{ACTIVITY_INTERVAL_MAX} seconds")
    
    while True:
        try:
            # If we detect user activity through hooks, idle_time might be low but we know the user is active
            if user_active and (time.time() - last_user_activity) < 5:
                time.sleep(CHECK_INTERVAL)
                continue
                
            # Get the actual system idle time
            idle_time = get_idle_time()
            
            # If the user has been idle for longer than threshold, simulate activity
            if idle_time >= MIN_IDLE_TIME:
                user_active = False
                logger.info(f"System idle for {idle_time:.1f} seconds - activating simulation")
                simulate_activity()
                
                # Wait a random interval before next activity
                wait_time = random.randint(ACTIVITY_INTERVAL_MIN, ACTIVITY_INTERVAL_MAX)
                logger.info(f"Waiting {wait_time} seconds before next activity simulation")
                time.sleep(wait_time)
            else:
                if idle_time > MIN_IDLE_TIME * 0.5:  # Log when approaching idle threshold
                    logger.debug(f"Current idle time: {idle_time:.1f} seconds")
                user_active = True
                last_user_activity = time.time()
                time.sleep(CHECK_INTERVAL)
                
        except Exception as e:
            logger.error(f"Error in keep_active function: {e}")
            time.sleep(CHECK_INTERVAL)

# Run as a Windows service or in background
if __name__ == "__main__":
    try:
        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_user_activity, daemon=True)
        monitor_thread.start()
        
        # Log startup information
        logger.info(f"Script started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Operating system: {sys.platform}")
        
        # Start keep-active function
        keep_active()
        
    except KeyboardInterrupt:
        logger.info("Keep-active service stopped by user.")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Critical error: {e}")
        sys.exit(1)