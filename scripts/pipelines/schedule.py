import json
import logging
import datetime

from scripts.constants import MANAGER_CONFIG_PATH, SCHEDULE_TOLERANCE_MINUTES

logger = logging.getLogger(__name__)


def load_manager_config() -> dict:
    """Load manager_config.json, returning empty defaults if missing."""
    if not MANAGER_CONFIG_PATH.exists():
        logger.warning("No manager_config.json found at %s", MANAGER_CONFIG_PATH)
        return {"schedules": {}, "manual_mode": {}, "privacy_status": {}}

    with open(MANAGER_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def is_scheduled_time(
    scheduled_times: list[str],
    tolerance_minutes: int = SCHEDULE_TOLERANCE_MINUTES,
) -> bool:
    """Check if current time matches any scheduled slot within tolerance."""
    now = datetime.datetime.now()
    current_minutes = now.hour * 60 + now.minute

    for t in scheduled_times:
        try:
            h, m = map(int, t.split(":"))
            sched_minutes = h * 60 + m
            diff = abs(current_minutes - sched_minutes)

            if diff <= tolerance_minutes or diff >= (24 * 60 - tolerance_minutes):
                return True
        except ValueError:
            logger.warning("Invalid time format in schedule: %s", t)

    return False
