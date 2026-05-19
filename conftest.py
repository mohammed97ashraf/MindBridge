"""Root conftest — adds MindBridge/ to sys.path so all tests can import backend.*."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
