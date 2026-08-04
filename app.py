from __future__ import annotations

import importlib.util
from pathlib import Path


APP_MODULE_PATH = Path(__file__).resolve().parent / "app" / "streamlit_app.py"
spec = importlib.util.spec_from_file_location("tcria_streamlit_app", APP_MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load Streamlit app module: {APP_MODULE_PATH}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.render()
