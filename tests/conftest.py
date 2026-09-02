import sys
from pathlib import Path

# The scripts/ directory is a flat module directory, not a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
