from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def apply_openapi_security(app: FastAPI) -> None:
    """
    Applies Swagger/OpenAPI customization:
    - Adds Bearer/JWT security scheme
    - Applies it globally unless an operation overrides it

    PR-CLEAN-04 Step 3:
    - Extracted from main.py (no behavior change)
    """

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title="Career Counseling API",
            version="0.1.0",
            description="Career Counseling API with JWT Bearer authentication",
            routes=app.routes,
        )

        schema.setdefault("components", {}).setdefault("securitySchemes", {})
        schema["components"]["securitySchemes"]["OAuth2PasswordBearer"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }

        # Apply default security globally unless an operation overrides it
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if "security" not in operation:
                    operation["security"] = [{"OAuth2PasswordBearer": []}]

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi# OpenAPI customization will move here in next steps.
# Placeholder only (no behavior change).
