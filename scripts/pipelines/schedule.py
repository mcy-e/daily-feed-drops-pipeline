import json
import logging
import datetime

from scripts.constants import CONTENT_TYPES, MANAGER_CONFIG_PATH, SCHEDULE_TOLERANCE_MINUTES

logger = logging.getLogger(__name__)


def load_manager_config() -> dict:
    """Load manager_config.json, returning empty defaults if missing."""
    if not MANAGER_CONFIG_PATH.exists():
        logger.warning("No manager_config.json found at %s", MANAGER_CONFIG_PATH)
        return {"schedules": {}, "manual_mode": {}, "privacy_status": {}}

    with open(MANAGER_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _schedule_slots_for_type(config: dict, content_type: str) -> list[str]:
    """Return only this content type's HH:MM slots from manager config."""
    schedules = config.get("schedules", {})
    if not isinstance(schedules, dict):
        logger.warning("Invalid schedules section in manager config (expected object)")
        return []

    slots = schedules.get(content_type, [])
    if isinstance(slots, str):
        return [slots]
    if isinstance(slots, list):
        return slots

    logger.warning(
        "Invalid schedule format for %s (expected list of HH:MM strings): %r",
        content_type,
        slots,
    )
    return []


def is_scheduled_time(
    scheduled_times: list[str],
    tolerance_minutes: int = SCHEDULE_TOLERANCE_MINUTES,
    now: datetime.datetime | None = None,
) -> bool:
    """Check if ``now`` falls within tolerance of any slot in ``scheduled_times``."""
    if isinstance(scheduled_times, dict):
        logger.error(
            "is_scheduled_time received a schedules mapping — pass one content type's slot list"
        )
        return False

    if not scheduled_times:
        return False

    if now is None:
        now = datetime.datetime.now()

    current_minutes = now.hour * 60 + now.minute

    for slot in scheduled_times:
        if not isinstance(slot, str):
            logger.warning("Invalid schedule entry (expected HH:MM string): %r", slot)
            continue
        try:
            parts = slot.strip().split(":")
            if len(parts) < 2:
                raise ValueError("missing minutes")
            h, m = int(parts[0]), int(parts[1])
            sched_minutes = h * 60 + m
            diff = abs(current_minutes - sched_minutes)
            diff = min(diff, 24 * 60 - diff)

            if diff <= tolerance_minutes:
                return True
        except ValueError:
            logger.warning("Invalid time format in schedule: %s", slot)

    return False


def should_run_for_schedule(
    content_type: str,
    config: dict | None = None,
    force: bool = False,
    now: datetime.datetime | None = None,
) -> bool:
    """Return True when ``content_type`` should run at ``now`` (or bypassed via force)."""
    if content_type not in CONTENT_TYPES:
        raise ValueError(f"Unknown content type: {content_type}. Valid: {CONTENT_TYPES}")

    if force:
        logger.info("Force run enabled for %s.", content_type)
        return True

    if config is None:
        config = load_manager_config()

    scheduled_times = _schedule_slots_for_type(config, content_type)
    if not scheduled_times:
        logger.info("No schedule configured for %s. Skipping.", content_type)
        return False

    if is_scheduled_time(scheduled_times, now=now):
        return True

    if now is None:
        now = datetime.datetime.now()
    logger.info(
        "Current time %s is outside schedule slots %s for %s.",
        now.strftime("%H:%M"),
        scheduled_times,
        content_type,
    )
    return False
