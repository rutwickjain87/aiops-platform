"""
src/core/auth.py — Authentication stub (Supabase JWT).

TODO — implement before going to production:

1. Install dependencies:
   uv pip install supabase gotrue python-jose[cryptography]

2. Set environment variables:
   SUPABASE_URL=https://<project>.supabase.co
   SUPABASE_ANON_KEY=eyJ...

3. Implement require_auth():
   - Extract Bearer token from Authorization header
   - Verify JWT using Supabase public key
   - Return the decoded user payload as AuthUser

4. Add to each protected endpoint:
   user: AuthUser = Depends(require_auth)

References:
   https://supabase.com/docs/guides/auth/server-side/creating-a-client
   https://supabase.com/docs/reference/python/introduction
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AuthUser:
    user_id: str
    email: str


async def require_auth() -> AuthUser:
    """
    TODO — replace stub with real Supabase JWT verification.

    Current behaviour: returns a hardcoded dev user.
    In production this must raise HTTP 401 on invalid/missing tokens.
    """
    # TODO: parse Authorization: Bearer <token> header
    # TODO: verify JWT against Supabase JWKS endpoint
    # TODO: raise HTTPException(401) on failure
    return AuthUser(user_id="dev-user-001", email="dev@localhost")
