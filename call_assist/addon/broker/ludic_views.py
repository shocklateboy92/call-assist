#!/usr/bin/env python3
"""
Ludic-based FastAPI views for Call Assist Broker web UI

Now using FastAPI dependency injection for clean dependency management.
"""

import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Path, Request
from fastapi.responses import HTMLResponse, Response
from ludic.html import a, div, fieldset, input, label, legend, p
from sqlmodel import Session

from .account_service import AccountService, get_account_service
from .broker import CallAssistBroker, HAEntity
from .call_station_service import (
    CallStationService,
    get_call_station_service,
)
from .data_types import (
    EntityInfo,
    SettingsValueType,
)
from .database import DatabaseManager
from .dependencies import (
    get_broker_instance,
    get_database_manager,
    get_database_session,
    get_plugin_manager,
)
from .ludic_components import (
    AccountForm,
    AccountsTable,
    CallHistoryTable,
    CallStationForm,
    CallStationsTable,
    ErrorPage,
    PageLayout,
    SettingsForm,
    StatusCard,
)
from .models import Account, CallStation
from .plugin_manager import PluginManager
from .queries import (
    delete_account_with_session,
    delete_call_station_with_session,
    get_account_by_protocol_and_id_with_session,
    get_call_logs_with_session,
    get_call_station_by_id_with_session,
    save_account_with_session,
    save_call_station_with_session,
)
from .settings_service import SettingsService, get_settings_service

logger = logging.getLogger(__name__)


def convert_ha_entities_to_entity_info(
    ha_entities: dict[str, HAEntity],
) -> dict[str, EntityInfo]:
    """Convert HAEntity dict to EntityInfo dict for type compatibility"""
    return {
        entity_id: EntityInfo(
            entity_id=entity_id,
            name=entity.name,
            domain=entity.domain,
            available=entity.available,
        )
        for entity_id, entity in ha_entities.items()
    }


def create_routes(app: FastAPI) -> None:
    """Create all web UI routes with dependency injection"""

    # Add exception handler for all exceptions
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> Response:
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
                "An unexpected error occurred. Please try again or file an issue."
            )
            error_code = 500

        # Show technical details only in debug mode
        show_details = logger.isEnabledFor(logging.INFO)

        error_page = PageLayout(
            f"{error_title} - Call Assist Broker",
            ErrorPage(
                error_title=error_title,
                error_message=error_message,
                error_code=error_code,
                show_details=show_details,
                exception=exc,
            ),
        )

        return HTMLResponse(
            content=str(error_page),
            status_code=error_code if isinstance(exc, HTTPException) else 500,
        )

    @app.get("/ui", response_class=HTMLResponse)
    async def main_page(
        account_service: Annotated[AccountService, Depends(get_account_service)],
    ) -> PageLayout:
        """Main dashboard page with accounts table"""
        # Get accounts with real-time status checking
        accounts_data = await account_service.get_accounts_with_status()

        # Format the updated_at field for display
        from dataclasses import replace

        formatted_accounts = []
        for account in accounts_data:
            # Create new AccountStatusData with formatted date
            formatted_account = replace(
                account,
                updated_at=(
                    account.updated_at[:16] if account.updated_at else "N/A"
                ),  # Show only YYYY-MM-DD HH:MM
            )
            formatted_accounts.append(formatted_account)

        return PageLayout(
            "Call Assist Broker", AccountsTable(accounts=formatted_accounts)
        )

    @app.get("/ui/add-account", response_class=HTMLResponse)
    async def add_account_page(
        plugin_manager: Annotated[PluginManager, Depends(get_plugin_manager)],
    ) -> PageLayout:
        """Add new account page"""
        protocols = plugin_manager.get_protocol_schemas()
        return PageLayout(
            "Add Account - Call Assist Broker",
            AccountForm(protocols=protocols, is_edit=False),
        )

    @app.post("/ui/add-account")
    async def add_account_submit(
        request: Request,
        session: Annotated[Session, Depends(get_database_session)],
        protocol: str = Form(...),
        account_id: str = Form(...),
        display_name: str = Form(...),
    ) -> Response:
        """Submit new account"""
        # Get all form data for credentials
        form_data = await request.form()
        credentials = {
            key: value
            for key, value in form_data.items()
            if key not in ["protocol", "account_id", "display_name"]
        }

        # Check if account already exists
        existing = get_account_by_protocol_and_id_with_session(
            session, protocol, account_id
        )
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
        session: Annotated[Session, Depends(get_database_session)],
        plugin_manager: Annotated[PluginManager, Depends(get_plugin_manager)],
        protocol: str = Path(...),
        account_id: str = Path(...),
    ) -> PageLayout:
        """Edit existing account page"""
        protocols = plugin_manager.get_protocol_schemas()
        # Load existing account
        existing_account = get_account_by_protocol_and_id_with_session(
            session, protocol, account_id
        )
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
            ),
        )

    @app.post("/ui/edit-account/{protocol}/{account_id}")
    async def edit_account_submit(
        request: Request,
        session: Annotated[Session, Depends(get_database_session)],
        protocol: str = Path(...),
        account_id: str = Path(...),
        new_account_id: str = Form(..., alias="account_id"),
        display_name: str = Form(...),
    ) -> Response:
        """Submit account changes"""
        # Load existing account
        existing_account = get_account_by_protocol_and_id_with_session(
            session, protocol, account_id
        )
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
        session: Annotated[Session, Depends(get_database_session)],
        protocol: str = Path(...),
        account_id: str = Path(...),
    ) -> Response:
        """Delete account endpoint for HTMX"""
        success = delete_account_with_session(session, protocol, account_id)
        if success:
            # Return empty response to remove the table row
            return Response(content="", status_code=200)
        raise HTTPException(status_code=400, detail="Failed to delete account")

    @app.get("/ui/api/protocol-fields", response_class=HTMLResponse)
    async def get_protocol_fields(
        plugin_manager: Annotated[PluginManager, Depends(get_plugin_manager)],
        protocol: str | None = None,
    ) -> HTMLResponse:
        """Get protocol-specific form fields for HTMX dynamic loading"""
        protocols = plugin_manager.get_protocol_schemas()
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
        credential_fields: list[label | input] = []
        if "credential_fields" in schema:
            for field_config in schema["credential_fields"]:
                field_name = field_config.get("key")
                if not field_name or field_name in ["account_id", "display_name"]:
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
        setting_fields: list[label | input] = []
        if "setting_fields" in schema:
            for field_config in schema["setting_fields"]:
                field_name = field_config.get("key")
                if not field_name:
                    continue
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
        broker: Annotated[CallAssistBroker, Depends(get_broker_instance)],
        plugin_manager: Annotated[PluginManager, Depends(get_plugin_manager)],
        db_manager: Annotated[DatabaseManager, Depends(get_database_manager)],
    ) -> PageLayout:
        """Status monitoring page"""
        # Database stats
        db_stats = await db_manager.get_database_stats()

        # Broker status
        broker_status = {}
        try:
            broker_status = {
                "status": "Running",
                "active_calls": len(getattr(broker, "active_calls", [])),
                "configured_accounts": len(getattr(broker, "account_credentials", {})),
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
            StatusCard("Broker Status", broker_status),
        )

    @app.get("/ui/history", response_class=HTMLResponse)
    async def history_page(
        session: Annotated[Session, Depends(get_database_session)],
    ) -> PageLayout:
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
            "Call History - Call Assist Broker", CallHistoryTable(call_logs=logs_data)
        )

    @app.get("/ui/settings", response_class=HTMLResponse)
    async def settings_page(
        settings_service: Annotated[SettingsService, Depends(get_settings_service)],
    ) -> PageLayout:
        """Settings page"""
        # Load current settings
        current_settings = await settings_service.get_all_settings()

        return PageLayout(
            "Settings - Call Assist Broker",
            SettingsForm(settings=dict(current_settings)),
        )

    @app.post("/ui/settings")
    async def settings_submit(
        settings_service: Annotated[SettingsService, Depends(get_settings_service)],
        web_ui_host: str = Form(...),
        web_ui_port: int = Form(...),
        enable_call_history: bool = Form(False),
        max_call_history_days: int = Form(...),
        auto_cleanup_logs: bool = Form(False),
    ) -> Response:
        """Submit settings changes"""
        # Save all settings
        settings_data: dict[str, SettingsValueType] = {
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

    # Call Station Routes

    @app.get("/ui/call-stations", response_class=HTMLResponse)
    async def call_stations_page(
        call_station_service: Annotated[
            CallStationService, Depends(get_call_station_service)
        ],
        broker: Annotated[CallAssistBroker, Depends(get_broker_instance)],
    ) -> PageLayout:
        """Call stations management page"""
        # Get available HA entities for status checking
        ha_entities = broker.ha_entities if broker else {}
        entity_info_dict = convert_ha_entities_to_entity_info(ha_entities)

        # Get call stations with status
        call_stations = call_station_service.get_call_stations_with_status(
            entity_info_dict
        )

        return PageLayout(
            "Call Stations - Call Assist Broker",
            CallStationsTable(call_stations=call_stations),
        )

    @app.get("/ui/add-call-station", response_class=HTMLResponse)
    async def add_call_station_page(
        call_station_service: Annotated[
            CallStationService, Depends(get_call_station_service)
        ],
        broker: Annotated[CallAssistBroker, Depends(get_broker_instance)],
    ) -> PageLayout:
        """Add new call station page"""
        # Get available entities for dropdowns
        ha_entities = broker.ha_entities if broker else {}
        entity_info_dict = convert_ha_entities_to_entity_info(ha_entities)
        available_entities = call_station_service.get_available_entities(
            entity_info_dict
        )

        return PageLayout(
            "Add Call Station - Call Assist Broker",
            CallStationForm(available_entities=available_entities),
        )

    @app.post("/ui/add-call-station")
    async def add_call_station_submit(
        session: Annotated[Session, Depends(get_database_session)],
        call_station_service: Annotated[
            CallStationService, Depends(get_call_station_service)
        ],
        broker: Annotated[CallAssistBroker, Depends(get_broker_instance)],
        station_id: str = Form(...),
        display_name: str = Form(...),
        camera_entity_id: str = Form(...),
        media_player_entity_id: str = Form(...),
        enabled: bool = Form(False),
    ) -> Response:
        """Submit new call station"""
        errors = []

        # Check if station already exists
        existing = get_call_station_by_id_with_session(session, station_id)
        if existing:
            errors.append("Call station already exists")

        # Validate entities exist
        ha_entities = broker.ha_entities if broker else {}
        entity_info_dict = convert_ha_entities_to_entity_info(ha_entities)
        validation_errors = call_station_service.validate_call_station_entities(
            camera_entity_id, media_player_entity_id, entity_info_dict
        )
        if validation_errors.has_errors:
            errors.extend(validation_errors.to_dict().values())

        # If there are errors, return form with errors and preserved input
        if errors:
            # Get available entities for re-rendering the form
            available_entities = call_station_service.get_available_entities(
                entity_info_dict
            )

            # Prepare station data to preserve user input
            station_data = {
                "station_id": station_id,
                "display_name": display_name,
                "camera_entity_id": camera_entity_id,
                "media_player_entity_id": media_player_entity_id,
                "enabled": enabled,
            }

            # Render form with errors
            error_list = div(
                *[p(error, class_="error-message") for error in errors],
                class_="form-errors",
            )

            # Determine appropriate HTTP status code based on error type
            # Check for conflict first (higher priority than validation errors)
            if any("already exists" in error.lower() for error in errors):
                status_code = 409  # Conflict for duplicate resources
            elif any(
                "validation" in error.lower() or "not found" in error.lower()
                for error in errors
            ):
                status_code = 422  # Unprocessable Entity for validation errors
            else:
                status_code = 400  # Default to bad request

            # Return full page with errors and preserved form data
            return HTMLResponse(
                content=str(
                    PageLayout(
                        "Add Call Station - Call Assist Broker",
                        div(
                            a("← Back to Call Stations", href="/ui/call-stations"),
                            error_list,
                            CallStationForm(
                                available_entities=available_entities,
                                station_data=station_data,
                                is_edit=False,
                            ),
                        ),
                    )
                ),
                status_code=status_code,
            )

        # Create new call station
        call_station = CallStation(
            station_id=station_id,
            display_name=display_name,
            camera_entity_id=camera_entity_id,
            media_player_entity_id=media_player_entity_id,
            enabled=enabled,
        )

        save_call_station_with_session(session, call_station)

        # Redirect to call stations page
        return Response(
            status_code=302,
            headers={
                "Location": "/ui/call-stations",
                "HX-Redirect": "/ui/call-stations",
            },
        )

    @app.get("/ui/edit-call-station/{station_id}", response_class=HTMLResponse)
    async def edit_call_station_page(
        session: Annotated[Session, Depends(get_database_session)],
        call_station_service: Annotated[
            CallStationService, Depends(get_call_station_service)
        ],
        broker: Annotated[CallAssistBroker, Depends(get_broker_instance)],
        station_id: str = Path(...),
    ) -> PageLayout:
        """Edit existing call station page"""
        # Load existing call station
        existing_station = get_call_station_by_id_with_session(session, station_id)
        if not existing_station:
            raise HTTPException(status_code=404, detail="Call station not found")

        # Get available entities for dropdowns
        ha_entities = broker.ha_entities if broker else {}
        entity_info_dict = convert_ha_entities_to_entity_info(ha_entities)
        available_entities = call_station_service.get_available_entities(
            entity_info_dict
        )

        # Prepare station data
        station_data = {
            "station_id": existing_station.station_id,
            "display_name": existing_station.display_name,
            "camera_entity_id": existing_station.camera_entity_id,
            "media_player_entity_id": existing_station.media_player_entity_id,
            "enabled": existing_station.enabled,
        }

        return PageLayout(
            "Edit Call Station - Call Assist Broker",
            CallStationForm(
                available_entities=available_entities,
                station_data=station_data,
                is_edit=True,
            ),
        )

    @app.post("/ui/edit-call-station/{station_id}")
    async def edit_call_station_submit(
        session: Annotated[Session, Depends(get_database_session)],
        call_station_service: Annotated[
            CallStationService, Depends(get_call_station_service)
        ],
        broker: Annotated[CallAssistBroker, Depends(get_broker_instance)],
        station_id: str = Path(...),
        display_name: str = Form(...),
        camera_entity_id: str = Form(...),
        media_player_entity_id: str = Form(...),
        enabled: bool = Form(False),
    ) -> Response:
        """Submit call station changes"""
        # Load existing call station
        existing_station = get_call_station_by_id_with_session(session, station_id)
        if not existing_station:
            raise HTTPException(status_code=404, detail="Call station not found")

        # Validate entities exist
        ha_entities = broker.ha_entities if broker else {}
        entity_info_dict = convert_ha_entities_to_entity_info(ha_entities)
        validation_errors = call_station_service.validate_call_station_entities(
            camera_entity_id, media_player_entity_id, entity_info_dict
        )
        if validation_errors.has_errors:
            error_msg = "; ".join(validation_errors.to_dict().values())
            raise HTTPException(
                status_code=400, detail=f"Validation failed: {error_msg}"
            )

        # Update existing call station
        existing_station.display_name = display_name
        existing_station.camera_entity_id = camera_entity_id
        existing_station.media_player_entity_id = media_player_entity_id
        existing_station.enabled = enabled

        save_call_station_with_session(session, existing_station)

        # Redirect to call stations page
        return Response(
            status_code=302,
            headers={
                "Location": "/ui/call-stations",
                "HX-Redirect": "/ui/call-stations",
            },
        )

    @app.delete("/ui/delete-call-station/{station_id}")
    async def delete_call_station_endpoint(
        session: Annotated[Session, Depends(get_database_session)],
        station_id: str = Path(...),
    ) -> Response:
        """Delete call station endpoint for HTMX"""
        success = delete_call_station_with_session(session, station_id)
        if success:
            # Return empty response to remove the table row
            return Response(content="", status_code=200)
        raise HTTPException(status_code=400, detail="Failed to delete call station")
