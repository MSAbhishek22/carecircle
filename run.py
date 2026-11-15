#!/usr/bin/env python3
"""CareCircle entry point.

Usage:
    python3 run.py serve [port]   — run the local server (default 8790)
    python3 run.py test           — run the test suite
"""
import sys
import unittest

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "test":
        suite = unittest.defaultTestLoader.discover("tests")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
    from app.server import main

    port = 8790
    if args and args[0] == "serve" and len(args) > 1:
        port = int(args[1])
    elif args and args[0].isdigit():
        port = int(args[0])
    main(port=port)
