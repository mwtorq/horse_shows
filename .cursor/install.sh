#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for the horse_shows scraping project.
# Installs the Microsoft ODBC driver (for pyodbc / SQL Server) and the Python
# dependencies. Chrome is already provided by the base image and is discovered
# automatically by Selenium Manager, so no chromedriver install is needed.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> horse_shows environment bootstrap"

# --- System packages: unixODBC + Microsoft ODBC Driver 18 for SQL Server ------
# msodbcsql18 provides the "ODBC Driver 18 for SQL Server" that the scrapers
# request via pyodbc. Only install when it is not already registered.
if ! command -v odbcinst >/dev/null 2>&1 \
   || ! odbcinst -q -d 2>/dev/null | grep -q "ODBC Driver 18 for SQL Server"; then
  echo "==> Installing unixODBC and the Microsoft ODBC Driver 18 for SQL Server"

  export DEBIAN_FRONTEND=noninteractive
  sudo apt-get update -y
  sudo apt-get install -y --no-install-recommends curl gnupg apt-transport-https unixodbc unixodbc-dev

  # Register the Microsoft package repository (handles the Ubuntu 24.04 apt
  # signing requirements via the shipped keyring).
  ubuntu_version="$(grep VERSION_ID /etc/os-release | cut -d '"' -f 2)"
  tmp_deb="$(mktemp --suffix=.deb)"
  curl -fsSL -o "$tmp_deb" \
    "https://packages.microsoft.com/config/ubuntu/${ubuntu_version}/packages-microsoft-prod.deb"
  sudo dpkg -i "$tmp_deb"
  rm -f "$tmp_deb"

  sudo apt-get update -y
  sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
else
  echo "==> Microsoft ODBC Driver 18 for SQL Server already installed; skipping"
fi

# --- Python dependencies ------------------------------------------------------
# Ubuntu 24.04 ships an externally-managed system Python; the scrapers are run
# directly as `python3 <script>.py`, so install into that interpreter.
echo "==> Installing Python dependencies from requirements.txt"
python3 -m pip install --break-system-packages --upgrade pip
python3 -m pip install --break-system-packages -r "${REPO_ROOT}/requirements.txt"

echo "==> Bootstrap complete"
odbcinst -q -d || true
