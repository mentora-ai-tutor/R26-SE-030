import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "services/knowledge-analysis"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def pytest_configure(config):
    """Ensure the app package is importable and shared fakes resolve as ``fakes``."""
    if "fakes" not in sys.modules:
        import importlib

        importlib.import_module("fakes")