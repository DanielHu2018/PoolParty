# PoolParty
# PoolParty — Carpooling MVP for HackOHI/O 2025

Visible at http://3.19.82.8/

This repository contains a minimal Flask-based carpooling web app (MVP).

Features (MVP):
- Login
- User registration / profile creation
- Pool creation
- Requests to join a pool
- Viewing listings to locations
- Ride management

Tech stack:
- Python + Flask
- SQLite (via Flask-SQLAlchemy)

Quick start (Windows PowerShell):

1. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies

```powershell
pip install -r requirements.txt
```

3. Create an instance config

```powershell
# create instance folder already present; edit instance\config.py to set SECRET_KEY if desired
```

4. Run the app

```powershell
python run.py
```

Open http://127.0.0.1:5000

Next steps:
- Add more tests (unit + integration)
- Integrate migrations (Flask-Migrate) if needed
- Harden auth and input validation before production

