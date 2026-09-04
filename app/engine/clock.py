from datetime import datetime, timedelta, timezone, time

# IST is UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

class VirtualClock:
    def __init__(self, initial_dt: datetime = None):
        if initial_dt is None:
            # Default to fixed reference point or current IST time
            now_utc = datetime.now(timezone.utc)
            self._current_time = now_utc.astimezone(IST)
        else:
            self._current_time = initial_dt.astimezone(IST)
        self._initial_time = self._current_time

    def get_now(self) -> datetime:
        return self._current_time

    def get_now_iso(self) -> str:
        return self._current_time.isoformat()

    def set_time(self, dt: datetime):
        self._current_time = dt.astimezone(IST)

    def advance_hours(self, hours: float) -> datetime:
        self._current_time += timedelta(hours=hours)
        return self._current_time

    def advance_days(self, days: int) -> datetime:
        self._current_time += timedelta(days=days)
        return self._current_time

    def total_hours_advanced(self) -> float:
        delta = self._current_time - self._initial_time
        return delta.total_seconds() / 3600.0

    def is_in_blackout(self, dt: datetime = None) -> bool:
        """
        NPCI Circular mandates no retry debit execution during the peak window:
        10:00 AM to 1:00 PM IST.
        """
        check_dt = dt or self._current_time
        check_dt_ist = check_dt.astimezone(IST)
        current_time = check_dt_ist.time()
        start = time(10, 0, 0)
        end = time(13, 0, 0)
        return start <= current_time <= end

    def adjust_for_blackout(self, dt: datetime) -> tuple[datetime, bool]:
        """
        If dt falls inside the 10:00 AM - 1:00 PM IST blackout, 
        defers to 1:05 PM (13:05:00) IST on the same day.
        Returns: (adjusted_datetime, was_adjusted_bool)
        """
        dt_ist = dt.astimezone(IST)
        if self.is_in_blackout(dt_ist):
            adjusted = dt_ist.replace(hour=13, minute=5, second=0, microsecond=0)
            return adjusted, True
        return dt_ist, False

    def jump_to_blackout(self) -> datetime:
        """Sets clock to today at 11:30 AM IST (peak blackout window)"""
        self._current_time = self._current_time.replace(hour=11, minute=30, second=0, microsecond=0)
        return self._current_time

    def jump_after_blackout(self) -> datetime:
        """Sets clock to today at 1:15 PM IST (compliant execution window)"""
        self._current_time = self._current_time.replace(hour=13, minute=15, second=0, microsecond=0)
        return self._current_time

# Global singleton instance for system runtime
virtual_clock = VirtualClock()
