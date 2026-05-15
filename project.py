import os
import json
import numpy as np

class Project:
    def __init__(self, folder_path=None):
        self.folder_path = folder_path
        self.metadata = {
            "name": "New Project",
            "status": "setup", # setup, in_progress, completed
            "params": {}, # {name: {"min": 0, "max": 1}}
            "sa_type": None,
            "sa_params": {},
            "colormap": {"name": "viridis", "source": "chosen by user", "min": 0.0, "max": 100.0},
            "additional_roi_status": "not capturing",
            "n_required": 0,
            # "main_roi": None,
            # "additional_roi": None,
            "completion_roi": None
        }
        self.results = []
        self.samples = []

    def save(self):
        if not self.folder_path: return
        os.makedirs(self.folder_path, exist_ok=True)
        with open(os.path.join(self.folder_path, "metadata.json"), "w") as f:
            json.dump(self.metadata, f, indent=4)
        if len(self.samples) > 0:
            np.save(os.path.join(self.folder_path, "samples.npy"), self.samples)
        if len(self.results) > 0:
            np.save(os.path.join(self.folder_path, "results.npy"), self.results)

    def load(self):
        try:
            with open(os.path.join(self.folder_path, "metadata.json"), "r") as f:
                self.metadata = json.load(f)
            
            # Request 10: Detect additional_roi_status from commands.txt
            cmd_file = os.path.join(self.folder_path, "commands.txt")
            if os.path.exists(cmd_file):
                with open(cmd_file, "r") as f:
                    content = f.read()
                    # Check if the command is present and not commented
                    if "capture additional region of interest" in content:
                        # Check if it's not commented
                        if not all(line.strip().startswith("#") for line in content.split("\n") 
                                  if "capture additional region of interest" in line):
                            self.metadata["additional_roi_status"] = "capturing"
                        else:
                            self.metadata["additional_roi_status"] = "not capturing"
                    else:
                        self.metadata["additional_roi_status"] = "not capturing"
            
            if os.path.exists(os.path.join(self.folder_path, "samples.npy")):
                self.samples = np.load(os.path.join(self.folder_path, "samples.npy")).tolist()
            if os.path.exists(os.path.join(self.folder_path, "results.npy")):
                self.results = np.load(os.path.join(self.folder_path, "results.npy")).tolist()
            return True
        except Exception:
            return False

    def validate(self):
        req_files = ["metadata.json", "commands.txt"]
        missing = [f for f in req_files if not os.path.exists(os.path.join(self.folder_path, f))]
        if missing: return f"Missing files: {', '.join(missing)}"
        return None

    def toggle_additional_roi_command(self, enable):
        cmd_file = os.path.join(self.folder_path, "commands.txt")
        if not os.path.exists(cmd_file): raise FileNotFoundError("commands.txt not found in project folder.")
        with open(cmd_file, "r") as f:
            lines = f.readlines()
        
        target = "capture additional region of interest"
        with open(cmd_file, "w") as f:
            for line in lines:
                clean_line = line.strip().replace("# ", "")
                if clean_line == target:
                    f.write(f"{target}\n" if enable else f"# {target}\n")
                else:
                    f.write(line)
        # Request 10: Use "not capturing" instead of "capturing stopped"
        self.metadata["additional_roi_status"] = "capturing" if enable else "not capturing"
        self.save()