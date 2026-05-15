import time
from pynput import mouse, keyboard

class TextReplayer:
    def __init__(self):
        self.m_ctrl = mouse.Controller()
        self.k_ctrl = keyboard.Controller()

    def inject_value(self, val):
        self.k_ctrl.press(keyboard.Key.ctrl)
        self.k_ctrl.press('a')
        self.k_ctrl.release('a')
        self.k_ctrl.release(keyboard.Key.ctrl)
        self.k_ctrl.press(keyboard.Key.backspace)

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
            time.sleep(0.05)

    def execute_run(self, cmd_file, param_dict, vision_engine, template_path=None, project=None, sample_index=0):
        with open(cmd_file, "r") as f:
            lines = f.readlines()

        for line in lines:
            cmd = line.strip()
            if not cmd or cmd.startswith("#"):
                continue

            if cmd.startswith("wait for simulation to finish with timeout"):
                timeout = float(cmd.split("timeout ")[-1])
                roi_coords = project.metadata.get('completion_roi')
                success = vision_engine.wait_for_completion(template_path, roi_coords, max_wait=timeout)
                if not success:
                    raise TimeoutError(f"Simulation did not finish within {timeout} seconds.")
                
            elif cmd.startswith("wait "):
                try:
                    delay = float(cmd.split()[1])
                    time.sleep(delay)
                except ValueError: pass

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
                try:
                    key = getattr(keyboard.Key, key_str, None)
                    if key: self.k_ctrl.press(key)
                    else: self.k_ctrl.press(key_str)
                except: self.k_ctrl.press(key_str)

            elif cmd.startswith("release key"):
                key_str = cmd.replace("release key ", "").strip()
                try:
                    key = getattr(keyboard.Key, key_str, None)
                    if key: self.k_ctrl.release(key)
                    else: self.k_ctrl.release(key_str)
                except: self.k_ctrl.release(key_str)

            elif cmd.startswith("enter value for"):
                param_name = cmd.replace("enter value for ", "").strip()
                if param_name in param_dict:
                    self.inject_value(param_dict[param_name])
                time.sleep(0.1)

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