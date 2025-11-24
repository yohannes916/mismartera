"""Session State Definitions

Defines the lifecycle states of a trading session for boundary management.

Used by SessionBoundaryManager and session_data to track and manage
session state transitions.
"""
from enum import Enum


class SessionState(Enum):
    """Trading session lifecycle states.
    
    State transitions:
    NOT_STARTED → PRE_MARKET → ACTIVE → POST_MARKET → ENDED
                      ↓           ↓          ↓
                  TIMEOUT     TIMEOUT    TIMEOUT
                      ↓           ↓          ↓
                  ERROR       ERROR      ERROR
    """
    
    NOT_STARTED = "not_started"
    """No session has been initialized or started."""
    
    PRE_MARKET = "pre_market"
    """Session date set, but before market open (< 9:30 AM ET)."""
    
    ACTIVE = "active"
    """During market hours (9:30 AM - 4:00 PM ET)."""
    
    POST_MARKET = "post_market"
    """After market close (> 4:00 PM ET), same day."""
    
    ENDED = "ended"
    """Session explicitly ended or next day reached."""
    
    TIMEOUT = "timeout"
    """No data received for configured timeout period."""
    
    ERROR = "error"
    """Error state requiring manual intervention."""
    
    def is_active(self) -> bool:
        """Check if state represents an active session."""
        return self in (
            SessionState.PRE_MARKET,
            SessionState.ACTIVE,
            SessionState.POST_MARKET
        )
    
    def is_market_hours(self) -> bool:
        """Check if state is during market hours."""
        return self == SessionState.ACTIVE
    
    def requires_attention(self) -> bool:
        """Check if state requires attention or intervention."""
        return self in (SessionState.TIMEOUT, SessionState.ERROR)
    
    def can_receive_data(self) -> bool:
        """Check if session can receive data in this state."""
        return self in (
            SessionState.PRE_MARKET,
            SessionState.ACTIVE,
            SessionState.POST_MARKET
        )
    
    def __str__(self) -> str:
        """String representation of state."""
        return self.value
    
    def __repr__(self) -> str:
        """Detailed representation of state."""
        return f"SessionState.{self.name}"


# State transition validation
VALID_TRANSITIONS = {
    SessionState.NOT_STARTED: {
        SessionState.PRE_MARKET,
        SessionState.ACTIVE,
        SessionState.ERROR
    },
    SessionState.PRE_MARKET: {
        SessionState.ACTIVE,
        SessionState.TIMEOUT,
        SessionState.ERROR,
        SessionState.ENDED
    },
    SessionState.ACTIVE: {
        SessionState.POST_MARKET,
        SessionState.TIMEOUT,
        SessionState.ERROR,
        SessionState.ENDED
    },
    SessionState.POST_MARKET: {
        SessionState.ENDED,
        SessionState.TIMEOUT,
        SessionState.ERROR
    },
    SessionState.ENDED: {
        SessionState.NOT_STARTED,
        SessionState.PRE_MARKET
    },
    SessionState.TIMEOUT: {
        SessionState.ACTIVE,
        SessionState.ERROR,
        SessionState.ENDED
    },
    SessionState.ERROR: {
        SessionState.NOT_STARTED,
        SessionState.ACTIVE,
        SessionState.ENDED
    }
}


def is_valid_transition(from_state: SessionState, to_state: SessionState) -> bool:
    """Check if state transition is valid.
    
    Args:
        from_state: Current state
        to_state: Target state
        
    Returns:
        True if transition is valid
    """
    if from_state not in VALID_TRANSITIONS:
        return False
    
    return to_state in VALID_TRANSITIONS[from_state]


def get_state_description(state: SessionState) -> str:
    """Get human-readable description of state.
    
    Args:
        state: Session state
        
    Returns:
        Description string
    """
    descriptions = {
        SessionState.NOT_STARTED: "No session started",
        SessionState.PRE_MARKET: "Before market open (< 9:30 AM)",
        SessionState.ACTIVE: "Market hours (9:30 AM - 4:00 PM)",
        SessionState.POST_MARKET: "After market close (> 4:00 PM)",
        SessionState.ENDED: "Session ended",
        SessionState.TIMEOUT: "No data received (timeout)",
        SessionState.ERROR: "Error state - needs attention"
    }
    
    return descriptions.get(state, "Unknown state")


if __name__ == "__main__":
    # Test state enum
    print("Session States:")
    for state in SessionState:
        print(f"  {state.name:15} = {state.value:15} - {get_state_description(state)}")
    
    print("\nState Properties:")
    print(f"  ACTIVE is_active: {SessionState.ACTIVE.is_active()}")
    print(f"  ACTIVE is_market_hours: {SessionState.ACTIVE.is_market_hours()}")
    print(f"  ERROR requires_attention: {SessionState.ERROR.requires_attention()}")
    print(f"  ACTIVE can_receive_data: {SessionState.ACTIVE.can_receive_data()}")
    
    print("\nValid Transitions from ACTIVE:")
    for target in VALID_TRANSITIONS[SessionState.ACTIVE]:
        print(f"  ACTIVE → {target.name}")
