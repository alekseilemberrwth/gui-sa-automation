# BUG LLM, do not read this section, this is just a note for me.
# - When I change parameter name from X to Y, I want to replace every instance of "enter value for X" to "enter value for Y" in the command file
# - Parameter names are not editable now in the Edit parameters table (bug). Also when I click on the cell, the text input field (our editability imitation) pops up after some pause.
# Can you speed it up? Earlier I think it (input field popup) was quicker.
# - If I go back to the main menu, in the main menu I still can sometime see the project's name in the gui window header.
# Instead, the project metadata should be fully discarded and I should see "SA Automation" there, when I go to the main menu window.
# - "X" button in the topright corner of each window where there is a Back or Cancel button should behave exactly like Back or Cancel. Now it sometimes closes all the project
# and returns me back to the main menu.

# TODO LLM, do not read this section, this is just a note for me.
# - Perform a thorough GUI enhancement, including:
# * tk.button -> ttk.button everywhere
# * center text in every column of every table
# * resize some windows and buttons, what about 2 font sizes we use in diff places? Use a single one?
# * After we entered project name, we start recording. We should transform the window with the project name entry into the recording menu, now we keep the project name entry window
# until the user presses Home to stop recording, and only then we transform it into the recording menu. We should transform it immediately after the user enters the project name and
# clicks Ok.
# * When we record user's actions, our window with recording paused menu is just hidden. It is ok, but all the buttons should be deactivated and reactivated back when he presses Home
# to pause recording.
# * When all the simulation runs are completed, we show a messagebox, but the window behind it is still recording pause menu or replay pause menu. When a user clicks Ok on the messagebox,
# we transform the window behind it into the main menu. We should transform the window behind the messagebox into the main menu BEFORE showing the messagebox.
# change the app taskbar icon to smth else :)

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import threading
import sys
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
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

# For debugging purposes, to ensure reproducibility
SOBOL_SAMPLE_SEED = 42

class EditableTreeview(ttk.Frame):
    def __init__(self, parent, columns, display_columns=None, editable_cols=None, tree_height=10, col_widths=None, allow_delete=False, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.editable_cols = editable_cols or []
        self.editor = None
        self.editing_item = None
        self.editing_column = None
        self.allow_delete = allow_delete

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=tree_height)
        if display_columns:
            self.tree.configure(displaycolumns=display_columns)

        col_widths = col_widths or {}
        for col in columns:
            self.tree.heading(col, text=col, anchor="center")
            self.tree.column(col, width=col_widths.get(col, 150), minwidth=60, stretch=False, anchor="center")

        self.v_scroll = ttk.Scrollbar(self, orient="vertical", command=self.on_vertical_scroll)
        self.h_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.on_horizontal_scroll)
        self.tree.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll.grid(row=1, column=0, sticky="ew")

        # Capture Button-1 to instantly place editor and stop Treeview from stealing focus
        self.tree.bind("<Button-1>", self.on_click)
        self.tree.bind("<MouseWheel>", self.on_mousewheel)

        if self.allow_delete:
            self.tree.bind("<Button-3>", self.on_right_click)

    def populate(self, data):
        self.tree.delete(*self.tree.get_children())
        for row in data:
            self.tree.insert("", "end", values=row)

    def get_data(self):
        return [list(self.tree.item(child)["values"]) for child in self.tree.get_children()]

    def on_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="Delete", command=lambda: self.delete_item(item))
            menu.post(event.x_root, event.y_root)

    def delete_item(self, item):
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this parameter?"):
            self.commit_editor()
            if self.tree.exists(item):
                self.tree.delete(item)

    def on_click(self, event):
        self.commit_editor()
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell": return
        
        item = self.tree.identify_row(event.y)
        if not item: return
        
        self.tree.selection_set(item)
        self.tree.focus(item)
        
        column = self.tree.identify_column(event.x)
        col_index = int(column[1:]) - 1

        if col_index not in self.editable_cols: return
        
        x, y, width, height = self.tree.bbox(item, column)
        value = self.tree.set(item, column)

        self.editor = ttk.Entry(self.tree, justify="center")
        self.editor.insert(0, value)
        self.editor.place(x=x, y=y, width=width, height=height)
        
        self.editor.focus_set()
        self.editor.icursor(tk.END)

        self.editing_item = item
        self.editing_column = column

        self.editor.bind("<Return>", lambda e: self.commit_editor())
        self.editor.bind("<Escape>", lambda e: self.cancel_editor())
        
        return "break"

    def commit_editor(self):
        if self.editor is None: return
        value = self.editor.get()
        if self.tree.exists(self.editing_item):
            self.tree.set(self.editing_item, self.editing_column, value)
        self.editor.destroy()
        self.editor = None
        self.editing_item = None
        self.editing_column = None

    def cancel_editor(self):
        if self.editor is None: return
        self.editor.destroy()
        self.editor = None
        self.editing_item = None
        self.editing_column = None

    def on_vertical_scroll(self, *args):
        self.commit_editor()
        self.tree.yview(*args)

    def on_horizontal_scroll(self, *args):
        self.commit_editor()
        self.tree.xview(*args)

    def on_mousewheel(self, event):
        self.commit_editor()
        self.tree.yview_scroll(-event.delta // 120, "units")
        return "break"


class SAViewer(ttk.Frame):
    def __init__(self, parent, project, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.project = project
        self.zoom_factor = 1.0
        self.param_names = list(self.project.metadata['params'].keys())
        self.sa_type = self.project.metadata.get('sa_type')
        self.current_annot_text = ""

        self.fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = None
        self.stats = {}

        self.analyze_results()

        self.current_plot = 'Gradient' if self.sa_type == 'Local Gradient Calculation' else 'S1'
        self.create_widgets()
        self.draw_plot()

        self.canvas.bind("<Configure>", lambda event: self.update_image_position())

    def analyze_results(self):
        scalars = self.project.results
        self.stats = {
            'Min': np.min(scalars), 'Max': np.max(scalars),
            'Mean': np.mean(scalars), 'Median': np.median(scalars),
            'STD': np.std(scalars), 'MAD': np.median(np.abs(scalars - np.median(scalars)))
        }

        if self.sa_type == 'Local Gradient Calculation':
            self.gradients = []
            grad_params = self.project.metadata.get('sa_params')
            for i, name in enumerate(self.param_names):
                step = grad_params.get(name).get('step')
                res_neg = scalars[2*i]
                res_pos = scalars[2*i + 1]
                self.gradients.append((res_pos - res_neg) / (2 * step))
        else:
            problem = {
                'num_vars': len(self.param_names),
                'names': self.param_names,
                'bounds': [[v['min'], v['max']] for v in self.project.metadata['params'].values()]
            }
            calc_second_order = self.project.metadata.get('sa_params', {}).get('calc_second_order', False)
            self.Si = sobol_analyze(problem, scalars, calc_second_order=calc_second_order, print_to_console=False)

    def create_widgets(self):
        top_bar = tk.Frame(self)
        top_bar.pack(fill=tk.X, pady=5)

        btn_frame = tk.Frame(top_bar)
        btn_frame.pack(side=tk.LEFT)
        
        if self.sa_type == 'Sobol Index':
            tk.Label(btn_frame, text="Plot type: ", font=("Arial", 10)).pack(side=tk.LEFT, padx=5)

            self.s1_btn = tk.Button(btn_frame, text="S1", width=5, command=lambda: self.switch_plot("S1"))
            self.s1_btn.pack(side=tk.LEFT, padx=2)
            self.st_btn = tk.Button(btn_frame, text="ST", width=5, command=lambda: self.switch_plot("ST"))
            self.st_btn.pack(side=tk.LEFT, padx=2)
            self.s2_btn = tk.Button(btn_frame, text="S2", width=5, command=lambda: self.switch_plot("S2"))
            self.s2_btn.pack(side=tk.LEFT, padx=2)
            
            calc_s2 = self.project.metadata.get('sa_params', {}).get('calc_second_order', False)
            if not calc_s2:
                self.s2_btn.config(state=tk.DISABLED)

        zoom_frame = ttk.Frame(top_bar)
        zoom_frame.pack(side=tk.LEFT, padx=(20 if self.sa_type == 'Sobol Index' else 0))
        ttk.Button(zoom_frame, text="Zoom In", width=10, command=self.zoom_in).pack(side=tk.LEFT, padx=2)
        ttk.Button(zoom_frame, text="Zoom Out", width=10, command=self.zoom_out).pack(side=tk.LEFT, padx=2)
        ttk.Button(zoom_frame, text="Reset", command=self.zoom_reset).pack(side=tk.LEFT, padx=2)

        self.canvas_frame = ttk.Frame(self)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas_frame.rowconfigure(0, weight=1)
        self.canvas_frame.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.canvas_frame, bg="white")
        self.v_scroll = ttk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        self.h_scroll = ttk.Scrollbar(self.canvas_frame, orient="horizontal", command=self.canvas.xview)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll.grid(row=1, column=0, sticky="ew")

        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        self.canvas.bind("<Motion>", self.on_hover)

        self.update_buttons()

    def update_buttons(self):
        if self.sa_type != 'Sobol Index': return
        self.s1_btn.config(state=tk.DISABLED if self.current_plot == 'S1' else tk.NORMAL)
        self.st_btn.config(state=tk.DISABLED if self.current_plot == 'ST' else tk.NORMAL)
        calc_s2 = self.project.metadata.get('sa_params', {}).get('calc_second_order', False)
        if calc_s2:
            self.s2_btn.config(state=tk.DISABLED if self.current_plot == 'S2' else tk.NORMAL)

    def switch_plot(self, plot_type):
        self.current_plot = plot_type
        self.update_buttons()
        self.draw_plot()

    def draw_plot(self):
        self.fig.clf()
        self.ax = self.fig.add_subplot(111)
        names = self.param_names[::-1]

        if self.current_plot == 'Gradient':
            vals = self.gradients[::-1]
            colors = ['red' if v >= 0 else 'blue' for v in vals]
            self.bars = self.ax.barh(names, vals, color=colors)
            self.plot_values = vals
            self.ax.set_title("Gradient Barplot")
            self.ax.set_xlabel("Partial Derivative")
            fig_width, fig_height = 6 * self.zoom_factor, max(2, len(names) * 0.3) * self.zoom_factor

        elif self.current_plot in ('S1', 'ST'):
            vals = self.Si[self.current_plot][::-1]
            colors = ['skyblue'] if self.current_plot == 'S1' else ['violet']
            self.bars = self.ax.barh(names, vals, color=colors[0])
            self.plot_values = vals
            self.ax.set_title(f"{'First' if self.current_plot == 'S1' else 'Total'} Order Sobol Indices ({self.current_plot})")
            self.ax.set_xlabel(f"{self.current_plot}")
            fig_width, fig_height = 6 * self.zoom_factor, max(2, len(names) * 0.3) * self.zoom_factor

        elif self.current_plot == 'S2':
            n = len(self.param_names)
            s2_data = self.Si['S2']
            self.plot_s2 = np.zeros((n, n))
            self.annot_s2 = [["" for _ in range(n)] for _ in range(n)]
            
            for i in range(n):
                for j in range(n):
                    if i == j:
                        self.plot_s2[i, j] = np.nan
                        self.annot_s2[i][j] = "N/A"
                    elif j > i:
                        val = s2_data[i, j]
                        self.plot_s2[i, j] = val
                        self.plot_s2[j, i] = val
                        self.annot_s2[i][j] = f"{val}"
                        self.annot_s2[j][i] = f"{val}"
                        
            self.im = self.ax.imshow(self.plot_s2, cmap='rainbow')
            self.colorbar = self.fig.colorbar(self.im, ax=self.ax)
            self.ax.set_xticks(range(n))
            self.ax.set_yticks(range(n))
            self.ax.set_xticklabels(self.param_names, rotation=45, ha='right')
            self.ax.set_yticklabels(self.param_names)
            self.ax.set_title("Second Order Sobol Indices (S2)")
            fig_width, fig_height = max(5, len(names) * 0.8) * self.zoom_factor, max(4, len(names) * 0.8) * self.zoom_factor

        self.annot = self.ax.annotate(
            "", xy=(0, 0), xytext=(0, 0), textcoords="offset points",
            ha='center', va='center', fontsize=9,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.9)
        )
        self.annot.set_visible(False)

        self.fig.set_size_inches(fig_width, fig_height)
        self.fig.tight_layout()
        self.render_canvas_image()

    def render_canvas_image(self):
        self.agg = FigureCanvasAgg(self.fig)
        self.agg.draw()
        self.img_width, self.img_height = self.agg.get_width_height()
        image = Image.fromarray(np.asarray(self.agg.buffer_rgba()))
        self.photo = ImageTk.PhotoImage(image)
        self.update_image_position()
        self.canvas.configure(scrollregion=(0, 0, self.img_width, self.img_height))

    def update_image_position(self):
        self.canvas.delete("all")
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        x = max(0, (canvas_width - self.img_width) // 2)
        y = max(0, (canvas_height - self.img_height) // 2)
        self.plot_offset_x = x
        self.plot_offset_y = y
        self.canvas.create_image(x, y, image=self.photo, anchor="nw")

    def on_hover(self, event):
        if not hasattr(self, 'agg'): return
        canvas_scroll_x = self.canvas.canvasx(event.x)
        canvas_scroll_y = self.canvas.canvasy(event.y)
        img_x = canvas_scroll_x - self.plot_offset_x
        img_y = canvas_scroll_y - self.plot_offset_y
        mpl_y = self.img_height - img_y

        class MockEvent:
            def __init__(self, x, y, inaxes):
                self.x, self.y, self.inaxes = x, y, inaxes

        bbox = self.ax.get_window_extent()
        inaxes = self.ax if bbox.contains(img_x, mpl_y) else None
        mock_event = MockEvent(img_x, mpl_y, inaxes)

        vis = self.annot.get_visible()
        if mock_event.inaxes == self.ax:
            if self.current_plot in ('Gradient', 'S1', 'ST'):
                for bar, val in zip(self.bars, self.plot_values):
                    cont, _ = bar.contains(mock_event)
                    if cont:
                        self.annot.xy = (0, bar.get_y() + bar.get_height() / 2)
                        self.annot.set_text(f"{val}")
                        self.annot.set_ha('center')
                        self.annot.set_visible(True)
                        if not vis or self.current_annot_text != self.annot.get_text():
                            self.current_annot_text = self.annot.get_text()
                            self.render_canvas_image()
                        return
            elif self.current_plot == 'S2':
                inv = self.ax.transData.inverted()
                x_data, y_data = inv.transform((mock_event.x, mock_event.y))
                col, row = int(round(x_data)), int(round(y_data))
                if 0 <= col < len(self.param_names) and 0 <= row < len(self.param_names):
                    if self.annot_s2[row][col] != "N/A":
                        self.annot.xy = (col, row)
                        self.annot.set_text(self.annot_s2[row][col])
                        self.annot.set_ha('center')
                        self.annot.set_visible(True)
                        if not vis or self.current_annot_text != self.annot.get_text():
                            self.current_annot_text = self.annot.get_text()
                            self.render_canvas_image()
                        return
                    elif self.annot_s2[row][col] == "N/A":
                        self.annot.xy = (col, row)
                        self.annot.set_text("N/A")
                        self.annot.set_ha('center')
                        self.annot.set_visible(True)
                        if not vis or self.current_annot_text != self.annot.get_text():
                            self.current_annot_text = self.annot.get_text()
                            self.render_canvas_image()
                        return

        if vis:
            self.annot.set_visible(False)
            self.current_annot_text = ""
            self.render_canvas_image()

    def zoom_in(self):
        self.zoom_factor *= 1.2
        self.draw_plot()

    def zoom_out(self):
        self.zoom_factor /= 1.2
        self.draw_plot()

    def zoom_reset(self):
        self.zoom_factor = 1.0
        self.draw_plot()


class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.config(bg="white")
        self.project = None
        self.recorder = None
        self.vision_engine = None
        self.roi_selection = None
        self.recording_paused = False
        self.replay_paused = False
        self.replay_stop_requested = False
        self._replay_thread = None
        self.current_sample_index = 0
        self.in_roi_preview = False
        self.replay_keyboard_listener = None
        
        self.setup_main_menu()

    def center_window(self, width, height):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = int((screen_width - width) / 2)
        y = int((screen_height - height) / 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _add_unique_command(self, cmd, prefix=None):
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
                if i == len(lines) - 1 and cmd.startswith("wait for simulation to finish") and line.startswith("wait "):
                    continue
                f.write(line)
            f.write(cmd + "\n")

    def quit_app(self):
        self._stop_replay_keyboard_listener()
        if self.recorder:
            try: self.recorder.stop_and_save()
            except: pass
        self.root.quit()
        self.root.destroy()
        sys.exit(0)

    def setup_main_menu(self):
        for widget in self.root.winfo_children(): widget.destroy()
        self.root.title("SA Automation")
        self.project = None
        self.recorder = None
        self.vision_engine = None
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)

        self.center_window(500, 600)
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(main_frame, text="Sensitivity Analysis Automation", font=("Arial", 14), bg="white").pack(pady=20)
        tk.Button(main_frame, text="Start new SA", command=self.start_new_sa, width=20, bg="white").pack(pady=10)
        tk.Button(main_frame, text="Open existing SA", command=self.open_existing_sa, width=20, bg="white").pack()

    def open_existing_sa(self):
        folder = filedialog.askdirectory()
        if not folder: return
        
        self.project = Project(folder)
        if not self.project.load():
            messagebox.showerror("Error", "Failed to load project. Project data might be corrupted or incomplete.")
            self.setup_main_menu()
            return
        
        err = self.project.validate()
        if err:
            messagebox.showerror("Invalid Project", err)
            self.setup_main_menu()
            return
        
        self.vision_engine = VisionEngine(self.project.folder_path)
        self.show_project_dashboard()

    def continue_recording_actions(self):
        cmd_file = os.path.join(self.project.folder_path, "commands.txt")
        self.recorder = TextRecorder(cmd_file, lambda: self.root.after(0, self.show_recording_menu_from_pause))
        self.vision_engine = VisionEngine(self.project.folder_path)
        self.recording_paused = True
        self.root.deiconify()
        self.show_recording_menu()

    def show_project_dashboard(self):
        for widget in self.root.winfo_children(): widget.destroy()
        
        self.root.title(f"Project: {self.project.metadata['name']}")
        self.root.protocol("WM_DELETE_WINDOW", self.setup_main_menu)
        self.center_window(1100, 900)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)

        # Top Bar containing Status and Additional ROI toggler
        top_bar = tk.Frame(main_frame, bg="white")
        top_bar.pack(fill=tk.X, pady=5)
        
        status_colors = {"Setup": "grey", "In progress": "orange", "Completed": "green"}
        status_color = status_colors.get(self.project.metadata['status'], 'black')

        stat_frame = tk.Frame(top_bar, bg="white")
        stat_frame.pack(side=tk.LEFT)
        tk.Label(stat_frame, text="Status:", font=("Arial", 10, "bold"), fg="black", bg="white").pack(side=tk.LEFT)
        tk.Label(stat_frame, text=self.project.metadata['status'], font=("Arial", 10, "bold"), fg=status_color, bg="white").pack(side=tk.LEFT)
        
        if self.project.metadata['status'] == "Setup":
            tk.Button(stat_frame, text="Continue recording actions", bg="lightblue",
                      command=self.continue_recording_actions).pack(side=tk.LEFT, padx=10)
        elif self.project.metadata['status'] == "In progress":
            tk.Button(stat_frame, text="Continue simulation runs", bg="lightblue",
                      command=self.resume_sims).pack(side=tk.LEFT, padx=10)

        roi_frame = tk.Frame(top_bar, bg="white")
        roi_frame.pack(side=tk.RIGHT)
        tk.Label(roi_frame, text=f"Additional ROI status: {self.project.metadata['additional_roi_status']}", bg="white").pack(side=tk.LEFT)
        btn_text = "Stop capturing" if self.project.metadata['additional_roi_status'] == "capturing" else "Resume capturing"
        tk.Button(roi_frame, text=btn_text, bg="white", command=self.toggle_additional_roi).pack(side=tk.LEFT, padx=10)
        
        # Info frame
        info_frame = tk.Frame(main_frame, bg="white")
        info_frame.pack(fill=tk.X, pady=5)
        info_frame_text = (f"SA type: {self.project.metadata.get('sa_type', '-')}"
                           f"{' (Including Second Order)' if self.project.metadata.get('sa_params', {}).get('calc_second_order', False) else ''}"
                           "          "
                           f"Simulation runs performed: {self.project.metadata.get('n_completed')}/{self.project.metadata.get('n_required')}          "
                           f"Colormap: {self.project.metadata.get('colormap', {}).get('name', '-')}")
        tk.Label(info_frame, text=info_frame_text, bg="white").pack(side=tk.LEFT, padx=0)
        
        # Parameter Table
        table_frame = tk.Frame(main_frame, bg="white")
        table_frame.pack(fill=tk.X, pady=10)
        tk.Label(table_frame, text="Parameter Settings Used in This SA", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W, padx=0, pady=0)
        
        sa_type = self.project.metadata.get('sa_type', '')
        headers = ["Name", "Range"]
        if sa_type == 'Local Gradient Calculation': headers += ["Point", "Step"]
        
        param_tree = EditableTreeview(table_frame, columns=headers, editable_cols=[], tree_height=3, col_widths={"Range": 450})
        param_tree.pack(fill=tk.X, padx=(3,3), pady=5)
        
        data = []
        for pname, bounds in self.project.metadata['params'].items():
            row = [pname, f"[{bounds['min']}, {bounds['max']}]"]
            if sa_type == 'Local Gradient Calculation':
                grad_params = self.project.metadata.get('sa_params', {}).get(pname, {})
                row.extend([grad_params.get('point', ''), grad_params.get('step', '')])
            data.append(row)
        param_tree.populate(data)

        # Embedded Results
        if self.project.metadata['status'] == "Completed":
            if np.any(np.isnan(self.project.results)):
                tk.Label(main_frame, text="Simulation runs contain NaN results. Cannot generate SA report.", fg="red", bg="white").pack(pady=10)
            else:
                res_frame = tk.Frame(main_frame, bg="white")
                res_frame.pack(fill=tk.BOTH, expand=True, pady=0)
                tk.Label(res_frame, text="Sensitivity Analysis Results", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W, pady=(0, 0))
                tk.Label(res_frame, text="Statistics Over Function Values", font=("Arial", 10), bg="white").pack(anchor=tk.W, pady=(0, 5))

                plot_viewer = SAViewer(res_frame, self.project)
                
                stats_tree = EditableTreeview(res_frame, columns=["Min", "Max", "Mean", "Median", "STD", "MAD"], editable_cols=[], tree_height=1)
                stats_tree.pack(fill=tk.X, padx=(3,3), pady=(0, 5))
                st = plot_viewer.stats
                stats_tree.populate([[f"{st['Min']}", f"{st['Max']}", f"{st['Mean']}", f"{st['Median']}", f"{st['STD']}", f"{st['MAD']}"]])

                plot_viewer.pack(fill=tk.BOTH, expand=True, padx=(3,3))

        tk.Button(main_frame, text="Back to Main Menu", bg="white", command=self.setup_main_menu).pack(side=tk.BOTTOM, pady=10)

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
            self.root.iconify()
            self.replay_paused = False
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
        self.show_completion_indicator_choice()

    def show_completion_indicator_choice(self):
        for widget in self.root.winfo_children(): widget.destroy()
        self.root.title(f"Set Simulation Completion Indicator | {self.project.metadata['name']}")
        self.root.protocol("WM_DELETE_WINDOW", self.show_recording_menu)
        self.center_window(400, 125)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=20, padx=20)
            
        btn_frame = tk.Frame(main_frame, bg="white")
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="Timeout Only", command=self.show_timeout_only_input, bg="white", width=15).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Image + Timeout", command=lambda: self.start_roi_selection("completion_indicator"), bg="white", width=15).pack(side=tk.LEFT, padx=10)
        
        tk.Button(main_frame, text="Back", command=self.show_recording_menu, bg="white").pack(side=tk.BOTTOM, pady=10)
    
    def show_timeout_only_input(self):
        for widget in self.root.winfo_children(): widget.destroy()
        self.root.title(f"Timeout Configuration | {self.project.metadata['name']}")
        self.root.protocol("WM_DELETE_WINDOW", self.show_completion_indicator_choice)
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
                for f in os.listdir(self.project.folder_path):
                    if f.startswith("simulation_completion_indicator"):
                        os.remove(os.path.join(self.project.folder_path, f))
                self.show_recording_menu()
            except ValueError:
                messagebox.showerror("Error", "Please enter a valid number")
        
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(side=tk.BOTTOM, pady=10)
        tk.Button(button_frame, text="Confirm", command=on_confirm, bg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Back", command=self.show_completion_indicator_choice, bg="white").pack(side=tk.LEFT, padx=5)
        
        timeout_entry.bind("<Return>", lambda e: on_confirm())

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
        self.root.protocol("WM_DELETE_WINDOW", self.setup_main_menu)
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
        self.show_recording_menu()

    def show_recording_menu(self):
        for widget in self.root.winfo_children(): widget.destroy()
        self.root.title(f"Recording Menu (Paused) | {self.project.metadata['name']}")
        self.root.protocol("WM_DELETE_WINDOW", self.setup_main_menu)
        self.center_window(500, 700)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        tk.Button(main_frame, text="Add new parameter", command=self.add_param_ui, bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Edit parameters", command=self.edit_param_ui, bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Set simulation completion indicator", command=self.capture_completion_indicator, bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Capture region of interest", command=lambda: self.start_roi_selection("main_roi"), bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Capture additional region of interest", command=lambda: self.start_roi_selection("additional_roi"), bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Select colormap", command=self.show_colormap_selection, bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Select colormap min value field", command=lambda: self.select_colormap_value_field("min"), bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Select colormap max value field", command=lambda: self.select_colormap_value_field("max"), bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="View command file", command=self.view_cmd_file, bg="white").pack(fill=tk.X, padx=20, pady=5)
        tk.Button(main_frame, text="Configure SA type", command=self.sa_setup_ui, bg="white").pack(fill=tk.X, padx=20, pady=5)
        
        tk.Button(main_frame, text="Resume recording", bg="lightblue", 
                  command=self.resume_recording).pack(fill=tk.X, padx=20, pady=10)
        tk.Button(main_frame, text="Save and start running simulations", bg="green", fg="white", 
                  command=self.start_running).pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=10)
        
    def resume_recording(self):
        self.recording_paused = False
        self.root.iconify()
        if self.recorder:
            self.recorder.start()

    def show_colormap_selection(self):
        for widget in self.root.winfo_children(): widget.destroy()
        self.root.title(f"Select Colormap | {self.project.metadata['name']}")
        self.root.protocol("WM_DELETE_WINDOW", self.show_recording_menu)
        self.center_window(400, 180)
        self.root.config(bg="white")

        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=20, padx=20)

        tk.Label(main_frame, text="Choose colormap:", font=("Arial", 12), bg="white").pack(anchor=tk.W, pady=(0, 10))
        cmap_var = tk.StringVar(value=self.project.metadata.get('colormap').get('name', "viridis"))
        cmap_dropdown = ttk.Combobox(main_frame, textvariable=cmap_var, values=['viridis', 'turbo'], state='readonly', width=20, justify="center")
        cmap_dropdown.pack(fill=tk.X, pady=5)

        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=15)

        def on_ok():
            self.project.metadata['colormap']['name'] = cmap_var.get()
            self.project.save()
            self.show_recording_menu()

        tk.Button(button_frame, text="Ok", command=on_ok, bg="lightgreen").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        tk.Button(button_frame, text="Cancel", command=self.show_recording_menu, bg="lightcoral").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

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
        self.root.protocol("WM_DELETE_WINDOW", self.stop_replay)
        self.center_window(500, 200)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        tk.Label(main_frame, text=f"Replay paused at sample {self.current_sample_index + 1} of {len(self.project.samples)}", 
                bg="white", font=("Arial", 12)).pack(pady=20)
        
        tk.Button(main_frame, text="Resume running simulations", bg="lightgreen", fg="white", 
                  command=self.resume_replay).pack(fill=tk.X, padx=20, pady=10)
        
        tk.Button(main_frame, text="Stop and return to main menu", bg="lightcoral", fg="white", 
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
        self.root.protocol("WM_DELETE_WINDOW", self.show_recording_menu)
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
        self.root.protocol("WM_DELETE_WINDOW", self.show_recording_menu)
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
                if mn >= mx: raise ValueError("Min > Max")
                param_name = name_ent.get().strip()
                
                if param_name in self.project.metadata['params']:
                    messagebox.showerror("Error", f"Parameter '{param_name}' already exists.")
                    return
                
                self.project.metadata['params'][param_name] = {"min": mn, "max": mx}
                self.project.save()
                self._add_unique_command(f"enter value for {param_name}")
                self.show_recording_menu()
            except ValueError:
                messagebox.showerror("Error", "Invalid float or Min >= Max")
        
        button_frame = tk.Frame(main_frame, bg="white")
        button_frame.grid(row=3, column=0, columnspan=2, pady=20)
        tk.Button(button_frame, text="Save", command=save, bg="white").pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", command=self.show_recording_menu, bg="white").pack(side=tk.LEFT, padx=10)

    def edit_param_ui(self):
        for widget in self.root.winfo_children(): widget.destroy()
        self.root.title("Edit Parameters")
        self.root.protocol("WM_DELETE_WINDOW", self.show_recording_menu)
        self.center_window(700, 500)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        tk.Label(main_frame, text="Parameter Settings", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W, pady=10)
        
        table_frame = tk.Frame(main_frame, bg="white", relief=tk.SUNKEN, borderwidth=1)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=10)

        columns = ["Original Name", "Name", "Min", "Max"]
        self.param_tree = EditableTreeview(
            table_frame, 
            columns=columns, 
            display_columns=["Name", "Min", "Max"], 
            editable_cols=[0, 1, 2], 
            tree_height=min(10, max(1, len(self.project.metadata['params']))), 
            allow_delete=True
        )
        self.param_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        data = []
        for p_name, bounds in self.project.metadata['params'].items():
            data.append([p_name, p_name, bounds['min'], bounds['max']])
        self.param_tree.populate(data)

        actions_frame = tk.Frame(main_frame, bg="white")
        actions_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        def on_save_clicked():
            self.param_tree.commit_editor()
            try:
                new_data = self.param_tree.get_data()
                old_params = self.project.metadata['params']
                sa_type = self.project.metadata.get('sa_type')
                sa_params = self.project.metadata.get('sa_params', {})
                
                new_params = {}
                sa_discarded = False
                current_orig_names = []

                for row in new_data:
                    orig_name = str(row[0]).strip()
                    new_name = str(row[1]).strip()
                    if not new_name: continue

                    if new_name in new_params:
                        messagebox.showerror("Validation Error", f"Duplicate parameter name: '{new_name}'")
                        return
                    
                    min_val = float(row[2])
                    max_val = float(row[3])
                    
                    if min_val >= max_val:
                        messagebox.showerror("Validation Error", f"Parameter '{new_name}': Min value must be less than Max value")
                        return
                        
                    new_params[new_name] = {"min": min_val, "max": max_val}
                    current_orig_names.append(orig_name)
                    
                    if orig_name in old_params:
                        old_min = old_params[orig_name]['min']
                        old_max = old_params[orig_name]['max']
                        
                        if min_val != old_min or max_val != old_max:
                            if sa_type == 'Sobol Index':
                                sa_discarded = True
                            elif sa_type == 'Local Gradient Calculation':
                                grad_p = sa_params.get(orig_name)
                                if grad_p:
                                    pt = grad_p['point']
                                    st = grad_p['step']
                                    if pt - st < min_val or pt + st > max_val:
                                        sa_discarded = True
                                else:
                                    sa_discarded = True
                
                for old_p in old_params:
                    if old_p not in current_orig_names:
                        sa_discarded = True

                if sa_discarded:
                    self.project.metadata['sa_type'] = None
                    self.project.metadata['sa_params'] = {}
                    self.project.metadata['n_required'] = "-"
                    self.project.metadata['n_completed'] = 0
                    self.project.samples = np.array([[]])
                    self.project.results = np.array([])
                else:
                    new_sa_params = {}
                    for row in new_data:
                        orig_name = str(row[0]).strip()
                        new_name = str(row[1]).strip()
                        if orig_name in sa_params:
                            new_sa_params[new_name] = sa_params[orig_name]
                    for k, v in sa_params.items():
                        if k not in old_params: 
                            new_sa_params[k] = v
                    self.project.metadata['sa_params'] = new_sa_params

                cmd_file = os.path.join(self.project.folder_path, "commands.txt")
                if os.path.exists(cmd_file):
                    with open(cmd_file, "r") as f:
                        lines = f.readlines()
                        
                    new_lines = []
                    for line in lines:
                        keep = True
                        for old_p in old_params:
                            if old_p not in current_orig_names:
                                if line.strip().startswith(f"enter value for {old_p}"):
                                    keep = False
                        
                        if keep:
                            for row in new_data:
                                orig_name = str(row[0]).strip()
                                new_name = str(row[1]).strip()
                                if orig_name and orig_name != new_name:
                                    if line.strip().startswith(f"enter value for {orig_name}"):
                                        line = line.replace(f"enter value for {orig_name}", f"enter value for {new_name}")
                            new_lines.append(line)
                            
                    with open(cmd_file, "w") as f:
                        f.writelines(new_lines)

                self.project.metadata['params'] = new_params
                self.project.save()
                messagebox.showinfo("Success", "Parameter changes saved successfully")
                if sa_discarded: messagebox.showwarning("SA Configuration Discarded", "Modifications to parameters invalidated the existing SA configuration. It has been cleared.")
                self.edit_param_ui()
            except ValueError:
                messagebox.showerror("Validation Error", "Min and Max values must be valid numbers")
        
        tk.Button(actions_frame, text="Save Changes", bg="lightgreen", command=on_save_clicked).pack(side=tk.RIGHT, padx=5)
        tk.Button(actions_frame, text="Back", bg="white", command=self.show_recording_menu).pack(side=tk.RIGHT, padx=5)

    def sa_setup_ui(self):
        for widget in self.root.winfo_children(): widget.destroy()
        
        self.root.title("SA Setup")
        self.root.protocol("WM_DELETE_WINDOW", self.show_recording_menu)
        self.center_window(500, 550)
        self.root.config(bg="white")
        
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, pady=20, padx=20)
        
        tk.Label(main_frame, text="SA Type:", font=("Arial", 10, "bold"), bg="white").pack(pady=10)
        type_var = tk.StringVar(value=self.project.metadata.get('sa_type', ''))
        
        sa_types = ['Sobol Index', 'Local Gradient Calculation']
        cb = ttk.Combobox(main_frame, textvariable=type_var, values=sa_types, state='readonly', justify="center")
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
                n_dropdown = ttk.Combobox(param_frame, textvariable=n_var, values=[str(p) for p in powers_of_2], state='readonly', justify="center")
                n_dropdown.pack()
                param_frame.sobol_n = n_var
                
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
                table_frame.pack(fill=tk.BOTH, expand=True)

                columns = ["Name", "Range", "Point", "Step"]
                self.grad_tree = EditableTreeview(table_frame, columns=columns, editable_cols=[2, 3], tree_height=min(8, max(1, len(self.project.metadata['params']))), allow_delete=False, col_widths={"Range": 300})
                self.grad_tree.pack(fill=tk.BOTH, expand=True)
                
                saved_grad_params = self.project.metadata.get('sa_params', {}) if self.project.metadata.get('sa_type') == 'Local Gradient Calculation' else {}
                data = []
                for param_name, bounds in self.project.metadata['params'].items():
                    default_point = saved_grad_params.get(param_name, {}).get('point', (bounds['min'] + bounds['max']) / 2)
                    default_step = saved_grad_params.get(param_name, {}).get('step', 0.1)
                    data.append([param_name, f"[{bounds['min']}, {bounds['max']}]", default_point, default_step])
                self.grad_tree.populate(data)
                param_frame.grad_tree = self.grad_tree
        
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
            
            if sa_type == 'Sobol Index':
                if sobol_sample is None:
                    messagebox.showerror("Error", "SALib not installed. Install with: pip install SALib")
                    return
                sobol_n = int(frame.sobol_n.get())
                calc_second_order = frame.calc_second_order.get()
                samples = sobol_sample(problem, sobol_n, calc_second_order=calc_second_order, seed=SOBOL_SAMPLE_SEED)
                self.project.metadata['sa_params'] = {'sobol_n': sobol_n, 'calc_second_order': calc_second_order}
            elif sa_type == 'Local Gradient Calculation':
                if hasattr(frame, 'grad_tree'):
                    frame.grad_tree.commit_editor()
                    data = frame.grad_tree.get_data()
                    gradient_params = {}
                    for row in data:
                        param_name = str(row[0])
                        point, step = float(row[2]), float(row[3])
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
                
        self.project.metadata['status'] = "In progress"
        self.project.results = np.array([np.nan] * len(self.project.samples))
        self.project.save()

        self.root.iconify()
        self.replay_paused = False
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
                    return
                except TimeoutError as e:
                    self.cleanup_partial_simulation_run_results()
                    self.replay_paused = True
                    self.root.after(0, lambda: self._show_timeout_error(str(e)))
                    continue
                except PauseRequested:
                    self.cleanup_partial_simulation_run_results()
                    self.replay_paused = True
                    self.root.after(0, self._show_replay_paused_ui)
                    continue
                
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