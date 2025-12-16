"""Simple cross-Python verifier for the `psutil` package.

This script safely loads the `importlib.util` submodule (works even
when the parent `importlib` is imported without `util`) and then uses
`find_spec` to check whether `psutil` is importable in the current
environment. It falls back to a direct import attempt if needed.

Usage:
  python scripts/verify_psutil.py

Exit code: 0 if found, 1 if not.
"""
import sys

def has_psutil_via_spec():
    try:
        # Prefer a direct import of the util submodule
        try:
            import importlib.util as importlib_util
        except Exception:
            import importlib
            importlib_util = importlib.import_module('importlib.util')

        spec = importlib_util.find_spec('psutil')
        return spec is not None
    except Exception:
        return False

def has_psutil_via_import():
    try:
        import importlib
        importlib.import_module('psutil')
        return True
    except Exception:
        return False

def main():
    ok = has_psutil_via_spec() or has_psutil_via_import()
    if ok:
        print('psutil installed')
        return 0
    else:
        print('psutil NOT found')
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
