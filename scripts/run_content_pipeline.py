import argparse
import logging
import os
import shutil

from dotenv import load_dotenv

from scripts.constants import CONTENT_TYPES, DEFAULT_TEMP_DIR
from scripts.pipelines.shared_pipeline import run_content_pipeline

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _cleanup_root_temp() -> None:
    """Delete and recreate the root temp directory at pipeline start."""
    if DEFAULT_TEMP_DIR.exists():
        shutil.rmtree(DEFAULT_TEMP_DIR)
    DEFAULT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Cleaned temp directory: %s", DEFAULT_TEMP_DIR)


def main():
    parser = argparse.ArgumentParser(description="Run the shared content pipeline.")
    parser.add_argument(
        "--type", required=True, choices=CONTENT_TYPES,
        help="Content type to generate.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Bypass schedule check and run immediately.",
    )
    args = parser.parse_args()

    force = args.force or os.getenv("FORCE_RUN", "").lower() == "true"

    _cleanup_root_temp()
    run_content_pipeline(args.type, force=force)


if __name__ == "__main__":
    main()
