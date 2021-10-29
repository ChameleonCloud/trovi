import re

from django.core import validators
from django.core.validators import RegexValidator
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from typing import List, Any, Optional


class URNField(models.CharField):
    """
    Represents a database Uniform Resource Name
    """

    description = _("URN")
    empty_strings_allowed = False
    default_error_messages = {
        "invalid": _("%(value)s invalid URN."),
    }

    # Validates that a URN follows the format described by
    # https://datatracker.ietf.org/doc/html/rfc8141
    pattern = re.compile(
        r"^urn:(?P<NID>[a-z0-9-]{0,31}):(?P<NSS>[a-z0-9()+,\-.:=@;$_!*'%/?#]+)$",
        flags=re.IGNORECASE,
    )

    @cached_property
    def validators(self) -> List[validators.BaseValidator]:
        return super(URNField, self).validators + [
            RegexValidator(URNField.pattern, message=_("Enter a valid URN."))
        ]

    def to_python(self, value: Any) -> Optional[str]:
        # This enforces that all URNs are converted to lowercase pre-write and post-read
        if value is None:
            return value
        else:
            return super(URNField, self).to_python(value).lower()
