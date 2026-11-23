"""Launch GameNext directly from the checkout."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from gamenext.app import main

if __name__ == "__main__":
    main()
