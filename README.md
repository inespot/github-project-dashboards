# github-project-dashboards

Solara app for exploring GitHub Projects data with milestone-focused progress views, recent activity, and roadmap timelines.

## What this app contains

This app is organized around three main views:

- `Projects`: connect a GitHub Project, save its local configuration, and reopen previously saved projects.
- `Overview`: inspect burn-up progress, weighted completion, recent milestone activity, and milestone workload summaries.
- `Roadmaps`: view milestone-scoped issue timelines with start and end dates, color-coded by completion state or assignee.

The app also keeps a local `data/` store for:

- saved project definitions
- cached project items and timelines
- per-project configuration
- snapshots and proposal files

## Get started

1. Create and activate a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Upgrade pip, then install the project.

```bash
python -m pip install -U pip
pip install -e .
```

3. Create a `.env` file in the project root and add a GitHub token.

```env
GITHUB_TOKEN=your_token_here
```

The token needs access to the GitHub Projects data you want to load, and to the underlying repositories and issues referenced by those project items.

4. Start the app.

```bash
solara run dashboard.py
```

5. Open the local Solara URL shown in the terminal, then connect or select a project from the `Projects` page.
