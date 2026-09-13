from typing import List, Dict, Optional
from datetime import datetime, timedelta
import uuid

from elmos_mature_platform.types import (
    OncallEngineer,
    OncallShift,
    OncallSchedule,
    OncallOverride,
    OncallShiftType
)

class OncallRotationEngine:
    """
    On-Call Rotation Engine for managing follow-the-sun schedules,
    engineer fatigue, shift assignments, and coverage tracking.
    """
    def __init__(self):
        self.engineers: Dict[str, OncallEngineer] = {}
        self.schedules: Dict[str, OncallSchedule] = {}
        self.overrides: Dict[str, OncallOverride] = {}

    def register_engineer(self, engineer: OncallEngineer) -> None:
        """Register a new on-call engineer."""
        self.engineers[engineer.engineer_id] = engineer

    def create_schedule(self, schedule: OncallSchedule) -> str:
        """Create rotation schedule for a service."""
        schedule.created_at = datetime.utcnow().isoformat()
        if not schedule.schedule_id:
            schedule.schedule_id = str(uuid.uuid4())
        self.schedules[schedule.schedule_id] = schedule
        return schedule.schedule_id

    def generate_shifts(self, schedule_id: str, days: int) -> List[OncallShift]:
        """
        Auto-generate shifts based on regions (follow-the-sun: rotate by timezone),
        respecting max_consecutive_shifts constraint.
        """
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            raise ValueError("Schedule not found")

        available_engs = [e for e in self.engineers.values() if e.available]
        if not available_engs:
            raise ValueError("No available engineers")
        
        # Sort engineers by timezone to simulate follow-the-sun rotation
        available_engs.sort(key=lambda x: x.timezone)
        
        generated = []
        now = datetime.utcnow()
        if schedule.shifts:
            last_shift_end = max(datetime.fromisoformat(s.ends_at) for s in schedule.shifts)
            current_time = last_shift_end
        else:
            current_time = now

        end_time = current_time + timedelta(days=days)
        eng_idx = 0
        num_engs = len(available_engs)

        while current_time < end_time:
            attempts = 0
            selected_eng = None
            
            while attempts < num_engs:
                eng = available_engs[eng_idx % num_engs]
                if eng.current_consecutive < eng.max_consecutive_shifts:
                    selected_eng = eng
                    break
                eng_idx += 1
                attempts += 1
            
            if not selected_eng:
                # No one available to take the shift, move time forward to detect coverage gaps
                current_time += timedelta(hours=schedule.rotation_period_hours)
                for e in available_engs:
                    e.current_consecutive = 0
                    e.available = True
                continue

            shift_end = current_time + timedelta(hours=schedule.rotation_period_hours)
            shift = OncallShift(
                shift_id=str(uuid.uuid4()),
                engineer_id=selected_eng.engineer_id,
                shift_type=OncallShiftType.PRIMARY,
                service_name=schedule.service_name,
                starts_at=current_time.isoformat(),
                ends_at=shift_end.isoformat()
            )
            generated.append(shift)
            schedule.shifts.append(shift)
            
            selected_eng.current_consecutive += 1
            selected_eng.total_shifts += 1
            if selected_eng.current_consecutive >= selected_eng.max_consecutive_shifts:
                selected_eng.available = False
            
            # Reset consecutive count for others to simulate resting
            for e in available_engs:
                if e.engineer_id != selected_eng.engineer_id:
                    e.current_consecutive = 0
                    e.available = True
            
            current_time = shift_end
            eng_idx += 1
            
        return generated

    def get_current_oncall(self, service_name: str, current_time: str) -> Optional[OncallShift]:
        """Who is on call right now for the specified service?"""
        curr_dt = datetime.fromisoformat(current_time)
        for schedule in self.schedules.values():
            if schedule.service_name == service_name:
                for shift in schedule.shifts:
                    start_dt = datetime.fromisoformat(shift.starts_at)
                    end_dt = datetime.fromisoformat(shift.ends_at)
                    if start_dt <= curr_dt < end_dt:
                        # Check overrides
                        for override in self.overrides.values():
                            if override.service_name == service_name:
                                o_start = datetime.fromisoformat(override.starts_at)
                                o_end = datetime.fromisoformat(override.ends_at)
                                if o_start <= curr_dt < o_end and override.original_engineer_id == shift.engineer_id:
                                    override_shift = OncallShift(
                                        shift_id=shift.shift_id,
                                        engineer_id=override.replacement_engineer_id,
                                        shift_type=shift.shift_type,
                                        service_name=shift.service_name,
                                        starts_at=shift.starts_at,
                                        ends_at=shift.ends_at,
                                        handoff_notes=shift.handoff_notes,
                                        incidents_handled=shift.incidents_handled,
                                        acknowledged=shift.acknowledged
                                    )
                                    return override_shift
                        return shift
        return None

    def acknowledge_shift(self, shift_id: str) -> OncallShift:
        """Engineer acknowledges their assigned shift."""
        for schedule in self.schedules.values():
            for shift in schedule.shifts:
                if shift.shift_id == shift_id:
                    shift.acknowledged = True
                    return shift
        raise ValueError(f"Shift {shift_id} not found")

    def handoff(self, shift_id: str, notes: str) -> OncallShift:
        """Record handoff notes for an ongoing or completed shift."""
        for schedule in self.schedules.values():
            for shift in schedule.shifts:
                if shift.shift_id == shift_id:
                    shift.handoff_notes = notes
                    return shift
        raise ValueError(f"Shift {shift_id} not found")

    def create_override(self, override: OncallOverride) -> str:
        """Create a shift override to swap an engineer."""
        repl_eng = self.engineers.get(override.replacement_engineer_id)
        if not repl_eng or not repl_eng.available:
            raise PermissionError("Replacement engineer is not available")
        if not override.override_id:
            override.override_id = str(uuid.uuid4())
        self.overrides[override.override_id] = override
        return override.override_id

    def record_incident(self, shift_id: str) -> OncallShift:
        """Increment incidents handled count for a specific shift."""
        for schedule in self.schedules.values():
            for shift in schedule.shifts:
                if shift.shift_id == shift_id:
                    shift.incidents_handled += 1
                    return shift
        raise ValueError(f"Shift {shift_id} not found")

    def get_engineer_stats(self, engineer_id: str) -> Dict:
        """Get summary stats: total shifts, incidents, consecutive count."""
        eng = self.engineers.get(engineer_id)
        if not eng:
            raise ValueError(f"Engineer {engineer_id} not found")
        
        total_incidents = 0
        for sched in self.schedules.values():
            for shift in sched.shifts:
                if shift.engineer_id == engineer_id:
                    total_incidents += shift.incidents_handled
                    
        return {
            "engineer_id": engineer_id,
            "total_shifts": eng.total_shifts,
            "current_consecutive": eng.current_consecutive,
            "incidents_handled": total_incidents,
            "available": eng.available
        }

    def get_fatigue_report(self) -> List[Dict]:
        """Report engineers approaching or exceeding max consecutive shifts."""
        report = []
        for eng in self.engineers.values():
            if eng.current_consecutive >= eng.max_consecutive_shifts - 1:
                report.append({
                    "engineer_id": eng.engineer_id,
                    "name": eng.name,
                    "current_consecutive": eng.current_consecutive,
                    "max_consecutive": eng.max_consecutive_shifts,
                    "status": "EXCEEDED" if eng.current_consecutive >= eng.max_consecutive_shifts else "APPROACHING"
                })
        return report

    def get_coverage_gaps(self, schedule_id: str) -> List[Dict]:
        """Find time periods with no shift coverage in the schedule."""
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            raise ValueError("Schedule not found")
            
        gaps = []
        if not schedule.shifts:
            return gaps
            
        sorted_shifts = sorted(schedule.shifts, key=lambda s: datetime.fromisoformat(s.starts_at))
        
        for i in range(len(sorted_shifts) - 1):
            curr_end = datetime.fromisoformat(sorted_shifts[i].ends_at)
            next_start = datetime.fromisoformat(sorted_shifts[i+1].starts_at)
            if curr_end < next_start:
                gaps.append({
                    "gap_start": curr_end.isoformat(),
                    "gap_end": next_start.isoformat(),
                    "duration_hours": (next_start - curr_end).total_seconds() / 3600
                })
        return gaps

    def get_schedule_report(self, schedule_id: str) -> Dict:
        """Provide a full schedule summary report."""
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            raise ValueError("Schedule not found")
            
        return {
            "schedule_id": schedule.schedule_id,
            "service_name": schedule.service_name,
            "total_shifts": len(schedule.shifts),
            "regions": schedule.regions,
            "coverage_gaps_count": len(self.get_coverage_gaps(schedule_id))
        }
