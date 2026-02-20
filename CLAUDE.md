# Project Overview

AntlerBot is a Python-based QQ bot application that uses NapCat to interact with QQ.

# Framework Documentation

Core framework docs are in `docs/frameworks/`. Read relevant files before implementing features.

NcatBot is the core framework for interacting with QQ. Docs: `docs/frameworks/NcatBot.md`.

# Current State

This is a new project with no code implementation yet. The repository structure is initialized with:
- Python virtual environment setup (.venv/)
- Basic project files (README.md, LICENSE, .gitignore)

# Dependency Management

Uses pip-tools. Direct deps in `requirements.in`, locked deps in `requirements.txt`.

To add a dependency:
1. Add it to `requirements.in`
2. Run: `pip-compile --index-url=https://mirrors.aliyun.com/pypi/simple/ --output-file=requirements.txt requirements.in`
3. Run: `pip install -r requirements.txt`
