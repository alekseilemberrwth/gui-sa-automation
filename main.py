# BUG
# 3. I open existing project, press "View SA results", close results window, close project window, close main menu. App is not finishing after it. This is a bug.
# 4. The delay between 2 actions, interrupted by Esc press, should be (delay before Esc + delay after Esc).
# Currently when I click lmb, then press Esc, then capture the region of interest, the delay between lmb click and capture is zero, which is incorrect.
# Also then I click Esc to capture additional roi, the delay between the commands "capture the region of interest" and "capture additional region of interest" is also zero,
# which is also incorrect.
# 5. When I open existing SA, min and max colormap value are restored to default instead of being loaded from metadata. I saved them in the previous launch of the app, but seemingly
# they are not being stored in metadata or not loaded correctly.
# 6. The results.npy should contain the average pixel of the main roi for each sample index. I do not know what this array contains now.
# The gradients and the sobol indices should be calculated when I click "View SA results" button.
# Because only at that point of time the min and max colormap values are known for sure, which are needed for the rgb to scalar function. Also, when showing gradient report,
# show also colormap name and min and max values which were used for the gradient calculation.

# TODO
# 1. When user clicks "Save & Start Running Simulations", make sure command file is valid:
# 0) there are no unknown commands;
# 1) every selected parameter {param} have exactly one corresponding command "enter value for {param}"; 2) there are no unknown parameter names;
# 3) there is only command of each of these types: "wait for simulation to finish", "capture additional region of interest", "capture the region of interest".
# 4) no parameter values can be entered after "wait for simulation to finish" command.
# 5) "capture the region of interest" command must be after "wait for simulation to finish" command.

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os
import threading
from project import Project
from recorder import TextRecorder
from replayer import TextReplayer
from vision_engine import VisionEngine
from PIL import Image, ImageTk
import numpy as np
import time
import mss
import cv2
from SALib.sample.sobol import sample as sobol_sample
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SA Automation")
        self.center_window(500, 600)
        self.root.config(bg="white")
        self.project = None
        self.recorder = None
        self.vision_engine = None
        self.screen_stack = []
        self.roi_selection = None
        self.recording_paused = False
        self.replay_paused = False
        self.replay_stop_requested = False
        self._replay_thread = None
        self.current_sample_index = 0
        self.in_roi_preview = False
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_window_close)
        self.setup_main_menu()

    def center_window(self, width, height):
        """Centers the window on the screen."""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = int((screen_width - width) / 2)
        y = int((screen_height - height) / 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _add_unique_command(self, cmd, prefix=None):
        """Adds a command, removing any existing command with the same prefix."""
        cmd_file = os.path.join(self.project.folder_path, "commands.txt")
        if not os.path.exists(cmd_file):
            with open(cmd_file, "w") as f: 
                f.write(cmd + "\n")
            return

        with open(cmd_file, "r") as f:
            lines = f.readlines()
        
        with open(cmd_file, "w") as f:
            for line in lines:
                if prefix and line.strip().startswith(prefix):
                    continue
                if not prefix and line.strip() == cmd:
                    continue
                f.write(line)
            f.write(cmd + "\n")

    def on_window_close(self):
        if self.in_roi_preview:
            self.in_roi_preview = False
            self.show_recording_menu()
            return
        
        if len(self.screen_stack) > 0:
            self.screen_stack.pop()
            if len(self.screen_stack) > 0:
                prev_screen, prev_data = self.screen_stack[-1]
                self.show_screen(prev_screen, prev_data)
            else:
                self.root.destroy()
        else:
            self.root.destroy()

    def push_screen(self, screen_name, screen_data=None):
        self.screen_stack.append((screen_name, screen_data))

    def show_screen(self, screen_name, screen_data=None):
        if screen_name == "main_menu":
            self.setup_main_menu()
        elif screen_name == "project_dashboard":
            self.show_project_dashboard()
        elif screen_name == "recording_menu":
            self.show_recording_menu()
        elif screen_name == "add_param":
            self.add_param_ui()
        elif screen_name == "edit_param":
            self.edit_param_ui()
        elif screen_name == "sa_setup":
            self.sa_setup_ui()

    def setup_main_menu(self):
        for widget in self.root.winfo_children(): widget.destroy()
        self.center_window(500, 600)
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(main_frame, text="Sensitivity Analysis Automation", font=("Arial", 14), bg="white").pack(pady=20)
        tk.Button(main_frame, text="Start new SA", command=self.start_new_sa, width=20, bg="white").pack(pady=10)
        tk.Button(main_frame, text="Open existing SA", command=self.open_existing_sa, width=20, bg="white").pack()
        self.screen_stack = [("main_menu", None)]

    def open_existing_sa(self):
        folder = filedialog.askdirectory()
        if not folder: return
        
        self.project = Project(folder)
        if not self.project.load():
            messagebox.showerror("Error", "Invalid Project Folder structure.")
            return
        
        err = self.project.validate()
        if err:
            messagebox.showerror("Invalid Project", err)
            return

        # TODO put in .validate() 
        # if 'completion_roi' in self.project.metadata and self.project.metadata['completion_roi'] is not None:
        #     roi_path = os.path.join(folder, "simulation_completion_indicator.png")
        #     if os.path.exists(roi_path):
        #         img = cv2.imread(roi_path)
        #         if img is not None:
        #             h, w = img.shape[:2]
        #             x1, y1, x2, y2 = self.project.metadata['completion_roi']
        #             if abs((x2 - x1) - w) > 0 or abs((y2 - y1) - h) > 0:
        #                 messagebox.showerror("Error", "Completion indicator image dimensions do not match coordinates in metadata.")
        #                 return
        
        self.push_screen("project_dashboard")
        self.vision_engine = VisionEngine(self.project.folder_path)
        self.show_project_dashboard()

    def show_project_dashboard(self):
        for widget in self.root.winfo_children(): widget.destroy()
        
        self.root.title(f"Project: {self.project.metadata['name']}")
        self.center_window(760, 860)
        self.root.config(bg="white")
        
        changes_made = {"changed": False}
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        status_colors = {"setup": "grey", "in_progress": "orange", "completed": "green"}
        
        stat_frame = tk.Frame(main_frame, bg="white")
        stat_frame.pack(fill=tk.X, pady=5)
        status_color = status_colors.get(self.project.metadata['status'], 'black')
        tk.Label(stat_frame, text="Status:", font=("Arial", 10, "bold"), fg="black", bg="white").pack(side=tk.LEFT)
        tk.Label(stat_frame, text=self.project.metadata['status'], font=("Arial", 10, "bold"), fg=status_color, bg="white").pack(side=tk.LEFT)
        if self.project.metadata['status'] == "in_progress":
            tk.Button(stat_frame, text="Continue simulation runs", bg="lightblue",
                      command=self.resume_sims).pack(side=tk.LEFT, padx=10)
        
        info_frame = tk.Frame(main_frame, bg="white")
        info_frame.pack(fill=tk.X, pady=5)
        tk.Label(info_frame, text=f"SA type: {self.project.metadata.get('sa_type', '-')}", bg="white").pack(side=tk.LEFT, padx=2)
        tk.Label(info_frame, text=f"Runs required: {self.project.metadata.get('n_required', '-')}", bg="white").pack(side=tk.LEFT, padx=20)
        
        table_frame = tk.Frame(main_frame, bg="white", relief=tk.RIDGE, borderwidth=1)
        table_frame.pack(fill=tk.X, pady=10)
        tk.Label(table_frame, text="Parameter settings", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W, padx=5, pady=5)
        
        param_table = tk.Frame(table_frame, bg="white")
        param_table.pack(fill=tk.X, padx=5, pady=5)
        
        sa_type = self.project.metadata.get('sa_type', '')
        headers = ["Name", "Range"]
        if sa_type == 'Gradient-Based': headers += ["Point", "Step"]
        widths = [18, 24, 14, 14]
        header_row = tk.Frame(param_table, bg="lightgrey")
        header_row.pack(fill=tk.X)
        for idx, header in enumerate(headers):
            tk.Label(header_row, text=header, bg="lightgrey", width=widths[idx], anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=3)
        
        if len(self.project.metadata['params']) == 0:
            tk.Label(param_table, text="No parameters defined.", bg="white").pack(padx=5, pady=5)
        else:
            for pname, bounds in self.project.metadata['params'].items():
                row = tk.Frame(param_table, bg="white")
                row.pack(fill=tk.X)
                tk.Label(row, text=pname, bg="white", width=widths[0], anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                tk.Label(row, text=f"[{bounds['min']}, {bounds['max']}]", bg="white", width=widths[1], anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                if sa_type == 'Gradient-Based':
                    grad_params = self.project.metadata.get('sa_params', {}).get(pname, {})
                    tk.Label(row, text=str(grad_params.get('point', '')), bg="white", width=widths[2], anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                    tk.Label(row, text=str(grad_params.get('step', '')), bg="white", width=widths[3], anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
        
        completion_frame = tk.Frame(main_frame, bg="white")
        completion_frame.pack(fill=tk.X, pady=10)
        comp_button = tk.Button(completion_frame, text="View Simulation Completion Indicator", bg="white",
                                command=self.view_completion_template)
        comp_button.pack(fill=tk.X, padx=10, pady=10)
        
        roi_frame = tk.Frame(main_frame, bg="white")
        roi_frame.pack(fill=tk.X, pady=10)
        tk.Label(roi_frame, text=f"Additional ROI status: {self.project.metadata['additional_roi_status']}", bg="white").pack(side=tk.LEFT)
        btn_text = "Stop capturing" if self.project.metadata['additional_roi_status'] == "capturing" else "Resume capturing"
        tk.Button(roi_frame, text=btn_text, bg="white", command=self.toggle_add_roi).pack(side=tk.LEFT, padx=10)
        tk.Button(roi_frame, text="View last additional ROI", bg="white", command=self.view_last_additional_roi).pack(side=tk.RIGHT)
        
        colormap_frame = tk.Frame(main_frame, bg="white", relief=tk.RIDGE, borderwidth=1)
        colormap_frame.pack(fill=tk.X, pady=10)
        
        cmap_info_frame = tk.Frame(colormap_frame, bg="white")
        cmap_info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        cmap_name_frame = tk.Frame(cmap_info_frame, bg="white")
        cmap_name_frame.pack(fill=tk.X, pady=2)
        tk.Label(cmap_name_frame, text="Colormap:", bg="white").pack(side=tk.LEFT)
        cmap_var = tk.StringVar(value=self.project.metadata['colormap']['name'])
        cmap_dropdown = ttk.Combobox(cmap_name_frame, textvariable=cmap_var, 
                                     values=['viridis', 'plasma', 'inferno', 'magma', 'cividis', 'twilight', 'rainbow'],
                                     state='readonly', width=15)
        cmap_dropdown.pack(side=tk.LEFT, padx=5)
        cmap_source = self.project.metadata['colormap']['source']
        tk.Label(cmap_name_frame, text=f"({cmap_source})", bg="white").pack(side=tk.LEFT)
        tk.Button(cmap_name_frame, text="Identify from data", bg="white", command=self.identify_colormap_from_data).pack(side=tk.LEFT, padx=5)
        
        def on_cmap_change(*args):
            changes_made["changed"] = True
            update_save_button()
        cmap_var.trace('w', on_cmap_change)
        
        min_frame = tk.Frame(cmap_info_frame, bg="white")
        min_frame.pack(fill=tk.X, pady=2)
        tk.Label(min_frame, text="Min value:", bg="white").pack(side=tk.LEFT)
        min_var = tk.StringVar(value=str(self.project.metadata['colormap']['min']))
        min_entry = tk.Entry(min_frame, textvariable=min_var, width=10, bg="white")
        min_entry.pack(side=tk.LEFT, padx=5)
        
        def on_min_change(*args):
            changes_made["changed"] = True
            update_save_button()
        min_var.trace('w', on_min_change)
        
        max_frame = tk.Frame(cmap_info_frame, bg="white")
        max_frame.pack(fill=tk.X, pady=2)
        tk.Label(max_frame, text="Max value:", bg="white").pack(side=tk.LEFT)
        max_var = tk.StringVar(value=str(self.project.metadata['colormap']['max']))
        max_entry = tk.Entry(max_frame, textvariable=max_var, width=10, bg="white")
        max_entry.pack(side=tk.LEFT, padx=5)
        
        def on_max_change(*args):
            changes_made["changed"] = True
            update_save_button()
        max_var.trace('w', on_max_change)

        if self.project.metadata['status'] == "completed":
            tk.Button(main_frame, text="View SA results", bg="lightgreen", command=self.generate_report).pack(pady=20)
        
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        
        save_button = tk.Button(button_frame, text="Save", bg="lightgrey", fg="grey", state=tk.DISABLED, 
                               command=lambda: on_save_clicked())
        save_button.pack(side=tk.RIGHT, padx=5)
        
        def update_save_button():
            if changes_made["changed"]: save_button.config(state=tk.NORMAL, bg="lightgreen", fg="black")
            else: save_button.config(state=tk.DISABLED, bg="lightgrey", fg="grey")
        
        def on_save_clicked():
            try:
                cmap_min, cmap_max = float(min_var.get()), float(max_var.get())
                if cmap_min >= cmap_max:
                    messagebox.showerror("Error", "Min value must be less than Max value")
                    return
                self.project.metadata['colormap']['name'] = cmap_var.get()
                self.project.metadata['colormap']['min'] = cmap_min
                self.project.metadata['colormap']['max'] = cmap_max
                self.project.save()
                messagebox.showinfo("Success", "Changes saved successfully")
                changes_made["changed"] = False
                update_save_button()
            except ValueError:
                messagebox.showerror("Error", "Invalid values - Min and Max must be numbers")
        
        def on_back_clicked():
            if changes_made["changed"]:
                if messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Discard them?"):
                    if len(self.screen_stack) > 0: self.screen_stack.pop()
                    self.setup_main_menu()
            else:
                if len(self.screen_stack) > 0: self.screen_stack.pop()
                self.setup_main_menu()
        
        tk.Button(button_frame, text="Back", bg="white", command=on_back_clicked).pack(side=tk.LEFT, padx=5)

    def toggle_add_roi(self):
        if self.project.metadata.get('status') == "completed":
            messagebox.showerror("Error", "Cannot change ROI capturing status: project is already completed.")
            return

        is_capturing = self.project.metadata['additional_roi_status'] == "capturing"
        if not is_capturing:
            if 'additional_roi' not in self.project.metadata:
                messagebox.showerror("Error", "No additional ROI selected yet")
                return
        self.project.toggle_additional_roi_command(not is_capturing)
        self.show_project_dashboard()

    def resume_sims(self):
        if messagebox.askokcancel("Confirm", "Resume simulation running?"):
            self.root.iconify()
            self.replay_paused = False
            self.replay_stop_requested = False
            self._replay_thread = threading.Thread(target=self.start_replay, daemon=True)
            self._replay_thread.start()

    def view_completion_template(self):
        template_files = self.find_files_with_prefix("simulation_completion_indicator_")
        if len(template_files) == 0:
            messagebox.showinfo("Info", "No simulation completion indicator found")
            return
        template_path = os.path.join(self.project.folder_path, template_files[0])
        os.startfile(template_path)

    def find_files_with_prefix(self, prefix):
        if prefix.startswith("roi_additional_"): folder = os.path.join(self.project.folder_path, "Additional ROIs")
        elif prefix.startswith("roi_main_"): folder = os.path.join(self.project.folder_path, "ROIs")
        else: folder = self.project.folder_path
        
        if not os.path.exists(folder): return []
        return [f for f in os.listdir(folder) if f.startswith(prefix)]

    def view_last_additional_roi(self):
        roi_files = self.find_files_with_prefix("roi_additional_")
        if not roi_files:
            messagebox.showinfo("Info", "No additional ROI captured yet (run simulation to capture)")
            return
        full_paths = [os.path.join(self.project.folder_path, "Additional ROIs", f) for f in roi_files]
        latest = max(full_paths, key=os.path.getmtime)
        os.startfile(latest)

    def capture_completion_indicator(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Simulation Completion Method")
        
        # Center this dialog
        dialog.geometry("300x150")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="Select completion detection method:").pack(pady=20)
        
        def on_timeout():
            dialog.destroy()
            self.prompt_timeout_only()
            
        def on_image_timeout():
            dialog.destroy()
            self.start_roi_selection("completion_indicator")
            
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Timeout Only", command=on_timeout).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Image + Timeout", command=on_image_timeout).pack(side=tk.LEFT, padx=10)

    def prompt_timeout_only(self):
        timeout = simpledialog.askfloat("Timeout", "Enter timeout in seconds:", minvalue=0.1, parent=self.root)
        if timeout:
            cmd = f"wait for simulation to finish with timeout {timeout}"
            self._add_unique_command(cmd, prefix="wait for simulation to finish")
            # Delete any old completion templates since we are using pure timeout
            for f in os.listdir(self.project.folder_path):
                if f.startswith("simulation_completion_indicator_"):
                    os.remove(os.path.join(self.project.folder_path, f))
            messagebox.showinfo("Success", f"Timeout set to {timeout} seconds.")

    def identify_colormap_from_data(self):
        messagebox.showinfo("Info", "Colormap identification from data not yet implemented")

    def generate_report(self):
        sa_type = self.project.metadata.get('sa_type')
        if sa_type == 'Sobol (SALib)':
            messagebox.showinfo("Info", "Sobol report to be implemented")
        elif sa_type == 'Gradient-Based':
            self.show_gradient_report()

    def show_gradient_report(self):
        report_win = tk.Toplevel(self.root)
        report_win.title("Gradient-Based SA Results")
        report_win.geometry("600x500")
        
        param_names = list(self.project.metadata['params'].keys())
        grad_params = self.project.metadata.get('sa_params', {})
        results = self.project.results

        print("In show_gradient_report:")
        print(f"Param names: {param_names}")
        print(f"Grad params: {grad_params}")
        print(f"Results: {results}")
        
        gradients = []
        points = []
        for i, name in enumerate(param_names):
            gp = grad_params.get(name, {})
            step = gp.get('step')
            point = gp.get('point')
            points.append(f"{name}: {point}")
            
            res_neg = results[2*i]
            res_pos = results[2*i + 1]

            print(f"res_neg={res_neg}, res_pos={res_pos}")
            
            if np.isnan(res_neg) or np.isnan(res_pos):
                print(f"Warning: NaN result for parameter {name} at point {point} with step {step}. Setting gradient to 0.")
                grad = 0.0
            else:
                grad = (res_pos - res_neg) / (2 * step)
            gradients.append(grad)
        
        info_frame = tk.Frame(report_win, bg="white")
        info_frame.pack(fill=tk.X, padx=10, pady=10)
        tk.Label(info_frame, text="Evaluation Point:", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W)
        tk.Label(info_frame, text=", ".join(points), bg="white").pack(anchor=tk.W)
        
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(param_names, gradients, color='skyblue')
        ax.set_ylabel("Gradient")
        ax.set_title("Gradient")
        plt.xticks(rotation=45, ha="right")
        fig.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, master=report_win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def start_new_sa(self):
        folder = filedialog.askdirectory(title="Select Empty Folder for New Project")
        if not folder: return
        
        project_files = ["metadata.json", "commands.txt", "samples.npy", "results.npy"]
        roi_files = [f for f in os.listdir(folder) if f.startswith("roi_")]
        if os.listdir(folder) and (any(os.path.exists(os.path.join(folder, f)) for f in project_files) or roi_files):
            messagebox.showerror("Error", "Selected folder is not empty. Please select an empty folder.")
            return
        
        for widget in self.root.winfo_children(): widget.destroy()
        
        self.root.title("New Project")
        self.center_window(400, 200)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=20, padx=20)
        
        tk.Label(main_frame, text="Enter project name:", bg="white", font=("Arial", 12)).pack(pady=10)
        name_entry = tk.Entry(main_frame, font=("Arial", 12), bg="white")
        name_entry.pack(pady=10, fill=tk.X)
        name_entry.focus()
        
        def confirm_name():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Error", "Project name cannot be empty")
                return
            self.proceed_with_recording(folder, name)
        
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(pady=10)
        tk.Button(button_frame, text="OK", command=confirm_name, bg="white").pack()
        name_entry.bind("<Return>", lambda e: confirm_name())

    def proceed_with_recording(self, folder, project_name):
        self.project = Project(folder)
        self.project.metadata['name'] = project_name
        self.project.save()
        
        cmd_file = os.path.join(folder, "commands.txt")
        # self.recorder = TextRecorder(cmd_file, self.show_recording_menu_from_pause)
        self.recorder = TextRecorder(cmd_file, lambda: self.root.after(0, self.show_recording_menu_from_pause))
        self.vision_engine = VisionEngine(folder)
        
        self.root.iconify()
        messagebox.showinfo("Recording Started", "Recording mouse and keyboard. Press Esc to pause and open the control menu.")
        self.recorder.start()

    def show_recording_menu_from_pause(self):
        self.recording_paused = True
        self.root.deiconify()
        try:
            self.root.attributes("-topmost", True)
            self.root.attributes("-topmost", False)
        except: pass
        self.root.lift()
        self.root.focus_force()
        if not self.screen_stack or self.screen_stack[-1][0] != "recording_menu":
            self.push_screen("recording_menu")
        self.show_recording_menu()

    def show_recording_menu(self):
        for widget in self.root.winfo_children(): widget.destroy()
        
        self.root.title(f"Recording Menu (Paused) | {self.project.metadata['name']}")
        self.center_window(500, 700)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        tk.Button(main_frame, text="Add new parameter", command=self.add_param_ui, bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Edit parameters", command=self.edit_param_ui, bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Set simulation completion indicator", command=self.capture_completion_indicator, bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Capture region of interest", command=lambda: self.start_roi_selection("main_roi"), bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Capture additional region of interest", command=lambda: self.start_roi_selection("additional_roi"), bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="View command file", command=self.view_cmd_file, bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Select SA type", command=self.sa_setup_ui, bg="white").pack(fill=tk.X, padx=20, pady=5)
        
        tk.Button(main_frame, text="Resume Recording", bg="lightblue", 
                  command=self.resume_recording).pack(fill=tk.X, padx=20, pady=10)
        tk.Button(main_frame, text="Save & Start Running Simulations", bg="green", fg="white", 
                  command=self.start_running).pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=10)
        
    def resume_recording(self):
        self.recording_paused = False
        self.root.iconify()
        if self.recorder:
            self.recorder.start()

    def pause_replay(self):
        self.replay_paused = True
        self.root.after(0, self._show_replay_paused_ui)

    def _show_replay_paused_ui(self):
        self.root.deiconify()
        self.root.lift()
        self.show_replay_pause_menu()

    def show_replay_pause_menu(self):
        for widget in self.root.winfo_children(): widget.destroy()
        
        self.root.title(f"Replay Paused | {self.project.metadata['name']}")
        self.center_window(500, 400)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        tk.Label(main_frame, text=f"Replay paused at sample {self.current_sample_index + 1} of {len(self.project.samples)}", 
                bg="white", font=("Arial", 12)).pack(pady=20)
        
        tk.Button(main_frame, text="Start running simulations", bg="green", fg="white", 
                  command=self.resume_replay).pack(fill=tk.X, padx=20, pady=10)
        
        tk.Button(main_frame, text="Stop and Return to Main Menu", bg="red", fg="white", 
                  command=self.stop_replay).pack(fill=tk.X, padx=20, pady=10)

    def resume_replay(self):
        self.replay_paused = False
        self.root.iconify()

    def stop_replay(self):
        self.replay_stop_requested = True
        self.replay_paused = False
        self.setup_main_menu()

    def view_cmd_file(self):
        cmd_file = os.path.join(self.project.folder_path, "commands.txt")
        os.startfile(cmd_file)

    def start_roi_selection(self, roi_type):
        self.roi_type = roi_type
        self.roi_data = {"x1": 0, "y1": 0, "x2": 0, "y2": 0}
        
        roi_win = tk.Tk()
        roi_win.attributes("-fullscreen", True)
        roi_win.attributes("-alpha", 0.3)
        roi_win.configure(bg="black")
        canvas = tk.Canvas(roi_win, cursor="cross", bg="black", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        
        rect = None
        
        def on_mouse_down(event):
            nonlocal rect
            self.roi_data["x1"] = event.x
            self.roi_data["y1"] = event.y
            if rect: canvas.delete(rect)
            rect = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=2)
        
        def on_mouse_drag(event):
            nonlocal rect
            if rect: canvas.coords(rect, self.roi_data["x1"], self.roi_data["y1"], event.x, event.y)
        
        def on_mouse_up(event):
            self.roi_data["x2"] = event.x
            self.roi_data["y2"] = event.y
            roi_win.destroy()
            self.show_roi_preview()
        
        canvas.bind("<ButtonPress-1>", on_mouse_down)
        canvas.bind("<B1-Motion>", on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", on_mouse_up)
        
        roi_win.mainloop()

    def show_roi_preview(self):
        self.in_roi_preview = True
        x1, y1, x2, y2 = self.roi_data["x1"], self.roi_data["y1"], self.roi_data["x2"], self.roi_data["y2"]
        
        if x1 > x2: x1, x2 = x2, x1
        if y1 > y2: y1, y2 = y2, y1
        
        with mss.mss() as sct:
            monitor = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
            screenshot = sct.grab(monitor)
            roi_image = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
        
        self.current_roi_image = roi_image
        self.current_roi_coords = (x1, y1, x2, y2)
        
        for widget in self.root.winfo_children(): widget.destroy()
        
        img_width, img_height = roi_image.size
        scale = min(800 / img_width, 600 / img_height, 1.0)
        display_width = int(img_width * scale)
        display_height = int(img_height * scale)
        
        window_width = max(display_width + 40, 280)
        window_height = display_height + 140
        self.root.title("Screenshot Preview")
        self.center_window(window_width, window_height)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        photo = ImageTk.PhotoImage(roi_image.resize((display_width, display_height)))
        label = tk.Label(main_frame, image=photo, bg="white")
        label.image = photo
        label.pack(pady=10)
        
        # Add timeout input if it's the completion indicator
        timeout_var = tk.StringVar(value="10.0")
        if self.roi_type == "completion_indicator":
            t_frame = tk.Frame(main_frame, bg="white")
            t_frame.pack(pady=5)
            tk.Label(t_frame, text="Timeout (seconds):", bg="white").pack(side=tk.LEFT)
            tk.Entry(t_frame, textvariable=timeout_var, width=10).pack(side=tk.LEFT)

        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(pady=10)
        
        def on_ok():
            try:
                t_val = float(timeout_var.get())
                self.in_roi_preview = False
                self.save_roi(timeout=t_val)
                self.show_recording_menu()
            except ValueError:
                messagebox.showerror("Error", "Invalid Timeout Value")
        
        def on_retake():
            self.in_roi_preview = False
            self.start_roi_selection(self.roi_type)
        
        def on_cancel():
            self.in_roi_preview = False
            self.show_recording_menu()
        
        tk.Button(button_frame, text="OK", bg="white", command=on_ok).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Retake", bg="white", command=on_retake).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", bg="white", command=on_cancel).pack(side=tk.LEFT, padx=5)

    def save_roi(self, timeout=None):
        if self.roi_type == "completion_indicator":
            rgb_img = np.array(self.current_roi_image)
            bgr_img = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2BGR)
            prefix = "simulation_completion_indicator" # <--- Removed trailing underscore
            cmd = f"wait for simulation to finish with timeout {timeout}"

            # Delete old indicator files
            for f in os.listdir(self.project.folder_path):
                if f.startswith(prefix):
                    os.remove(os.path.join(self.project.folder_path, f))

            roi_path = os.path.join(self.project.folder_path, f"{prefix}.png") # <--- Simplified name
            cv2.imwrite(roi_path, bgr_img)
            
            self.project.metadata['completion_roi'] = self.current_roi_coords
            self.project.save()
            
            self._add_unique_command(cmd, prefix="wait for simulation to finish")

        elif self.roi_type == "main_roi":
            self.project.metadata['main_roi'] = self.current_roi_coords
            self.project.save()
            self._add_unique_command("capture the region of interest")

        elif self.roi_type == "additional_roi":
            self.project.metadata['additional_roi'] = self.current_roi_coords
            self.project.save()
            self._add_unique_command("capture additional region of interest")

    def add_param_ui(self):
        for widget in self.root.winfo_children(): widget.destroy()
        
        self.root.title("Add New Parameter")
        self.center_window(400, 300)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=20, padx=20)
        
        tk.Label(main_frame, text="Name:", bg="white").grid(row=0, column=0, sticky=tk.W, pady=5)
        name_ent = tk.Entry(main_frame, bg="white")
        name_ent.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=10)
        
        tk.Label(main_frame, text="Min:", bg="white").grid(row=1, column=0, sticky=tk.W, pady=5)
        min_ent = tk.Entry(main_frame, bg="white")
        min_ent.grid(row=1, column=1, sticky=tk.EW, pady=5, padx=10)
        
        tk.Label(main_frame, text="Max:", bg="white").grid(row=2, column=0, sticky=tk.W, pady=5)
        max_ent = tk.Entry(main_frame, bg="white")
        max_ent.grid(row=2, column=1, sticky=tk.EW, pady=5, padx=10)

        main_frame.columnconfigure(1, weight=1)

        def save():
            try:
                mn, mx = float(min_ent.get()), float(max_ent.get())
                if mn > mx: raise ValueError("Min > Max")
                param_name = name_ent.get().upper()
                
                if param_name in self.project.metadata['params']:
                    messagebox.showerror("Error", f"Parameter '{param_name}' already exists.")
                    return
                
                self.project.metadata['params'][param_name] = {"min": mn, "max": mx}
                self.project.save()
                self._add_unique_command(f"enter value for {param_name}")
                self.show_recording_menu()
            except ValueError:
                messagebox.showerror("Error", "Invalid float or Min > Max")
        
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.grid(row=3, column=0, columnspan=2, pady=20)
        tk.Button(button_frame, text="Save", command=save, bg="white").pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", command=self.show_recording_menu, bg="white").pack(side=tk.LEFT, padx=10)

    def edit_param_ui(self):
        for widget in self.root.winfo_children(): widget.destroy()
        
        self.root.title("Edit Parameters")
        self.center_window(700, 500)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        tk.Label(main_frame, text="Parameter settings", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W, pady=10)
        
        changes_made = {"changed": False}
        param_entries = {}
        
        table_frame = tk.Frame(main_frame, bg="white", relief=tk.SUNKEN, borderwidth=1)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=10)
        
        header_frame = tk.Frame(table_frame, bg="lightgrey")
        header_frame.pack(fill=tk.X)
        tk.Label(header_frame, text="Name", bg="lightgrey", width=20, anchor=tk.W, font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Label(header_frame, text="Min", bg="lightgrey", width=15, anchor=tk.W, font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Label(header_frame, text="Max", bg="lightgrey", width=15, anchor=tk.W, font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5, pady=5)
        
        canvas = tk.Canvas(table_frame, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="white")
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        for p_name, bounds in self.project.metadata['params'].items():
            row_frame = tk.Frame(scrollable_frame, bg="white", relief=tk.RIDGE, borderwidth=1)
            row_frame.pack(fill=tk.X, padx=2, pady=2)
            
            tk.Label(row_frame, text=p_name, bg="white", width=20, anchor=tk.W).pack(side=tk.LEFT, padx=5, pady=5)
            min_var = tk.StringVar(value=str(bounds['min']))
            min_entry = tk.Entry(row_frame, textvariable=min_var, width=15, bg="white")
            min_entry.pack(side=tk.LEFT, padx=5, pady=5)
            
            max_var = tk.StringVar(value=str(bounds['max']))
            max_entry = tk.Entry(row_frame, textvariable=max_var, width=15, bg="white")
            max_entry.pack(side=tk.LEFT, padx=5, pady=5)
            
            def delete_param_callback(param_name=p_name):
                if messagebox.askyesno("Confirm Delete", f"Delete parameter '{param_name}'?"):
                    self.delete_param(param_name)
            
            tk.Button(row_frame, text="Delete", fg="red", bg="white", command=delete_param_callback).pack(side=tk.LEFT, padx=5, pady=5)
            
            def on_change(*args):
                changes_made["changed"] = True
                update_save_button()
            
            min_var.trace('w', on_change)
            max_var.trace('w', on_change)
            param_entries[p_name] = {"min": min_var, "max": max_var}
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        
        save_button = tk.Button(button_frame, text="Save", bg="lightgrey", fg="grey", state=tk.DISABLED)
        save_button.pack(side=tk.RIGHT, padx=5)
        
        def update_save_button():
            if changes_made["changed"]: save_button.config(state=tk.NORMAL, bg="lightgreen", fg="black")
            else: save_button.config(state=tk.DISABLED, bg="lightgrey", fg="grey")
        
        def on_save_clicked():
            try:
                for p_name, entries in param_entries.items():
                    min_val = float(entries["min"].get())
                    max_val = float(entries["max"].get())
                    if min_val >= max_val:
                        messagebox.showerror("Validation Error", f"Parameter '{p_name}': Min value must be less than Max value")
                        return
                
                for p_name, entries in param_entries.items():
                    self.project.metadata['params'][p_name] = {"min": float(entries["min"].get()), "max": float(entries["max"].get())}
                
                self.project.save()
                messagebox.showinfo("Success", "Parameter changes saved successfully")
                changes_made["changed"] = False
                update_save_button()
                self.edit_param_ui()
            except ValueError:
                messagebox.showerror("Validation Error", "Min and Max values must be valid numbers")
        
        save_button.config(command=on_save_clicked)
        tk.Button(button_frame, text="Back", bg="white", command=self.show_recording_menu).pack(side=tk.LEFT, padx=5)

    def delete_param(self, param_name):
        if param_name in self.project.metadata['params']:
            del self.project.metadata['params'][param_name]
            self.project.save()
            
            cmd_file = os.path.join(self.project.folder_path, "commands.txt")
            if os.path.exists(cmd_file):
                with open(cmd_file, "r") as f: lines = f.readlines()
                filtered_lines = [line for line in lines if not line.strip().startswith(f"enter value for {param_name}")]
                with open(cmd_file, "w") as f: f.writelines(filtered_lines)
            self.edit_param_ui()

    def sa_setup_ui(self):
        for widget in self.root.winfo_children(): widget.destroy()
        
        self.root.title("SA Setup")
        self.center_window(500, 550)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=20, padx=20)
        
        tk.Label(main_frame, text="SA Type:", font=("Arial", 10, "bold"), bg="white").pack(pady=10)
        type_var = tk.StringVar(value=self.project.metadata.get('sa_type', ''))
        
        sa_types = ['Sobol (SALib)', 'Gradient-Based']
        cb = ttk.Combobox(main_frame, textvariable=type_var, values=sa_types, state='readonly')
        cb.pack(pady=10, fill=tk.X)
        
        param_frame = tk.Frame(main_frame, bg="white")
        param_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        def on_select(event):
            for w in param_frame.winfo_children(): w.destroy()
            sa_type = type_var.get()
            
            if sa_type == 'Sobol (SALib)':
                powers_of_2 = [2**i for i in range(4, 13)]
                tk.Label(param_frame, text="N (must be power of 2):", bg="white").pack()
                current_n = self.project.metadata.get('sa_params', {}).get('n', 128)
                if current_n not in powers_of_2: current_n = 128
                n_var = tk.StringVar(value=str(current_n))
                n_dropdown = ttk.Combobox(param_frame, textvariable=n_var, values=[str(p) for p in powers_of_2], state='readonly')
                n_dropdown.pack()
                param_frame.sobol_n = n_var
            elif sa_type == 'Gradient-Based':
                tk.Label(param_frame, text="Parameter settings", bg="white", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=10)
                table_frame = tk.Frame(param_frame, bg="white")
                table_frame.pack(fill=tk.X, padx=10)
                
                header_frame = tk.Frame(table_frame, bg="lightgrey")
                header_frame.pack(fill=tk.X)
                tk.Label(header_frame, text="Name", bg="lightgrey", width=15, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                tk.Label(header_frame, text="Interval", bg="lightgrey", width=15, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                tk.Label(header_frame, text="Point", bg="lightgrey", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                tk.Label(header_frame, text="Step", bg="lightgrey", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                
                param_entries = {}
                saved_grad_params = self.project.metadata.get('sa_params', {}) if self.project.metadata.get('sa_type') == 'Gradient-Based' else {}
                for param_name, bounds in self.project.metadata['params'].items():
                    row_frame = tk.Frame(table_frame, bg="white")
                    row_frame.pack(fill=tk.X)
                    
                    tk.Label(row_frame, text=param_name, bg="white", width=15, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                    tk.Label(row_frame, text=f"[{bounds['min']}, {bounds['max']}]", bg="white", width=15, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                    
                    default_point = saved_grad_params.get(param_name, {}).get('point', (bounds['min'] + bounds['max']) / 2)
                    point_var = tk.StringVar(value=str(default_point))
                    tk.Entry(row_frame, textvariable=point_var, width=12, bg="white").pack(side=tk.LEFT, padx=2, pady=2)
                    
                    default_step = saved_grad_params.get(param_name, {}).get('step', 0.01)
                    step_var = tk.StringVar(value=str(default_step))
                    tk.Entry(row_frame, textvariable=step_var, width=12, bg="white").pack(side=tk.LEFT, padx=2, pady=2)
                    
                    param_entries[param_name] = {"point": point_var, "step": step_var}
                
                param_frame.gradient_params = param_entries
        
        cb.bind("<<ComboboxSelected>>", on_select)
        if type_var.get(): on_select(None)
        
        info_frame = tk.Frame(main_frame, bg="white")
        info_frame.pack(fill=tk.X, pady=10)
        tk.Label(info_frame, text=f"Number of simulation runs required: {self.project.metadata.get('n_required', '-')}", bg="white").pack()
        
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(side=tk.BOTTOM, pady=10)
        
        def generate_samples(): self.generate_samples(type_var.get(), param_frame)
        tk.Button(button_frame, text="Generate sample", bg="white", command=generate_samples).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Back", bg="white", command=self.show_recording_menu).pack(side=tk.LEFT, padx=5)

    def generate_samples(self, sa_type, frame):
        try:
            if not sa_type:
                messagebox.showerror("Error", "Please select an SA type")
                return
            if len(self.project.metadata['params']) == 0:
                messagebox.showerror("Error", "Please add parameters first")
                return
            
            problem = {
                'num_vars': len(self.project.metadata['params']),
                'names': list(self.project.metadata['params'].keys()),
                'bounds': [[v['min'], v['max']] for v in self.project.metadata['params'].values()]
            }
            
            if sa_type == 'Sobol (SALib)':
                if sobol_sample is None:
                    messagebox.showerror("Error", "SALib not installed. Install with: pip install SALib")
                    return
                n = 128
                if hasattr(frame, 'sobol_n'):
                    try:
                        n_val = int(frame.sobol_n.get())
                        if n_val in [2**i for i in range(4, 13)]: n = n_val
                    except: pass
                samples = sobol_sample(problem, n)
                self.project.metadata['sa_params'] = {'n': n}
            elif sa_type == 'Gradient-Based':
                if hasattr(frame, 'gradient_params'):
                    gradient_params = {}
                    for param_name, entries in frame.gradient_params.items():
                        point, step = float(entries['point'].get()), float(entries['step'].get())
                        if step <= 0:
                            messagebox.showerror("Error", f"Step size for {param_name} must be > 0")
                            return
                        gradient_params[param_name] = {"point": point, "step": step}
                    samples = self.generate_gradient_samples(problem, gradient_params)
                    self.project.metadata['sa_params'] = gradient_params
                else:
                    messagebox.showerror("Error", "Gradient parameters not found")
                    return
            
            self.project.samples = samples.tolist() if hasattr(samples, 'tolist') else samples
            self.project.metadata['n_required'] = len(self.project.samples)
            self.project.metadata['sa_type'] = sa_type
            self.project.save()
            
            messagebox.showinfo("Success", f"Generated {len(self.project.samples)} sample points for {sa_type}")
            self.sa_setup_ui()
        except Exception as e:
            messagebox.showerror("Error", f"Error generating samples: {str(e)}")

    def generate_gradient_samples(self, problem, gradient_params):
        n_vars = problem['num_vars']
        samples = []
        param_names = problem['names']
        bounds = problem['bounds']
        
        for i, name in enumerate(param_names):
            gp = gradient_params.get(name, {})
            step = abs(gp.get('step', 0.0))
            if step <= 0: step = (bounds[i][1] - bounds[i][0]) * 0.1
            
            central = []
            for j, pname in enumerate(param_names):
                if j == i: central.append(gp.get('point', (bounds[j][0] + bounds[j][1]) / 2))
                else: central.append(gradient_params.get(pname, {}).get('point', (bounds[j][0] + bounds[j][1]) / 2))
            
            sample_neg = central.copy()
            sample_neg[i] = max(bounds[i][0], min(bounds[i][1], sample_neg[i] - step))
            samples.append(sample_neg)
            
            sample_pos = central.copy()
            sample_pos[i] = max(bounds[i][0], min(bounds[i][1], sample_pos[i] + step))
            samples.append(sample_pos)
        
        return np.array(samples)

    def cleanup_partial_roi_files(self):
        roi_dir = os.path.join(self.project.folder_path, "ROIs")
        if os.path.exists(roi_dir):
            for f in os.listdir(roi_dir):
                if f.startswith(f"roi_main_{self.current_sample_index}.png"):
                    try: os.remove(os.path.join(roi_dir, f))
                    except OSError: pass
        
        add_roi_dir = os.path.join(self.project.folder_path, "Additional ROIs")
        if os.path.exists(add_roi_dir):
            for f in os.listdir(add_roi_dir):
                if f.startswith(f"roi_additional_{self.current_sample_index}.png"):
                    try: os.remove(os.path.join(add_roi_dir, f))
                    except OSError: pass

    def start_running(self):
        if 'main_roi' not in self.project.metadata:
            messagebox.showerror("Error", "Please capture the region of interest first")
            return
        
        cmd_file = os.path.join(self.project.folder_path, "commands.txt")
        has_completion = False
        if os.path.exists(cmd_file):
            with open(cmd_file, "r") as f:
                has_completion = any("wait for simulation to finish" in line for line in f)
        
        if not has_completion:
            messagebox.showerror("Error", "Please set the simulation completion indicator first")
            return
        
        if not self.project.metadata.get('sa_type'):
            messagebox.showerror("Error", "Please select an SA type and generate samples")
            return
        
        sa_type = self.project.metadata['sa_type']
        num_params = len(self.project.metadata['params'])
        if sa_type == 'Gradient-Based' and num_params < 1:
            messagebox.showerror("Error", "Gradient-Based SA requires at least 1 parameter")
            return
        elif sa_type == 'Sobol (SALib)' and num_params < 2:
            messagebox.showerror("Error", "Sobol SA requires at least 2 parameters")
            return
        
        self.project.metadata['status'] = "in_progress"
        self.project.results = [np.nan] * len(self.project.samples)
        self.project.save()

        self.root.iconify()
        self.replay_paused = False
        self.replay_stop_requested = False
        self._replay_thread = threading.Thread(target=self.start_replay, daemon=True)
        self._replay_thread.start()

    def _show_timeout_error(self, err_msg):
        messagebox.showerror("Timeout Error", f"Simulation discarded due to timeout: {err_msg}")
        self.pause_replay()

    def start_replay(self):
        try:
            cmd_file = os.path.join(self.project.folder_path, "commands.txt")
            replayer = TextReplayer()
            template_path = None

            for f in os.listdir(self.project.folder_path):
                if f.startswith("simulation_completion_indicator_") or f.startswith("roi_completion_"):
                    template_path = os.path.join(self.project.folder_path, f)
                    break

            param_names = list(self.project.metadata['params'].keys())
            
            i = 0
            while i < len(self.project.samples):
                if self.replay_stop_requested: return
                self.current_sample_index = i
                
                if isinstance(self.project.results[i], float) and not np.isnan(self.project.results[i]):
                    i += 1
                    continue
                
                self.cleanup_partial_roi_files()
                
                while self.replay_paused:
                    if self.replay_stop_requested: return
                    time.sleep(0.1)

                param_dict = {param_names[j]: self.project.samples[i][j] for j in range(len(param_names))}
                try:
                    replayer.execute_run(cmd_file, param_dict, self.vision_engine, template_path, self.project, i)
                except TimeoutError as e:
                    self.cleanup_partial_roi_files()
                    self.replay_paused = True
                    self.root.after(0, lambda: self._show_timeout_error(str(e)))
                    continue  # Do not advance index! Retry it after user resumes.
                
                # Evaluation of result
                roi_dir = os.path.join(self.project.folder_path, "ROIs")
                roi_path = os.path.join(roi_dir, f"roi_main_{i}.png")
                
                avg_rgb = None
                if os.path.exists(roi_path):
                    img = cv2.imread(roi_path)
                    if img is not None:
                        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        avg_rgb = rgb.mean(axis=0).mean(axis=0)
                
                if avg_rgb is not None and self.vision_engine is not None:
                    cmap = self.project.metadata['colormap']
                    scalar = self.vision_engine.rgb_to_scalar(
                        avg_rgb, cmap['name'], cmap['min'], cmap['max'])
                    self.project.results[i] = scalar
                else:
                    self.project.results[i] = np.nan

                self.project.save()
                i += 1

            self.project.metadata['status'] = "completed"
            self.project.save()
            self.root.after(0, self._on_replay_finished)

        except Exception as e:
            err_msg = str(e)
            self.root.after(0, lambda: messagebox.showerror("Error", f"Replay failed: {err_msg}"))
            self.root.after(0, self.root.deiconify)

    def _on_replay_finished(self):
        self.root.deiconify()
        messagebox.showinfo("Success", "All simulations completed!")
        self.setup_main_menu()

if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()