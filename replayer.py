import time
import numpy as np
import pyperclip
from pynput import mouse, keyboard

class PauseRequested(Exception):
    """Exception raised when pause is requested during replay."""
    pass

class StopRequested(Exception):
    """Exception raised when stop is requested during replay."""
    pass

class TextReplayer:
    def __init__(self):
        self.m_ctrl = mouse.Controller()
        self.k_ctrl = keyboard.Controller()

    def _copy_selection_to_clipboard(self):
        self.k_ctrl.press(keyboard.Key.ctrl)
        self.k_ctrl.press('a')
        self.k_ctrl.release('a')
        time.sleep(0.5)
        self.k_ctrl.press('c')
        self.k_ctrl.release('c')
        self.k_ctrl.release(keyboard.Key.ctrl)
        time.sleep(0.5)

        #print(f"Copied selection to clipboard: {pyperclip.paste()}")

    def _check_pause(self, should_pause_fn):
        """Check if pause is requested and raise exception if so."""
        if should_pause_fn and should_pause_fn():
            raise PauseRequested()

    def _check_stop(self, should_stop_fn):
        """Check if stop is requested and raise exception if so."""
        if should_stop_fn and should_stop_fn():
            raise StopRequested()

    def inject_value(self, val):
        self.k_ctrl.press(keyboard.Key.ctrl)
        self.k_ctrl.press('a')
        self.k_ctrl.release('a')
        self.k_ctrl.release(keyboard.Key.ctrl)
        self.k_ctrl.press(keyboard.Key.backspace)
        self.k_ctrl.release(keyboard.Key.backspace)

        val_str = str(val)
        for char in val_str:
            try:
                key = getattr(keyboard.Key, char, None)
                if key:
                    self.k_ctrl.press(key)
                    self.k_ctrl.release(key)
                else:
                    self.k_ctrl.press(char)
                    self.k_ctrl.release(char)
            except:
                self.k_ctrl.press(char)
                self.k_ctrl.release(char)
            # time.sleep(0.05)

    def execute_run(self, cmd_file, param_dict, vision_engine, template_path, project, sample_index, should_pause_fn, should_stop_fn):
        with open(cmd_file, "r") as f:
            lines = f.readlines()

        min_value = None
        max_value = None

        for line in lines:
            cmd = line.strip()
            if not cmd or cmd.startswith("#"):
                continue

            if cmd.startswith("wait for simulation to finish with timeout"):
                timeout = float(cmd.split("timeout ")[-1])
                completion_roi_coords = project.metadata.get('completion_roi')
                success = vision_engine.wait_for_completion(template_path, completion_roi_coords, max_wait=timeout, should_pause_fn=should_pause_fn, should_stop_fn=should_stop_fn)
                if not success:
                    if not (should_stop_fn and should_stop_fn() or should_pause_fn and should_pause_fn()):
                        raise TimeoutError(f"Simulation did not finish within {timeout} seconds.")
                
            elif cmd.startswith("wait "):
                delay = float(cmd.split()[1])
                time.sleep(delay)

            elif cmd.startswith("lmb click"):
                coords_str = cmd.replace("lmb click at ", "").strip()
                coords = coords_str.split(", ")
                x, y = int(coords[0]), int(coords[1])
                self.m_ctrl.position = (x, y)
                self.m_ctrl.click(mouse.Button.left)

            elif cmd.startswith("rmb click"):
                coords_str = cmd.replace("rmb click at ", "").strip()
                coords = coords_str.split(", ")
                x, y = int(coords[0]), int(coords[1])
                self.m_ctrl.position = (x, y)
                self.m_ctrl.click(mouse.Button.right)

            elif cmd.startswith("press key"):
                key_str = cmd.replace("press key ", "").strip()
                key = getattr(keyboard.Key, key_str, None)
                if key: self.k_ctrl.press(key)
                else: self.k_ctrl.press(key_str)

            elif cmd.startswith("release key"):
                key_str = cmd.replace("release key ", "").strip()
                key = getattr(keyboard.Key, key_str, None)
                if key: self.k_ctrl.release(key)
                else: self.k_ctrl.release(key_str)

            elif cmd.startswith("enter value for"):
                param_name = cmd.replace("enter value for ", "").strip()
                if param_name in param_dict:
                    self.inject_value(param_dict[param_name])
                else:
                    # raise ValueError(f"Parameter '{param_name}' not found in param_dict for command: {cmd}")
                    pass # Ignore if parameter not found

            elif cmd in ("select colormap min value field", "select colormap max value field"):
                self._copy_selection_to_clipboard()
                value_str = pyperclip.paste()
                try:
                    value = float(value_str)
                except ValueError:
                    raise ValueError(f"Invalid clipboard value for '{cmd}': {value_str}")

                if cmd.endswith("min value field"):
                    min_value = value
                else:
                    max_value = value
                
                #print(f"execute_run: '{cmd}'")
                #print(f"execute_run: Project results [{sample_index}] = {project.results[sample_index]}")

                
            elif cmd == "capture the region of interest":
                if project and 'main_roi' in project.metadata:
                    coords = project.metadata['main_roi']
                    if coords:
                        vision_engine.extract_and_store_main_roi(coords, sample_index)

            elif cmd == "capture additional region of interest":
                if project and 'additional_roi' in project.metadata:
                    coords = project.metadata['additional_roi']
                    if coords:
                        vision_engine.extract_and_store_additional_roi(coords, sample_index)
            else:
                # raise ValueError(f"Unknown command in command file: {cmd}")
                pass # Ignore unknown command

            self._check_stop(should_stop_fn)
            self._check_pause(should_pause_fn)

        return min_value, max_value