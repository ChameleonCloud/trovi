from django.db import models
from typing import TYPE_CHECKING, Union, Protocol, Type, Dict, Any

if TYPE_CHECKING:

    class JSONArray(Protocol):
        __class__: Type[list["JSON"]]

    class JSONObject(Protocol):
        __class__: Type[dict[str, "JSON"]]

    class JSONPrimitive(Protocol):
        __class__: Type[Union[None, float, int, str]]

    JSON = Union[JSONPrimitive, JSONArray, JSONObject]

    class APISerializable(Protocol):
        __class__: Type[Union[models.Field, models.Manager, "APIFormat"]]

    APIFormat = Dict[str, APISerializable]


else:
    JSONPrimitive = Any
    JSON = dict
    APISerializable = Any
    APIFormat = dict
