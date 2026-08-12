# About

This repository contains the source code of the software application developed by me as part of my Master's Thesis at RWTH Aachen University from April to August 2026. The full thesis' title is: **Automating Image-Based Sensitivity Analysis for GUI-Based Black-Box Simulation Software**. Please find the description of the application in the [Master's Thesis Report](Master_Thesis.pdf).

# Demo Video

I have recorded a video demonstrating how to perform a single full sensitivity analysis workflow (from creating a new project to viewing the results) in [SimFlow](https://sim-flow.com/) for the [Internal Pipe Flow example simulation project](https://help.sim-flow.com/tutorials/pipe-flow):

<p align="center">
  <a href="https://youtu.be/kp1RgoEh6Ws">
    <img src="https://img.youtube.com/vi/kp1RgoEh6Ws/maxresdefault.jpg" alt="Watch Video" width="700"/>
  </a>
</p>

# Installation

## Prerequisites
- Python 3.13.13+ (developed and tested with Python 3.13.13)
- git

## Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/alekseilemberrwth/gui-sa-automation.git
   cd gui-sa-automation
   ```

2. **Create and activate a virtual environment** (recommended)

   **Linux / macOS:**
   ```bash
   python3 -m venv .venv
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

## Launch

Start the application:

```bash
python main.py
```
