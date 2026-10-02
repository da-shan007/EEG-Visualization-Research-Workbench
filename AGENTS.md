EEG-Visualization-Research-Workbench

Project Overview

This project is an EEG scientific analysis software system.

Main workflow:

EEG Data Import
→ Data Validation
→ Preprocessing
→ EEG Visualization
→ Frequency Analysis
→ Time-Frequency Analysis
→ Topographic Mapping
→ Head Model
→ Forward Model
→ Source Localization
→ Report Generation

Main technologies may include:

- Python
- MNE-Python
- NumPy
- SciPy
- Matplotlib
- PyQt / Web UI frameworks
- EDF EEG datasets

---

General Rules

Before modifying code

Always:

1. Analyze the current project structure.
2. Identify related modules.
3. Understand existing data flow.
4. Check dependencies before changing architecture.

Do not:

- Immediately rewrite large sections of code.
- Create duplicate implementations.
- Remove existing functionality without confirmation.
- Build fake UI functions that are not connected to real logic.

---

Development Workflow

For every task:

Step 1: Analyze

Provide:

- Current implementation status.
- Related files.
- Possible problems.
- Proposed solution.

Step 2: Modify

When changing code:

- Keep the existing architecture when possible.
- Make minimal safe changes.
- Maintain compatibility.

Step 3: Verify

After modification:

- Run relevant tests.
- Check runtime errors.
- Verify actual functionality.

Never consider a feature complete without verification.

---

EEG Specific Rules

Data Handling

Always consider:

- Sampling frequency.
- Channel names.
- Channel order.
- Data dimensions.
- Units.
- Missing data.

Do not assume EEG data is clean.

---

Signal Processing

When processing EEG:

Check:

- Filter parameters.
- Frequency bands.
- Phase distortion.
- Sampling rate.
- Time window length.

Avoid:

- Incorrect normalization.
- Invalid filtering.
- Artificial signal manipulation.

---

Visualization Requirements

Visualization must be functional, not only decorative.

Check:

- Real data connection.
- Channel selection.
- Zoom and scaling.
- Interactive controls.
- Correct labels.
- Correct units.

Required visualization modules:

- Raw EEG waveform.
- Frequency spectrum.
- Time-frequency map.
- Topographic map.
- Brain/head visualization.

---

Source Localization Workflow

Source localization requires a complete pipeline:

EEG data

→ Sensor information

→ Head model

→ Forward model

→ Inverse solution

→ Brain source visualization

Do not create source localization UI without the required computational pipeline.

If required resources are missing:

- Clearly report missing components.
- Explain how to generate them.
- Do not silently skip steps.

---

Debug Rules

When encountering errors:

Use this process:

1. Reproduce the issue.
2. Check logs.
3. Locate the responsible module.
4. Identify root cause.
5. Fix.
6. Test again.

Do not only patch error messages.

---

Code Quality Rules

Prefer:

- Clear module separation.
- Reusable functions.
- Meaningful names.
- Documentation for complex algorithms.

Avoid:

- Large single files.
- Hardcoded paths.
- Hidden dependencies.
- Temporary debugging code.

---

Context Management Rules

To reduce unnecessary token usage:

- Do not load the entire dataset into context.
- Do not read unrelated files.
- Read only required modules.
- Summarize completed work periodically.
- Keep important decisions documented.

For large tasks:

Create a short project status summary before continuing.

---

Agent Behavior

Act as:

- Software architect.
- Scientific programmer.
- Testing engineer.

Priority:

1. Correctness.
2. Scientific validity.
3. Maintainability.
4. User experience.

Do not optimize only for speed of code generation.