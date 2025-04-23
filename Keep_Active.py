import time
import random
import threading
import ctypes
import sys
import os
import math
import logging
import win32com.client
import win32gui
import win32con
import pyautogui
from datetime import datetime
from ctypes import wintypes
import pythoncom
import pyWinhook as pyHook

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

# Function to simulate typing a single key
def type_key(char):
    # Virtual key codes for common characters
    VK_SPACE = 0x20
    VK_RETURN = 0x0D
    VK_BACK = 0x08
    VK_TAB = 0x09
    
    # Dictionary mapping for common special keys
    special_keys = {
        ' ': VK_SPACE,
        '\n': VK_RETURN,
        '\t': VK_TAB,
        '\b': VK_BACK
    }
    
    # For normal keys, we can use the ord() function to get ASCII/Unicode values
    if char in special_keys:
        vk_code = special_keys[char]
    else:
        vk_code = ctypes.windll.user32.VkKeyScanA(ord(char.lower())) & 0xFF
    
    # Check if shift is needed for uppercase or special characters
    shift_needed = char.isupper() or char in '~!@#$%^&*()_+{}|:"<>?'
    
    try:
        # Press shift if needed
        if shift_needed:
            ctypes.windll.user32.keybd_event(0x10, 0, 0, 0)  # SHIFT key down
        
        # Press and release the key
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)  # Key down
        time.sleep(0.01)
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)  # Key up (2 = KEYEVENTF_KEYUP)
        
        # Release shift if it was pressed
        if shift_needed:
            ctypes.windll.user32.keybd_event(0x10, 0, 2, 0)  # SHIFT key up
            
    except Exception as e:
        logger.error(f"Error typing key '{char}': {e}")
        # Fall back to pyautogui for problematic characters
        try:
            pyautogui.write(char)
        except:
            pass

# Function to simulate keyboard shortcuts and special key combinations
def press_key_combination(keys):
    """
    Simulates pressing multiple keys at once (e.g., Alt+F4)
    keys: list of virtual key codes to press
    """
    try:
        # Press all keys in sequence
        for key in keys:
            ctypes.windll.user32.keybd_event(key, 0, 0, 0)  # Key down
            time.sleep(0.05)
        
        # Small delay while keys are held
        time.sleep(0.1)
        
        # Release all keys in reverse order
        for key in reversed(keys):
            ctypes.windll.user32.keybd_event(key, 0, 2, 0)  # Key up
            time.sleep(0.05)
            
    except Exception as e:
        logger.error(f"Error with key combination {keys}: {e}")
        # Fall back to pyautogui for problematic cases
        try:
            # Map common combinations to pyautogui hotkey calls
            if keys == [0x12, 0x73]:  # Alt+F4
                pyautogui.hotkey('alt', 'f4')
            elif keys == [0x09]:  # Tab
                pyautogui.press('tab')
            elif keys == [0x0D]:  # Enter
                pyautogui.press('enter')
        except:
            pass

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
        type_key(char)
        
    # Add a pause at the end
    time.sleep(random.uniform(0.5, 1.0))

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

# Function to open a new Outlook email and ensure it has focus
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
        
        # Find and focus the Outlook window
        # Look for windows with "Message" in the title (Outlook email windows)
        outlook_window = None
        
        def enum_windows_callback(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                window_title = win32gui.GetWindowText(hwnd)
                # Look for typical Outlook email window titles
                if " - Message" in window_title or "Untitled - Message" in window_title:
                    results.append(hwnd)
                    return False  # Stop enumeration once found
            return True
        
        outlook_windows = []
        win32gui.EnumWindows(enum_windows_callback, outlook_windows)
        
        if outlook_windows:
            outlook_window = outlook_windows[0]
            # Bring window to foreground and give it focus
            try:
                # First, check if window is minimized
                if win32gui.IsIconic(outlook_window):
                    win32gui.ShowWindow(outlook_window, win32con.SW_RESTORE)
                
                # Set foreground window
                win32gui.SetForegroundWindow(outlook_window)
                # Store window handle for later use
                global current_outlook_window
                current_outlook_window = outlook_window
                
                logger.info(f"Outlook window focused with handle: {outlook_window}")
                
                # Extra time to ensure focus
                time.sleep(1.0)
                return True
            except Exception as e:
                logger.error(f"Error setting focus to Outlook window: {e}")
                # Fall back to alternative focus method
                try:
                    shell = win32com.client.Dispatch("WScript.Shell")
                    shell.AppActivate(win32gui.GetWindowText(outlook_window))
                    time.sleep(1.0)
                    current_outlook_window = outlook_window
                    return True
                except:
                    logger.error("Failed to activate Outlook window with alternative method")
        
        logger.error("No Outlook email windows found after creation")
        return False
    except Exception as e:
        logger.error(f"Error opening Outlook: {e}")
        return False

# Global variable to track the current Outlook window handle
current_outlook_window = None

# Function to close the current email window
def close_email_window():
    try:
        logger.info("Closing email window")
        
        global current_outlook_window
        
        # Only proceed if we have a valid Outlook window handle
        if current_outlook_window and win32gui.IsWindow(current_outlook_window):
            # Make sure the correct window has focus before closing
            try:
                if win32gui.IsIconic(current_outlook_window):
                    win32gui.ShowWindow(current_outlook_window, win32con.SW_RESTORE)
                
                # Focus the window before sending close command
                win32gui.SetForegroundWindow(current_outlook_window)
                time.sleep(0.5)  # Give it a moment to gain focus
                
                # Check if we actually got focus
                active_window = win32gui.GetForegroundWindow()
                if active_window == current_outlook_window:
                    logger.info("Successfully focused Outlook window before closing")
                else:
                    logger.warning(f"Failed to focus Outlook window. Active window: {win32gui.GetWindowText(active_window)}")
                    # Try alternative method to focus
                    try:
                        shell = win32com.client.Dispatch("WScript.Shell")
                        shell.AppActivate(win32gui.GetWindowText(current_outlook_window))
                        time.sleep(1.0)
                    except:
                        logger.error("Failed to focus with alternative method")
                
                # Try to close the window properly
                win32gui.PostMessage(current_outlook_window, win32con.WM_CLOSE, 0, 0)
                time.sleep(0.8)
                
                # Handle potential "save draft" dialog
                # Look for dialog window asking to save
                def find_save_dialog_callback(hwnd, results):
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        if "Microsoft Outlook" in title and ("Save" in title or "?" in title):
                            results.append(hwnd)
                            return False
                    return True
                
                save_dialogs = []
                win32gui.EnumWindows(find_save_dialog_callback, save_dialogs)
                
                if save_dialogs:
                    save_dialog = save_dialogs[0]
                    # Focus the dialog
                    win32gui.SetForegroundWindow(save_dialog)
                    time.sleep(0.3)
                    
                    # For "Yes", "No", "Cancel" dialog buttons (in that order):
                    # We want to select "No" which is the middle button
                    # First, ensure we're at the first button by tabbing
                    press_key_combination([0x09])  # Tab
                    time.sleep(0.1)
                    # Then move to second button (No)
                    press_key_combination([0x27])  # RIGHT ARROW
                    time.sleep(0.2)
                    # Then press ENTER to activate "No"
                    press_key_combination([0x0D])  # Enter
                
                # Reset the current_outlook_window
                current_outlook_window = None
                logger.info("Email window closed")
                return True
            
            except Exception as e:
                logger.error(f"Error closing window gracefully: {e}")
                # Force close as a fallback - but make sure we're closing the right window
                try:
                    if win32gui.IsWindow(current_outlook_window):
                        win32gui.SetForegroundWindow(current_outlook_window)
                        time.sleep(0.5)
                        # Alt+F4
                        press_key_combination([0x12, 0x73])
                        time.sleep(0.8)
                        
                        # Check for save dialog again
                        save_dialogs = []
                        win32gui.EnumWindows(find_save_dialog_callback, save_dialogs)
                        if save_dialogs:
                            win32gui.SetForegroundWindow(save_dialogs[0])
                            time.sleep(0.3)
                            # Tab to ensure focus on first button
                            press_key_combination([0x09])  # Tab
                            time.sleep(0.1)
                            # Move to "No" button
                            press_key_combination([0x27])  # RIGHT ARROW
                            time.sleep(0.2)
                            # Activate "No"
                            press_key_combination([0x0D])  # Enter - Don't save
                            
                        current_outlook_window = None
                        return True
                except Exception as e2:
                    logger.error(f"Error in fallback closing: {e2}")
        else:
            logger.warning("No valid Outlook window handle to close")
            
        return False
    except Exception as e:
        logger.error(f"Error in close_email_window: {e}")
        return False

# Function to verify if the current focused window is our Outlook window
def verify_outlook_focus():
    try:
        active_window = win32gui.GetForegroundWindow()
        global current_outlook_window
        
        if active_window == current_outlook_window:
            return True
            
        # If not focused, try to bring it to focus
        if current_outlook_window and win32gui.IsWindow(current_outlook_window):
            logger.info("Outlook window lost focus, attempting to refocus")
            if win32gui.IsIconic(current_outlook_window):
                win32gui.ShowWindow(current_outlook_window, win32con.SW_RESTORE)
            
            # Try primary method
            try:
                win32gui.SetForegroundWindow(current_outlook_window)
                time.sleep(0.5)
            except:
                # Try alternative method
                try:
                    shell = win32com.client.Dispatch("WScript.Shell")
                    shell.AppActivate(win32gui.GetWindowText(current_outlook_window))
                    time.sleep(0.5)
                except:
                    logger.error("Failed to refocus Outlook window")
                    return False
                    
            # Verify focus again
            if win32gui.GetForegroundWindow() == current_outlook_window:
                logger.info("Successfully refocused Outlook window")
                return True
            else:
                logger.error("Failed to regain focus on Outlook window")
                return False
        return False
    except Exception as e:
        logger.error(f"Error verifying Outlook focus: {e}")
        return False

# Function to simulate typing in Outlook
def simulate_outlook_email_typing():
    try:
        logger.info("Starting Outlook email typing simulation")
        
        # Open a new email
        if not open_new_outlook_email():
            logger.error("Failed to open Outlook - trying alternative method")
            # Alternative: try pyautogui approach
            try:
                # Save current active window to return focus later if needed
                original_window = win32gui.GetForegroundWindow()
                
                # Try to launch new email with keyboard shortcut
                pyautogui.hotkey('ctrl', 'shift', 'm')
                time.sleep(2)
                
                # Try to find the newly opened window
                def find_new_email_window(hwnd, results):
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        if " - Message" in title or "Untitled - Message" in title:
                            results.append(hwnd)
                    return True
                
                email_windows = []
                win32gui.EnumWindows(find_new_email_window, email_windows)
                
                if email_windows:
                    global current_outlook_window
                    current_outlook_window = email_windows[0]
                    win32gui.SetForegroundWindow(current_outlook_window)
                    time.sleep(0.5)
                else:
                    logger.error("Could not find Outlook window after hotkey")
                    # Restore original focus if we can't find Outlook
                    if win32gui.IsWindow(original_window):
                        win32gui.SetForegroundWindow(original_window)
                    return False
            except Exception as e:
                logger.error(f"Alternative Outlook opening failed: {e}")
                return False
        
        # Verify we have focus before continuing
        if not verify_outlook_focus():
            logger.error("Could not focus Outlook window, aborting email simulation")
            return False
            
        # Wait a moment for the window to be fully ready
        time.sleep(1.0)
        
        # Directly click in the subject field using Tab (typically need one tab from initial focus)
        press_key_combination([0x09])  # Tab once to get to subject
        time.sleep(0.5)
        
        # Verify we still have focus
        if not verify_outlook_focus():
            logger.error("Lost focus after tabbing to subject field")
            return False
            
        # Type a subject
        subject = f"Draft - {random.choice(FINANCE_KEYWORDS)}"
        simulate_human_typing(subject)
        time.sleep(0.8)
        
        # Verify we still have focus
        if not verify_outlook_focus():
            logger.error("Lost focus after typing subject")
            return False
            
        # Tab to the body (one more tab after subject)
        press_key_combination([0x09])  # Tab to body
        time.sleep(0.5)
        
        # Verify we still have focus
        if not verify_outlook_focus():
            logger.error("Lost focus after tabbing to body")
            return False
            
        # Type some content in the body
        # Create a paragraph with 3-5 sentences using finance keywords
        num_sentences = random.randint(3, 5)
        for i in range(num_sentences):
            # Verify we still have focus before each sentence
            if not verify_outlook_focus():
                logger.error(f"Lost focus while typing body (sentence {i+1})")
                return False
                
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
        if close_email_window():
            logger.info("Email typing simulation completed successfully")
            return True
        else:
            logger.error("Failed to close email window properly")
            return False
    except Exception as e:
        logger.error(f"Error in email simulation: {e}")
        # Try to clean up if an exception occurred
        try:
            if current_outlook_window and win32gui.IsWindow(current_outlook_window):
                win32gui.SetForegroundWindow(current_outlook_window)
                time.sleep(0.5)
                win32gui.PostMessage(current_outlook_window, win32con.WM_CLOSE, 0, 0)
                time.sleep(0.5)
                # Handle potential dialog
                press_key_combination([0x09])  # Tab
                time.sleep(0.2)
                press_key_combination([0x09])  # Tab
                time.sleep(0.2)
                press_key_combination([0x0D])  # Enter
        except:
            pass
        return False

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