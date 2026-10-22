# Flash-Flood Street Alerts (prototype)

Sime Darby Property University Hackathon 2026 — Planet track, Climate Resilience.
Pilot township: Bandar Bukit Raja (BBR), Klang. See [PLAN.md](PLAN.md) for the full build plan.

> **Honesty note.** The water model is a *reduced-complexity* model (rational-method runoff, a
> drain-node network and a cellular surface-flow scheme). It is not a full hydraulic model. All
> results are simulation estimates until a real sensor pilot exists.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev,geo]"     # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m pytest -q
```

Every Makefile target is also available as `python -m ffsa.cli <target>` (for Windows without `make`).

## Status

| Phase | State |
|---|---|
| 0. Scaffold | done |
| 1. Core formulas | done |
