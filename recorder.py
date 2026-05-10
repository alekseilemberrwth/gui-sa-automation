import os
from pynput import mouse, keyboard

class TextRecorder:
    def __init__(self, cmd_file_path, on_menu_trigger):
        self.cmd_file_path = cmd_file_path
        self.on_menu_trigger = on_menu_trigger
        self.recording = False
        self.events = []
        self.m_listener = None
        self.k_listener = None

    def start(self):
        self.recording = True
        self.m_listener = mouse.Listener(on_click=self.on_click)
        self.k_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.m_listener.start()
        self.k_listener.start()

    def stop_and_save(self):
        self.recording = False
        if self.m_listener: self.m_listener.stop()
        if self.k_listener: self.k_listener.stop()
        
        with open(self.cmd_file_path, "a") as f:
            for ev in self.events:
                f.write(ev + "\n")
        self.events.clear()

    def on_click(self, x, y, button, pressed):
        if not self.recording: return
        if pressed:
            mouse_click = "lmb click" if button == mouse.Button.left else "rmb click"
            self.events.append(f'{mouse_click} at {x}, {y}')

    def on_press(self, key):
        if key == keyboard.Key.alt or key == keyboard.Key.alt_gr or key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
            self.stop_and_save()
            self.on_menu_trigger()
            return
        
        if not self.recording: return
        
        # Get key name
        if hasattr(key, 'char') and key.char:
            key_name = key.char
        else:
            key_name = key.name
        
        self.events.append(f"press key {key_name}")

    def on_release(self, key):
        if not self.recording: return
        
        # Skip Alt key
        if key == keyboard.Key.alt or key == keyboard.Key.alt_gr or key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
            return
        
        # Get key name
        if hasattr(key, 'char') and key.char:
            key_name = key.char
        else:
            key_name = key.name
        
        self.events.append(f"release key {key_name}")

    def append_command(self, cmd):
        with open(self.cmd_file_path, "a") as f:
            f.write(cmd + "\n")