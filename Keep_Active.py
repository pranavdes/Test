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