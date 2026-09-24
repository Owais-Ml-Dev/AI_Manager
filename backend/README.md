# AI Task Manager Backend

Flask + MongoDB backend for the AI Task Manager project.

## Current feature

The current implementation supports one-time tasks:

- Create a one-time task
- Get all one-time tasks
- Get a one-time task by id
- Partially update a one-time task

## Architecture

The one-time task feature follows this flow:

`routes -> controller -> validation/service -> repository -> MongoDB`

## Run locally

1. Activate the virtual environment.
2. Make sure MongoDB is running locally.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Start the backend from the project root:

```bash
python -m src.server
```

The API runs at `http://127.0.0.1:5000` by default.
