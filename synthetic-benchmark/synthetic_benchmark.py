import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib as mpl
import random
import time

def ishigami(x1, x2, x3, a, b):
    return np.sin(x1) + a * np.sin(x2)**2 + b * (x3**4) * np.sin(x1)

class BenchmarkApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Ishigami Function Simulator")
        self.root.resizable(True, True)  # Make window resizable
        self.root.state('zoomed')  # Start maximized/fullscreen-like on Windows
        self.root.config(bg="white")  # White background
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)  # Handle window close
        
        # Apply ttk styles ("vista" theme + white backgrounds)
        self.style = ttk.Style()
        try:
            self.style.theme_use("vista")
        except tk.TclError:
            pass
        self.style.configure("TLabel", background="white")
        self.style.configure("TFrame", background="white")
        self.style.configure("TCheckbutton", background="white")
        
        self.defaults = {
            'x1': 1.0,
            'x2': 1.0,
            'x3': 1.0,
            'colormap': 'viridis',
            'a_min': 5,
            'a_max': 9,
            'b_min': -0.4,
            'b_max': 0.6,
            'a_bins': 1670, # 1670x1009 is the size in pixels of the plot area on my pc
            'b_bins': 1009,
            'colorbar_min': '',
            'colorbar_max': '',
            'sim_time_min': 0.0,
            'sim_time_max': 4.0,
        }
        self.current = self.defaults.copy()
        
        # Layout using grid for better resizing
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=0, minsize=250)  # Left column fixed width
        self.root.grid_columnconfigure(1, weight=1)
        
        # Left Panel: Inputs
        left_frame = ttk.Frame(root)
        # Using fixed width doesn't easily translate automatically with ttk.Frame without config tricks,
        # but we handle sizing via grid properties anyway.
        left_frame.grid(row=0, column=0, sticky='ns')
        
        ttk.Label(left_frame, text="Ishigami Function", font=("Arial", 14, "bold")).pack(pady=10)
        
        # LaTeX formula using matplotlib
        self.formula_fig = plt.Figure(figsize=(2.5, 0.5), facecolor='white')
        self.formula_ax = self.formula_fig.add_subplot(111)
        self.formula_ax.text(0.5, 0.5, r'$y = \sin(x_1) + a \cdot \sin^2(x_2) + b \cdot x_3^4 \cdot \sin(x_1)$', fontsize=9, ha='center', va='center')
        self.formula_ax.set_xlim(0, 1)
        self.formula_ax.set_ylim(0, 1)
        self.formula_ax.axis('off')
        # Match background color
        self.formula_fig.set_facecolor('white')
        self.formula_ax.set_facecolor('white')
        self.formula_canvas = FigureCanvasTkAgg(self.formula_fig, master=left_frame)
        self.formula_canvas.get_tk_widget().pack(pady=(0, 0))
        
        ttk.Label(left_frame, text="Function Parameters", font=("Arial", 14, "bold")).pack(pady=4)
        
        self.vars = {}
        for param in ['x1', 'x2', 'x3']:
            param_frame = ttk.Frame(left_frame)
            param_frame.pack(pady=5)
            ttk.Label(param_frame, text=f"{param}:").pack(side=tk.LEFT)
            var = tk.StringVar(value=str(self.current[param]))
            ttk.Entry(param_frame, textvariable=var, width=10).pack(side=tk.LEFT)
            self.vars[param] = var
            
        ttk.Label(left_frame, text="Plot Parameters", font=("Arial", 14, "bold")).pack(pady=(15, 10))
        
        a_min_frame = ttk.Frame(left_frame)
        a_min_frame.pack(pady=5)
        ttk.Label(a_min_frame, text="a min:").pack(side=tk.LEFT)
        self.a_min_var = tk.StringVar(value=str(self.current['a_min']))
        ttk.Entry(a_min_frame, textvariable=self.a_min_var, width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        a_max_frame = ttk.Frame(left_frame)
        a_max_frame.pack(pady=5)
        ttk.Label(a_max_frame, text="a max:").pack(side=tk.LEFT)
        self.a_max_var = tk.StringVar(value=str(self.current['a_max']))
        ttk.Entry(a_max_frame, textvariable=self.a_max_var, width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        b_min_frame = ttk.Frame(left_frame)
        b_min_frame.pack(pady=5)
        ttk.Label(b_min_frame, text="b min:").pack(side=tk.LEFT)
        self.b_min_var = tk.StringVar(value=str(self.current['b_min']))
        ttk.Entry(b_min_frame, textvariable=self.b_min_var, width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        b_max_frame = ttk.Frame(left_frame)
        b_max_frame.pack(pady=5)
        ttk.Label(b_max_frame, text="b max:").pack(side=tk.LEFT)
        self.b_max_var = tk.StringVar(value=str(self.current['b_max']))
        ttk.Entry(b_max_frame, textvariable=self.b_max_var, width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        a_bins_frame = ttk.Frame(left_frame)
        a_bins_frame.pack(pady=5)
        ttk.Label(a_bins_frame, text="a bins:").pack(side=tk.LEFT)
        self.a_bins_var = tk.StringVar(value=str(self.current['a_bins']))
        ttk.Entry(a_bins_frame, textvariable=self.a_bins_var, width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        b_bins_frame = ttk.Frame(left_frame)
        b_bins_frame.pack(pady=5)
        ttk.Label(b_bins_frame, text="b bins:").pack(side=tk.LEFT)
        self.b_bins_var = tk.StringVar(value=str(self.current['b_bins']))
        ttk.Entry(b_bins_frame, textvariable=self.b_bins_var, width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        # Colormap
        cmap_frame = ttk.Frame(left_frame)
        cmap_frame.pack(pady=10)
        ttk.Label(cmap_frame, text="Colormap:").pack(side=tk.LEFT)
        self.cmap_var = tk.StringVar(value=self.current['colormap'])
        cmaps = ttk.Combobox(cmap_frame, textvariable=self.cmap_var, values=['viridis', 'turbo', 'binary', 'gray'], width=10, state="readonly")
        cmaps.pack(side=tk.LEFT)
        
        # Colorbar min max
        min_frame = ttk.Frame(left_frame)
        min_frame.pack(pady=5)
        ttk.Label(min_frame, text="Colorbar min:").pack(side=tk.LEFT)
        self.min_var = tk.StringVar()
        ttk.Entry(min_frame, textvariable=self.min_var, width=10).pack(side=tk.LEFT)
        
        max_frame = ttk.Frame(left_frame)
        max_frame.pack(pady=5)
        ttk.Label(max_frame, text="Colorbar max:").pack(side=tk.LEFT)
        self.max_var = tk.StringVar(value=self.current['colorbar_max'])
        ttk.Entry(max_frame, textvariable=self.max_var, width=10).pack(side=tk.LEFT)
        
        sim_min_frame = ttk.Frame(left_frame)
        sim_min_frame.pack(pady=5)
        ttk.Label(sim_min_frame, text="Simulation time min (s):").pack(side=tk.LEFT)
        self.sim_time_min_var = tk.StringVar(value=str(self.current['sim_time_min']))
        ttk.Entry(sim_min_frame, textvariable=self.sim_time_min_var, width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        sim_max_frame = ttk.Frame(left_frame)
        sim_max_frame.pack(pady=5)
        ttk.Label(sim_max_frame, text="Simulation time max (s):").pack(side=tk.LEFT)
        self.sim_time_max_var = tk.StringVar(value=str(self.current['sim_time_max']))
        ttk.Entry(sim_max_frame, textvariable=self.sim_time_max_var, width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        self.update_plot_button = ttk.Button(left_frame, text="Update plot", command=self.update_plot)
        self.update_plot_button.pack(pady=10)
        self.reset_parameters_button = ttk.Button(left_frame, text="Reset parameters", command=self.reset_parameters)
        self.reset_parameters_button.pack(pady=(0, 10))
        self.run_sim_button = ttk.Button(left_frame, text="Run simulation", command=self.run_sim)
        self.run_sim_button.pack(side=tk.BOTTOM, pady=20)

        self.progress_frame = ttk.Frame(left_frame)
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient="horizontal", mode="determinate", maximum=100)
        self.progress_bar.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(10, 0))
        self.progress_percent_label = ttk.Label(self.progress_frame, text="0%", width=4, anchor='e')
        self.progress_percent_label.pack(side=tk.RIGHT, padx=(5, 0))
        self.progress_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        self.progress_frame.pack_forget()

        # Right Panel: Output Image
        self.right_frame = tk.Frame(root, bg="white")
        self.right_frame.grid(row=0, column=1, sticky='nsew')
        self.fig, self.ax = plt.subplots(figsize=(5, 5))
        self.fig.set_facecolor('white')
        self.ax.set_facecolor('white')
        self.ax.set_xlabel('Parameter a')
        self.ax.set_ylabel('Parameter b')
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.right_frame)
        self.canvas.get_tk_widget().pack(expand=True, fill=tk.BOTH)
        
        # Bind resize event to redraw
        self.root.bind('<Configure>', self.on_resize)
        
        self.Z = None  # Store the data for updating

    def run_sim(self):
        self.show_progress()
        # Deactivate buttons to prevent multiple runs
        self.update_plot_button.config(state="disabled")
        self.reset_parameters_button.config(state="disabled")
        self.run_sim_button.config(state="disabled")

        self.root.update_idletasks()

        try:
            self.update_current_from_inputs()
        except ValueError:
            messagebox.showerror("Error", "Invalid input parameters")
            self.hide_progress()
            return

        self.sim_delay = random.uniform(self.current['sim_time_min'], self.current['sim_time_max'])
        self.sim_start_time = time.time()

        if self.sim_delay <= 0:
            self.finish_simulation()
        else:
            self._advance_progress()

    def update_plot(self):
        try:
            self.update_current_from_inputs()
            # Validate colorbar min and max
            if self.current['colorbar_min'].strip():
                float(self.current['colorbar_min'])
            if self.current['colorbar_max'].strip():
                float(self.current['colorbar_max'])
            self.compute_data()
            vmin = None
            vmax = None
            try:
                vmin = float(self.current['colorbar_min'])
            except (ValueError, TypeError):
                vmin = None
            try:
                vmax = float(self.current['colorbar_max'])
            except (ValueError, TypeError):
                vmax = None
            self.draw_data(vmin=vmin, vmax=vmax)
            messagebox.showinfo("Success", "The plot has been updated with the new parameters.")
        except ValueError:
            messagebox.showerror("Error", "Invalid plot parameters")

    def _advance_progress(self):
        elapsed = time.time() - self.sim_start_time
        percentage = min(100, int(elapsed / self.sim_delay * 100))
        self.progress_bar['value'] = percentage
        self.progress_percent_label.config(text=f"{percentage}%")
        self.root.update_idletasks()

        if elapsed >= self.sim_delay:
            self.finish_simulation()
        else:
            self.root.after(50, self._advance_progress)

    def finish_simulation(self):
        try:
            self.compute_data()
        except ValueError:
            messagebox.showerror("Error", "Invalid function parameters")
            self.hide_progress()
            return

        self.current['colorbar_min'] = f"{self.Z.min()}"
        self.current['colorbar_max'] = f"{self.Z.max()}"
        self.min_var.set(self.current['colorbar_min'])
        self.max_var.set(self.current['colorbar_max'])
        self.draw_data()
        self.progress_bar['value'] = 100
        self.progress_percent_label.config(text="100%")
        self.hide_progress()
        messagebox.showinfo("Success", "Simulation completed!")
        # Reactivate buttons
        self.update_plot_button.config(state="normal")
        self.reset_parameters_button.config(state="normal")
        self.run_sim_button.config(state="normal")


    def show_progress(self):
        if not self.progress_frame.winfo_ismapped():
            self.progress_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        self.progress_bar['value'] = 0
        self.progress_percent_label.config(text="0%")

    def hide_progress(self):
        self.progress_frame.pack_forget()
        self.progress_bar['value'] = 0
        self.progress_percent_label.config(text="0%")

    def compute_data(self):
        a = np.linspace(self.current['a_min'], self.current['a_max'], self.current['a_bins'])
        b = np.linspace(self.current['b_min'], self.current['b_max'], self.current['b_bins'])
        A, B = np.meshgrid(a, b)
        self.Z = ishigami(self.current['x1'], self.current['x2'], self.current['x3'], A, B)
        # print('Meshgrid A:')
        # print(A)
        # print('Meshgrid B:')
        # print(B)

    def draw_data(self, vmin=None, vmax=None):
        if self.Z is None:
            return
        # Ensure the Matplotlib figure matches the Tk canvas pixel size
        canvas_widget = self.canvas.get_tk_widget()
        canvas_width = canvas_widget.winfo_width()
        canvas_height = canvas_widget.winfo_height()
        if canvas_width > 1 and canvas_height > 1:
            width_inches = canvas_width / self.fig.dpi
            height_inches = canvas_height / self.fig.dpi
            self.fig.set_size_inches(width_inches, height_inches)
            # print(f"Resizing figure to {width_inches:.2f}x{height_inches:.2f} inches for canvas size {canvas_width}x{canvas_height} pixels")
            self.fig.tight_layout()
        if vmin is None:
            try:
                vmin = float(self.current['colorbar_min'])
            except (ValueError, TypeError):
                vmin = self.Z.min()
        if vmax is None:
            try:
                vmax = float(self.current['colorbar_max'])
            except (ValueError, TypeError):
                vmax = self.Z.max()
        self.ax.clear()
        self.ax.set_facecolor('white')
        c = self.ax.imshow(self.Z, extent=[self.current['a_min'], self.current['a_max'], self.current['b_min'], self.current['b_max']], origin='lower', cmap=self.current['colormap'], vmin=vmin, vmax=vmax)
        if not hasattr(self, 'cbar'):
            self.cbar = self.fig.colorbar(c, ax=self.ax)
        else:
            self.cbar.update_normal(c)
        self.ax.set_xlabel('Parameter a')
        self.ax.set_ylabel('Parameter b')
        # Let the axes fill the canvas shape instead of forcing a square
        self.ax.set_aspect('auto')
        self.canvas.draw()

        self.root.update_idletasks()  # Ensure the canvas updates
        
        # plt.show()

    def update_current_from_inputs(self):
        self.current['x1'] = float(self.vars['x1'].get())
        self.current['x2'] = float(self.vars['x2'].get())
        self.current['x3'] = float(self.vars['x3'].get())
        self.current['a_min'] = float(self.a_min_var.get())
        self.current['a_max'] = float(self.a_max_var.get())
        self.current['b_min'] = float(self.b_min_var.get())
        self.current['b_max'] = float(self.b_max_var.get())
        self.current['a_bins'] = max(1, int(self.a_bins_var.get()))
        self.current['b_bins'] = max(1, int(self.b_bins_var.get()))
        self.current['colormap'] = self.cmap_var.get()
        self.current['colorbar_min'] = self.min_var.get().strip()
        self.current['colorbar_max'] = self.max_var.get().strip()
        self.current['sim_time_min'] = float(self.sim_time_min_var.get())
        self.current['sim_time_max'] = float(self.sim_time_max_var.get())

    def apply_current_to_controls(self):
        self.vars['x1'].set(str(self.current['x1']))
        self.vars['x2'].set(str(self.current['x2']))
        self.vars['x3'].set(str(self.current['x3']))
        self.a_min_var.set(str(self.current['a_min']))
        self.a_max_var.set(str(self.current['a_max']))
        self.b_min_var.set(str(self.current['b_min']))
        self.b_max_var.set(str(self.current['b_max']))
        self.a_bins_var.set(str(self.current['a_bins']))
        self.b_bins_var.set(str(self.current['b_bins']))
        self.cmap_var.set(self.current['colormap'])
        self.min_var.set(self.current['colorbar_min'])
        self.max_var.set(self.current['colorbar_max'])
        self.sim_time_min_var.set(str(self.current['sim_time_min']))
        self.sim_time_max_var.set(str(self.current['sim_time_max']))

    def reset_parameters(self):
        self.current = self.defaults.copy()
        self.apply_current_to_controls()
        self.compute_data()
        self.draw_data()
        messagebox.showinfo("Success", "All parameters have been reset to their default values.")

    def on_resize(self, event):
        # Get the actual canvas size and adjust figure
        canvas_width = self.canvas.get_tk_widget().winfo_width()
        canvas_height = self.canvas.get_tk_widget().winfo_height()
        if canvas_width > 1 and canvas_height > 1:  # Avoid invalid sizes during init
            width_inches = canvas_width / self.fig.dpi
            height_inches = canvas_height / self.fig.dpi
            self.fig.set_size_inches(width_inches, height_inches)
            self.fig.tight_layout()  # Adjust layout
            self.canvas.draw_idle()

    def on_closing(self):
        self.root.quit()


if __name__ == "__main__":
    root = tk.Tk()
    icon = tk.PhotoImage(file=r"gui-sa-automation\synthetic-benchmark\app_logo.png")
    root.iconphoto(True, icon)
    app = BenchmarkApp(root)
    root.mainloop()