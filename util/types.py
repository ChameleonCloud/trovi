from collections import namedtuple
from typing import Union, Protocol, Type, Dict

from django.db import models


class JSONArray(Protocol):
    __class__: Type[list["JSON"]]


class JSONObject(Protocol):
    __class__: Type[dict[str, "JSON"]]


class JSONPrimitive(Protocol):
    __class__: Type[Union[None, float, int, str]]


JSON = Union[JSONPrimitive, JSONArray, JSONObject]


class APISerializable(Protocol):
    __class__: Type[Union[models.Field, models.Manager, "APIObject"]]


APIObject = Dict[str, Union[APISerializable, JSON]]

# Dumb type used to modify request bodies
DummyRequest = namedtuple("DummyRequest", ["data"])
