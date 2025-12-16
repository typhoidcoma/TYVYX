"""
Lightweight network diagnostics helper used by tests and the simplified app.

This provides a minimal `DroneNetworkDiagnostics` class that exposes a
`log_file` attribute and a `log()` method which appends text to the log file.
It intentionally avoids any heavy network probing or external dependencies.
"""

class DroneNetworkDiagnostics:
    def __init__(self, log_file: str = 'drone_network.log'):
        self.log_file = log_file

    def log(self, message: str) -> None:
        try:
            with open(self.log_file, 'a', encoding='utf-8') as fh:
                fh.write(f"{message}\n")
        except Exception:
            # Swallow errors on logging to avoid test/environment failures
            pass

