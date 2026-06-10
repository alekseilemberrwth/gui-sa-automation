# BUG LLM, do not read this section, this is just a note for me.
#

# TODO LLM, do not read this section, this is just a note for me.
# - Perform tests (point-based and area-based) for gradient and sobol.
# - Review the window stack management and app closing. There was an issue with the app not closing properly after viewing results and closing all windows. 
# It seems that we fixed it by adding os._exit(0) in quit_app, but I am not sure if this is the correct way to do it.
# - Perform a thorough GUI enhancement, including:
# * Every table we have in the app should have resizable-by-user (by dragging the column borders) columns so I can adjust the column widths and horizontal and vertical scrollbars if the content does not fit.
# * Open existing project. Currently, we have a separate button to open the results. We should load the results directly under the parameter table, if the result is available.
# The result consists of 1) stats table (same for both gradient and sobol) and 2) barplot. For gradient it will be a single barplot,
# for sobol add buttons "S1", "ST", and "S2" (inactive if second order indices were not calculated), clicking on a button changes the plot type. Button is inactive when its plot is already displayed.
# For both gradient and sobol plots there should be horizontal and vertical scrollbars. For both gradient and sobol, there should be "+" and "-" buttons to increase and decrease the plot size.
# * After we entered project name, we start recording. We should transform the window with the project name entry into the recording menu, now we keep the project name entry window
# until the user presses Home to stop recording, and only then we transform it into the recording menu. We should transform it immediately after the user enters the project name and
# clicks Ok.
# * When we record user's actions, our window with recording paused menu is just hidden. It is ok, but all the buttons should be deactivated and reactivated back when he presses Home
# to pause recording.
# * When all the simulation runs are completed, we show a messagebox, but the window behind it is still recording pause menu or replay pause menu. When a user clicks Ok on the messagebox,
# we transform the window behind it into the main menu. We should transform the window behind the messagebox into the main menu BEFORE showing the messagebox.

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import threading
from project import Project
from recorder import TextRecorder
from replayer import TextReplayer, PauseRequested, StopRequested
from vision_engine import VisionEngine
from PIL import Image, ImageTk
import numpy as np
import time
import mss
import cv2
from pynput import keyboard
from SALib.sample.sobol import sample as sobol_sample
from SALib.analyze.sobol import analyze as sobol_analyze
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# For debugging purposes, to ensure reproducibility
SOBOL_SAMPLE_SEED = 42


class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SA Automation")
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
        self.replay_keyboard_listener = None
        
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
            for i in range(len(lines)):
                line = lines[i]
                if prefix and line.strip().startswith(prefix):
                    continue
                if not prefix and line.strip() == cmd:
                    continue
                # Remove last "wait" command, because we have a custom waiting logic (simulation completion indicator)
                if i == len(lines) - 1 and cmd.startswith("wait for simulation to finish") and line.startswith("wait "):
                    continue
                f.write(line)
            f.write(cmd + "\n")

    def on_window_close(self):
        if self.in_roi_preview:
            self.in_roi_preview = False
            self.show_recording_menu()
            return
        
        self.go_back()
    
    def go_back(self):
        if len(self.screen_stack) > 0:
            self.screen_stack.pop()
            if len(self.screen_stack) > 0:
                prev_screen, prev_data = self.screen_stack[-1]
                self.show_screen(prev_screen, prev_data)
            else:
                self.quit_app()
        else:
            self.quit_app()

    def quit_app(self):
        self.root.destroy()
        os._exit(0)

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
        elif screen_name == "capture_completion_choice":
            self.show_completion_indicator_choice()
        elif screen_name == "timeout_only_input":
            self.show_timeout_only_input()
        elif screen_name == "colormap_selection":
            self.show_colormap_selection()

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
            messagebox.showerror("Error", "Failed to load project. Project data might be corrupted or incomplete.")
            return
        
        err = self.project.validate()
        if err:
            messagebox.showerror("Invalid Project", err)
            return
        
        self.push_screen("project_dashboard")
        self.vision_engine = VisionEngine(self.project.folder_path)
        self.show_project_dashboard()

    def continue_recording_actions(self):
        cmd_file = os.path.join(self.project.folder_path, "commands.txt")
        self.recorder = TextRecorder(cmd_file, lambda: self.root.after(0, self.show_recording_menu_from_pause))
        self.vision_engine = VisionEngine(self.project.folder_path)
        self.recording_paused = True
        self.root.deiconify()
        self.push_screen("recording_menu")
        self.show_recording_menu()

    def show_project_dashboard(self):
        for widget in self.root.winfo_children(): widget.destroy()
        
        self.root.title(f"Project: {self.project.metadata['name']}")
        self.center_window(760, 860)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        status_colors = {"Setup": "grey", "In progress": "orange", "Completed": "green"}
        
        stat_frame = tk.Frame(main_frame, bg="white")
        stat_frame.pack(fill=tk.X, pady=5)
        status_color = status_colors.get(self.project.metadata['status'], 'black')
        tk.Label(stat_frame, text="Status:", font=("Arial", 10, "bold"), fg="black", bg="white").pack(side=tk.LEFT)
        tk.Label(stat_frame, text=self.project.metadata['status'], font=("Arial", 10, "bold"), fg=status_color, bg="white").pack(side=tk.LEFT)
        if self.project.metadata['status'] == "Setup":
            tk.Button(stat_frame, text="Continue recording actions", bg="lightblue",
                      command=self.continue_recording_actions).pack(side=tk.LEFT, padx=10)
        elif self.project.metadata['status'] == "In progress":
            tk.Button(stat_frame, text="Continue simulation runs", bg="lightblue",
                      command=self.resume_sims).pack(side=tk.LEFT, padx=10)
        
        # TODO display info_frame as a table
        info_frame = tk.Frame(main_frame, bg="white")
        info_frame.pack(fill=tk.X, pady=5)
        info_frame_text = (f"SA type: {self.project.metadata.get('sa_type', '-')}          "
                           f"Simulation runs performed: {self.project.metadata.get('n_completed')}/{self.project.metadata.get('n_required')}          "
                           f"Colormap: {self.project.metadata.get('colormap', {}).get('name', '-')}")
        tk.Label(info_frame, text=info_frame_text, bg="white").pack(side=tk.LEFT, padx=2)
        
        table_frame = tk.Frame(main_frame, bg="white", relief=tk.RIDGE, borderwidth=1)
        table_frame.pack(fill=tk.X, pady=10)
        tk.Label(table_frame, text="Parameter settings", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W, padx=5, pady=5)
        
        param_table = tk.Frame(table_frame, bg="white")
        param_table.pack(fill=tk.X, padx=5, pady=5)
        
        sa_type = self.project.metadata.get('sa_type', '')
        headers = ["Name", "Range"]
        if sa_type == 'Local Gradient Calculation': headers += ["Point", "Step"]
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
                if sa_type == 'Local Gradient Calculation':
                    grad_params = self.project.metadata.get('sa_params', {}).get(pname, {})
                    tk.Label(row, text=str(grad_params.get('point', '')), bg="white", width=widths[2], anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                    tk.Label(row, text=str(grad_params.get('step', '')), bg="white", width=widths[3], anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
        
        roi_frame = tk.Frame(main_frame, bg="white")
        roi_frame.pack(fill=tk.X, pady=10)
        # TODO move the additional roi toggler to the topright corner of the project dashboard.
        tk.Label(roi_frame, text=f"Additional ROI status: {self.project.metadata['additional_roi_status']}", bg="white").pack(side=tk.LEFT)
        btn_text = "Stop capturing" if self.project.metadata['additional_roi_status'] == "capturing" else "Resume capturing"
        tk.Button(roi_frame, text=btn_text, bg="white", command=self.toggle_additional_roi).pack(side=tk.LEFT, padx=10)
        
        if self.project.metadata['status'] == "Completed":
            tk.Button(main_frame, text="View SA results", bg="lightgreen", command=self.generate_report).pack(pady=20)

    def toggle_additional_roi(self):
        if self.project.metadata.get('status') == "Completed":
            messagebox.showerror("Error", "Cannot change ROI capturing status: project is already completed.")
            return

        is_capturing = self.project.metadata['additional_roi_status'] == "capturing"
        if not is_capturing:
            if 'additional_roi' not in self.project.metadata:
                messagebox.showerror("Error", "No additional ROI was selected for this SA.")
                return
        self.project.toggle_additional_roi_command(not is_capturing)
        self.show_project_dashboard()

    def resume_sims(self):
        if messagebox.askokcancel("Confirm", "Resume simulation running?"):
            self.root.iconify()  # Hide window, will appear if Home is pressed
            self.replay_paused = False  # Start running immediately
            self.replay_stop_requested = False
            self._start_replay_keyboard_listener()
            self._replay_thread = threading.Thread(target=self.start_replay, daemon=True)
            self._replay_thread.start()

    def find_files_with_prefix(self, prefix):
        if prefix.startswith("roi_additional_"): folder = os.path.join(self.project.folder_path, "Additional ROIs")
        elif prefix.startswith("roi_main_"): folder = os.path.join(self.project.folder_path, "ROIs")
        else: folder = self.project.folder_path
        
        if not os.path.exists(folder): return []
        return [f for f in os.listdir(folder) if f.startswith(prefix)]

    def select_colormap_value_field(self, value_type):
        if value_type not in ("min", "max"):
            raise ValueError("Invalid value_type for select_colormap_value_field. Must be 'min' or 'max'.")
        cmd = f"select colormap {value_type} value field"
        self._add_unique_command(cmd)
        messagebox.showinfo("Info", f"Selected colormap {value_type} value field")
        self.show_recording_menu()

    def capture_completion_indicator(self):
        self.push_screen("capture_completion_choice")
        self.show_completion_indicator_choice()

    def show_completion_indicator_choice(self):
        for widget in self.root.winfo_children(): widget.destroy()
        
        self.root.title(f"Set Simulation Completion Indicator | {self.project.metadata['name']}")
        self.center_window(400, 125)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=20, padx=20)
            
        def on_timeout():
            if len(self.screen_stack) > 0: self.screen_stack.pop()
            self.push_screen("timeout_only_input")
            self.show_timeout_only_input()
            
        def on_image_timeout():
            if len(self.screen_stack) > 0: self.screen_stack.pop()
            self.start_roi_selection("completion_indicator")
            
        btn_frame = tk.Frame(main_frame, bg="white")
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="Timeout Only", command=on_timeout, bg="white", width=15).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Image + Timeout", command=on_image_timeout, bg="white", width=15).pack(side=tk.LEFT, padx=10)
        
        tk.Button(main_frame, text="Back", command=lambda: self.go_back(), bg="white").pack(side=tk.BOTTOM, pady=10)
    
    def show_timeout_only_input(self):
        for widget in self.root.winfo_children(): widget.destroy()
        
        self.root.title(f"Timeout Configuration | {self.project.metadata['name']}")
        self.center_window(400, 200)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=20, padx=20)
        
        tk.Label(main_frame, text="Enter timeout in seconds:", font=("Arial", 11), bg="white").pack(pady=10)
        
        timeout_var = tk.StringVar(value="10.0")
        timeout_entry = tk.Entry(main_frame, textvariable=timeout_var, font=("Arial", 12), bg="white")
        timeout_entry.pack(pady=10, fill=tk.X)
        timeout_entry.focus()
        
        def on_confirm():
            try:
                timeout = float(timeout_var.get())
                if timeout <= 0:
                    messagebox.showerror("Error", "Timeout must be a positive number")
                    return
                cmd = f"wait for simulation to finish with timeout {timeout}"
                self._add_unique_command(cmd, prefix="wait for simulation to finish")
                # Delete any old completion templates since we are using pure timeout
                for f in os.listdir(self.project.folder_path):
                    if f.startswith("simulation_completion_indicator"):
                        os.remove(os.path.join(self.project.folder_path, f))
                if len(self.screen_stack) > 0: self.screen_stack.pop()
                self.show_recording_menu()
            except ValueError:
                messagebox.showerror("Error", "Please enter a valid number")
        
        def on_back():
            if len(self.screen_stack) > 0: self.screen_stack.pop()
            self.show_completion_indicator_choice()
        
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(side=tk.BOTTOM, pady=10)
        tk.Button(button_frame, text="Confirm", command=on_confirm, bg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Back", command=on_back, bg="white").pack(side=tk.LEFT, padx=5)
        
        timeout_entry.bind("<Return>", lambda e: on_confirm())

    def generate_report(self):
        sa_type = self.project.metadata.get('sa_type')
        if sa_type == 'Sobol Index':
            self.show_sobol_report()
        elif sa_type == 'Local Gradient Calculation':
            self.show_gradient_report()

    def show_gradient_report(self):
        param_names = list(self.project.metadata['params'].keys())
        grad_params = self.project.metadata.get('sa_params')
        results = self.project.results
        cmap = self.project.metadata['colormap']

        report_win = tk.Toplevel(self.root)
        report_win.title("Local Gradient Calculation Results")
        report_win.geometry(f"600x{max(len(param_names)*100, 500)}")
        
        if np.any(np.isnan(results)):
            messagebox.showerror("Error", "One of the simulation runs did not produce a valid result (NaN). Cannot generate report.")
            return

        scalars = results
        gradients = []
        points = []

        # Calculate gradients using central difference
        for i, name in enumerate(param_names):
            gp = grad_params.get(name)
            step = gp.get('step')
            point = gp.get('point')
            points.append(f"{name}: {point}")
            
            res_neg = scalars[2*i]
            res_pos = scalars[2*i + 1]

            grad = (res_pos - res_neg) / (2 * step)
            gradients.append(grad)
            print(f"Parameter '{name}': step={step}, point={point}, res_neg={res_neg}, res_pos={res_pos}, gradient={grad}")
        
        # Calculate statistics over scalars
        scalar_stats = {
            'min': np.min(scalars),
            'max': np.max(scalars),
            'mean': np.mean(scalars),
            'median': np.median(scalars),
            'std': np.std(scalars),
            'mad': np.median(np.abs(scalars - np.median(scalars))) # Median Absolute Deviation from the median
        }

        info_frame = tk.Frame(report_win, bg="white")
        info_frame.pack(fill=tk.X, padx=10, pady=10)
        tk.Label(info_frame, text="Evaluation Point:", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W)
        tk.Label(info_frame, text="     ".join(points), bg="white").pack(anchor=tk.W)

        stats_frame = tk.Frame(report_win, bg="white")
        stats_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        tk.Label(stats_frame, text="Statistics over Function Values:", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W)
        tk.Label(stats_frame, text=f"Min: {scalar_stats['min']}", bg="white").pack(anchor=tk.W)
        tk.Label(stats_frame, text=f"Max: {scalar_stats['max']}", bg="white").pack(anchor=tk.W)
        tk.Label(stats_frame, text=f"Mean: {scalar_stats['mean']}", bg="white").pack(anchor=tk.W)
        tk.Label(stats_frame, text=f"Median: {scalar_stats['median']}", bg="white").pack(anchor=tk.W)
        tk.Label(stats_frame, text=f"STD: {scalar_stats['std']}", bg="white").pack(anchor=tk.W)
        tk.Label(stats_frame, text=f"MAD: {scalar_stats['mad']}", bg="white").pack(anchor=tk.W)

        # Inverse the order of parameters and gradients for better visualization (the first parameter will be at the top of the plot)
        param_names = param_names[::-1]
        gradients = gradients[::-1]

        # Plot gradient as a barplot
        fig_height = min(10, len(param_names) * 0.9) # After 10, the captions start to be hidden
        fig, ax = plt.subplots(figsize=(6, fig_height))

        bars = ax.barh(param_names, gradients)

        ax.set_xlabel("Partial Derivative")
        ax.set_title('Gradient Barplot')

        # Add padding so labels fit inside frame
        max_abs = max(abs(g) for g in gradients)
        padding = max_abs * 0.5

        ax.set_xlim(
            -max_abs - padding,
            max_abs + padding
        )

        # Value labels
        for bar, grad in zip(bars, gradients):
            y = bar.get_y() + bar.get_height() / 2

            if grad >= 0:
                ax.text(
                    grad + padding * 0.05,
                    y,
                    f"{grad:.4E}",
                    va='center',
                    ha='left',
                    fontsize=9
                )
                bar.set_color('red')
            else:
                ax.text(
                    grad - padding * 0.05,
                    y,
                    f"{grad:.4E}",
                    va='center',
                    ha='right',
                    fontsize=9
                )
                bar.set_color('blue')

        fig.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, master=report_win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def show_sobol_report(self):
        param_names = list(self.project.metadata['params'].keys())
        sobol_params = self.project.metadata.get('sa_params')
        results = self.project.results
        cmap = self.project.metadata['colormap']

        report_win = tk.Toplevel(self.root)
        report_win.title("Sobol Index Results")
        report_win.geometry(f"900x{max(len(param_names)*100, 600)}")
        
        if np.any(np.isnan(results)):
            messagebox.showerror("Error", "One of the simulation runs did not produce a valid result (NaN). Cannot generate report.")
            return

        scalars = results
        
        # Calculate statistics over scalars
        scalar_stats = {
            'min': np.min(scalars),
            'max': np.max(scalars),
            'mean': np.mean(scalars),
            'median': np.median(scalars),
            'std': np.std(scalars),
            'mad': np.median(np.abs(scalars - np.median(scalars)))
        }

        # Calculate Sobol indices
        problem = {
            'num_vars': len(param_names),
            'names': param_names,
            'bounds': [[v['min'], v['max']] for v in self.project.metadata['params'].values()]
        }
        
        calc_second_order = sobol_params.get('calc_second_order')
        
        print(f'Calculating Sobol indices for problem:\n{problem}')
        Si = sobol_analyze(problem, scalars, calc_second_order=calc_second_order, print_to_console=False)
        
        # Display statistics frame
        stats_frame = tk.Frame(report_win, bg="white")
        stats_frame.pack(fill=tk.X, padx=10, pady=10)
        tk.Label(stats_frame, text="Statistics over Function Values:", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W)
        tk.Label(stats_frame, text=f"Min: {scalar_stats['min']}", bg="white").pack(anchor=tk.W)
        tk.Label(stats_frame, text=f"Max: {scalar_stats['max']}", bg="white").pack(anchor=tk.W)
        tk.Label(stats_frame, text=f"Mean: {scalar_stats['mean']}", bg="white").pack(anchor=tk.W)
        tk.Label(stats_frame, text=f"Median: {scalar_stats['median']}", bg="white").pack(anchor=tk.W)
        tk.Label(stats_frame, text=f"STD: {scalar_stats['std']}", bg="white").pack(anchor=tk.W)
        tk.Label(stats_frame, text=f"MAD: {scalar_stats['mad']}", bg="white").pack(anchor=tk.W)

        # Display results table
        table_frame = tk.Frame(report_win, bg="white", relief=tk.RIDGE, borderwidth=1)
        table_frame.pack(fill=tk.X, padx=10, pady=10)
        tk.Label(table_frame, text="Sobol Indices:", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W, padx=5, pady=5)
        
        results_table = tk.Frame(table_frame, bg="white")
        results_table.pack(fill=tk.X, padx=5, pady=5)
        
        # Header row
        header_frame = tk.Frame(results_table, bg="lightgrey")
        header_frame.pack(fill=tk.X)
        tk.Label(header_frame, text="Parameter(s)", bg="lightgrey", width=20, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
        tk.Label(header_frame, text="S1", bg="lightgrey", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
        tk.Label(header_frame, text="S1_conf", bg="lightgrey", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
        tk.Label(header_frame, text="ST", bg="lightgrey", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
        tk.Label(header_frame, text="ST_conf", bg="lightgrey", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
        if calc_second_order:
            tk.Label(header_frame, text="S2", bg="lightgrey", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
            tk.Label(header_frame, text="S2_conf", bg="lightgrey", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
        
        # First order indices
        for i, param_name in enumerate(param_names):
            row_frame = tk.Frame(results_table, bg="white")
            row_frame.pack(fill=tk.X)
            tk.Label(row_frame, text=param_name, bg="white", width=20, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
            tk.Label(row_frame, text=f"{Si['S1'][i]:.6E}", bg="white", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
            tk.Label(row_frame, text=f"{Si['S1_conf'][i]:.6E}", bg="white", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
            tk.Label(row_frame, text=f"{Si['ST'][i]:.6E}", bg="white", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
            tk.Label(row_frame, text=f"{Si['ST_conf'][i]:.6E}", bg="white", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
        
        # Second order indices if calculated
        if calc_second_order and 'S2' in Si:
            second_order_indices = Si['S2']
            second_order_conf = Si['S2_conf']
            for i, param_name_i in enumerate(param_names):
                for j, param_name_j in enumerate(param_names):
                    if j > i:
                        row_frame = tk.Frame(results_table, bg="white")
                        row_frame.pack(fill=tk.X)
                        pair_name = f"{param_name_i}-{param_name_j}"
                        tk.Label(row_frame, text=pair_name, bg="white", width=20, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                        tk.Label(row_frame, text="", bg="white", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                        tk.Label(row_frame, text="", bg="white", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                        tk.Label(row_frame, text="", bg="white", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                        tk.Label(row_frame, text="", bg="white", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                        tk.Label(row_frame, text=f"{second_order_indices[i, j]:.6E}", bg="white", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                        tk.Label(row_frame, text=f"{second_order_conf[i, j]:.6E}", bg="white", width=12, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)

        # Create plot frame
        plot_frame = tk.Frame(report_win, bg="white")
        plot_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Button frame for switching plots
        button_frame = tk.Frame(plot_frame, bg="white")
        button_frame.pack(fill=tk.X, pady=5)

        # Store current plot state
        plot_state = {'current_plot': 'S1', 'fig': None, 'canvas': None}

        def create_s1_plot():
            param_names_reversed = param_names[::-1]
            s1_reversed = Si['S1'][::-1]
            
            fig, ax = plt.subplots(figsize=(8, max(4, len(param_names) * 0.8)))
            bars = ax.barh(param_names_reversed, s1_reversed, color='green')
            ax.set_xlabel("S1 (First Order Index)")
            ax.set_title('First Order Sobol Indices (S1)')

            # Add padding so labels fit inside frame
            max_abs = max(abs(s1) for s1 in s1_reversed)
            padding = max_abs * 0.5
            ax.set_xlim(-max_abs - padding, max_abs + padding)
            
            for bar, val in zip(bars, s1_reversed):
                y = bar.get_y() + bar.get_height() / 2
                ax.text(val + 0.02, y, f"{val:.4E}", va='center', ha='left', fontsize=9)
            
            fig.tight_layout()
            return fig

        def create_st_plot():
            param_names_reversed = param_names[::-1]
            st_reversed = Si['ST'][::-1]
            
            fig, ax = plt.subplots(figsize=(8, max(4, len(param_names) * 0.8)))
            bars = ax.barh(param_names_reversed, st_reversed, color='orange')
            ax.set_xlabel("ST (Total Order Index)")
            ax.set_title('Total Order Sobol Indices (ST)')

            # Add padding so labels fit inside frame
            max_abs = max(abs(st) for st in st_reversed)
            padding = max_abs * 0.5
            ax.set_xlim(-max_abs - padding, max_abs + padding)
            
            for bar, val in zip(bars, st_reversed):
                y = bar.get_y() + bar.get_height() / 2
                ax.text(val + 0.02, y, f"{val:.4E}", va='center', ha='left', fontsize=9)
            
            fig.tight_layout()
            return fig

        def create_s2_plot():
            if not calc_second_order or 'S2' not in Si:
                return None
            
            second_order = Si['S2']
            fig, ax = plt.subplots(figsize=(8, 6))
            
            # Create heatmap
            im = ax.imshow(second_order, cmap='YlOrRd', aspect='auto')
            ax.set_xticks(range(len(param_names)))
            ax.set_yticks(range(len(param_names)))
            ax.set_xticklabels(param_names, rotation=45, ha='right')
            ax.set_yticklabels(param_names)
            ax.set_title('Second Order Sobol Indices (S2)')
            
            # Add colorbar
            plt.colorbar(im, ax=ax)
            
            # Add values to heatmap
            for i in range(len(param_names)):
                for j in range(len(param_names)):
                    text = ax.text(j, i, f"{second_order[i, j]:.3E}", ha="center", va="center", color="black", fontsize=8)
            
            fig.tight_layout()
            return fig

        def show_plot(plot_type):
            # Clear previous plot
            if plot_state['canvas']:
                plot_state['canvas'].get_tk_widget().destroy()
            if plot_state['fig']:
                plt.close(plot_state['fig'])
            
            # Create new plot
            if plot_type == 'S1':
                plot_state['fig'] = create_s1_plot()
            elif plot_type == 'ST':
                plot_state['fig'] = create_st_plot()
            elif plot_type == 'S2':
                plot_state['fig'] = create_s2_plot()
            
            if plot_state['fig']:
                plot_state['canvas'] = FigureCanvasTkAgg(plot_state['fig'], master=plot_frame)
                plot_state['canvas'].draw()
                plot_state['canvas'].get_tk_widget().pack(fill=tk.BOTH, expand=True)
            
            plot_state['current_plot'] = plot_type
            
            # Update button states
            s1_btn.config(state=tk.DISABLED if plot_type == 'S1' else tk.NORMAL)
            st_btn.config(state=tk.DISABLED if plot_type == 'ST' else tk.NORMAL)
            s2_btn.config(state=tk.DISABLED if plot_type == 'S2' else (tk.NORMAL if calc_second_order else tk.DISABLED))

        # Create buttons
        s1_btn = tk.Button(button_frame, text="S1", command=lambda: show_plot('S1'), bg="white")
        s1_btn.pack(side=tk.LEFT, padx=5)
        
        st_btn = tk.Button(button_frame, text="ST", command=lambda: show_plot('ST'), bg="white")
        st_btn.pack(side=tk.LEFT, padx=5)
        
        s2_btn = tk.Button(button_frame, text="S2", command=lambda: show_plot('S2'), bg="white")
        s2_btn.pack(side=tk.LEFT, padx=5)
        if not calc_second_order:
            s2_btn.config(state=tk.DISABLED)
        
        # Show initial plot
        show_plot('S1')

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
        self.recorder = TextRecorder(cmd_file, lambda: self.root.after(0, self.show_recording_menu_from_pause))
        self.vision_engine = VisionEngine(folder)
        
        self.root.iconify()
        messagebox.showinfo("Recording Started", "Recording mouse and keyboard. Press Home to pause and open the control menu.")
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
        tk.Button(main_frame, text="Select colormap", command=lambda: [self.push_screen("colormap_selection"), self.show_colormap_selection()], bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Select colormap min value field", command=lambda: self.select_colormap_value_field("min"), bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Select colormap max value field", command=lambda: self.select_colormap_value_field("max"), bg="white").pack(fill=tk.X, padx=20, pady=5)
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

    def show_colormap_selection(self):
        for widget in self.root.winfo_children(): widget.destroy()

        self.root.title(f"Select Colormap | {self.project.metadata['name']}")
        self.center_window(400, 180)
        self.root.config(bg="white")

        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=20, padx=20)

        tk.Label(main_frame, text="Choose colormap:", font=("Arial", 12), bg="white").pack(anchor=tk.W, pady=(0, 10))
        cmap_var = tk.StringVar(value=self.project.metadata.get('colormap').get('name', "viridis"))
        cmap_dropdown = ttk.Combobox(main_frame, textvariable=cmap_var, values=['viridis', 'turbo'], state='readonly', width=20)
        cmap_dropdown.pack(fill=tk.X, pady=5)

        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=15)

        def on_ok():
            self.project.metadata['colormap']['name'] = cmap_var.get()
            self.project.save()
            if len(self.screen_stack) > 0:
                self.screen_stack.pop()
            self.show_recording_menu()

        def on_cancel():
            if len(self.screen_stack) > 0:
                self.screen_stack.pop()
            self.show_recording_menu()

        tk.Button(button_frame, text="Ok", command=on_ok, bg="lightgreen").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        tk.Button(button_frame, text="Cancel", command=on_cancel, bg="lightcoral").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

    def pause_replay(self):
        self.replay_paused = True
        self.root.after(0, self._show_replay_paused_ui)

    def _show_replay_paused_ui(self):
        self.root.deiconify()
        self.root.lift()
        self.show_replay_pause_menu()

    def _on_replay_key_press(self, key):
        if key == keyboard.Key.home and not self.replay_paused and not self.replay_stop_requested:
            self.root.after(0, self.pause_replay)

    def _start_replay_keyboard_listener(self):
        self._stop_replay_keyboard_listener()
        self.replay_keyboard_listener = keyboard.Listener(on_press=self._on_replay_key_press)
        self.replay_keyboard_listener.daemon = True
        self.replay_keyboard_listener.start()

    def _stop_replay_keyboard_listener(self):
        if self.replay_keyboard_listener:
            self.replay_keyboard_listener.stop()
            self.replay_keyboard_listener = None

    def show_replay_pause_menu(self):
        for widget in self.root.winfo_children(): widget.destroy()
        
        self.root.title(f"Replay paused | {self.project.metadata['name']}")
        self.center_window(500, 200)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        tk.Label(main_frame, text=f"Replay paused at sample {self.current_sample_index + 1} of {len(self.project.samples)}", 
                bg="white", font=("Arial", 12)).pack(pady=20)
        
        tk.Button(main_frame, text="Resume running simulations", bg="green", fg="white", 
                  command=self.resume_replay).pack(fill=tk.X, padx=20, pady=10)
        
        tk.Button(main_frame, text="Stop and return to main menu", bg="red", fg="white", 
                  command=self.stop_replay).pack(fill=tk.X, padx=20, pady=10)

    def resume_replay(self):
        self.replay_paused = False
        self.root.iconify()

    def stop_replay(self):
        self.replay_stop_requested = True
        self.replay_paused = False
        self._stop_replay_keyboard_listener()
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
            prefix = "simulation_completion_indicator"
            cmd = f"wait for simulation to finish with timeout {timeout}"

            # Delete old indicator files
            for f in os.listdir(self.project.folder_path):
                if f.startswith(prefix):
                    os.remove(os.path.join(self.project.folder_path, f))

            roi_path = os.path.join(self.project.folder_path, f"{prefix}.png")
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
        
        sa_types = ['Sobol Index', 'Local Gradient Calculation']
        cb = ttk.Combobox(main_frame, textvariable=type_var, values=sa_types, state='readonly')
        cb.pack(pady=10, fill=tk.X)
        
        param_frame = tk.Frame(main_frame, bg="white")
        param_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        def on_select(event):
            for w in param_frame.winfo_children(): w.destroy()
            sa_type = type_var.get()
            
            if sa_type == 'Sobol Index':
                if len(self.project.metadata['params']) < 2:
                    messagebox.showerror("Error", "Sobol Index calculation requires at least 2 parameters. Please add more parameters first.")
                    type_var.set('')
                    return
                powers_of_2 = [2**i for i in range(2, 13)]
                tk.Label(param_frame, text="N (must be power of 2):", bg="white").pack()
                current_n = self.project.metadata.get('sa_params', {}).get('sobol_n', 128)
                n_var = tk.StringVar(value=str(current_n))
                n_dropdown = ttk.Combobox(param_frame, textvariable=n_var, values=[str(p) for p in powers_of_2], state='readonly')
                n_dropdown.pack()
                param_frame.sobol_n = n_var
                
                # Add checkbox for second order indices
                calc_second_order_default = self.project.metadata.get('sa_params', {}).get('calc_second_order', False)
                calc_second_order_var = tk.BooleanVar(value=calc_second_order_default)
                second_order_cb = tk.Checkbutton(param_frame, text="Calculate second order indices", variable=calc_second_order_var, bg="white")
                second_order_cb.pack(anchor=tk.W, pady=10)
                param_frame.calc_second_order = calc_second_order_var
            elif sa_type == 'Local Gradient Calculation':
                if len(self.project.metadata['params']) == 0:
                    messagebox.showerror("Error", "Local Gradient Calculation requires at least 1 parameter. Please add parameters first.")
                    type_var.set('')
                    return
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
                saved_grad_params = self.project.metadata.get('sa_params', {}) if self.project.metadata.get('sa_type') == 'Local Gradient Calculation' else {}
                for param_name, bounds in self.project.metadata['params'].items():
                    row_frame = tk.Frame(table_frame, bg="white")
                    row_frame.pack(fill=tk.X)
                    
                    tk.Label(row_frame, text=param_name, bg="white", width=15, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                    tk.Label(row_frame, text=f"[{bounds['min']}, {bounds['max']}]", bg="white", width=15, anchor=tk.W).pack(side=tk.LEFT, padx=2, pady=2)
                    
                    default_point = saved_grad_params.get(param_name, {}).get('point', (bounds['min'] + bounds['max']) / 2)
                    point_var = tk.StringVar(value=str(default_point))
                    tk.Entry(row_frame, textvariable=point_var, width=12, bg="white").pack(side=tk.LEFT, padx=2, pady=2)
                    
                    default_step = saved_grad_params.get(param_name, {}).get('step', 0.1)
                    step_var = tk.StringVar(value=str(default_step))
                    tk.Entry(row_frame, textvariable=step_var, width=12, bg="white").pack(side=tk.LEFT, padx=2, pady=2)
                    
                    param_entries[param_name] = {"point": point_var, "step": step_var}
                
                param_frame.gradient_params = param_entries
        
        cb.bind("<<ComboboxSelected>>", on_select)
        if type_var.get(): on_select(None)
        
        info_frame = tk.Frame(main_frame, bg="white")
        info_frame.pack(fill=tk.X, pady=10)
        tk.Label(info_frame, text=f"Number of simulation runs required: {self.project.metadata.get('n_required')}", bg="white").pack()
        
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
            
            # Sobol sample size = N * (D + 2), for second order indices turned off, N * (2D + 2) for turned on, where D is number of parameters.
            if sa_type == 'Sobol Index':
                if sobol_sample is None:
                    messagebox.showerror("Error", "SALib not installed. Install with: pip install SALib")
                    return
                sobol_n = int(frame.sobol_n.get())
                calc_second_order = frame.calc_second_order.get()
                samples = sobol_sample(problem, sobol_n, calc_second_order=calc_second_order, seed=SOBOL_SAMPLE_SEED)
                self.project.metadata['sa_params'] = {'sobol_n': sobol_n, 'calc_second_order': calc_second_order}
            elif sa_type == 'Local Gradient Calculation':
                if hasattr(frame, 'gradient_params'):
                    gradient_params = {}
                    for param_name, entries in frame.gradient_params.items():
                        point, step = float(entries['point'].get()), float(entries['step'].get())
                        if step <= 0:
                            messagebox.showerror("Error", f"Step size for {param_name} must be > 0")
                            return
                        gradient_params[param_name] = {"point": point, "step": step}

                    try:
                        samples = self.generate_gradient_samples(problem, gradient_params)
                    except ValueError as e:
                        messagebox.showerror("Error", str(e))
                        return
                    
                    self.project.metadata['sa_params'] = gradient_params
                else:
                    messagebox.showerror("Error", "Gradient parameters not found")
                    return
            
            self.project.samples = samples
            self.project.metadata['n_required'] = len(self.project.samples)
            self.project.metadata['sa_type'] = sa_type
            self.project.save()
            
            messagebox.showinfo("Success", f"Generated {len(self.project.samples)} sample points for {sa_type}")
            self.sa_setup_ui()
        except Exception as e:
            messagebox.showerror("Error", f"Error generating samples: {str(e)}")

    def generate_gradient_samples(self, problem, gradient_params):
        samples = []
        param_names = problem['names']
        bounds = problem['bounds']
        central_points = [gradient_params.get(name).get('point') for name in param_names]

        for i, name in enumerate(param_names):
            sample_neg = central_points.copy()
            sample_pos = central_points.copy()
            sample_neg[i] = sample_neg[i] - gradient_params.get(name).get('step')
            sample_pos[i] = sample_pos[i] + gradient_params.get(name).get('step')
            if sample_neg[i] < bounds[i][0] or sample_pos[i] > bounds[i][1]:
                raise ValueError(f"Sample points for parameter '{name}' are out of bounds: [{sample_neg[i]}, {sample_pos[i]}]. Please adjust the central point or step size.")
            samples.append(sample_neg)
            samples.append(sample_pos)

        return np.array(samples)

    def cleanup_partial_simulation_run_results(self):
        current_roi_path = os.path.join(self.project.folder_path, "ROIs", f"roi_main_{self.current_sample_index}.png")
        if os.path.exists(current_roi_path):
            os.remove(current_roi_path)
        
        current_additional_roi_path = os.path.join(self.project.folder_path, "Additional ROIs", f"roi_additional_{self.current_sample_index}.png")
        if os.path.exists(current_additional_roi_path):
            os.remove(current_additional_roi_path)
        
        self.project.results[self.current_sample_index] = np.nan

    def start_running(self):        
        cmd_file = os.path.join(self.project.folder_path, "commands.txt")

        # Perform basic validation of command file before starting simulations:
        wait_for_simulation_to_finish_found = False
        capture_main_roi_found = False
        capture_additional_roi_found = False
        min_colormap_value_field_selected = False
        max_colormap_value_field_selected = False
        if os.path.exists(cmd_file):
            with open(cmd_file, "r") as f:
                lines = f.readlines()
                for line in lines:
                    stripped_line = line.strip()
                    if stripped_line.startswith("wait for simulation to finish"):
                        if wait_for_simulation_to_finish_found:
                            messagebox.showerror("Error", "Multiple simulation completion indicators found in the command file. Please ensure there is only one.")
                            return
                        if capture_main_roi_found:
                            messagebox.showerror("Error", "Wait for simulation to finish command must go before main region of interest capture command in the command file.")
                            return
                        wait_for_simulation_to_finish_found = True
                    elif stripped_line == "capture the region of interest":
                        if capture_main_roi_found:
                            messagebox.showerror("Error", "Multiple main region of interest capture commands found in the command file. Please ensure there is only one.")
                            return
                        capture_main_roi_found = True
                    elif stripped_line == "capture additional region of interest":
                        if capture_additional_roi_found:
                            messagebox.showerror("Error", "Multiple additional region of interest capture commands found in the command file. Please ensure there is only one.")
                            return
                        capture_additional_roi_found = True
                    elif stripped_line == "select colormap min value field":
                        if min_colormap_value_field_selected:
                            messagebox.showerror("Error", "Multiple colormap min value field selection commands found in the command file. Please ensure there is only one.")
                            return
                        min_colormap_value_field_selected = True
                    elif stripped_line == "select colormap max value field":
                        if max_colormap_value_field_selected:
                            messagebox.showerror("Error", "Multiple colormap max value field selection commands found in the command file. Please ensure there is only one.")
                            return
                        max_colormap_value_field_selected = True
        
        if not wait_for_simulation_to_finish_found:
            messagebox.showerror("Error", "Please set the simulation completion indicator first")
            return
        
        if not capture_main_roi_found:
            messagebox.showerror("Error", "Please capture the main region of interest first")
            return
        
        if not self.project.metadata.get('colormap').get('name', "") in ("viridis", "turbo"):
            messagebox.showerror("Error", "Please select a valid colormap before starting simulations.")
            return

        if not min_colormap_value_field_selected:
            messagebox.showerror("Error", "Please select the colormap min value field first")
            return
        
        if not max_colormap_value_field_selected:
            messagebox.showerror("Error", "Please select the colormap max value field first")
            return

        if not self.project.metadata.get('sa_type'):
            messagebox.showerror("Error", "Please select an SA type and generate samples")
            return
                
        # If everything looks good, initialize results and start replay
        self.project.metadata['status'] = "In progress"
        self.project.results = np.array([np.nan] * len(self.project.samples))
        self.project.save()

        self.root.iconify()  # Hide window, will appear if Home is pressed
        self.replay_paused = False  # Start running immediately
        self.replay_stop_requested = False
        self._start_replay_keyboard_listener()
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
                if f.startswith("simulation_completion_indicator"):
                    template_path = os.path.join(self.project.folder_path, f)
                    break

            param_names = list(self.project.metadata['params'].keys())
            
            i = 0
            while i < len(self.project.samples):
                if self.replay_stop_requested: return
                self.current_sample_index = i
                
                res_val = self.project.results[i]

                # Skip replay if result already exists
                if np.ndim(res_val) == 0:
                    existing_result = not np.isnan(res_val)
                else:
                    existing_result = not np.all(np.isnan(res_val))
                if existing_result:
                    i += 1
                    continue
                
                self.cleanup_partial_simulation_run_results()
                
                while self.replay_paused:
                    if self.replay_stop_requested: return
                    time.sleep(0.1)

                param_dict = {param_names[j]: self.project.samples[i][j] for j in range(len(param_names))}
                try:
                    min_val, max_val = replayer.execute_run(cmd_file, param_dict, self.vision_engine, template_path, self.project, i, should_pause_fn=lambda: self.replay_paused, should_stop_fn=lambda: self.replay_stop_requested)
                except StopRequested:
                    self.cleanup_partial_simulation_run_results()
                    return  # Exit immediately on stop
                except TimeoutError as e:
                    self.cleanup_partial_simulation_run_results()
                    self.replay_paused = True
                    self.root.after(0, lambda: self._show_timeout_error(str(e)))
                    continue  # Do not advance index! Retry it after user resumes.
                except PauseRequested:
                    self.cleanup_partial_simulation_run_results()
                    self.replay_paused = True
                    self.root.after(0, self._show_replay_paused_ui)
                    continue  # Do not advance index! Retry it after user resumes.
                
                # Compute average RGB for main ROI
                roi_path = os.path.join(self.project.folder_path, "ROIs", f"roi_main_{i}.png")
                
                avg_rgb = None
                if os.path.exists(roi_path):
                    img = cv2.imread(roi_path)
                    if img is not None:
                        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        rgb = np.array(rgb).astype('float64')
                        avg_rgb = rgb.mean(axis=(0, 1))
                    else:
                        raise ValueError(f"Failed to read ROI image for sample {i} at: {roi_path}")
                else:
                    raise FileNotFoundError(f"Expected ROI screenshot not found for sample {i}. Expected at: {roi_path}")

                if min_val is None or max_val is None:
                    raise ValueError(f"Missing colormap min/max values for sample {i}. Cannot compute scalar result.")

                scalar_value = self.vision_engine.rgb_to_scalar(avg_rgb, self.project.metadata['colormap']['name'], min_val, max_val)
                self.project.results[i] = scalar_value

                print(f"start_replay: Project results [{i}]: reconstructed {avg_rgb} as {scalar_value}")

                self.project.metadata['n_completed'] += 1
                self.project.save()
                i += 1

            self.project.metadata['status'] = "Completed"
            self.project.save()
            self.root.after(0, self._on_replay_finished)

        except Exception as e:
            err_msg = str(e)
            self.root.after(0, lambda: messagebox.showerror("Error", f"Replay failed: {err_msg}"))
            self.root.after(0, self.root.deiconify)
        finally:
            self._stop_replay_keyboard_listener()

    def _on_replay_finished(self):
        self.root.deiconify()
        messagebox.showinfo("Success", "All simulations completed!")
        self.setup_main_menu()

if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()