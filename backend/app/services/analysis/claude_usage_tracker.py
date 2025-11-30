"""
Claude API Usage Tracker
Tracks token consumption and costs for monitoring
"""
from typing import Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, asdict
from app.logger import logger


@dataclass
class UsageRecord:
    """Single usage record"""
    timestamp: datetime
    username: str
    operation: str  # "ask", "analyze", etc.
    input_tokens: int
    output_tokens: int
    total_tokens: int
    model: str
    
    @property
    def estimated_cost(self) -> float:
        """
        Estimate cost in USD based on Claude Opus 4 pricing
        Input: $15 per million tokens
        Output: $75 per million tokens
        """
        input_cost = (self.input_tokens / 1_000_000) * 15.0
        output_cost = (self.output_tokens / 1_000_000) * 75.0
        return input_cost + output_cost


class ClaudeUsageTracker:
    """
    Track Claude API usage for monitoring and cost estimation
    """
    
    def __init__(self):
        self.records: List[UsageRecord] = []
        self.session_start = datetime.now()
        
    def record_usage(
        self,
        username: str,
        operation: str,
        input_tokens: int,
        output_tokens: int,
        model: str
    ):
        """
        Record a Claude API usage event
        
        Args:
            username: User who made the request
            operation: Type of operation (ask, analyze, etc.)
            input_tokens: Input token count
            output_tokens: Output token count
            model: Model used
        """
        record = UsageRecord(
            timestamp=datetime.now(),
            username=username,
            operation=operation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            model=model
        )
        
        self.records.append(record)
        logger.info(
            f"Usage recorded: {username} - {operation} - "
            f"{record.total_tokens} tokens (~${record.estimated_cost:.4f})"
        )
    
    def get_user_stats(self, username: str) -> Dict[str, Any]:
        """
        Get usage statistics for a specific user
        
        Args:
            username: Username to get stats for
            
        Returns:
            Usage statistics dictionary
        """
        user_records = [r for r in self.records if r.username == username]
        
        if not user_records:
            return {
                "username": username,
                "total_requests": 0,
                "total_tokens": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "estimated_total_cost": 0.0,
                "operations": {}
            }
        
        total_tokens = sum(r.total_tokens for r in user_records)
        total_input = sum(r.input_tokens for r in user_records)
        total_output = sum(r.output_tokens for r in user_records)
        total_cost = sum(r.estimated_cost for r in user_records)
        
        # Count operations
        operations = {}
        for record in user_records:
            if record.operation not in operations:
                operations[record.operation] = {
                    "count": 0,
                    "tokens": 0,
                    "cost": 0.0
                }
            operations[record.operation]["count"] += 1
            operations[record.operation]["tokens"] += record.total_tokens
            operations[record.operation]["cost"] += record.estimated_cost
        
        return {
            "username": username,
            "total_requests": len(user_records),
            "total_tokens": total_tokens,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "estimated_total_cost": total_cost,
            "operations": operations,
            "first_request": user_records[0].timestamp.isoformat(),
            "last_request": user_records[-1].timestamp.isoformat()
        }
    
    def get_global_stats(self) -> Dict[str, Any]:
        """
        Get global usage statistics across all users
        
        Returns:
            Global statistics dictionary
        """
        if not self.records:
            return {
                "total_requests": 0,
                "total_tokens": 0,
                "estimated_total_cost": 0.0,
                "unique_users": 0,
                "session_start": self.session_start.isoformat(),
                "uptime_hours": 0.0
            }
        
        total_tokens = sum(r.total_tokens for r in self.records)
        total_cost = sum(r.estimated_cost for r in self.records)
        unique_users = len(set(r.username for r in self.records))
        uptime = (datetime.now() - self.session_start).total_seconds() / 3600
        
        return {
            "total_requests": len(self.records),
            "total_tokens": total_tokens,
            "total_input_tokens": sum(r.input_tokens for r in self.records),
            "total_output_tokens": sum(r.output_tokens for r in self.records),
            "estimated_total_cost": total_cost,
            "unique_users": unique_users,
            "session_start": self.session_start.isoformat(),
            "uptime_hours": round(uptime, 2)
        }
    
    def get_recent_history(self, limit: int = 10, username: str = None) -> List[Dict[str, Any]]:
        """
        Get recent usage history
        
        Args:
            limit: Maximum number of records to return
            username: Optional filter by username
            
        Returns:
            List of recent records
        """
        records = self.records
        if username:
            records = [r for r in records if r.username == username]
        
        # Get most recent records
        recent = sorted(records, key=lambda r: r.timestamp, reverse=True)[:limit]
        
        return [
            {
                **asdict(r),
                "timestamp": r.timestamp.isoformat(),
                "estimated_cost": round(r.estimated_cost, 6)
            }
            for r in recent
        ]
    
    def clear_history(self):
        """Clear all usage history"""
        self.records.clear()
        self.session_start = datetime.now()
        logger.info("Usage history cleared")


# Global usage tracker instance
usage_tracker = ClaudeUsageTracker()
