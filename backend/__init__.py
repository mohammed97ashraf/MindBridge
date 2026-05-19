"""MindBridge backend package — installs the global exception hook on import."""
from backend.logger import install_exception_hook

install_exception_hook()
