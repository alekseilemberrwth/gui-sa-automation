import os
import time
from pynput import mouse, keyboard

class TextRecorder:
    def __init__(self, cmd_file_path, on_menu_trigger):
        self.cmd_file_path = cmd_file_path
        self.on_menu_trigger = on_menu_trigger
        self.recording = False
        self.events = []
        self.m_listener = None
        self.k_listener = None
        self.last_event_time = None

    def start(self):
        self.recording = True
        self.last_event_time = time.time()
        self.m_listener = mouse.Listener(on_click=self.on_click)
        self.k_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.m_listener.start()
        self.k_listener.start()

    def _record_delay(self):
        if self.last_event_time:
            delay = time.time() - self.last_event_time
            if delay > 0.01:
                self.events.append(f"wait {delay:.4f}")
        self.last_event_time = time.time()

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
            self._record_delay()
            mouse_click = "lmb click" if button == mouse.Button.left else "rmb click"
            self.events.append(f'{mouse_click} at {x}, {y}')

    def on_press(self, key):
        if not self.recording: return

        if key == keyboard.Key.esc:
            self.stop_and_save()
            self.on_menu_trigger()
            return
        
        self._record_delay()
        if hasattr(key, 'char') and key.char:
            key_name = key.char
            if ord(key_name) < 32:
                key_name = chr(ord(key_name) + 96)
        else:
            key_name = key.name
        
        self.events.append(f"press key {key_name}")

    def on_release(self, key):
        if not self.recording: return
        if key == keyboard.Key.esc: return
        
        self._record_delay()
        if hasattr(key, 'char') and key.char:
            key_name = key.char
            if ord(key_name) < 32:
                key_name = chr(ord(key_name) + 96)
        else:
            key_name = key.name
        
        self.events.append(f"release key {key_name}")

    def append_command(self, cmd):
        with open(self.cmd_file_path, "a") as f:
            f.write(cmd + "\n")