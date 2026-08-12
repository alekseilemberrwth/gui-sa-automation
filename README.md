# GUI-SA-Automation

Automating Image-Based Sensitivity Analysis for GUI-Based Black-Box Simulation Software.

## What this app does

A lightweight, non-intrusive Python application that automates GUI-driven simulation workflows. It:

- **Records and replays** mouse and keyboard actions to operate closed-source GUI simulators (e.g., SimFlow, ElmerFEM, Ansys).
- **Captures color-coded result images** from the simulator's output viewport.
- **Reconstructs scalar values** by inverting colormaps (converting RGB pixels back to underlying numerical data).
- **Computes sensitivity indices** including local gradients (via finite differences) and global variance-based Sobol indices.

All interaction is **external only** — no source code access, APIs, or DLLs required.

## Demo Video

A complete walkthrough video demonstrating the app's full workflow with the **SimFlow Internal Pipe Flow gradient calculation** case study is available as a release asset.

**[Download demo video from the latest release](https://github.com/alekseilemberrwth/gui-sa-automation/releases/latest)**

---

## Installation

### Prerequisites
- Python 3.10+ (developed and tested with Python 3.13)
- git

### Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/alekseilemberrwth/gui-sa-automation.git
   cd gui-sa-automation
   ```

2. **Create and activate a virtual environment** (recommended)

   **Linux / macOS:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

   **Windows (PowerShell):**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

## Launch

Start the application:

```bash
python main.py
```

This launches the GUI. From there you can:

1. **Create a new SA project** and choose a folder to store results.
2. **Record a single simulation run** by interacting with your target simulator:
   - Map parameter input fields to named parameters.
   - Capture a **Simulation Completion Indicator (SCI)** — a small visual template that signals when the solver finishes (e.g., a "Done" window).
   - Select your **Region of Interest (ROI)** — the area of the color-coded output to analyze.
   - Configure the **colormap** and min/max bounds.
3. **Configure sensitivity analysis type** (Gradient or Sobol) and generate sample points.
4. **Save and run** — the app automatically replays your recorded workflow for each sample point, injects parameter values, detects completion, extracts and reconstructs scalar data, and computes indices.
5. **View results** — interactive plots (bar charts for gradients, heatmaps for Sobol interactions).

### Key tips
- Ensure no other apps will steal focus or generate popups during long parametric sweeps.
- Disable color post-processing (anti-aliasing, interpolation) in visualization software to preserve exact RGB values.
- The app auto-saves frequently, so you can safely pause and resume runs.
