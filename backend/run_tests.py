"""Minimal runner so tests work without pytest (pytest also works: `pytest tests`)."""
import importlib, inspect, os, sys, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tests"))
sys.path.insert(0, os.path.dirname(__file__))
ok = bad = 0
for f in sorted(os.listdir(os.path.join(os.path.dirname(__file__), "tests"))):
    if f.startswith("test_") and f.endswith(".py"):
        m = importlib.import_module(f[:-3])
        for n, fn in inspect.getmembers(m, inspect.isfunction):
            if n.startswith("test_"):
                try:
                    fn(); ok += 1; print("PASS", n)
                except Exception:
                    bad += 1; print("FAIL", n); traceback.print_exc()
print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
