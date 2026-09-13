#!/usr/bin/env python3
"""Fixed version probe for the pilot's Python test dependencies; never installs."""
import sys


def main():
    if sys.argv[1:] != ["--version"]:
        raise SystemExit("usage: verification-toolchain.py --version")
    import pytest
    import yaml
    print(f"Python {sys.version.split()[0]}; pytest {pytest.__version__}; PyYAML {yaml.__version__}")


if __name__ == "__main__":
    main()
