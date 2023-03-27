from rest_framework.routers import Route
from rest_framework_extensions import routers


class TroviRouter(routers.ExtendedSimpleRouter):
    """
    Special override for uncooperative routes
    """

    @property
    def routes(self) -> list[Route]:
        return [
            # UnassignRole
            # Typically, this route would be a detail view or an action.
            # Detail view generates a URL with a path parameter with the default router.
            # Action generates a new layer of nesting named after the view (/unassign).
            # This custom route allows UnassignRole to exist at the same path as
            # the other role views (/artifacts/<uuid>/roles/)
            Route(
                url=r"^{prefix}{trailing_slash}$",
                mapping={
                    "delete": "unassign",
                    "get": "list",
                    "post": "create",
                },
                name="{basename}-list",
                detail=False,
                initkwargs={"suffix": "List"},
            )
        ] + super(TroviRouter, self).routes
