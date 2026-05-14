import time
from pynput import mouse, keyboard

class TextReplayer:
    def __init__(self):
        self.m_ctrl = mouse.Controller()
        self.k_ctrl = keyboard.Controller()

    def inject_value(self, val):
        """Injects a numerical value by simulating keyboard presses."""
        # Clear existing input first
        self.k_ctrl.press(keyboard.Key.ctrl)
        self.k_ctrl.press('a')
        self.k_ctrl.release('a')
        self.k_ctrl.release(keyboard.Key.ctrl)
        self.k_ctrl.press(keyboard.Key.backspace)

        val_str = str(val)
        for char in val_str:
            try:
                # Try to get special key first
                key = getattr(keyboard.Key, char, None)
                if key:
                    self.k_ctrl.press(key)
                    self.k_ctrl.release(key)
                else:
                    # Regular character
                    self.k_ctrl.press(char)
                    self.k_ctrl.release(char)
            except:
                # Fallback to character
                self.k_ctrl.press(char)
                self.k_ctrl.release(char)
            time.sleep(0.05)

    def execute_run(self, cmd_file, param_dict, vision_engine, template_path=None):
        """Executes a single run of commands with the given parameters."""
        with open(cmd_file, "r") as f:
            lines = f.readlines()

        for line in lines:
            cmd = line.strip()
            if not cmd or cmd.startswith("#"):
                continue

            # Parse and execute commands
            if cmd.startswith("lmb click"):
                coords_str = cmd.replace("lmb click at ", "").strip()
                coords = coords_str.split(", ")
                x, y = int(coords[0]), int(coords[1])
                self.m_ctrl.position = (x, y)
                self.m_ctrl.click(mouse.Button.left)
                time.sleep(0.1)

            elif cmd.startswith("rmb click"):
                coords_str = cmd.replace("rmb click at ", "").strip()
                coords = coords_str.split(", ")
                x, y = int(coords[0]), int(coords[1])
                self.m_ctrl.position = (x, y)
                self.m_ctrl.click(mouse.Button.right)
                time.sleep(0.1)

            elif cmd.startswith("press key"):
                key_str = cmd.replace("press key ", "").strip()
                try:
                    key = getattr(keyboard.Key, key_str, None)
                    if key:
                        self.k_ctrl.press(key)
                    else:
                        self.k_ctrl.press(key_str)
                except:
                    self.k_ctrl.press(key_str)
                time.sleep(0.05)

            elif cmd.startswith("release key"):
                key_str = cmd.replace("release key ", "").strip()
                try:
                    key = getattr(keyboard.Key, key_str, None)
                    if key:
                        self.k_ctrl.release(key)
                    else:
                        self.k_ctrl.release(key_str)
                except:
                    self.k_ctrl.release(key_str)
                time.sleep(0.05)

            elif cmd.startswith("enter value for"):
                param_name = cmd.replace("enter value for ", "").strip()
                if param_name in param_dict:
                    self.inject_value(param_dict[param_name])
                time.sleep(0.1)

            elif cmd == "wait for simulation to finish":
                print(f"Waiting for simulation to finish with template path: {template_path}")
                if template_path:
                    vision_engine.wait_for_completion(template_path)
                else:
                    time.sleep(5)

            elif cmd == "capture the region of interest":
                # This should be called with ROI coordinates from project
                pass

            elif cmd == "capture additional region of interest":
                # This should be called with ROI coordinates from project
                pass