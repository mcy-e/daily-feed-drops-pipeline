import argparse
import logging
import os

from dotenv import load_dotenv

from scripts.pipelines.shared_pipeline import run_content_pipeline

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ALL_CONTENT_TYPES = ("meme_recap", "cursed_screenshots")


def main():
    parser = argparse.ArgumentParser(description="Run the content pipeline.")
    parser.add_argument(
        "--type", required=True, choices=ALL_CONTENT_TYPES,
        help="Content type to generate.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Bypass schedule check.",
    )
    args = parser.parse_args()

    force = args.force or os.getenv("FORCE_RUN", "").lower() == "true"

    if args.type == "cursed_screenshots":
        from scripts.pipelines.cursed_pipeline import run_cursed_pipeline
        run_cursed_pipeline(force=force)
    else:
        run_content_pipeline(args.type, force=force)


if __name__ == "__main__":
    main()