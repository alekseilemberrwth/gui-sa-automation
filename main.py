import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from project import Project
from recorder import TextRecorder
from replayer import TextReplayer
from vision_engine import VisionEngine
from PIL import Image, ImageTk
import numpy as np
import threading


# TODO
# 1. Why does sample generation take so long?
# 2. On pressing Alt, window is still not brought to the foreground.
# I want it to forcibly come to the front (pop up) so user can interact with it.
# Currently, if user clicks on the taskbar icon, it brings up the correct window,
# but ideally it should just pop up in front of them immediately.
# 3. After generating sample, I am thrown back to the menu. I want to stay at
# the sample generation screen and just update the number of simulation runs required.
# 4. I should enter the new project name after I select the folder in the separate dialogue window, not in the recording menu.
# The recording menu should just show the name I entered.
# 5. Generate sample and back buttons should be centered.
# 6. Why is "release key a" being recorded correctly, but "press key a" looks like ? symbol in the notepad?
# If I try to read it back, which symbol do I get? I want to get "press key a" when I read it back, not "press key ?"


class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SA Automation")
        self.root.geometry("500x600")
        self.root.config(bg="white")
        self.project = None
        self.recorder = None
        self.vision_engine = None
        self.screen_stack = []
        self.roi_selection = None
        
        self.setup_main_menu()

    def setup_main_menu(self):
        for widget in self.root.winfo_children(): widget.destroy()
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(main_frame, text="Sensitivity Analysis Automation", font=("Arial", 14), bg="white").pack(pady=20)
        tk.Button(main_frame, text="Start new SA", command=self.start_new_sa, width=20, bg="white").pack(pady=10)
        tk.Button(main_frame, text="Open existing SA", command=self.open_existing_sa, width=20, bg="white").pack()

    # --- OPEN EXISTING FLOW ---
    def open_existing_sa(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        
        self.project = Project(folder)
        if not self.project.load():
            messagebox.showerror("Error", "Invalid Project Folder structure.")
            self.setup_main_menu()
            return
        
        err = self.project.validate()
        if err:
            messagebox.showerror("Invalid Project", err)
            self.setup_main_menu()
            return
        
        self.show_project_dashboard()

    def show_project_dashboard(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.root.title(f"Project: {self.project.metadata['name']}")
        self.root.geometry("600x800")
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        # Status Line with Continue button
        stat_frame = tk.Frame(main_frame, bg="white")
        stat_frame.pack(fill=tk.X, pady=5)
        tk.Label(stat_frame, text=f"Status: {self.project.metadata['status']}", font=("Arial", 10, "bold"), bg="white").pack(side=tk.LEFT)
        if self.project.metadata['status'] == "in_progress":
            tk.Button(stat_frame, text="Continue simulation runs", bg="lightblue",
                      command=self.resume_sims).pack(side=tk.LEFT, padx=10)

        # Parameters
        tk.Label(main_frame, text="Parameters:", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W)
        for k, v in self.project.metadata['params'].items():
            tk.Label(main_frame, text=f"{k}: [{v['min']}, {v['max']}]", bg="white").pack(anchor=tk.W, padx=20)

        # Simulation Completion Indicator
        comp_frame = tk.Frame(main_frame, bg="white", relief=tk.RIDGE, borderwidth=1)
        comp_frame.pack(fill=tk.X, pady=10)
        tk.Label(comp_frame, text="Simulation Completion Indicator", font=("Arial", 9, "bold"), bg="white").pack(anchor=tk.W, padx=5, pady=5)
        
        btn_frame = tk.Frame(comp_frame, bg="white")
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(btn_frame, text="View", bg="white", command=self.view_completion_template).pack(side=tk.LEFT, padx=5)
        if self.project.metadata['status'] == "in_progress":
            tk.Button(btn_frame, text="Capture new", bg="white", command=self.capture_completion_indicator).pack(side=tk.LEFT, padx=5)

        # Additional ROI Toggle
        roi_frame = tk.Frame(main_frame, bg="white")
        roi_frame.pack(fill=tk.X, pady=10)
        tk.Label(roi_frame, text=f"Additional ROI: {self.project.metadata['additional_roi_status']}", bg="white").pack(side=tk.LEFT)
        btn_text = "Stop capturing" if self.project.metadata['additional_roi_status'] == "capturing" else "Resume capturing"
        tk.Button(roi_frame, text=btn_text, bg="white", command=self.toggle_add_roi).pack(side=tk.LEFT, padx=10)

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
        
        def save_colormap(*args):
            self.project.metadata['colormap']['name'] = cmap_var.get()
            self.project.save()
        cmap_var.trace('w', save_colormap)
        
        min_frame = tk.Frame(cmap_info_frame, bg="white")
        min_frame.pack(fill=tk.X, pady=2)
        tk.Label(min_frame, text="Min value:", bg="white").pack(side=tk.LEFT)
        min_var = tk.StringVar(value=str(self.project.metadata['colormap']['min']))
        min_entry = tk.Entry(min_frame, textvariable=min_var, width=10, bg="white")
        min_entry.pack(side=tk.LEFT, padx=5)
        
        def save_min(*args):
            try:
                self.project.metadata['colormap']['min'] = float(min_var.get())
                self.project.save()
            except:
                pass
        min_var.trace('w', save_min)
        
        max_frame = tk.Frame(cmap_info_frame, bg="white")
        max_frame.pack(fill=tk.X, pady=2)
        tk.Label(max_frame, text="Max value:", bg="white").pack(side=tk.LEFT)
        max_var = tk.StringVar(value=str(self.project.metadata['colormap']['max']))
        max_entry = tk.Entry(max_frame, textvariable=max_var, width=10, bg="white")
        max_entry.pack(side=tk.LEFT, padx=5)
        
        def save_max(*args):
            try:
                self.project.metadata['colormap']['max'] = float(max_var.get())
                self.project.save()
            except:
                pass
        max_var.trace('w', save_max)

        # View Results Button
        if self.project.metadata['status'] == "completed":
            tk.Button(main_frame, text="View SA results", bg="lightgreen", command=self.generate_report).pack(pady=20)
        
        tk.Button(main_frame, text="Back", bg="white", command=self.setup_main_menu).pack(side=tk.BOTTOM, pady=10)

    def toggle_add_roi(self):
        is_capturing = self.project.metadata['additional_roi_status'] == "capturing"
        self.project.toggle_additional_roi_command(not is_capturing)
        self.show_project_dashboard()

    def resume_sims(self):
        if messagebox.askokcancel("Confirm", "Resume simulation running?"):
            self.start_replay()

    def view_completion_template(self):
        template_files = [f for f in os.listdir(self.project.folder_path) if f.startswith("roi_completion")]
        if not template_files:
            messagebox.showinfo("Info", "No simulation completion indicator found")
            return
        
        template_path = os.path.join(self.project.folder_path, template_files[0])
        img = Image.open(template_path)
        img.show()

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

    # --- START NEW FLOW ---
    def start_new_sa(self):
        folder = filedialog.askdirectory(title="Select Empty Folder for New Project")
        if not folder:
            return
        
        self.project = Project(folder)
        self.project.save()
        
        cmd_file = os.path.join(folder, "commands.txt")
        self.recorder = TextRecorder(cmd_file, self.show_recording_menu)
        self.vision_engine = VisionEngine(folder)
        
        self.root.iconify()
        messagebox.showinfo("Recording Started", "Recording mouse and keyboard. Press Alt to pause and open the control menu.")
        self.recorder.start()

    def show_recording_menu(self):
        self.root.deiconify()
        self.root.lift()
        
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.root.title("Recording Menu (Paused)")
        self.root.geometry("500x700")
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)

        # Project Name
        name_frame = tk.Frame(main_frame, bg="white")
        name_frame.pack(fill=tk.X, pady=10)
        tk.Label(name_frame, text="Project Name:", bg="white").pack(side=tk.LEFT)
        name_var = tk.StringVar(value=self.project.metadata['name'])
        name_entry = tk.Entry(name_frame, textvariable=name_var, font=("Arial", 12), bg="white")
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        def save_name(*args):
            self.project.metadata['name'] = name_var.get()
            self.project.save()
        name_var.trace('w', save_name)
        
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
        tk.Button(main_frame, text="Save & Start Running", bg="green", fg="white", 
                  command=self.start_running).pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=10)

    def resume_recording(self):
        self.root.iconify()
        self.recorder.start()

    def view_cmd_file(self):
        cmd_file = os.path.join(self.project.folder_path, "commands.txt")
        os.startfile(cmd_file)

    def start_roi_selection(self, roi_type):
        """Start ROI selection by taking a screenshot and allowing user to select region."""
        # Take a screenshot
        self.vision_engine = VisionEngine(self.project.folder_path)
        screenshot = self.vision_engine.grab_screen()
        
        # Store screenshot for later use in selection
        self.current_screenshot = screenshot
        self.roi_type = roi_type
        
        # Create ROI selection window
        self.show_roi_selection_window(screenshot)

    def show_roi_selection_window(self, screenshot):
        """Show the screenshot for ROI selection."""
        # Convert numpy array to PIL Image
        img_pil = Image.fromarray(screenshot)
        
        # Create new window
        roi_win = tk.Toplevel(self.root)
        roi_win.title(f"Select ROI ({self.roi_type})")
        roi_win.config(bg="white")
        
        # Convert to PhotoImage for display
        photo = ImageTk.PhotoImage(img_pil.resize((800, 600)))
        label = tk.Label(roi_win, image=photo, bg="white")
        label.image = photo
        label.pack()
        
        # Instructions
        instr = tk.Label(roi_win, text="Click and drag to select ROI region", bg="white")
        instr.pack()
        
        # Store rectangle coordinates
        self.rect_coords = {"x1": 0, "y1": 0, "x2": 0, "y2": 0, "start": False}
        
        def on_mouse_down(event):
            self.rect_coords["x1"] = event.x
            self.rect_coords["y1"] = event.y
            self.rect_coords["start"] = True
        
        def on_mouse_up(event):
            if self.rect_coords["start"]:
                self.rect_coords["x2"] = event.x
                self.rect_coords["y2"] = event.y
                self.rect_coords["start"] = False
                roi_win.destroy()
                self.show_roi_preview()
        
        label.bind("<Button-1>", on_mouse_down)
        label.bind("<ButtonRelease-1>", on_mouse_up)

    def show_roi_preview(self):
        """Show preview of selected ROI."""
        x1, y1, x2, y2 = self.rect_coords["x1"], self.rect_coords["y1"], self.rect_coords["x2"], self.rect_coords["y2"]
        
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1
        
        # Extract ROI from screenshot
        roi_image = self.current_screenshot[y1:y2, x1:x2]
        roi_pil = Image.fromarray(roi_image)
        
        # Create preview window
        prev_win = tk.Toplevel(self.root)
        prev_win.title("ROI Preview")
        prev_win.config(bg="white")
        
        photo = ImageTk.PhotoImage(roi_pil.resize((600, 400)))
        label = tk.Label(prev_win, image=photo, bg="white")
        label.image = photo
        label.pack(pady=10)
        
        button_frame = tk.Frame(prev_win, bg="white")
        button_frame.pack(pady=10)
        
        def on_ok():
            self.save_roi(x1, y1, x2, y2)
            prev_win.destroy()
            self.show_recording_menu()
        
        def on_retake():
            prev_win.destroy()
            self.start_roi_selection(self.roi_type)
        
        def on_cancel():
            prev_win.destroy()
            self.show_recording_menu()
        
        tk.Button(button_frame, text="OK", bg="white", command=on_ok).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Retake", bg="white", command=on_retake).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", bg="white", command=on_cancel).pack(side=tk.LEFT, padx=5)

    def save_roi(self, x1, y1, x2, y2):
        """Save ROI and add command to file."""
        if self.roi_type == "completion_indicator":
            self.vision_engine.extract_and_store_main_roi((x1, y1, x2, y2))
            self.recorder.append_command("wait for simulation to finish")
        elif self.roi_type == "main_roi":
            self.vision_engine.extract_and_store_main_roi((x1, y1, x2, y2))
            self.recorder.append_command("capture the region of interest")
        elif self.roi_type == "additional_roi":
            self.vision_engine.extract_and_store_additional_roi((x1, y1, x2, y2))
            self.recorder.append_command("capture additional region of interest")

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
        self.root.geometry("600x400")
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        for p_name, bounds in self.project.metadata['params'].items():
            frame = tk.Frame(main_frame, bg="white", relief=tk.RIDGE, borderwidth=1)
            frame.pack(fill=tk.X, pady=5)
            tk.Button(frame, text="Delete", fg="red", bg="white", 
                      command=lambda n=p_name: self.delete_param(n)).pack(side=tk.LEFT, padx=5)
            tk.Label(frame, text=f"{p_name}: [{bounds['min']}, {bounds['max']}]", bg="white", 
                     font=("Arial", 10)).pack(side=tk.LEFT, padx=10)
        
        tk.Button(main_frame, text="Back", bg="white", command=self.show_recording_menu).pack(side=tk.BOTTOM, pady=10)

    def delete_param(self, param_name):
        if param_name in self.project.metadata['params']:
            del self.project.metadata['params'][param_name]
            self.project.save()
            self.edit_param_ui()

    def sa_setup_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.root.title("SA Setup")
        self.root.geometry("500x600")
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=20, padx=20)
        
        tk.Label(main_frame, text="SA Type:", font=("Arial", 10, "bold"), bg="white").pack(pady=10)
        type_var = tk.StringVar(value=self.project.metadata.get('sa_type', ''))
        
        sa_types = [
            'Sobol (SALib)',
            'Morris (SALib)',
            'Saltelli (SALib)',
            'Gradient-Based',
            'LHS (Latin Hypercube)',
            'Fast (SALib)'
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
                tk.Label(param_frame, text="N (Samples):", bg="white").pack()
                tk.Entry(param_frame, name="n_entry", bg="white").pack()
            elif sa_type == 'Morris (SALib)':
                tk.Label(param_frame, text="N (Trajectories):", bg="white").pack()
                tk.Entry(param_frame, name="n_entry", bg="white").pack()
            elif sa_type == 'Saltelli (SALib)':
                tk.Label(param_frame, text="N (Samples):", bg="white").pack()
                tk.Entry(param_frame, name="n_entry", bg="white").pack()
            elif sa_type == 'Gradient-Based':
                tk.Label(param_frame, text="Point values (comma-separated):", bg="white").pack()
                tk.Entry(param_frame, name="point_entry", bg="white").pack()
                tk.Label(param_frame, text="Step sizes (comma-separated):", bg="white").pack()
                tk.Entry(param_frame, name="step_entry", bg="white").pack()
                tk.Label(param_frame, text="Approximation order (1 or 2):", bg="white").pack()
                tk.Entry(param_frame, name="order_entry", bg="white").pack()
            elif sa_type == 'LHS (Latin Hypercube)':
                tk.Label(param_frame, text="N (Samples):", bg="white").pack()
                tk.Entry(param_frame, name="n_entry", bg="white").pack()
            elif sa_type == 'Fast (SALib)':
                tk.Label(param_frame, text="N (Samples):", bg="white").pack()
                tk.Entry(param_frame, name="n_entry", bg="white").pack()
        
        cb.bind("<<ComboboxSelected>>", on_select)
        
        # Trigger initial display
        if type_var.get():
            on_select(None)
        
        # Sample info
        info_frame = tk.Frame(main_frame, bg="white")
        info_frame.pack(fill=tk.X, pady=10)
        tk.Label(info_frame, text=f"Number of simulation runs required: {self.project.metadata.get('n_required', '-')}", 
                 bg="white").pack()
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        
        def generate_samples():
            self.generate_samples(type_var.get(), param_frame)
        
        tk.Button(button_frame, text="Generate sample", bg="white", command=generate_samples).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Back", bg="white", command=self.show_recording_menu).pack(side=tk.LEFT, padx=5)

    def generate_samples(self, sa_type, frame):
        """Generate samples using SALib or gradient method."""
        try:
            from SALib.sample.saltelli import sample as saltelli_sample
            from SALib.sample.sobol import sample as sobol_sample
            from SALib.sample.morris import sample as morris_sample
            from SALib.sample.latin import sample as latin_sample
            from SALib.sample.fast_sampler import sample as fast_sample
            
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
                n = 128
                samples = sobol_sample(problem, n)
            elif sa_type == 'Morris (SALib)':
                n = 20
                samples = morris_sample(problem, n)
            elif sa_type == 'Saltelli (SALib)':
                n = 128
                samples = saltelli_sample(problem, n)
            elif sa_type == 'LHS (Latin Hypercube)':
                n = 128
                samples = latin_sample(problem, n)
            elif sa_type == 'Fast (SALib)':
                n = 128
                samples = fast_sample(problem, n)
            elif sa_type == 'Gradient-Based':
                samples = self.generate_gradient_samples(problem)
            
            self.project.samples = samples.tolist() if hasattr(samples, 'tolist') else samples
            self.project.metadata['n_required'] = len(self.project.samples)
            self.project.metadata['sa_type'] = sa_type
            self.project.save()
            
            messagebox.showinfo("Success", f"Generated {len(self.project.samples)} sample points for {sa_type}")
            self.show_recording_menu()
        except ImportError:
            messagebox.showerror("Error", "SALib not installed. Install with: pip install SALib")
        except Exception as e:
            messagebox.showerror("Error", f"Error generating samples: {str(e)}")

    def generate_gradient_samples(self, problem):
        """Generate samples for gradient-based SA."""
        # Simple gradient sampling at central point with variations
        n_vars = problem['num_vars']
        samples = []
        
        # Central point
        central = [(problem['bounds'][i][0] + problem['bounds'][i][1]) / 2 for i in range(n_vars)]
        samples.append(central)
        
        # Perturbed samples
        for i in range(n_vars):
            for sign in [-1, 1]:
                sample = central.copy()
                sample[i] += sign * (problem['bounds'][i][1] - problem['bounds'][i][0]) * 0.1
                samples.append(sample)
        
        return np.array(samples)

    def start_running(self):
        """Save project and start replay simulation."""
        if len(self.project.metadata['params']) == 0:
            messagebox.showerror("Error", "Please add parameters first")
            return
        
        if not self.project.metadata.get('sa_type'):
            messagebox.showerror("Error", "Please select an SA type and generate samples")
            return
        
        self.project.metadata['status'] = "in_progress"
        self.project.results = [np.nan] * len(self.project.samples)
        self.project.save()
        
        self.root.deiconify()
        self.setup_main_menu()
        
        # Start replay in background
        threading.Thread(target=self.start_replay, daemon=True).start()

    def start_replay(self):
        """Start replaying commands for all samples."""
        try:
            cmd_file = os.path.join(self.project.folder_path, "commands.txt")
            replayer = TextReplayer()
            template_path = None
            
            # Find completion template
            for f in os.listdir(self.project.folder_path):
                if f.startswith("roi_completion"):
                    template_path = os.path.join(self.project.folder_path, f)
                    break
            
            # Run simulations
            param_names = list(self.project.metadata['params'].keys())
            for i, sample in enumerate(self.project.samples):
                if np.isnan(self.project.results[i]):
                    param_dict = {param_names[j]: sample[j] for j in range(len(param_names))}
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

if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()