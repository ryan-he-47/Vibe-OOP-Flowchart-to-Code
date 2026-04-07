# Flow Rebuild Prototype

This is a clean-room reimplementation based only on the runtime model in `program_flow.mmd`.

## Run

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## What is included

- `main.py`: startup entry
- `app/editor_window.py`: main editor runtime flow
- `app/graphics_items.py`: node/edge graphics and interaction primitives
- `app/templates.py`: semantic template registry
- `program_flow.mmd`: runtime flowchart that this implementation follows
