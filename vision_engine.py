import mss
import cv2
import numpy as np
import matplotlib.pyplot as plt
import os
import time

class VisionEngine:
    def __init__(self, project_path=None):
        self.sct = mss.mss()
        self.project_path = project_path
        self.main_roi = None
        self.additional_roi = None

    def grab_screen(self, bbox=None):
        """Grabs screen. bbox is a dict: {'top', 'left', 'width', 'height'}"""
        if bbox:
            screenshot = self.sct.grab(bbox)
        else:
            screenshot = self.sct.grab(self.sct.monitors[1]) # Primary monitor
        img = np.array(screenshot)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)

    def is_completed(self, template_path, threshold=10.0):
        """
        Checks if the are on the screen matches template using mean absolute deviation threshold. 
        Template path should be of a form {name_x1_y1_x2_y2}.png where (x1, y1) and (x2, y2) are
        the bottom-left and top-right corners of the template region in screen coordinates.
        """
        template = cv2.imread(template_path)
        if template is None:
            raise ValueError(f"Template image not found at {template_path}")

        # Extract coordinates from filename
        try:
            name_part = template_path.split("/")[-1].split(".")[0]
            _, x1, y1, x2, y2 = name_part.split("_")
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        except Exception as e:
            raise ValueError(f"Filename must be in format {{name_x1_y1_x2_y2}}.png. Error: {e}")
        
        screen_img = self.grab_screen({'top': y2, 'left': x1, 'width': x2 - x1, 'height': y1 - y2})
        
        if screen_img.shape != template.shape:
            raise ValueError("Template and screen region shapes do not match.")
        
        mad = np.mean(np.abs(screen_img.astype("float") - template.astype("float")))
        return mad < threshold

    def wait_for_completion(self, template_path, max_wait=300, check_interval=1.0):
        """Waits for simulation to complete by checking template match."""
        if not self.project_path or not os.path.exists(template_path):
            # If no template, just wait a default amount
            time.sleep(5)
            return
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                if self.is_completed(template_path):
                    return True
            except:
                pass
            time.sleep(check_interval)
        return False

    def extract_roi_average(self, bbox):
        """Extracts the average RGB value of a screen region."""
        screenshot = self.sct.grab(bbox)
        img = np.array(screenshot)
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        avg_color = rgb_img.mean(axis=0).mean(axis=0)
        return avg_color

    def extract_and_store_completion_indicator(self, roi_coords):
        """Extracts and stores simulation completion indicator (request 8: different name from main ROI).
        roi_coords: (x1, y1, x2, y2)
        """
        if not self.project_path:
            return None
        
        # Request 8: Delete old completion indicator file if exists
        for f in os.listdir(self.project_path):
            if f.startswith("roi_completion_"):
                os.remove(os.path.join(self.project_path, f))
        
        x1, y1, x2, y2 = roi_coords
        bbox = {'left': x1, 'top': y1, 'width': x2 - x1, 'height': y2 - y1}
        screenshot = self.sct.grab(bbox)
        img = np.array(screenshot)
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        
        # Save with different naming scheme
        roi_path = os.path.join(self.project_path, f"roi_completion_{x1}_{y1}_{x2}_{y2}.png")
        cv2.imwrite(roi_path, cv2.cvtColor(rgb_img, cv2.COLOR_RGB2BGR))
        return roi_path

    def extract_and_store_main_roi(self, roi_coords):
        """Extracts and stores main ROI screenshot (request 9: replace old file).
        roi_coords: (x1, y1, x2, y2) where (x1,y1) is top-left, (x2,y2) is bottom-right
        """
        if not self.project_path:
            return None
        
        # Request 9: Delete old main ROI file if exists
        for f in os.listdir(self.project_path):
            if f.startswith("roi_main_"):
                os.remove(os.path.join(self.project_path, f))
        
        x1, y1, x2, y2 = roi_coords
        bbox = {'left': x1, 'top': y1, 'width': x2 - x1, 'height': y2 - y1}
        screenshot = self.sct.grab(bbox)
        img = np.array(screenshot)
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        
        # Save with coordinate naming
        roi_path = os.path.join(self.project_path, f"roi_main_{x1}_{y1}_{x2}_{y2}.png")
        cv2.imwrite(roi_path, cv2.cvtColor(rgb_img, cv2.COLOR_RGB2BGR))
        self.main_roi = roi_coords
        return roi_path

    def extract_and_store_additional_roi(self, roi_coords):
        """Extracts and stores additional ROI screenshot (request 9: replace old file)."""
        if not self.project_path:
            return None
        
        # Request 9: Delete old additional ROI file if exists
        for f in os.listdir(self.project_path):
            if f.startswith("roi_additional_"):
                os.remove(os.path.join(self.project_path, f))
        
        x1, y1, x2, y2 = roi_coords
        bbox = {'left': x1, 'top': y1, 'width': x2 - x1, 'height': y2 - y1}
        screenshot = self.sct.grab(bbox)
        img = np.array(screenshot)
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        
        # Save with coordinate naming
        roi_path = os.path.join(self.project_path, f"roi_additional_{x1}_{y1}_{x2}_{y2}.png")
        cv2.imwrite(roi_path, cv2.cvtColor(rgb_img, cv2.COLOR_RGB2BGR))
        self.additional_roi = roi_coords
        return roi_path

    def rgb_to_scalar(self, rgb, cmap_name, val_min, val_max):
        """Maps an RGB triple back to a scalar value using nearest neighbor in colormap space."""
        try:
            cmap = plt.get_cmap(cmap_name)
        except ValueError:
            cmap = plt.get_cmap('viridis') # fallback

        # Generate 1000 points from the colormap to create a lookup table
        colors = cmap(np.linspace(0, 1, 1000))[:, :3] * 255
        
        # Find closest color (Euclidean distance in RGB space)
        distances = np.sqrt(np.sum((colors - rgb)**2, axis=1))
        closest_idx = np.argmin(distances)
        
        # Map back to value range
        normalized_val = closest_idx / 999.0
        return val_min + (normalized_val * (val_max - val_min))