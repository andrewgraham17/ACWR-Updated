"""
Press ▶ (Run Python File) in VS Code on this file to start the app.
It installs anything missing the first time, then opens the app in your browser.
"""
import importlib.util
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NEEDED = {"streamlit": "streamlit>=1.64", "pandas": "pandas", "altair": "altair", "openpyxl": "openpyxl",
          "sqlalchemy": "sqlalchemy>=2.0", "psycopg2": "psycopg2-binary"}


def ensure_packages():
    missing = [pkg for mod, pkg in NEEDED.items() if importlib.util.find_spec(mod) is None]
    if not missing and importlib.util.find_spec("streamlit"):
        import streamlit
        major, minor = (int(x) for x in streamlit.__version__.split(".")[:2])
        if (major, minor) < (1, 64):
            missing = ["streamlit>=1.64"]
    if not missing:
        return
    print("Installing:", ", ".join(missing), "(one time, about a minute)…")
    for extra in ([], ["--user"], ["--break-system-packages"]):   # fallbacks for Mac/Homebrew Pythons
        if subprocess.call([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-U", *extra, *missing]) == 0:
            return
    sys.exit("Couldn't install the packages. In the VS Code terminal run:\n  "
             f"{sys.executable} -m pip install -r requirements.txt")


if __name__ == "__main__":
    ensure_packages()
    print("Starting the K-State Throw Log… (press Ctrl+C in this terminal to stop it)")
    subprocess.call([sys.executable, "-m", "streamlit", "run", os.path.join(HERE, "app.py")], cwd=HERE)
