"""Billing service — calculates costs for sessions.

Business rules:
- Rate determined by: microscope type × billing tier
- Discount reduces TIME, not rate
- Override hierarchy: cost_override > time_override + discount > raw calculation
- Excluded from billing accounts: cost = 0
- Cancelled sessions: cost = 0
"""

import logging
from typing import List, Optional, Dict

from models.enums import BillingTier, MicroscopeType, SessionStatus
from models.dataclasses import Session, User, BillingTierConfig, Penalty

logger = logging.getLogger(__name__)

# Default rates per microscope type per tier
DEFAULT_RATES = {
    MicroscopeType.VEGA3: {
        BillingTier.PROJECT: 150.0,
        BillingTier.UJ_UNIT: 150.0,
        BillingTier.EXTERNAL: 150.0,
    },
    MicroscopeType.MIRA3_FEG: {
        BillingTier.PROJECT: 225.0,
        BillingTier.UJ_UNIT: 225.0,
        BillingTier.EXTERNAL: 225.0,
    },
}


class BillingService:
    """Calculates session costs based on rates, tiers, and discounts.

    Cost calculation priority:
    1. If cancelled → 0
    2. If excluded_from_billing (user) → 0
    3. If cost_override set → use it directly
    4. Otherwise: effective_hours × discount_factor × effective_rate
    """

    def __init__(self, tier_configs: Optional[List[BillingTierConfig]] = None):
        """Initialize with optional tier configurations.

        Args:
            tier_configs: List of BillingTierConfig from database.
                         If None, uses DEFAULT_RATES.
        """
        self._rates: Dict[int, Dict[BillingTier, float]] = {}
        if tier_configs:
            for tc in tier_configs:
                if tc.microscope_id not in self._rates:
                    self._rates[tc.microscope_id] = {}
                self._rates[tc.microscope_id][tc.tier] = tc.rate_pln_per_hour

    def get_rate(
        self, microscope_id: int, microscope_type: MicroscopeType, tier: BillingTier
    ) -> float:
        """Get hourly rate for a specific microscope and tier.

        Falls back to default rate for the microscope type if not configured.
        """
        if microscope_id in self._rates:
            if tier in self._rates[microscope_id]:
                return self._rates[microscope_id][tier]

        # Fallback to defaults
        return DEFAULT_RATES.get(microscope_type, {}).get(tier, 150.0)

    def calculate_session_cost(
        self,
        session: Session,
        user: Optional[User] = None,
    ) -> float:
        """Calculate cost for a single session.

        Args:
            session: Session to calculate cost for.
            user: Optional User object for global discount and billing exclusion.

        Returns:
            Calculated cost in PLN.
        """
        # Cancelled = free
        if session.cancelled or session.status == SessionStatus.CANCELLED:
            return 0.0

        # User excluded from billing
        if user and user.excluded_from_billing:
            return 0.0

        # Cost override takes priority
        if session.cost_override is not None:
            return session.cost_override

        # Determine effective rate
        effective_rate = session.effective_rate
        if effective_rate == session.hourly_rate and session.rate_override is None:
            # No rate override on session, use tier config
            effective_rate = self.get_rate(
                session.microscope_id, session.microscope_type, session.billing_tier
            )

        # Determine effective duration
        if session.time_override_minutes is not None:
            effective_hours = session.time_override_minutes / 60.0
        else:
            effective_hours = session.duration_seconds / 3600.0

        # Apply discount (reduces time, not rate)
        discount_percent = session.discount_percent
        if discount_percent == 0.0 and user and user.discount_percent > 0:
            discount_percent = user.discount_percent

        discount_factor = 1.0 - (discount_percent / 100.0)
        billable_hours = effective_hours * discount_factor

        cost = round(billable_hours * effective_rate, 2)
        return max(cost, 0.0)

    def calculate_batch(
        self,
        sessions: List[Session],
        users: Optional[Dict[str, User]] = None,
    ) -> List[Session]:
        """Calculate costs for a batch of sessions.

        Updates each session's calculated_cost field in place.

        Args:
            sessions: List of sessions to process.
            users: Optional dict of username → User for discount lookup.

        Returns:
            Same list with calculated_cost updated.
        """
        users = users or {}

        for session in sessions:
            user = users.get(session.username)
            session.calculated_cost = self.calculate_session_cost(session, user)

        return sessions

    def get_summary(
        self,
        sessions: List[Session],
        penalties: Optional[List[Penalty]] = None,
    ) -> dict:
        """Generate billing summary.

        Returns:
            Dict with total_cost, total_hours, session_count,
            penalties_total, breakdown by user, breakdown by tier.
        """
        penalties = penalties or []

        total_cost = 0.0
        total_hours = 0.0
        by_user: Dict[str, dict] = {}
        by_tier: Dict[str, dict] = {}

        for session in sessions:
            if session.cancelled or session.excluded_from_invoice:
                continue

            cost = session.effective_cost
            hours = session.effective_duration_seconds / 3600.0
            total_cost += cost
            total_hours += hours

            # By user
            if session.username not in by_user:
                by_user[session.username] = {"cost": 0.0, "hours": 0.0, "sessions": 0}
            by_user[session.username]["cost"] += cost
            by_user[session.username]["hours"] += hours
            by_user[session.username]["sessions"] += 1

            # By tier
            tier_name = session.billing_tier.value
            if tier_name not in by_tier:
                by_tier[tier_name] = {"cost": 0.0, "hours": 0.0, "sessions": 0}
            by_tier[tier_name]["cost"] += cost
            by_tier[tier_name]["hours"] += hours
            by_tier[tier_name]["sessions"] += 1

        penalties_total = sum(p.amount for p in penalties)

        return {
            "total_cost": round(total_cost, 2),
            "total_hours": round(total_hours, 2),
            "session_count": len([s for s in sessions if not s.cancelled]),
            "penalties_total": round(penalties_total, 2),
            "penalties_count": len(penalties),
            "grand_total": round(total_cost + penalties_total, 2),
            "by_user": by_user,
            "by_tier": by_tier,
        }
