import datetime
from dataclasses import dataclass, field, fields
from enum import Enum, EnumMeta
from functools import lru_cache

import jwt
from django.conf import settings
from jwt import DecodeError
from rest_framework_simplejwt.exceptions import InvalidToken

LONGEST_EXPIRATION = datetime.datetime.max.timestamp()


class TokenTypes(Enum):
    ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"


# TODO python 3.10: kw_only=True
@dataclass(frozen=True)
class JWT:
    """
    Class for holding data from a provided JWT

    Functions mostly as a convenient interface for interacting with JWTs rather than
    a JSON object. The data in instances of this class cannot be modified. The
    process of "modifying" a token should involve getting a new token.
    """

    class ScopeMeta(EnumMeta):
        def __contains__(cls, item: str) -> bool:
            return item in (s.value for s in cls.__members__.values())

    class Scopes(Enum, metaclass=ScopeMeta):
        ARTIFACTS_READ = "artifacts:read"
        ARTIFACTS_WRITE = "artifacts:write"
        ARTIFACTS_WRITE_METRICS = "artifacts:write_metrics"

    class Algorithm(Enum):
        HS256 = "HS256"
        RS256 = "RS256"

    # Authorized Party: The party to whom the token was issued
    azp: str
    # Audience: The audience for whom the token is intended
    aud: list[str]
    # Issuer: The party who issued the token
    iss: str
    # Issued At: The time at which the token was issued
    iat: int
    # Subject: The subject of the token
    sub: str
    # Expiration: The time past which this token can no longer be used
    exp: int = field(default=int(LONGEST_EXPIRATION))
    # Scope: The authorization scopes granted by this token
    scope: list[Scopes] = field(default_factory=list)
    # Actor: The acting party (IdP) who authorized the token (Trovi Token only)
    act: dict[str, str] = field(default=None)

    # Algorithm: The algorithm with which the key is signed
    alg: Algorithm = field(default=Algorithm.HS256)
    # Key: The key which signed this JWT
    key: bytes = field(default=None)

    # The raw serialized token in base64
    jws: str = field(default=None)

    # Any claims not explicitly declared above
    additional_claims: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, kwargs: dict) -> "JWT":
        """
        Creates a JWT from a dictionary. Helpful for tokens defined as dictionaries
        that have unknown arguments, which are currently unsupported by dataclasses.
        """
        supported_claims = {f.name for f in fields(cls)}
        cleaned = {
            claim: value for claim, value in kwargs.items() if claim in supported_claims
        }
        additional_claims = {
            claim: value
            for claim, value in kwargs.items()
            if claim not in supported_claims
        }
        try:
            return JWT(additional_claims=additional_claims, **cleaned)
        except Exception:
            raise InvalidToken

    @classmethod
    @lru_cache(maxsize=settings.AUTH_TOKEN_CONVERSION_CACHE_SIZE)
    def from_jws(cls, jws: str, validate: bool = True) -> "JWT":
        """
        Creates a JWT from a JWS.
        """
        try:
            options = {"verify_signature": False} if not validate else None
            token = jwt.decode(jws, options=options)
        except DecodeError as e:
            raise InvalidToken(e)

        token["jws"] = jws
        return JWT.from_dict(token)

    def to_jws(self) -> str:
        """
        Serializes this JWT to the base64 representation defined by
        the JWS Spec: https://datatracker.ietf.org/doc/html/rfc7515
        """
        if self.jws:
            return self.jws
        return jwt.encode(
            payload=self.asdict(),
            key=self.key,
            algorithm=self.alg,
        )

    def asdict(self) -> dict:
        """
        Converts this JWT to a dictionary representing its claims
        """
        ret = {
            "azp": self.azp,
            "aud": self.aud,
            "sub": self.sub,
            "iss": self.iss,
            "iat": self.iat,
        }
        if self.exp != LONGEST_EXPIRATION:
            ret["exp"] = self.exp
        if self.scope:
            ret["scope"] = self.scope_to_str()
        if self.act:
            ret["act"] = self.act

        return ret | self.additional_claims

    def scope_to_str(self) -> str:
        return " ".join(s.value for s in self.scope)

    def __repr__(self) -> str:
        return repr(self.asdict())

    def __str__(self) -> str:
        return self.to_jws()

    def __hash__(self) -> int:
        return hash(str(self))


@dataclass(frozen=True)
class OAuth2TokenIntrospection:
    """
    Represents introspection information about a particular token
    """

    # The token itself
    token: JWT

    # True if the token has not been revoked, expired,
    # and was issued by the introspecting server
    active: bool

    # The ID for the OAuth client to whom the token was issued
    client_id: str

    # Human-readable identifier for the user who authorized the token
    username: str

    # Converted from unix timestamp for when this token expires
    exp: datetime.datetime

    # A list of scopes associated with this token
    scope: list[str] = field(default_factory=list)

    # Any other data provided by the introspection endpoint
    additional_claims: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, kwargs: dict) -> "OAuth2TokenIntrospection":
        supported_claims = {f.name for f in fields(cls)}
        cleaned = {
            claim: value for claim, value in kwargs.items() if claim in supported_claims
        }
        additional_claims = {
            claim: value
            for claim, value in kwargs.items()
            if claim not in supported_claims
        }
        try:
            return OAuth2TokenIntrospection(
                additional_claims=additional_claims, **cleaned
            )
        except Exception:
            raise InvalidToken
