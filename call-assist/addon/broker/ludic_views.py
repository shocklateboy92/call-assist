#!/usr/bin/env python3
"""
Ludic-based FastAPI views for Call Assist Broker web UI

Now using FastAPI dependency injection for clean dependency management.
"""

import logging
from typing import Dict, Any
from fastapi import FastAPI, Form, HTTPException, Path, Request, Depends
from fastapi.responses import HTMLResponse, Response
from ludic.html import div, fieldset, legend, label, input, p
from sqlmodel import Session

from addon.broker.ludic_components import (
    PageLayout,
    AccountsTable,
    AccountForm,
    StatusCard,
    CallHistoryTable,
    SettingsForm,
    ErrorPage,
)
from addon.broker.queries import (
    get_account_by_protocol_and_id_with_session,
    save_account_with_session,
    delete_account_with_session,
    get_call_logs_with_session,
)
from addon.broker.account_service import get_account_service
from addon.broker.settings_service import get_settings_service
from addon.broker.database import DatabaseManager
from addon.broker.models import Account
from addon.broker.dependencies import get_plugin_manager, get_broker_instance, get_database_manager, get_database_session
from addon.broker.plugin_manager import PluginManager

logger = logging.getLogger(__name__)


def get_protocol_schemas(
    plugin_manager: PluginManager = Depends(get_plugin_manager)
) -> Dict[str, Any]:
    """Get protocol schemas from plugin manager (via dependency injection)"""
    try:
        schemas_dict = plugin_manager.get_protocol_schemas()
        return schemas_dict
    except Exception as e:
        logger.error(f"Failed to get protocol schemas: {e}")
        return {}


def create_routes(app: FastAPI):
    """Create all web UI routes with dependency injection"""

    # Add exception handler for all exceptions
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Global exception handler using Ludic ErrorPage component"""
        logger.exception(f"Unhandled exception in {request.url.path}: {exc}")

        # Determine appropriate error message based on exception type
        if isinstance(exc, HTTPException):
            error_title = f"HTTP {exc.status_code} Error"
            error_message = exc.detail
            error_code = exc.status_code
        else:
            error_title = "Internal Server Error"
            error_message = (
                "An unexpected error occurred. Please try again or contact support."
            )
            error_code = 500

        # Show technical details only in debug mode
        show_details = logger.isEnabledFor(logging.DEBUG)
        error_details = str(exc) if show_details else None

        error_page = PageLayout(
            f"{error_title} - Call Assist Broker",
            ErrorPage(
                error_title=error_title,
                error_message=error_message,
                error_code=error_code,
                show_details=show_details,
                error_details=error_details,
            )
        )

        return HTMLResponse(
            content=str(error_page),
            status_code=error_code if isinstance(exc, HTTPException) else 500,
        )

    @app.get("/ui", response_class=HTMLResponse)
    async def main_page(
        account_service = Depends(get_account_service)
    ):
        """Main dashboard page with accounts table"""
        # Get accounts with real-time status checking
        accounts_data = await account_service.get_accounts_with_status()
        
        # Format the updated_at field for display
        for account in accounts_data:
            if account.get("updated_at"):
                # updated_at is already formatted as string from get_accounts_with_status
                account["updated_at"] = account["updated_at"][:16]  # Show only YYYY-MM-DD HH:MM
            else:
                account["updated_at"] = "N/A"

        return PageLayout(
            "Call Assist Broker",
            AccountsTable(accounts=accounts_data)
        )

    @app.get("/ui/add-account", response_class=HTMLResponse)
    async def add_account_page(protocols: Dict[str, Any] = Depends(get_protocol_schemas)):
        """Add new account page"""
        return PageLayout(
            "Add Account - Call Assist Broker",
            AccountForm(protocols=protocols, is_edit=False)
        )

    @app.post("/ui/add-account")
    async def add_account_submit(
        request: Request,
        protocol: str = Form(...),
        account_id: str = Form(...),
        display_name: str = Form(...),
        session: Session = Depends(get_database_session),
    ):
        """Submit new account"""
        # Get all form data for credentials
        form_data = await request.form()
        credentials = {
            key: value
            for key, value in form_data.items()
            if key not in ["protocol", "account_id", "display_name"]
        }

        # Check if account already exists
        existing = get_account_by_protocol_and_id_with_session(session, protocol, account_id)
        if existing:
            raise HTTPException(status_code=400, detail="Account already exists")

        # Create new account
        account = Account(
            protocol=protocol,
            account_id=account_id,
            display_name=display_name,
            credentials_json="",  # Will be set via property
        )
        # Convert form values to strings for credentials
        account.credentials = {k: str(v) for k, v in credentials.items()}

        save_account_with_session(session, account)

        # Redirect to main page
        return Response(
            status_code=302, headers={"Location": "/ui", "HX-Redirect": "/ui"}
        )

    @app.get("/ui/edit-account/{protocol}/{account_id}", response_class=HTMLResponse)
    async def edit_account_page(
        protocol: str = Path(...), 
        account_id: str = Path(...),
        session: Session = Depends(get_database_session),
        protocols: Dict[str, Any] = Depends(get_protocol_schemas),
    ):
        """Edit existing account page"""
        # Load existing account
        existing_account = get_account_by_protocol_and_id_with_session(session, protocol, account_id)
        if not existing_account:
            raise HTTPException(status_code=404, detail="Account not found")

        if protocol not in protocols:
            raise HTTPException(
                status_code=400, detail=f"Protocol '{protocol}' not found"
            )

        # Prepare account data
        account_data = {
            "account_id": existing_account.account_id,
            "display_name": existing_account.display_name,
            **existing_account.credentials,
        }

        return PageLayout(
            "Edit Account - Call Assist Broker",
            AccountForm(
                protocols=protocols,
                selected_protocol=protocol,
                account_data=account_data,
                is_edit=True,
            )
        )

    @app.post("/ui/edit-account/{protocol}/{account_id}")
    async def edit_account_submit(
        request: Request,
        protocol: str = Path(...),
        account_id: str = Path(...),
        new_account_id: str = Form(..., alias="account_id"),
        display_name: str = Form(...),
        session: Session = Depends(get_database_session),
    ):
        """Submit account changes"""
        # Load existing account
        existing_account = get_account_by_protocol_and_id_with_session(session, protocol, account_id)
        if not existing_account:
            raise HTTPException(status_code=404, detail="Account not found")

        # Get all form data for credentials
        form_data = await request.form()
        credentials = {
            key: value
            for key, value in form_data.items()
            if key not in ["account_id", "display_name"]
        }

        # If account_id changed, check if new one already exists
        if new_account_id != existing_account.account_id:
            existing_new = get_account_by_protocol_and_id_with_session(
                session, protocol, new_account_id
            )
            if existing_new:
                raise HTTPException(
                    status_code=400, detail="Account with new ID already exists"
                )

        # Update existing account
        existing_account.account_id = new_account_id
        existing_account.display_name = display_name
        # Convert form values to strings for credentials
        existing_account.credentials = {k: str(v) for k, v in credentials.items()}

        save_account_with_session(session, existing_account)

        # Redirect to main page
        return Response(
            status_code=302, headers={"Location": "/ui", "HX-Redirect": "/ui"}
        )

    @app.delete("/ui/delete-account/{protocol}/{account_id}")
    async def delete_account_endpoint(
        protocol: str = Path(...), 
        account_id: str = Path(...),
        session: Session = Depends(get_database_session),
    ):
        """Delete account endpoint for HTMX"""
        success = delete_account_with_session(session, protocol, account_id)
        if success:
            # Return empty response to remove the table row
            return Response(content="", status_code=200)
        else:
            raise HTTPException(status_code=400, detail="Failed to delete account")

    @app.get("/ui/api/protocol-fields", response_class=HTMLResponse)
    async def get_protocol_fields(
        protocol: str | None = None,
        protocols: Dict[str, Any] = Depends(get_protocol_schemas),
    ):
        """Get protocol-specific form fields for HTMX dynamic loading"""
        if not protocol:
            return HTMLResponse(content="")

        if protocol not in protocols:
            return HTMLResponse(content="<p>Protocol not found</p>")

        schema = protocols[protocol]
        fields = []

        # Basic fields
        fields.append(
            fieldset(
                legend("Account Information"),
                label("Account ID", for_="account_id"),
                input(type="text", name="account_id", id="account_id", required=True),
                label("Display Name", for_="display_name"),
                input(
                    type="text", name="display_name", id="display_name", required=True
                ),
            )
        )

        # Protocol-specific credential fields
        credential_fields = []
        if "credential_fields" in schema:
            for field_config in schema["credential_fields"]:
                field_name = field_config.get("key")
                if field_name in ["account_id", "display_name"]:
                    continue

                field_type = field_config.get("type", "STRING")
                field_label = field_config.get(
                    "display_name", field_name.replace("_", " ").title()
                )
                field_required = field_config.get("required", False)
                field_placeholder = field_config.get("placeholder", "")

                credential_fields.append(label(field_label, for_=field_name))

                if field_type == "PASSWORD":
                    credential_fields.append(
                        input(
                            type="password",
                            name=field_name,
                            id=field_name,
                            placeholder=field_placeholder,
                            required=field_required,
                        )
                    )
                elif field_type == "URL":
                    credential_fields.append(
                        input(
                            type="url",
                            name=field_name,
                            id=field_name,
                            placeholder=field_placeholder,
                            required=field_required,
                        )
                    )
                elif field_type == "INTEGER":
                    credential_fields.append(
                        input(
                            type="number",
                            name=field_name,
                            id=field_name,
                            placeholder=field_placeholder,
                            required=field_required,
                        )
                    )
                else:  # STRING
                    credential_fields.append(
                        input(
                            type="text",
                            name=field_name,
                            id=field_name,
                            placeholder=field_placeholder,
                            required=field_required,
                        )
                    )

        # Protocol-specific setting fields
        setting_fields = []
        if "setting_fields" in schema:
            for field_config in schema["setting_fields"]:
                field_name = field_config.get("key")
                field_type = field_config.get("type", "STRING")
                field_label = field_config.get(
                    "display_name", field_name.replace("_", " ").title()
                )
                field_required = field_config.get("required", False)
                field_placeholder = field_config.get("placeholder", "")

                setting_fields.append(label(field_label, for_=field_name))

                if field_type == "PASSWORD":
                    setting_fields.append(
                        input(
                            type="password",
                            name=field_name,
                            id=field_name,
                            placeholder=field_placeholder,
                            required=field_required,
                        )
                    )
                elif field_type == "URL":
                    setting_fields.append(
                        input(
                            type="url",
                            name=field_name,
                            id=field_name,
                            placeholder=field_placeholder,
                            required=field_required,
                        )
                    )
                elif field_type == "INTEGER":
                    setting_fields.append(
                        input(
                            type="number",
                            name=field_name,
                            id=field_name,
                            placeholder=field_placeholder,
                            required=field_required,
                        )
                    )
                else:  # STRING
                    setting_fields.append(
                        input(
                            type="text",
                            name=field_name,
                            id=field_name,
                            placeholder=field_placeholder,
                            required=field_required,
                        )
                    )

        if credential_fields:
            fields.append(fieldset(legend("Credentials"), *credential_fields))

        if setting_fields:
            fields.append(fieldset(legend("Settings"), *setting_fields))

        return HTMLResponse(content=str(div(*fields)))

    @app.get("/ui/status", response_class=HTMLResponse)
    async def status_page(
        broker = Depends(get_broker_instance),
        plugin_manager: PluginManager = Depends(get_plugin_manager),
        db_manager: DatabaseManager = Depends(get_database_manager)
    ):
        """Status monitoring page"""
        # Database stats
        db_stats = await db_manager.get_database_stats()

        # Broker status
        broker_status = {}
        try:
            broker_status = {
                "status": "Running",
                "active_calls": len(getattr(broker, 'active_calls', [])),
                "configured_accounts": len(getattr(broker, 'account_credentials', {})),
                "available_protocols": ", ".join(
                    plugin_manager.get_available_protocols()
                ),
            }
        except Exception as e:
            logger.error(f"Error getting broker status: {e}")
            broker_status = {"status": "Error", "error": str(e)}

        return PageLayout(
            "Status - Call Assist Broker",
            StatusCard("Database Statistics", db_stats),
            StatusCard("Broker Status", broker_status)
        )

    @app.get("/ui/history", response_class=HTMLResponse)
    async def history_page(session: Session = Depends(get_database_session)):
        """Call history page"""
        call_logs = get_call_logs_with_session(session)
        logs_data = []

        for log in call_logs:
            logs_data.append(
                {
                    "id": log.id,
                    "call_id": log.call_id,
                    "protocol": log.protocol,
                    "target_address": log.target_address,
                    "start_time": (
                        log.start_time.strftime("%Y-%m-%d %H:%M:%S")
                        if log.start_time
                        else "N/A"
                    ),
                    "duration_seconds": log.duration_seconds,
                    "final_state": log.final_state,
                }
            )

        return PageLayout(
            "Call History - Call Assist Broker",
            CallHistoryTable(call_logs=logs_data)
        )

    @app.get("/ui/settings", response_class=HTMLResponse)
    async def settings_page(
        settings_service = Depends(get_settings_service)
    ):
        """Settings page"""
        # Load current settings
        current_settings = await settings_service.get_all_settings()

        return PageLayout(
            "Settings - Call Assist Broker",
            SettingsForm(settings=current_settings)
        )

    @app.post("/ui/settings")
    async def settings_submit(
        web_ui_host: str = Form(...),
        web_ui_port: int = Form(...),
        enable_call_history: bool = Form(False),
        max_call_history_days: int = Form(...),
        auto_cleanup_logs: bool = Form(False),
        settings_service = Depends(get_settings_service)
    ):
        """Submit settings changes"""
        # Save all settings
        settings_data = {
            "web_ui_host": web_ui_host,
            "web_ui_port": web_ui_port,
            "enable_call_history": enable_call_history,
            "max_call_history_days": max_call_history_days,
            "auto_cleanup_logs": auto_cleanup_logs,
        }
        
        await settings_service.update_settings(settings_data)

        # Redirect back to settings page
        return Response(
            status_code=302,
            headers={"Location": "/ui/settings", "HX-Redirect": "/ui/settings"},
        )

    # Return the configured app
    return app
