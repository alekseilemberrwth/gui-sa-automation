# About

This repository contains the source code of the software application developed as part of a Master's Thesis at RWTH Aachen University from April to August 2026. The thesis's title is: **Automating Image-Based Sensitivity Analysis for GUI-Based Black-Box Simulation Software**.

As follows from the thesis's title, given a simulation software which has a GUI and which renders the output of its simulations as color-coded images, the application is capable of conducting automated sensitivity analysis of the simulations that software performs in a completely non-intrusive fashion by imitating human mouse and keyboard actions to interact with that software's GUI and capturing the output of the simulations directly from the corresponding rendered color-coded visualizations. In order to conduct a single sensitivity analysis of a single simulation a user has to:

1. Show the application how to perform a single simulation run (the user's mouse and keyboard actions will be recorded).
2. Define the simulation input parameters, sensitivity to which the application should analyze, and their corresponding domains (intervals $[min,\ max]$).
3. Select the rectangular region (the Region of Interest) of the simulation software's output color-coded picture. The application will analyze the sensitivity of that image region to the simulation input parameters.
4. Select which kind of sensitivity analysis to perform.

as well as some other actions. When everything is set up, the application will replay user's mouse and keyboard actions to run the same simulation many times with different input parameter values and capture its output (the Region of Interest). After all the necessary simulation runs have been performed, the application will conduct the sensitivity analysis on the obtained simulation input-output pairs.

You can find the full description of the application in the [Master's Thesis Report](Master_Thesis.pdf).

## Demo Video

A video demonstrating how to perform sensitivity analysis for the [SimFlow](https://sim-flow.com/) simulation software (the [Internal Pipe Flow example project](https://help.sim-flow.com/tutorials/pipe-flow)) was recorded and is available on YouTube:

<p align="center">
  <a href="https://youtu.be/kp1RgoEh6Ws">
    <img src="https://img.youtube.com/vi/kp1RgoEh6Ws/maxresdefault.jpg" alt="Watch Video" width="700"/>
  </a>
</p>

# Installation

## Prerequisites
- Python 3.13.13+ (developed and tested with Python 3.13.13)
- pip
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

   **Linux / macOS:**
   ```bash
   python3 main.py
   ```

   **Windows (PowerShell):**
   ```powershell
   python main.py
   ```
