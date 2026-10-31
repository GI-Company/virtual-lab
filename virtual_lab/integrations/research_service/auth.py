"""Pinned issuer/audience/public keys. No identity or authority from UI flags."""
from dataclasses import dataclass
import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey


class Unauthenticated(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    subject: str
    token_id: str
    expires: int


class TokenVerifier:
    """RS256 only; key IDs select preconfigured keys, never remote URLs.

    A deployment's identity broker must mint short-lived service-audience tokens.
    This class is not a login server or a Supabase/ChatGPT OAuth integration.
    """
    def __init__(self, *, issuer, audience, public_keys, max_age_seconds=900):
        if not issuer.startswith('https://') or not audience or not public_keys:
            raise ValueError('Configure an HTTPS issuer, service audience and pinned public keys')
        self.issuer, self.audience = issuer, audience
        self.max_age = max_age_seconds
        if not 1 <= max_age_seconds <= 900:
            raise ValueError('Service token lifetime must be at most 15 minutes')
        self.keys = {}
        for kid, pem in public_keys.items():
            key = serialization.load_pem_public_key(pem.encode())
            if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
                raise ValueError('Use RSA public keys of at least 2048 bits')
            self.keys[kid] = key

    def verify(self, token):
        try:
            if not isinstance(token, str) or not 1 <= len(token) <= 8192:
                raise Unauthenticated()
            header = jwt.get_unverified_header(token)
            # Do not dereference jku/x5u or accept token-selected algorithms.
            if set(header) - {'alg', 'kid', 'typ'} or header.get('alg') != 'RS256':
                raise Unauthenticated()
            key = self.keys[header['kid']]
            claims = jwt.decode(token, key, algorithms=['RS256'], issuer=self.issuer,
                audience=self.audience, options={'require':['iss','aud','sub','exp','iat','jti']})
            for field in ('sub', 'jti'):
                if not isinstance(claims[field], str) or not 1 <= len(claims[field]) <= 200 or any(ord(c) < 32 for c in claims[field]):
                    raise Unauthenticated()
            if type(claims['iat']) is not int or type(claims['exp']) is not int:
                raise Unauthenticated()
            if not 0 < claims['exp'] - claims['iat'] <= self.max_age or claims['exp'] <= time.time():
                raise Unauthenticated()
            return Principal(claims['sub'], claims['jti'], claims['exp'])
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise Unauthenticated() from exc
