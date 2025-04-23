import time
import random
import threading
import ctypes
import sys
from ctypes import wintypes
import pythoncom
import pyWinhook as pyHook

# Constants
MIN_IDLE_TIME = 180  # seconds (3 minutes) before considering the system idle
CHECK_INTERVAL = 10  # seconds between idle checks
ACTIVITY_INTERVAL_MIN = 30  # minimum seconds between simulated activities
ACTIVITY_INTERVAL_MAX = 120  # maximum seconds between simulated activities

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

# Function to simulate a subtle mouse movement
def simulate_subtle_mouse_movement():
    # Get current mouse position
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    
    # Move mouse to a very nearby position (1-3 pixels in random direction)
    x_offset = random.randint(-3, 3)
    y_offset = random.randint(-3, 3)
    
    # If both offsets are 0, make a minimum movement
    if x_offset == 0 and y_offset == 0:
        x_offset = 1
    
    # Move mouse
    user32.SetCursorPos(point.x + x_offset, point.y + y_offset)
    time.sleep(0.05)
    
    # Move mouse back to original position
    user32.SetCursorPos(point.x, point.y)

# Function to simulate pressing a harmless key (e.g., NumLock or Scroll Lock)
def simulate_harmless_key_press():
    # Key codes for non-disruptive keys
    VK_SCROLL = 0x91  # Scroll Lock
    
    # Press and release Scroll Lock
    user32.keybd_event(VK_SCROLL, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_SCROLL, 0, KEYEVENTF_KEYUP, 0)

# Function to simulate human activity
def simulate_activity():
    # Randomly choose between mouse movement and key press
    if random.random() < 0.7:  # 70% chance for mouse movement
        simulate_subtle_mouse_movement()
    else:
        simulate_harmless_key_press()
    
    print(f"Activity simulated at {time.strftime('%H:%M:%S')}")

# Variables for tracking user activity
user_active = True
last_user_activity = time.time()

# Callback function for mouse events
def on_mouse_event(event):
    global user_active, last_user_activity
    user_active = True
    last_user_activity = time.time()
    return True

# Callback function for keyboard events
def on_keyboard_event(event):
    global user_active, last_user_activity
    user_active = True
    last_user_activity = time.time()
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
    
    print("Keep-active service started.")
    print(f"Will activate after {MIN_IDLE_TIME} seconds of inactivity.")
    
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
                simulate_activity()
                
                # Wait a random interval before next activity
                wait_time = random.randint(ACTIVITY_INTERVAL_MIN, ACTIVITY_INTERVAL_MAX)
                time.sleep(wait_time)
            else:
                user_active = True
                last_user_activity = time.time()
                time.sleep(CHECK_INTERVAL)
                
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(CHECK_INTERVAL)

# Run as a Windows service or in background
if __name__ == "__main__":
    try:
        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_user_activity, daemon=True)
        monitor_thread.start()
        
        # Start keep-active function
        keep_active()
        
    except KeyboardInterrupt:
        print("Keep-active service stopped.")
        sys.exit(0)