# GUI-SA-Automation: Sensitivity Analysis Automation Tool

A comprehensive Python application for automating sensitivity analysis workflows through GUI recording and replay, with support for multiple SA methodologies from SALib.

## Features

### Recording Mode
- **Mouse & Keyboard Recording**: Records user mouse movements and keyboard actions
- **Command-Based Format**: Actions saved in user-friendly .txt format
- **Project Management**: Create new projects with custom parameters
- **ROI Capture**: Support for capturing regions of interest (main and additional)
- **Simulation Completion Detection**: Set visual indicators for simulation completion

### Project Management
- **Parameter Definition**: Define custom parameters with min/max bounds
- **SA Type Selection**: Support for multiple sensitivity analysis methods
- **Project Persistence**: Save and load projects with metadata
- **Additional ROI Management**: Toggle capturing of additional regions during simulation

### Sensitivity Analysis Methods Supported
- Sobol (SALib)
- Morris (SALib)
- Saltelli (SALib)
- Latin Hypercube Sampling (LHS)
- FAST (SALib)
- Gradient-Based Method

### Recording Commands Format
The application supports the following commands in .txt format:
```
move mouse to <x>, <y>          # Move mouse to coordinates
lmb click                       # Left mouse button click
rmb click                       # Right mouse button click
press key <key>                 # Press a keyboard key
release key <key>               # Release a keyboard key
enter value for <PARAM_NAME>    # Inject parameter value
wait for simulation to finish   # Wait for completion indicator
capture the region of interest  # Capture main ROI
capture additional region of interest  # Capture additional ROI
# This is a comment              # Lines starting with # are ignored
```

### Data Visualization
- **Colormap Selection**: Choose from multiple colormaps (viridis, plasma, inferno, etc.)
- **Function Value Mapping**: Map RGB values back to scalar values using colormaps
- **Interactive Reports**: Generate PDF reports with SA results

## Installation

1. Clone the repository:
```bash
cd e:\gui-sa-automation\gui-sa-automation
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Starting a New Sensitivity Analysis

1. Run the application:
```bash
python main.py
```

2. Click "Start new SA"

3. Select an empty folder for your project

4. The recording begins (Press F13 to pause and open menu)

5. In the menu, configure your analysis:
   - **Add parameters**: Define input parameters with ranges
   - **Set simulation completion indicator**: Capture screen region indicating simulation completion
   - **Capture ROI**: Define region of interest to extract results
   - **Select SA type**: Choose sensitivity analysis method
   - **Generate samples**: Create parameter sample set

6. Click "Save & Start Running" to execute simulations

### Opening an Existing Project

1. Click "Open existing SA"
2. Select project folder
3. View or modify project settings:
   - Check/adjust parameters
   - View/capture new simulation completion indicator
   - Toggle additional ROI capturing
   - Change colormap and value ranges
   - Generate reports (if completed)

## Project Structure

```
project_folder/
├── metadata.json              # Project metadata and configuration
├── commands.txt               # User action commands
├── samples.npy               # Parameter sample matrix
├── results.npy               # Simulation results
├── roi_main_x1_y1_x2_y2.png # Main region of interest image
├── roi_additional_*.png      # Additional ROI images (if captured)
└── roi_completion_*.png      # Simulation completion indicator image
```

## Configuration Files

### metadata.json
Stores project information including:
- Project name and status (setup, in_progress, completed)
- Parameter definitions with bounds
- SA type and parameters
- Colormap settings (name, source, min/max values)
- ROI status (main, additional, completion indicator)

## ROI Naming Convention

Images are saved with coordinates encoded in filename:
- `roi_main_x1_y1_x2_y2.png`: Main ROI
- `roi_additional_x1_y1_x2_y2.png`: Additional ROI  
- `roi_completion_x1_y1_x2_y2.png`: Completion indicator

Where (x1, y1) is top-left corner and (x2, y2) is bottom-right corner in screen coordinates.

## Module Description

### main.py
Main GUI application with:
- Main menu interface
- Project dashboard
- Recording menu with controls
- Parameter management UI
- SA type selection and configuration
- ROI capture interface
- Report generation

### recorder.py
Records user interactions:
- Mouse movement tracking
- Mouse click detection
- Keyboard press/release recording
- Command file management
- Fn key trigger support (F13)

### replayer.py
Replays recorded actions:
- Mouse movement and clicking
- Keyboard input injection
- Parameter value injection
- Timing and synchronization

### project.py
Project management:
- Metadata storage and loading
- Parameter and results persistence
- Project validation
- Additional ROI toggling

### vision_engine.py
Computer vision operations:
- Screen capture
- ROI extraction
- Average color extraction
- RGB to scalar mapping via colormaps
- Template matching for completion detection
- Simulation result extraction

## Keyboard Controls

- **F13**: Pause recording and open menu (can be remapped in recorder.py)
- **During ROI selection**: Click and drag to select region
- **In preview dialogs**: "OK", "Retake", or "Cancel" buttons

## Error Handling

- Invalid parameter ranges: Error message with OK button
- Missing project files: Validation error with recovery to main menu
- SA library issues: Error message with installation instructions
- Replay failures: Error logging with recovery options

## Performance Considerations

- Large sample sets may require significant recording time
- ROI extraction runs in main thread - minimize window updates during replay
- Results stored as numpy arrays for efficient storage
- Threading used for replay operations to prevent UI freezing

## Future Enhancements

- Automated colormap identification from results data
- Additional SA methods integration
- Multi-parameter optimization
- Real-time progress monitoring
- Batch project processing
- Advanced visualization options

## License

See LICENSE file for details.

## Contributing

Contributions welcome! Please ensure:
- Code follows existing style conventions
- All features tested before submission
- Documentation updated for new features
- Backward compatibility maintained where possible
