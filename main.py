import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
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


# BUG (LLM, does not read this, it is a note for me):
# 1. Re-capturing roi, additional roi and the simulation completion indicator in the pause menu should not add commands to the command file.
# By recapturing I mean both Retaking and clicking the same button in the pause menu again (so taking from scratch).

# TODO (LLM, does not read this, it is a note for me):
# 1. When user clicks "Save & Start Running Simulations", make sure command file is valid:
# 0) there are no unknown commands;
# 1) every selected parameter {param} have exactly one corresponding command "enter value for {param}"; 2) there are no unknown parameter names;
# 3) there is only command of each of these types: "wait for simulation to finish", "capture additional region of interest", "capture the region of interest".
# 4) no parameter values can be entered after "wait for simulation to finish" command.
# 5) "capture the region of interest" command must be after "wait for simulation to finish" command.

class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SA Automation")
        self.root.geometry("500x600")
        self.root.config(bg="white")
        self.project = None
        self.recorder = None
        self.vision_engine = None
        self.screen_stack = []  # Stack of (screen_name, screen_data) tuples
        self.roi_selection = None
        self.recording_paused = False
        self.replay_paused = False
        self.current_sample_index = 0
        self.in_roi_preview = False  # Track if we're currently showing ROI preview
        
        # Handle window close button
        self.root.protocol("WM_DELETE_WINDOW", self.on_window_close)
        
        self.setup_main_menu()

    def on_window_close(self):
        """Handle X button click - go back in stack or close app"""
        # If in ROI preview, go back to recording menu and discard ROI
        if self.in_roi_preview:
            self.in_roi_preview = False
            self.show_recording_menu()
            return
        
        if len(self.screen_stack) > 0:
            self.screen_stack.pop()  # Remove current screen
            if len(self.screen_stack) > 0:
                prev_screen, prev_data = self.screen_stack[-1]
                self.show_screen(prev_screen, prev_data)
            else:
                self.root.destroy()
        else:
            self.root.destroy()

    def push_screen(self, screen_name, screen_data=None):
        """Push a new screen onto the stack"""
        self.screen_stack.append((screen_name, screen_data))

    def show_screen(self, screen_name, screen_data=None):
        """Show a screen"""
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
        self.root.geometry("500x600")
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(main_frame, text="Sensitivity Analysis Automation", font=("Arial", 14), bg="white").pack(pady=20)
        tk.Button(main_frame, text="Start new SA", command=self.start_new_sa, width=20, bg="white").pack(pady=10)
        tk.Button(main_frame, text="Open existing SA", command=self.open_existing_sa, width=20, bg="white").pack()
        self.screen_stack = [("main_menu", None)]  # Reset stack to main menu

    # --- OPEN EXISTING FLOW ---
    def open_existing_sa(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        
        self.project = Project(folder)
        if not self.project.load():
            messagebox.showerror("Error", "Invalid Project Folder structure.")
            return
        
        err = self.project.validate()
        if err:
            messagebox.showerror("Invalid Project", err)
            return
        
        self.push_screen("project_dashboard")
        self.show_project_dashboard()

    def show_project_dashboard(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.root.title(f"Project: {self.project.metadata['name']}")
        self.root.geometry("760x860")
        self.root.config(bg="white")
        
        # Request 11: Track changes for Save button
        changes_made = {"changed": False}
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        status_colors = {
            "setup": "grey",
            "in_progress": "orange",
            "completed": "green"
        }
        
        # Status Line with Continue button
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
        
        # Parameters table
        table_frame = tk.Frame(main_frame, bg="white", relief=tk.RIDGE, borderwidth=1)
        table_frame.pack(fill=tk.X, pady=10)
        tk.Label(table_frame, text="Parameter settings", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W, padx=5, pady=5)
        
        param_table = tk.Frame(table_frame, bg="white")
        param_table.pack(fill=tk.X, padx=5, pady=5)
        
        sa_type = self.project.metadata.get('sa_type', '')
        headers = ["Name", "Range"]
        if sa_type == 'Gradient-Based':
            headers += ["Point", "Step"]
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
        
        # Simulation Completion Indicator
        completion_frame = tk.Frame(main_frame, bg="white")
        completion_frame.pack(fill=tk.X, pady=10)
        comp_button = tk.Button(completion_frame,
                                text="View Simulation Completion Indicator",
                                bg="white",
                                state=tk.NORMAL,
                                command=self.view_completion_template)
        comp_button.pack(fill=tk.X, padx=10, pady=10)
        
        # Additional ROI Toggle + View last
        roi_frame = tk.Frame(main_frame, bg="white")
        roi_frame.pack(fill=tk.X, pady=10)
        tk.Label(roi_frame, text=f"Additional ROI status: {self.project.metadata['additional_roi_status']}", bg="white").pack(side=tk.LEFT)
        btn_text = "Stop capturing" if self.project.metadata['additional_roi_status'] == "capturing" else "Resume capturing"
        tk.Button(roi_frame, text=btn_text, bg="white", command=self.toggle_add_roi).pack(side=tk.LEFT, padx=10)
        tk.Button(roi_frame, text="View last additional ROI", bg="white", command=self.view_last_additional_roi).pack(side=tk.RIGHT)
        
        # Colormap Status
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

        # View Results Button
        if self.project.metadata['status'] == "completed":
            tk.Button(main_frame, text="View SA results", bg="lightgreen", command=self.generate_report).pack(pady=20)
        
        # Request 11: Save and Back buttons at bottom
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        
        save_button = tk.Button(button_frame, text="Save", bg="lightgrey", fg="grey", state=tk.DISABLED, 
                               command=lambda: on_save_clicked())
        save_button.pack(side=tk.RIGHT, padx=5)
        
        def update_save_button():
            if changes_made["changed"]:
                save_button.config(state=tk.NORMAL, bg="lightgreen", fg="black")
            else:
                save_button.config(state=tk.DISABLED, bg="lightgrey", fg="grey")
        
        def on_save_clicked():
            try:
                cmap_min = float(min_var.get())
                cmap_max = float(max_var.get())
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
                    if len(self.screen_stack) > 0:
                        self.screen_stack.pop()
                    self.setup_main_menu()
            else:
                if len(self.screen_stack) > 0:
                    self.screen_stack.pop()
                self.setup_main_menu()
        
        tk.Button(button_frame, text="Back", bg="white", command=on_back_clicked).pack(side=tk.LEFT, padx=5)

    def toggle_add_roi(self):
        is_capturing = self.project.metadata['additional_roi_status'] == "capturing"
        if not is_capturing:
            # Check if additional ROI has been selected
            roi_files = self.find_files_with_prefix("roi_additional_")
            if not roi_files:
                messagebox.showerror("Error", "No additional ROI selected yet")
                return
        self.project.toggle_additional_roi_command(not is_capturing)
        self.show_project_dashboard()

    def resume_sims(self):
        if messagebox.askokcancel("Confirm", "Resume simulation running?"):
            self.start_replay()

    def view_completion_template(self):
        template_files = self.find_files_with_prefix("simulation_completion_indicator_")
        if len(template_files) == 0:
            messagebox.showinfo("Info", "No simulation completion indicator found")
            return
        if len(template_files) > 1:
            messagebox.showerror("Error", "Multiple completion indicator files found.")
            return
        template_path = os.path.join(self.project.folder_path, template_files[0])
        os.startfile(template_path)

    def find_files_with_prefix(self, prefix):
        if prefix.startswith("roi_additional_"):
            folder = os.path.join(self.project.folder_path, "Additional ROIs")
        elif prefix.startswith("roi_main_"):
            folder = os.path.join(self.project.folder_path, "ROIs")
        elif prefix in ("simulation_completion_indicator_", "roi_completion_"):
            folder = self.project.folder_path
        else:
            folder = os.path.join(self.project.folder_path, "ROIs")
        
        if not os.path.exists(folder):
            return []
        return [f for f in os.listdir(folder) if f.startswith(prefix)]

    def view_last_additional_roi(self):
        roi_files = self.find_files_with_prefix("roi_additional_")
        if not roi_files:
            messagebox.showinfo("Info", "No additional ROI captured yet")
            return
        full_paths = [os.path.join(self.project.folder_path, "Additional ROIs", f) for f in roi_files]
        latest = max(full_paths, key=os.path.getmtime)
        os.startfile(latest)

    def capture_completion_indicator(self):
        self.start_roi_selection("completion_indicator")

    def identify_colormap_from_data(self):
        if len(self.project.results) == 0:
            messagebox.showerror("Error", "No simulation data available yet")
            return
        messagebox.showinfo("Info", "Colormap identification from data not yet implemented")

    def generate_report(self):
        """Generate PDF report with SA results."""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib import colors
            
            report_path = os.path.join(self.project.folder_path, "SA_Results.pdf")
            doc = SimpleDocTemplate(report_path, pagesize=letter)
            story = []
            styles = getSampleStyleSheet()
            
            # Title
            title = Paragraph("Sensitivity Analysis Results", styles['Title'])
            story.append(title)
            story.append(Spacer(1, 12))
            
            # Project Info
            info_data = [
                ["Project Name", self.project.metadata['name']],
                ["Status", self.project.metadata['status']],
                ["SA Type", self.project.metadata.get('sa_type', 'N/A')],
            ]
            info_table = Table(info_data)
            info_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.beige),
                                            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                                            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                                            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                                            ('FONTSIZE', (0, 0), (-1, -1), 10),]))
            story.append(info_table)
            story.append(Spacer(1, 12))
            
            # Parameters
            param_data = [["Parameter", "Min", "Max"]]
            for pname, pbounds in self.project.metadata['params'].items():
                param_data.append([pname, str(pbounds['min']), str(pbounds['max'])])
            param_table = Table(param_data)
            param_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                                             ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                             ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                                             ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                             ('FONTSIZE', (0, 0), (-1, -1), 9),
                                             ('GRID', (0, 0), (-1, -1), 1, colors.black)]))
            story.append(param_table)
            
            doc.build(story)
            messagebox.showinfo("Success", f"Report generated: {report_path}")
            os.startfile(report_path)
        except ImportError:
            messagebox.showerror("Error", "reportlab not installed. Install with: pip install reportlab")

    def start_new_sa(self):
        folder = filedialog.askdirectory(title="Select Empty Folder for New Project")
        if not folder:
            return
        
        # Check if folder is empty or has project files
        project_files = ["metadata.json", "commands.txt", "samples.npy", "results.npy"]
        roi_files = [f for f in os.listdir(folder) if f.startswith("roi_")]
        if os.listdir(folder) and (any(os.path.exists(os.path.join(folder, f)) for f in project_files) or roi_files):
            messagebox.showerror("Error", "Selected folder is not empty. Please select an empty folder.")
            return
        
        # Transform main window into project name input (request 1)
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.root.title("New Project")
        self.root.geometry("400x200")
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
        """Initialize project and start recording"""
        self.project = Project(folder)
        self.project.metadata['name'] = project_name
        self.project.save()
        
        cmd_file = os.path.join(folder, "commands.txt")
        self.recorder = TextRecorder(cmd_file, self.show_recording_menu_from_pause)
        self.vision_engine = VisionEngine(folder)
        
        self.root.iconify()
        messagebox.showinfo("Recording Started", "Recording mouse and keyboard. Press Esc to pause and open the control menu.")
        self.recorder.start()

    def show_recording_menu_from_pause(self):
        """Called when recording is paused - bring window to front"""
        self.recording_paused = True
        self.root.deiconify()
        # Request 3: Try multiple methods to bring window to front
        try:
            self.root.attributes("-topmost", True)
            self.root.attributes("-topmost", False)
        except:
            pass
        self.root.lift()
        self.root.focus_force()
        if not self.screen_stack or self.screen_stack[-1][0] != "recording_menu":
            self.push_screen("recording_menu")
        self.show_recording_menu()

    def show_recording_menu(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # Request 2: Project name in title bar format
        self.root.title(f"Recording Menu (Paused) | {self.project.metadata['name']}")
        self.root.geometry("500x700")
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        # Menu Buttons
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
        """Pause replay and show pause menu."""
        self.replay_paused = True
        self.show_replay_pause_menu()

    def show_replay_pause_menu(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.root.title(f"Replay Paused | {self.project.metadata['name']}")
        self.root.geometry("500x400")
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
        """Resume replay."""
        self.replay_paused = False
        self.setup_main_menu()

    def stop_replay(self):
        """Stop replay and return to main menu."""
        self.replay_paused = False
        self.setup_main_menu()

    def view_cmd_file(self):
        cmd_file = os.path.join(self.project.folder_path, "commands.txt")
        os.startfile(cmd_file)

    def start_roi_selection(self, roi_type):
        """Start ROI selection with fullscreen overlay (improved from example)"""
        self.roi_type = roi_type
        self.roi_data = {"x1": 0, "y1": 0, "x2": 0, "y2": 0}
        
        # Create fullscreen overlay for ROI selection
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
            if rect:
                canvas.delete(rect)
            rect = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=2)
        
        def on_mouse_drag(event):
            nonlocal rect
            if rect:
                canvas.coords(rect, self.roi_data["x1"], self.roi_data["y1"], event.x, event.y)
        
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
        """Show preview of selected ROI for confirmation - transform main window (request 4,5)"""
        self.in_roi_preview = True  # Set flag to handle X button properly
        x1, y1, x2, y2 = self.roi_data["x1"], self.roi_data["y1"], self.roi_data["x2"], self.roi_data["y2"]
        
        # Normalize coordinates
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1
        
        # Capture ROI using mss
        with mss.mss() as sct:
            monitor = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
            screenshot = sct.grab(monitor)
            roi_image = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
        
        # Store for later use and saving
        self.current_roi_image = roi_image
        self.current_roi_coords = (x1, y1, x2, y2)
        
        # Request 4 & 5: Transform main window for preview instead of creating new window
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # Request 5: Adapt window size to image (natural size, no distortion)
        img_width, img_height = roi_image.size
        # Scale if too large, maintain aspect ratio
        max_width, max_height = 800, 600
        scale = min(max_width / img_width, max_height / img_height, 1.0)
        display_width = int(img_width * scale)
        display_height = int(img_height * scale)
        
        min_window_width = 280
        window_width = max(display_width + 40, min_window_width)
        window_height = display_height + 100
        self.root.title("Screenshot Preview")
        self.root.geometry(f"{window_width}x{window_height}")
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        photo = ImageTk.PhotoImage(roi_image.resize((display_width, display_height)))
        label = tk.Label(main_frame, image=photo, bg="white")
        label.image = photo
        label.pack(pady=10)
        
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(pady=10)
        
        def on_ok():
            self.in_roi_preview = False  # Clear flag before going back
            self.save_roi()
            self.show_recording_menu()
        
        def on_retake():
            self.in_roi_preview = False  # Clear flag before retaking
            self.start_roi_selection(self.roi_type)
        
        def on_cancel():
            self.in_roi_preview = False  # Clear flag before canceling
            self.show_recording_menu()
        
        tk.Button(button_frame, text="OK", bg="white", command=on_ok).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Retake", bg="white", command=on_retake).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", bg="white", command=on_cancel).pack(side=tk.LEFT, padx=5)

    def save_roi(self):
        """Save ROI using the stored image from preview."""
        x1, y1, x2, y2 = self.current_roi_coords
        
        # Convert PIL to numpy array for cv2
        rgb_img = np.array(self.current_roi_image)
        bgr_img = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2BGR)
        
        if self.roi_type == "completion_indicator":
            subfolder = None
            prefix = "simulation_completion_indicator_"
            command = "wait for simulation to finish"
        elif self.roi_type == "main_roi":
            subfolder = "ROIs"
            prefix = "roi_main_"
            command = "capture the region of interest"
        elif self.roi_type == "additional_roi":
            subfolder = "Additional ROIs"
            prefix = "roi_additional_"
            command = "capture additional region of interest"
        
        if subfolder:
            roi_dir = os.path.join(self.project.folder_path, subfolder)
            os.makedirs(roi_dir, exist_ok=True)
        else:
            roi_dir = self.project.folder_path
        
        # Delete old files with the same prefix in the target folder
        for f in os.listdir(roi_dir):
            if f.startswith(prefix):
                os.remove(os.path.join(roi_dir, f))
        
        roi_path = os.path.join(roi_dir, f"{prefix}{x1}_{y1}_{x2}_{y2}.png")
        cv2.imwrite(roi_path, bgr_img)
        self.recorder.append_command(command)

    def add_param_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.root.title("Add New Parameter")
        self.root.geometry("400x300")
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
                if mn > mx:
                    raise ValueError("Min > Max")
                param_name = name_ent.get().upper()
                
                # Check for duplicate parameter names
                if param_name in self.project.metadata['params']:
                    messagebox.showerror("Error", f"Parameter '{param_name}' already exists. Please choose a different name.")
                    return
                
                self.project.metadata['params'][param_name] = {"min": mn, "max": mx}
                self.project.save()
                self.recorder.append_command(f"enter value for {param_name}")
                self.show_recording_menu()
            except ValueError as e:
                messagebox.showerror("Error", "Invalid float or Min > Max")
        
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.grid(row=3, column=0, columnspan=2, pady=20)
        tk.Button(button_frame, text="Save", command=save, bg="white").pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", command=self.show_recording_menu, bg="white").pack(side=tk.LEFT, padx=10)

    def edit_param_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.root.title("Edit Parameters")
        self.root.geometry("700x500")
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        # Title
        tk.Label(main_frame, text="Parameter settings", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W, pady=10)
        
        # Track changes
        changes_made = {"changed": False}
        param_entries = {}  # Store references to entry widgets: {param_name: {"min": entry, "max": entry, "original_min": float, "original_max": float}}
        
        # Table frame
        table_frame = tk.Frame(main_frame, bg="white", relief=tk.SUNKEN, borderwidth=1)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=10)
        
        # Header row
        header_frame = tk.Frame(table_frame, bg="lightgrey")
        header_frame.pack(fill=tk.X)
        tk.Label(header_frame, text="Name", bg="lightgrey", width=20, anchor=tk.W, font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Label(header_frame, text="Min", bg="lightgrey", width=15, anchor=tk.W, font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Label(header_frame, text="Max", bg="lightgrey", width=15, anchor=tk.W, font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Scrollable content frame
        canvas = tk.Canvas(table_frame, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="white")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Data rows
        for p_name, bounds in self.project.metadata['params'].items():
            row_frame = tk.Frame(scrollable_frame, bg="white", relief=tk.RIDGE, borderwidth=1)
            row_frame.pack(fill=tk.X, padx=2, pady=2)
            
            # Parameter name (read-only)
            tk.Label(row_frame, text=p_name, bg="white", width=20, anchor=tk.W).pack(side=tk.LEFT, padx=5, pady=5)
            
            # Min entry (editable)
            min_var = tk.StringVar(value=str(bounds['min']))
            min_entry = tk.Entry(row_frame, textvariable=min_var, width=15, bg="white")
            min_entry.pack(side=tk.LEFT, padx=5, pady=5)
            
            # Max entry (editable)
            max_var = tk.StringVar(value=str(bounds['max']))
            max_entry = tk.Entry(row_frame, textvariable=max_var, width=15, bg="white")
            max_entry.pack(side=tk.LEFT, padx=5, pady=5)
            
            # Delete button
            def delete_param_callback(param_name=p_name):
                if messagebox.askyesno("Confirm Delete", f"Delete parameter '{param_name}'?"):
                    self.delete_param(param_name)
            
            tk.Button(row_frame, text="Delete", fg="red", bg="white", command=delete_param_callback).pack(side=tk.LEFT, padx=5, pady=5)
            
            # Track changes for this parameter
            def on_min_change(*args, pname=p_name):
                changes_made["changed"] = True
                update_save_button()
            
            def on_max_change(*args, pname=p_name):
                changes_made["changed"] = True
                update_save_button()
            
            min_var.trace('w', on_min_change)
            max_var.trace('w', on_max_change)
            
            # Store entry references
            param_entries[p_name] = {
                "min": min_var,
                "max": max_var,
                "original_min": bounds['min'],
                "original_max": bounds['max']
            }
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Button frame at bottom
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        
        # Save button
        save_button = tk.Button(button_frame, text="Save", bg="lightgrey", fg="grey", state=tk.DISABLED)
        save_button.pack(side=tk.RIGHT, padx=5)
        
        def update_save_button():
            if changes_made["changed"]:
                save_button.config(state=tk.NORMAL, bg="lightgreen", fg="black")
            else:
                save_button.config(state=tk.DISABLED, bg="lightgrey", fg="grey")
        
        def on_save_clicked():
            # Validate all parameters
            try:
                for p_name, entries in param_entries.items():
                    min_val = float(entries["min"].get())
                    max_val = float(entries["max"].get())
                    
                    if min_val >= max_val:
                        messagebox.showerror("Validation Error", f"Parameter '{p_name}': Min value must be less than Max value")
                        return
                
                # Save changes
                for p_name, entries in param_entries.items():
                    min_val = float(entries["min"].get())
                    max_val = float(entries["max"].get())
                    self.project.metadata['params'][p_name] = {"min": min_val, "max": max_val}
                
                self.project.save()
                messagebox.showinfo("Success", "Parameter changes saved successfully")
                changes_made["changed"] = False
                update_save_button()
                # Refresh UI to show updated values
                self.edit_param_ui()
            except ValueError:
                messagebox.showerror("Validation Error", "Min and Max values must be valid numbers")
        
        save_button.config(command=on_save_clicked)
        
        # Back button
        tk.Button(button_frame, text="Back", bg="white", command=self.show_recording_menu).pack(side=tk.LEFT, padx=5)

    def delete_param(self, param_name):
        if param_name in self.project.metadata['params']:
            del self.project.metadata['params'][param_name]
            self.project.save()
            
            # Remove corresponding "enter value for X" command from command file
            cmd_file = os.path.join(self.project.folder_path, "commands.txt")
            if os.path.exists(cmd_file):
                with open(cmd_file, "r") as f:
                    lines = f.readlines()
                
                # Filter out the "enter value for param_name" line
                filtered_lines = [line for line in lines if not line.strip().startswith(f"enter value for {param_name}")]
                
                # Write back the filtered lines
                with open(cmd_file, "w") as f:
                    f.writelines(filtered_lines)
            
            self.edit_param_ui()

    def sa_setup_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.root.title("SA Setup")
        self.root.geometry("500x550")
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=20, padx=20)
        
        tk.Label(main_frame, text="SA Type:", font=("Arial", 10, "bold"), bg="white").pack(pady=10)
        type_var = tk.StringVar(value=self.project.metadata.get('sa_type', ''))
        
        sa_types = [
            'Sobol (SALib)',
            'Gradient-Based'
        ]
        
        cb = ttk.Combobox(main_frame, textvariable=type_var, values=sa_types, state='readonly')
        cb.pack(pady=10, fill=tk.X)
        
        param_frame = tk.Frame(main_frame, bg="white")
        param_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Dynamic UI Update
        def on_select(event):
            for w in param_frame.winfo_children():
                w.destroy()
            
            sa_type = type_var.get()
            
            if sa_type == 'Sobol (SALib)':
                # Powers of 2 from 2^4 to 2^12 (16 to 4096)
                powers_of_2 = [2**i for i in range(4, 13)]
                tk.Label(param_frame, text="N (must be power of 2):", bg="white").pack()
                current_n = self.project.metadata.get('sa_params', {}).get('n', 128)
                if current_n not in powers_of_2:
                    current_n = 128
                n_var = tk.StringVar(value=str(current_n))
                n_dropdown = ttk.Combobox(param_frame, textvariable=n_var, values=[str(p) for p in powers_of_2], 
                                         state='readonly')
                n_dropdown.pack()
                param_frame.sobol_n = n_var
            elif sa_type == 'Gradient-Based':
                # Request 13: Gradient-based UI with parameter table
                tk.Label(param_frame, text="Parameter settings", 
                        bg="white", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=10)
                
                # Create parameter table
                table_frame = tk.Frame(param_frame, bg="white")
                table_frame.pack(fill=tk.X, padx=10)
                
                # Header
                header_frame = tk.Frame(table_frame, bg="lightgrey")
                header_frame.pack(fill=tk.X)
                tk.Label(header_frame, text="Name", bg="lightgrey", width=15, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                tk.Label(header_frame, text="Interval", bg="lightgrey", width=15, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                tk.Label(header_frame, text="Point", bg="lightgrey", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                tk.Label(header_frame, text="Step", bg="lightgrey", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                
                # Rows for each parameter
                param_entries = {}
                saved_grad_params = self.project.metadata.get('sa_params', {}) if self.project.metadata.get('sa_type') == 'Gradient-Based' else {}
                for param_name, bounds in self.project.metadata['params'].items():
                    row_frame = tk.Frame(table_frame, bg="white")
                    row_frame.pack(fill=tk.X)
                    
                    tk.Label(row_frame, text=param_name, bg="white", width=15, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                    interval_text = f"[{bounds['min']}, {bounds['max']}]"
                    tk.Label(row_frame, text=interval_text, bg="white", width=15, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                    
                    # Point entry
                    default_point = saved_grad_params.get(param_name, {}).get('point', (bounds['min'] + bounds['max']) / 2)
                    point_var = tk.StringVar(value=str(default_point))
                    point_entry = tk.Entry(row_frame, textvariable=point_var, width=12, bg="white")
                    point_entry.pack(side=tk.LEFT, padx=2, pady=2)
                    
                    # Step entry
                    default_step = saved_grad_params.get(param_name, {}).get('step', 0.001)
                    step_var = tk.StringVar(value=str(default_step))
                    step_entry = tk.Entry(row_frame, textvariable=step_var, width=12, bg="white")
                    step_entry.pack(side=tk.LEFT, padx=2, pady=2)
                    
                    param_entries[param_name] = {"point": point_var, "step": step_var}
                
                # Store references for later use
                param_frame.gradient_params = param_entries
        
        cb.bind("<<ComboboxSelected>>", on_select)
        
        # Trigger initial display
        if type_var.get():
            on_select(None)
        
        # Sample info
        info_frame = tk.Frame(main_frame, bg="white")
        info_frame.pack(fill=tk.X, pady=10)
        tk.Label(info_frame, text=f"Number of simulation runs required: {self.project.metadata.get('n_required', '-')}", 
                 bg="white").pack()
        
        # Buttons (request 6 - properly centered)
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(side=tk.BOTTOM, pady=10)
        
        def generate_samples():
            self.generate_samples(type_var.get(), param_frame)
        
        tk.Button(button_frame, text="Generate sample", bg="white", command=generate_samples).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Back", bg="white", command=self.show_recording_menu).pack(side=tk.LEFT, padx=5)

    def generate_samples(self, sa_type, frame):
        """Generate samples using SALib or gradient method."""
        try:
            if not sa_type:
                messagebox.showerror("Error", "Please select an SA type")
                return
            
            if len(self.project.metadata['params']) == 0:
                messagebox.showerror("Error", "Please add parameters first")
                return
            
            # Create problem definition
            problem = {
                'num_vars': len(self.project.metadata['params']),
                'names': list(self.project.metadata['params'].keys()),
                'bounds': [[v['min'], v['max']] for v in self.project.metadata['params'].values()]
            }
            
            # Generate samples based on type
            if sa_type == 'Sobol (SALib)':
                if sobol_sample is None:
                    messagebox.showerror("Error", "SALib not installed. Install with: pip install SALib")
                    return
                n = 128
                if hasattr(frame, 'sobol_n'):
                    try:
                        n_val = int(frame.sobol_n.get())
                        if n_val in [2**i for i in range(4, 13)]:
                            n = n_val
                    except Exception:
                        pass
                samples = sobol_sample(problem, n)
                self.project.metadata['sa_params'] = {'n': n}
            elif sa_type == 'Gradient-Based':
                if hasattr(frame, 'gradient_params'):
                    try:
                        gradient_params = {}
                        for param_name, entries in frame.gradient_params.items():
                            point = float(entries['point'].get())
                            step = float(entries['step'].get())
                            if step <= 0:
                                messagebox.showerror("Error", f"Step size for {param_name} must be > 0")
                                return
                            gradient_params[param_name] = {"point": point, "step": step}
                        samples = self.generate_gradient_samples(problem, gradient_params)
                        self.project.metadata['sa_params'] = gradient_params
                    except ValueError:
                        messagebox.showerror("Error", "Invalid parameter values - must be numbers")
                        return
                else:
                    messagebox.showerror("Error", "Gradient parameters not found")
                    return
            else:
                messagebox.showerror("Error", "Unsupported SA type")
                return
            
            self.project.samples = samples.tolist() if hasattr(samples, 'tolist') else samples
            self.project.metadata['n_required'] = len(self.project.samples)
            self.project.metadata['sa_type'] = sa_type
            self.project.save()
            
            # Request 7: Ensure UI updates with new value - force reload
            messagebox.showinfo("Success", f"Generated {len(self.project.samples)} sample points for {sa_type}")
            self.sa_setup_ui()  # This will reload and show updated n_required
        except ImportError:
            messagebox.showerror("Error", "SALib not installed. Install with: pip install SALib")
        except Exception as e:
            messagebox.showerror("Error", f"Error generating samples: {str(e)}")

    def generate_gradient_samples(self, problem, gradient_params):
        """Generate samples for gradient-based SA using central difference."""
        n_vars = problem['num_vars']
        samples = []
        param_names = problem['names']
        bounds = problem['bounds']
        
        # For central difference, generate 2 points per parameter: negative and positive step
        for i, name in enumerate(param_names):
            gp = gradient_params.get(name, {})
            step = abs(gp.get('step', 0.0))
            if step <= 0:
                step = (bounds[i][1] - bounds[i][0]) * 0.1
            
            # Central point for this parameter
            central = []
            for j, pname in enumerate(param_names):
                if j == i:
                    central.append(gp.get('point', (bounds[j][0] + bounds[j][1]) / 2))
                else:
                    central.append(gradient_params.get(pname, {}).get('point', (bounds[j][0] + bounds[j][1]) / 2))
            
            # Negative step
            sample_neg = central.copy()
            sample_neg[i] = max(bounds[i][0], min(bounds[i][1], sample_neg[i] - step))
            samples.append(sample_neg)
            
            # Positive step
            sample_pos = central.copy()
            sample_pos[i] = max(bounds[i][0], min(bounds[i][1], sample_pos[i] + step))
            samples.append(sample_pos)
        
        return np.array(samples)

    def cleanup_partial_roi_files(self):
        """Remove partial ROI files before replaying the current sample."""
        # Clean ROIs folder
        roi_dir = os.path.join(self.project.folder_path, "ROIs")
        if os.path.exists(roi_dir):
            for f in os.listdir(roi_dir):
                if f.startswith("roi_main"):
                    try:
                        os.remove(os.path.join(roi_dir, f))
                    except OSError:
                        pass
        
        # Clean Additional ROIs folder
        add_roi_dir = os.path.join(self.project.folder_path, "Additional ROIs")
        if os.path.exists(add_roi_dir):
            for f in os.listdir(add_roi_dir):
                if f.startswith("roi_additional"):
                    try:
                        os.remove(os.path.join(add_roi_dir, f))
                    except OSError:
                        pass

    def start_running(self):
        """Save project and start replay simulation."""
        # Validate ROI is selected
        roi_files = self.find_files_with_prefix("roi_main_")
        if len(roi_files) == 0:
            messagebox.showerror("Error", "Please capture the region of interest first")
            return
        
        # Validate simulation completion indicator is selected
        completion_files = self.find_files_with_prefix("simulation_completion_indicator_")
        if len(completion_files) == 0:
            messagebox.showerror("Error", "Please set the simulation completion indicator first")
            return
        
        # Validate SA type is selected
        if not self.project.metadata.get('sa_type'):
            messagebox.showerror("Error", "Please select an SA type and generate samples")
            return
        
        # Validate parameters based on SA type
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
        
        # TODO
        # Here I have concerns. Do we return to the main menu? Why? We should just hide the window and start replaying. If pressed Esc during replay,
        # we should show the pause menu, discarding the incomplete run's results. So when resumed, we start that run from the beginning.
        # If finished, we show the corresponding info window with OK button, after clicking OK or closing the window, we show the main menu.
        self.root.deiconify()
        self.setup_main_menu()
        
        # Start replay synchronously
        self.start_replay()

    def start_replay(self):
        """Start replaying commands for all samples."""
        try:
            # Bind Esc for pause
            self.root.bind('<Escape>', lambda e: self.pause_replay())
            
            cmd_file = os.path.join(self.project.folder_path, "commands.txt")
            replayer = TextReplayer()
            template_path = None
            
            # Find completion template
            for f in os.listdir(self.project.folder_path):
                if f.startswith("simulation_completion_indicator_") or f.startswith("roi_completion_"):
                    template_path = os.path.join(self.project.folder_path, f)
                    break
            
            # Run simulations
            param_names = list(self.project.metadata['params'].keys())
            for i in range(len(self.project.samples)):
                self.current_sample_index = i
                if np.isnan(self.project.results[i]):
                    # Check if paused before starting this sample, and discard any partial ROI files
                    self.cleanup_partial_roi_files()
                    while self.replay_paused:
                        self.root.update()
                        time.sleep(0.1)
                    
                    param_dict = {param_names[j]: self.project.samples[i][j] for j in range(len(param_names))}
                    replayer.execute_run(cmd_file, param_dict, self.vision_engine, template_path)
                    
                    # Extract result from main ROI
                    roi_files = [f for f in os.listdir(self.project.folder_path) if f.startswith("roi_main")]
                    if roi_files:
                        # Extract average RGB value
                        pass  # TODO: implement result extraction
                    
                    self.project.results[i] = np.nan  # Placeholder
            
            self.project.metadata['status'] = "completed"
            self.project.save()
            messagebox.showinfo("Success", "All simulations completed!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Replay failed: {str(e)}")
        finally:
            self.root.unbind('<Escape>')

if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()