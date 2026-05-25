"""Billing service - flat rate calculation with discounts and overrides.

Rules:
- Flat rate: configurable PLN/h (default 150 PLN/h)
- Discount reduces billable TIME, not rate
- Per-user discount (global) or per-session discount (PPM override)
- Per-session override: fixed cost OR fixed time
- Per-session discount overrides user global discount
- excluded_from_billing: user has zero cost (vacuum still analyzed)
- Penalty LEFT_VENTED: 100 PLN per occurrence
"""

import logging
from typing import Optional

from models.dataclasses import Session, User, Penalty

logger = logging.getLogger(__name__)

DEFAULT_RATE_PLN_PER_HOUR = 150.0
PENALTY_LEFT_VENTED_PLN = 100.0


class BillingService:
    """Calculates costs for sessions based on flat rate billing."""

    def __init__(self, rate_pln_per_hour: float = DEFAULT_RATE_PLN_PER_HOUR):
        self.rate_pln_per_hour = rate_pln_per_hour

    def calculate_session_cost(
        self,
        session: Session,
        user: Optional[User] = None,
    ) -> float:
        """Calculate cost for a single session.

        Priority:
        1. If excluded_from_billing -> 0.0
        2. If override_cost is set -> use override_cost directly
        3. If override_time_minutes is set -> rate * override_time
        4. Otherwise -> rate * (gvl_total_seconds * (1 - discount%))

        Discount priority:
        - session.discount_percent > 0 -> use session discount
        - user.discount_percent > 0 -> use user discount
        - else -> 0%

        Args:
            session: The session to calculate cost for.
            user: Optional user for global discount lookup.

        Returns:
            Calculated cost in PLN.
        """
        # Check exclusion
        if session.excluded_from_billing:
            return 0.0
        if user and user.excluded_from_billing:
            return 0.0

        # Check override cost (fixed amount)
        if session.override_cost is not None:
            return session.override_cost

        # Determine effective discount
        discount_percent = self._get_effective_discount(session, user)

        # Determine billable seconds
        if session.override_time_minutes is not None:
            billable_seconds = session.override_time_minutes * 60.0
        else:
            # Apply discount percent to GVL total time, then subtract discount hours
            billable_seconds = session.gvl_total_seconds * (
                1.0 - discount_percent / 100.0
            )
            billable_seconds -= session.discount_hours * 3600.0

        # Ensure non-negative
        billable_seconds = max(billable_seconds, 0.0)

        # Calculate cost: rate per hour * hours
        billable_hours = billable_seconds / 3600.0
        cost = billable_hours * self.rate_pln_per_hour

        return round(cost, 2)

    def _get_effective_discount(
        self, session: Session, user: Optional[User]
    ) -> float:
        """Get effective discount - session override takes priority over user global."""
        if session.discount_percent > 0:
            return session.discount_percent
        if user and user.discount_percent > 0:
            return user.discount_percent
        return 0.0

    def calculate_penalty_cost(self, penalty: Penalty) -> float:
        """Calculate penalty cost (always 100 PLN for LEFT_VENTED)."""
        if penalty.penalty_type == "LEFT_VENTED":
            return PENALTY_LEFT_VENTED_PLN
        return penalty.amount_pln

    def calculate_total_for_user(
        self,
        sessions: list,
        penalties: list,
        user: Optional[User] = None,
    ) -> dict:
        """Calculate total billing summary for a user.

        Returns:
            Dictionary with total_cost, total_penalties, total_billable_hours,
            session_count, measurement_count.
        """
        total_cost = 0.0
        total_penalties = 0.0
        total_billable_seconds = 0.0
        measurement_count = 0

        for session in sessions:
            cost = self.calculate_session_cost(session, user)
            total_cost += cost

            if session.gvl_total_seconds > 0:
                measurement_count += 1
                if session.override_time_minutes is not None:
                    total_billable_seconds += session.override_time_minutes * 60.0
                else:
                    discount = self._get_effective_discount(session, user)
                    effective = session.gvl_total_seconds * (1.0 - discount / 100.0)
                    total_billable_seconds += max(effective, 0.0)

        for penalty in penalties:
            total_penalties += self.calculate_penalty_cost(penalty)

        return {
            "total_cost": round(total_cost, 2),
            "total_penalties": round(total_penalties, 2),
            "grand_total": round(total_cost + total_penalties, 2),
            "total_billable_hours": round(total_billable_seconds / 3600.0, 2),
            "session_count": len(sessions),
            "measurement_count": measurement_count,
        }

    def update_rate(self, new_rate: float) -> None:
        """Update the billing rate."""
        if new_rate <= 0:
            raise ValueError("Rate must be positive")
        self.rate_pln_per_hour = new_rate
        logger.info("Billing rate updated to %.2f PLN/h", new_rate)
