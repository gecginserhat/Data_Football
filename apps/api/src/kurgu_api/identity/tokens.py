"""OIDC erişim token'ı doğrulama (ADR-0005)."""

from dataclasses import dataclass
from typing import Any, Protocol

import anyio
import httpx
import jwt

from kurgu_api.config import Settings


@dataclass(frozen=True)
class TokenClaims:
    issuer: str
    subject: str
    email: str | None
    name: str | None
    mfa: bool
    raw: dict[str, Any]


class InvalidTokenError(Exception):
    pass


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> TokenClaims: ...


MFA_AMR_VALUES = frozenset({"mfa", "otp", "hwk", "swk", "webauthn"})


def claims_from_payload(payload: dict[str, Any]) -> TokenClaims:
    amr = payload.get("amr") or []
    acr = str(payload.get("acr") or "")
    mfa = bool(MFA_AMR_VALUES.intersection(amr)) or acr in {"2", "mfa"}
    name = payload.get("name") or payload.get("preferred_username")
    return TokenClaims(
        issuer=str(payload["iss"]),
        subject=str(payload["sub"]),
        email=payload.get("email"),
        name=str(name) if name else None,
        mfa=mfa,
        raw=payload,
    )


class JwksTokenVerifier:
    """JWKS ile RS256/ES256 imza, `iss`, `aud` ve `exp` doğrulaması."""

    ALGORITHMS = ("RS256", "ES256", "PS256")

    def __init__(self, settings: Settings) -> None:
        self._issuer = settings.oidc_issuer.rstrip("/")
        self._audience = settings.oidc_audience
        self._jwks_url = settings.oidc_jwks_url
        self._client: jwt.PyJWKClient | None = None

    async def _get_client(self) -> jwt.PyJWKClient:
        if self._client is None:
            url = self._jwks_url
            if url is None:
                async with httpx.AsyncClient(timeout=5) as http:
                    response = await http.get(f"{self._issuer}/.well-known/openid-configuration")
                    response.raise_for_status()
                    url = str(response.json()["jwks_uri"])
            self._client = jwt.PyJWKClient(url, cache_keys=True, lifespan=600)
        return self._client

    async def verify(self, token: str) -> TokenClaims:
        try:
            client = await self._get_client()
            signing_key = await anyio.to_thread.run_sync(client.get_signing_key_from_jwt, token)
            payload: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self.ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iss", "sub"]},
            )
        except (jwt.PyJWTError, httpx.HTTPError, KeyError) as exc:
            raise InvalidTokenError(str(exc)) from exc
        return claims_from_payload(payload)
