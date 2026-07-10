import sys
from pathlib import Path

# pytest gets src/ on sys.path via pyproject `pythonpath`; at runtime we must
# add it ourselves so the flat imports ("api", "db", ...) resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn

from config.settings import get_settings

if __name__ == "__main__":
    uvicorn.run("api:app", host="127.0.0.1", port=get_settings().port, reload=False)
