import os
from pathlib import Path

def load_dotenv_once():
    """
    Load a .env file from the selector-service directory or any parent of CWD once.
    Safe to call multiple times; only first call loads.
    """
    if getattr(load_dotenv_once, "_loaded", False):
        return
    try:
        from dotenv import load_dotenv
    except Exception:
        # python-dotenv not installed; skip silently
        load_dotenv_once._loaded = True
        return

    # Search for a .env starting from CWD up to root
    cwd = Path(os.getcwd()).resolve()
    candidates = []
    for p in [cwd] + list(cwd.parents):
        candidates.append(p / ".env")

    # Also consider the selector-service directory explicitly
    ss_dir = Path(__file__).resolve().parent.parent
    candidates.insert(0, ss_dir / ".env")

    for c in candidates:
        if c.is_file():
            load_dotenv(dotenv_path=str(c), override=False)
            break

    load_dotenv_once._loaded = True
