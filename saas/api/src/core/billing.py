"""
src/core/billing.py — Billing stub (Stripe metered usage).

TODO — implement before charging users:

1. Install dependencies:
   uv pip install stripe

2. Set environment variables:
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_METERED_PRICE_ID=price_...   # Stripe metered price for IaC runs

3. Implement record_usage():
   - Look up the Stripe customer ID for the user
   - Call stripe.billing.MeterEvent.create() with the token count
   - Or use stripe.SubscriptionItem.create_usage_record() for legacy metered billing

4. Implement get_usage_this_period():
   - Query Stripe for the current billing period usage
   - Used to enforce soft quota limits before a run starts

References:
   https://stripe.com/docs/billing/subscriptions/usage-based
   https://stripe.com/docs/api/billing/meter-event/create
"""

from __future__ import annotations

import logging

log = logging.getLogger("saas.api.billing")


async def record_usage(user_id: str, tokens_used: int, run_id: str) -> None:
    """
    TODO — replace stub with real Stripe metered usage recording.

    Current behaviour: logs the intent, does nothing.
    In production this must call Stripe's usage recording API.
    """
    # TODO: look up stripe_customer_id for user_id from DB
    # TODO: stripe.billing.MeterEvent.create(
    #           event_name="iac_tokens",
    #           payload={"stripe_customer_id": ..., "value": tokens_used},
    #       )
    log.info(
        "BILLING STUB — user=%s run=%s tokens=%d (not recorded to Stripe)",
        user_id, run_id, tokens_used,
    )


async def get_usage_this_period(user_id: str) -> int:
    """
    TODO — replace stub with Stripe usage query.

    Current behaviour: returns 0 (no usage tracking).
    In production this must return real usage so quota enforcement works.
    """
    # TODO: query Stripe for current billing period usage
    # TODO: compare against plan limit; raise HTTP 402 if over quota
    log.debug("BILLING STUB — get_usage_this_period for user=%s → 0 (stub)", user_id)
    return 0
