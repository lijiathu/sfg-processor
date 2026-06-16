# Contributing

Thanks for your interest in improving **SFG Processor**! This is a small,
focused scientific tool, so the barrier to contribute is low.

## Reporting issues

Open an issue and include:
- What you expected vs. what happened.
- The smallest sample (or a synthetic reproducer) that triggers it.
- The console output if you ran `python sfg_app.py`.

## Suggested workflow

1. Fork & clone the repo, create a feature branch.
2. Install dev dependencies:
   ```bash
   pip install -r requirements.txt
   pip install pytest
   ```
3. Make your change. The project separates concerns:
   - `sfg_processor.py` — pure data logic (no GUI). **Add a unit test**
     in `test_sfg_processor.py` for any new behaviour.
   - `sfg_app.py` — the Flask + web-UI layer.
   - `frontend/index.html` — the (self-contained) interface.
4. Run the tests:
   ```bash
   python -m pytest -q
   ```
5. Open a Pull Request describing the change and referencing any issue.

## Conventions

- Keep `sfg_processor.py` free of GUI/web dependencies so it stays testable.
- File-name parsing rules live in `parse_filename`; extend there if your
  instrument uses a different naming scheme, and add a test.
- Figures should remain publication-grade (Helvetica, thin axes, no grid).

## Code of conduct

Be kind and constructive. Scientific software thrives on collaboration.
