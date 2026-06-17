import mss
import cv2
import numpy as np
import matplotlib as mpl
import os
import time

class VisionEngine:
    def __init__(self, project_path=None):
        self.sct = mss.mss()
        self.project_path = project_path
        self.main_roi = None
        self.additional_roi = None

    def grab_screen(self, bbox=None):
        if bbox: screenshot = self.sct.grab(bbox)
        else: screenshot = self.sct.grab(self.sct.monitors[1])
        img = np.array(screenshot)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)

    def is_completed(self, template_path, completion_roi_coords, threshold=1e-7):
        template = cv2.imread(template_path)
        if template is None:
            raise ValueError(f"Template image not found at {template_path}")
            
        template = cv2.cvtColor(template, cv2.COLOR_BGR2RGB)

        if not completion_roi_coords or len(completion_roi_coords) != 4:
            raise ValueError("Valid simulation completion indicator coordinates not found in metadata.")
            
        x1, y1, x2, y2 = completion_roi_coords
        screen_img = self.grab_screen({'top': y1, 'left': x1, 'width': x2 - x1, 'height': y2 - y1})

        if screen_img.shape != template.shape:
            raise ValueError("Template and screen region shapes do not match.")
        
        mad = np.mean(np.abs(screen_img.astype("float") - template.astype("float")))
        # print(f"Completion check - MAD: {mad:.4f}, Threshold: {threshold}")
        return mad <= threshold

    def wait_for_completion(self, template_path, completion_roi_coords, max_wait=10.0, check_interval=1.0, should_pause_fn=None, should_stop_fn=None):
        if not self.project_path or not template_path or not os.path.exists(template_path):
            # print("Project path or template path not set or template file does not exist. Falling back to fixed wait.")
            # print(f"self.project_path: {self.project_path}, template_path: {template_path}")
            time.sleep(max_wait)
            return True
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            if should_stop_fn and should_stop_fn():
                return False
            if should_pause_fn and should_pause_fn():
                return False
            try:
                if self.is_completed(template_path, completion_roi_coords):
                    return True
            except Exception as e:
                print(f"Error during completion check: {e}")
            time.sleep(check_interval)
        return False

    def extract_and_store_main_roi(self, completion_roi_coords, sample_index):
        if not self.project_path: return None
        
        roi_dir = os.path.join(self.project_path, "ROIs")
        os.makedirs(roi_dir, exist_ok=True)
        
        x1, y1, x2, y2 = completion_roi_coords
        bbox = {'left': x1, 'top': y1, 'width': x2 - x1, 'height': y2 - y1}
        screenshot = self.sct.grab(bbox)
        img = np.array(screenshot)
        bgr_img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        
        roi_path = os.path.join(roi_dir, f"roi_main_{sample_index}.png")
        cv2.imwrite(roi_path, bgr_img)
        self.main_roi = completion_roi_coords
        return roi_path

    def extract_and_store_additional_roi(self, completion_roi_coords, sample_index):
        if not self.project_path: return None
        
        roi_dir = os.path.join(self.project_path, "Additional ROIs")
        os.makedirs(roi_dir, exist_ok=True)
        
        x1, y1, x2, y2 = completion_roi_coords
        bbox = {'left': x1, 'top': y1, 'width': x2 - x1, 'height': y2 - y1}
        screenshot = self.sct.grab(bbox)
        img = np.array(screenshot)
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        
        roi_path = os.path.join(roi_dir, f"roi_additional_{sample_index}.png")
        cv2.imwrite(roi_path, cv2.cvtColor(rgb_img, cv2.COLOR_RGB2BGR))
        self.additional_roi = completion_roi_coords
        return roi_path

    def rgb_to_scalar(self, rgb, cmap_name, val_min, val_max):
        rgb = rgb[..., None, :]
        cmap = mpl.colormaps[cmap_name]
        colors = (np.array(cmap.colors) * 255).astype('int64') # Colors are floats, but a PC display's RGB pixels are triples of integer values
        distances = np.sqrt(np.sum((colors - rgb)**2, axis=-1))
        closest_idx = np.argmin(distances, axis=-1)

        if not np.allclose(np.min(distances, axis=-1), 0, rtol=0, atol=1e-10):
            print(f'[WARNING] rgb_to_scalar: the exact matching color was not found, min distances = {np.min(distances, axis=-1)}')

        normalized_val = (closest_idx.astype('float64') + 0.5) / cmap.N  # 0.5, 1.5, ..., 255.5 - to minimize the expected squared reconstruction error, we reconstruct the midpoint of the ListedColormap's interval
        return val_min + (normalized_val * (val_max - val_min))