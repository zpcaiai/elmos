import uuid
import datetime
from typing import List, Optional, Dict
from elmos_mature_platform.types import (
    KillswitchAction,
    KillswitchTrigger,
    KillswitchRule,
    KillswitchEvent
)

class AgentIncidentKillswitchEngine:
    """Engine for managing agent incident killswitches and rollbacks."""
    
    def __init__(self):
        self._rules: Dict[str, KillswitchRule] = {}
        self._events: Dict[str, KillswitchEvent] = {}

    def _now(self) -> str:
        return datetime.datetime.utcnow().isoformat()

    def create_rule(self, rule: KillswitchRule) -> str:
        """Create a new killswitch rule.
        
        Args:
            rule: The rule definition.
            
        Returns:
            The rule ID.
        """
        if not rule.rule_id:
            rule.rule_id = str(uuid.uuid4())
        self._rules[rule.rule_id] = rule
        return rule.rule_id

    def enable_rule(self, rule_id: str) -> KillswitchRule:
        """Enable an existing killswitch rule.
        
        Args:
            rule_id: The ID of the rule.
            
        Returns:
            The enabled rule.
            
        Raises:
            KeyError: If the rule does not exist.
        """
        if rule_id not in self._rules:
            raise KeyError(f"Rule {rule_id} not found.")
        self._rules[rule_id].enabled = True
        return self._rules[rule_id]

    def disable_rule(self, rule_id: str) -> KillswitchRule:
        """Disable an existing killswitch rule.
        
        Args:
            rule_id: The ID of the rule.
            
        Returns:
            The disabled rule.
            
        Raises:
            KeyError: If the rule does not exist.
        """
        if rule_id not in self._rules:
            raise KeyError(f"Rule {rule_id} not found.")
        self._rules[rule_id].enabled = False
        return self._rules[rule_id]

    def evaluate_trigger(self, agent_id: str, trigger: KillswitchTrigger, metric_value: float) -> Optional[KillswitchEvent]:
        """Check if metric exceeds threshold for a rule, trigger if so.
        
        Args:
            agent_id: The agent to check.
            trigger: The trigger type being evaluated.
            metric_value: The current metric value.
            
        Returns:
            A KillswitchEvent if triggered, otherwise None.
        """
        rules = [r for r in self._rules.values() if r.agent_id == agent_id and r.trigger == trigger and r.enabled]
        for rule in rules:
            if metric_value >= rule.threshold:
                # Trigger the rule
                event_id = str(uuid.uuid4())
                event = KillswitchEvent(
                    event_id=event_id,
                    rule_id=rule.rule_id,
                    agent_id=agent_id,
                    trigger=trigger,
                    action=rule.action,
                    triggered_at=self._now(),
                    metric_value=metric_value
                )
                self._events[event_id] = event
                
                # Update rule statistics
                rule.last_triggered = event.triggered_at
                rule.trigger_count += 1
                
                return event
        return None

    def manual_killswitch(self, agent_id: str, action: KillswitchAction, reason: str) -> KillswitchEvent:
        """Trigger a manual killswitch.
        
        Args:
            agent_id: The agent to kill.
            action: The action to take.
            reason: The reason for the manual killswitch.
            
        Returns:
            The generated KillswitchEvent.
        """
        event_id = str(uuid.uuid4())
        event = KillswitchEvent(
            event_id=event_id,
            rule_id="manual",
            agent_id=agent_id,
            trigger=KillswitchTrigger.MANUAL,
            action=action,
            triggered_at=self._now(),
            metric_value=0.0
        )
        # Note: could store reason in resolution_notes or a new field, using resolution_notes for now
        # Actually it's better not to muddy resolution_notes if it's unresolved, but we don't have a reason field.
        # Let's add it to resolution notes or just let the caller handle it.
        self._events[event_id] = event
        return event

    def resolve_event(self, event_id: str, notes: str) -> KillswitchEvent:
        """Resolve a killswitch event.
        
        Args:
            event_id: The event to resolve.
            notes: Notes regarding the resolution.
            
        Returns:
            The resolved event.
            
        Raises:
            KeyError: If the event is not found.
        """
        if event_id not in self._events:
            raise KeyError(f"Event {event_id} not found.")
            
        event = self._events[event_id]
        event.resolved = True
        event.resolved_at = self._now()
        event.resolution_notes = notes
        return event

    def get_active_events(self) -> List[KillswitchEvent]:
        """Get all unresolved killswitch events.
        
        Returns:
            A list of active events.
        """
        return [e for e in self._events.values() if not e.resolved]

    def get_agent_events(self, agent_id: str) -> List[KillswitchEvent]:
        """Get all killswitch events for a specific agent.
        
        Args:
            agent_id: The ID of the agent.
            
        Returns:
            A list of events for the agent.
        """
        return [e for e in self._events.values() if e.agent_id == agent_id]

    def get_rules_for_agent(self, agent_id: str) -> List[KillswitchRule]:
        """Get all rules for a specific agent.
        
        Args:
            agent_id: The ID of the agent.
            
        Returns:
            A list of rules for the agent.
        """
        return [r for r in self._rules.values() if r.agent_id == agent_id]

    def is_agent_killed(self, agent_id: str) -> bool:
        """Check if an agent has an unresolved TERMINATE event.
        
        Args:
            agent_id: The ID of the agent.
            
        Returns:
            True if the agent is killed, False otherwise.
        """
        active_events = self.get_agent_events(agent_id)
        return any(not e.resolved and e.action == KillswitchAction.TERMINATE for e in active_events)

    def get_killswitch_report(self) -> Dict:
        """Generate a report of killswitch activity.
        
        Returns:
            A dictionary containing report metrics.
        """
        trigger_counts = {}
        action_counts = {}
        agent_counts = {}
        
        for event in self._events.values():
            trigger_counts[event.trigger.value] = trigger_counts.get(event.trigger.value, 0) + 1
            action_counts[event.action.value] = action_counts.get(event.action.value, 0) + 1
            agent_counts[event.agent_id] = agent_counts.get(event.agent_id, 0) + 1
            
        top_agents = sorted(agent_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Simple resolution time calc
        total_time = 0.0
        resolved_count = 0
        for event in self._events.values():
            if event.resolved and event.resolved_at and event.triggered_at:
                try:
                    t1 = datetime.datetime.fromisoformat(event.triggered_at)
                    t2 = datetime.datetime.fromisoformat(event.resolved_at)
                    total_time += (t2 - t1).total_seconds()
                    resolved_count += 1
                except ValueError:
                    pass
                    
        avg_resolution_time = total_time / resolved_count if resolved_count > 0 else 0.0

        return {
            "by_trigger": trigger_counts,
            "by_action": action_counts,
            "top_agents": dict(top_agents),
            "avg_resolution_time_seconds": avg_resolution_time,
            "total_events": len(self._events),
            "active_events": len(self.get_active_events())
        }
