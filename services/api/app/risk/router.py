from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from tradeforge_shared.schemas import (
    OrderProposal,
    RiskCheckResult,
    UserRiskSettings,
)

from services.api.app.auth.router import UserRecord, get_current_user
from services.api.app.core.logging import logger
from services.api.app.risk.service import global_kill_switch, global_risk_guard
from services.api.app.risk.storage import (
    get_user_risk_settings,
    update_user_risk_settings,
)

router = APIRouter(prefix="/api/v1/risk", tags=["Risk Guard"])


class RiskValidateRequest(BaseModel):
    """
    Pre-trade validation request.
    Security: User limits and trading hours are strictly loaded and enforced server-side.
    """
    proposal: OrderProposal
    current_ltp: float = Field(..., gt=0.0, description="Current Last Traded Price")


class KillSwitchActivateRequest(BaseModel):
    reason: str = Field(default="Manual Emergency Halt")
    scope: str = Field(default="USER", description="'USER' to halt own trading, or 'GLOBAL' for platform halt")
    user_id: Optional[str] = Field(default=None, description="Specific user to halt (admins only)")


class KillSwitchDeactivateRequest(BaseModel):
    scope: str = Field(default="USER", description="'USER' or 'GLOBAL'")
    user_id: Optional[str] = Field(default=None, description="Specific user to unhalt (admins only)")


@router.post("/validate", response_model=RiskCheckResult)
async def validate_order_risk(
    payload: RiskValidateRequest,
    current_user: UserRecord = Depends(get_current_user),
):
    """
    Standalone pre-trade risk verification endpoint.
    Requires authentication. Limits loaded and trading hours enforced server-side per Non-Negotiable Rule 1.
    """
    if payload.proposal.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot validate order proposals for another user account.",
        )

    # Load verified limits from server-side store
    user_settings = get_user_risk_settings(current_user.user_id)

    result = global_risk_guard.validate_proposal(
        proposal=payload.proposal,
        user_settings=user_settings,
        current_ltp=payload.current_ltp,
        enforce_trading_hours=True,
    )
    return result


@router.get("/settings", response_model=UserRiskSettings)
async def get_my_risk_settings(
    current_user: UserRecord = Depends(get_current_user),
):
    """Fetch current user's active risk settings and limits."""
    return get_user_risk_settings(current_user.user_id)


@router.put("/settings", response_model=UserRiskSettings)
async def set_my_risk_settings(
    payload: UserRiskSettings,
    current_user: UserRecord = Depends(get_current_user),
):
    """
    Update authenticated user's risk settings within platform hard ceilings.
    """
    if payload.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify risk settings of another user.",
        )

    return update_user_risk_settings(current_user.user_id, payload)


@router.post("/kill-switch/activate")
async def activate_kill_switch(
    payload: KillSwitchActivateRequest,
    current_user: UserRecord = Depends(get_current_user),
):
    """
    Trigger emergency trading halt.
    - Regular users can halt only their own account.
    - Platform-wide GLOBAL halt requires administrator privileges.
    """
    scope = payload.scope.upper()
    if scope == "GLOBAL":
        if not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only platform administrators can activate the global kill switch.",
            )
        global_kill_switch.activate_global(payload.reason)
        logger.critical(f"GLOBAL KILL SWITCH ACTIVATED by admin {current_user.email}: {payload.reason}")
    else:
        target_user = payload.user_id or current_user.user_id
        if target_user != current_user.user_id and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot activate kill switch for another user account.",
            )
        global_kill_switch.activate_user(target_user, payload.reason)
        logger.warning(f"Kill switch activated for user {target_user} by {current_user.email}: {payload.reason}")

    return {
        "status": "HALTED",
        "scope": scope,
        "global_active": global_kill_switch.is_global_active,
        "user_active": global_kill_switch.is_active_for_user(current_user.user_id),
    }


@router.post("/kill-switch/deactivate")
async def deactivate_kill_switch(
    payload: KillSwitchDeactivateRequest,
    current_user: UserRecord = Depends(get_current_user),
):
    """
    Deactivate emergency trading halt.
    - Global deactivation requires administrator privileges.
    - User unhalt requires the authenticated user or an admin.
    """
    scope = payload.scope.upper()
    if scope == "GLOBAL":
        if not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only platform administrators can deactivate the global kill switch.",
            )
        global_kill_switch.deactivate_global()
        logger.info(f"Global kill switch deactivated by admin {current_user.email}")
    else:
        target_user = payload.user_id or current_user.user_id
        if target_user != current_user.user_id and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot deactivate kill switch for another user account.",
            )
        global_kill_switch.deactivate_user(target_user)
        logger.info(f"Kill switch deactivated for user {target_user} by {current_user.email}")

    return {
        "status": "ACTIVE" if not global_kill_switch.is_active_for_user(current_user.user_id) else "HALTED",
        "scope": scope,
        "global_active": global_kill_switch.is_global_active,
        "user_active": global_kill_switch.is_active_for_user(current_user.user_id),
    }


@router.get("/kill-switch/status")
async def get_kill_switch_status(
    current_user: UserRecord = Depends(get_current_user),
):
    """Check emergency halt status for authenticated session."""
    return {
        "global_active": global_kill_switch.is_global_active,
        "user_active": global_kill_switch.is_active_for_user(current_user.user_id),
        "user_id": current_user.user_id,
        "platform_summary": global_kill_switch.status() if current_user.is_admin else None,
    }
