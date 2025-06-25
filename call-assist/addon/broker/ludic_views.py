#!/usr/bin/env python3
"""
Ludic-based FastAPI views for Call Assist Broker web UI
"""

import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, Form, HTTPException, Path, Request
from fastapi.responses import HTMLResponse, Response
from ludic.html import div, fieldset, legend, label, input_, p

from addon.broker.ludic_components import (
    PageLayout, AccountsTable, AccountForm, StatusCard, 
    CallHistoryTable, SettingsForm
)
from addon.broker.queries import (
    get_all_accounts,
    get_account_by_protocol_and_id,
    save_account,
    delete_account,
    get_setting,
    save_setting,
    get_call_history,
)
from addon.broker.database import get_db_stats
from addon.broker.models import Account

logger = logging.getLogger(__name__)

# Global state for broker reference
_broker_ref = None


def set_broker_reference(broker):
    """Set reference to the broker for accessing protocol schemas and other data"""
    global _broker_ref
    _broker_ref = broker


async def get_protocol_schemas() -> Dict[str, Any]:
    """Get protocol schemas from broker's plugin manager"""
    if _broker_ref:
        try:
            # Access plugin manager directly since we're in the same process
            schemas_dict = _broker_ref.plugin_manager.get_protocol_schemas()
            return schemas_dict
        except Exception as e:
            logger.error(f"Failed to get protocol schemas: {e}")
            return {}
    return {}


def create_routes(app: FastAPI, broker_ref=None):
    """Create all web UI routes"""
    if broker_ref:
        set_broker_reference(broker_ref)
    
    @app.get("/ui", response_class=HTMLResponse)
    async def main_page():
        """Main dashboard page with accounts table"""
        try:
            accounts = await get_all_accounts()
            accounts_data = []
            
            for account in accounts:
                accounts_data.append({
                    "id": account.id,
                    "protocol": account.protocol,
                    "account_id": account.account_id,
                    "display_name": account.display_name,
                    "is_valid": account.is_valid,
                    "updated_at": account.updated_at.strftime("%Y-%m-%d %H:%M") if account.updated_at else "N/A"
                })
            
            return PageLayout(
                page_title="Call Assist Broker",
                children=[AccountsTable(accounts=accounts_data)]
            )
            
        except Exception as e:
            logger.error(f"Failed to load main page: {e}")
            return PageLayout(
                page_title="Call Assist Broker - Error",
                children=[p(f"Error loading accounts: {e}")]
            )
    
    @app.get("/ui/add-account", response_class=HTMLResponse)
    async def add_account_page():
        """Add new account page"""
        try:
            protocols = await get_protocol_schemas()
            return PageLayout(
                page_title="Add Account - Call Assist Broker",
                children=[AccountForm(protocols=protocols, is_edit=False)]
            )
        except Exception as e:
            logger.error(f"Failed to load add account page: {e}")
            return PageLayout(
                page_title="Add Account - Error",
                children=[p(f"Error loading form: {e}")]
            )
    
    @app.post("/ui/add-account")
    async def add_account_submit(
        protocol: str = Form(...),
        account_id: str = Form(...),
        display_name: str = Form(...),
        request: Request = None
    ):
        """Submit new account"""
        try:
            # Get all form data for credentials
            if request:
                form_data = await request.form()
                credentials = {
                    key: value for key, value in form_data.items()
                    if key not in ["protocol", "account_id", "display_name"]
                }
            else:
                credentials = {}
            
            # Check if account already exists
            existing = await get_account_by_protocol_and_id(protocol, account_id)
            if existing:
                raise HTTPException(status_code=400, detail="Account already exists")
            
            # Create new account
            account = Account(
                protocol=protocol,
                account_id=account_id,
                display_name=display_name,
                credentials_json="",  # Will be set via property
            )
            account.credentials = credentials
            
            await save_account(account)
            
            # Redirect to main page
            return Response(
                status_code=302,
                headers={"Location": "/ui", "HX-Redirect": "/ui"}
            )
            
        except Exception as e:
            logger.error(f"Failed to add account: {e}")
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.get("/ui/edit-account/{protocol}/{account_id}", response_class=HTMLResponse)
    async def edit_account_page(
        protocol: str = Path(...),
        account_id: str = Path(...)
    ):
        """Edit existing account page"""
        try:
            # Load existing account
            existing_account = await get_account_by_protocol_and_id(protocol, account_id)
            if not existing_account:
                raise HTTPException(status_code=404, detail="Account not found")
            
            protocols = await get_protocol_schemas()
            if protocol not in protocols:
                raise HTTPException(status_code=400, detail=f"Protocol '{protocol}' not found")
            
            # Prepare account data
            account_data = {
                "account_id": existing_account.account_id,
                "display_name": existing_account.display_name,
                **existing_account.credentials
            }
            
            return PageLayout(
                page_title="Edit Account - Call Assist Broker",
                children=[
                    AccountForm(
                        protocols=protocols,
                        selected_protocol=protocol,
                        account_data=account_data,
                        is_edit=True
                    )
                ]
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to load edit account page: {e}")
            return PageLayout(
                page_title="Edit Account - Error",
                children=[p(f"Error loading account: {e}")]
            )
    
    @app.post("/ui/edit-account/{protocol}/{account_id}")
    async def edit_account_submit(
        protocol: str = Path(...),
        account_id: str = Path(...),
        new_account_id: str = Form(..., alias="account_id"),
        display_name: str = Form(...),
        request: Request = None
    ):
        """Submit account changes"""
        try:
            # Load existing account
            existing_account = await get_account_by_protocol_and_id(protocol, account_id)
            if not existing_account:
                raise HTTPException(status_code=404, detail="Account not found")
            
            # Get all form data for credentials
            if request:
                form_data = await request.form()
                credentials = {
                    key: value for key, value in form_data.items()
                    if key not in ["account_id", "display_name"]
                }
            else:
                credentials = {}
            
            # If account_id changed, check if new one already exists
            if new_account_id != existing_account.account_id:
                existing_new = await get_account_by_protocol_and_id(protocol, new_account_id)
                if existing_new:
                    raise HTTPException(status_code=400, detail="Account with new ID already exists")
            
            # Update existing account
            existing_account.account_id = new_account_id
            existing_account.display_name = display_name
            existing_account.credentials = credentials
            
            await save_account(existing_account)
            
            # Redirect to main page
            return Response(
                status_code=302,
                headers={"Location": "/ui", "HX-Redirect": "/ui"}
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update account: {e}")
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.delete("/ui/delete-account/{protocol}/{account_id}")
    async def delete_account_endpoint(
        protocol: str = Path(...),
        account_id: str = Path(...)
    ):
        """Delete account endpoint for HTMX"""
        try:
            success = await delete_account(protocol, account_id)
            if success:
                # Return empty response to remove the table row
                return Response(content="", status_code=200)
            else:
                raise HTTPException(status_code=400, detail="Failed to delete account")
        except Exception as e:
            logger.error(f"Failed to delete account: {e}")
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.get("/ui/api/protocol-fields", response_class=HTMLResponse)
    async def get_protocol_fields(protocol: str = None):
        """Get protocol-specific form fields for HTMX dynamic loading"""
        if not protocol:
            return HTMLResponse(content="")
        
        try:
            protocols = await get_protocol_schemas()
            if protocol not in protocols:
                return HTMLResponse(content="<p>Protocol not found</p>")
            
            schema = protocols[protocol]
            fields = []
            
            # Basic fields
            fields.append(
                fieldset(
                    legend("Account Information"),
                    label("Account ID", for_="account_id"),
                    input_(
                        type="text",
                        name="account_id",
                        id="account_id",
                        required=True
                    ),
                    label("Display Name", for_="display_name"),
                    input_(
                        type="text",
                        name="display_name",
                        id="display_name",
                        required=True
                    )
                )
            )
            
            # Protocol-specific fields
            if "fields" in schema:
                credential_fields = []
                for field_name, field_def in schema["fields"].items():
                    if field_name in ["account_id", "display_name"]:
                        continue
                    
                    field_type = field_def.get("type", "text")
                    field_label = field_def.get("label", field_name.replace("_", " ").title())
                    field_required = field_def.get("required", False)
                    
                    credential_fields.append(label(field_label, for_=field_name))
                    
                    if field_type == "password":
                        credential_fields.append(
                            input_(
                                type="password",
                                name=field_name,
                                id=field_name,
                                required=field_required
                            )
                        )
                    elif field_type == "url":
                        credential_fields.append(
                            input_(
                                type="url",
                                name=field_name,
                                id=field_name,
                                required=field_required
                            )
                        )
                    else:
                        credential_fields.append(
                            input_(
                                type="text",
                                name=field_name,
                                id=field_name,
                                required=field_required
                            )
                        )
                
                if credential_fields:
                    fields.append(
                        fieldset(
                            legend("Credentials"),
                            *credential_fields
                        )
                    )
            
            return HTMLResponse(content=str(div(*fields)))
            
        except Exception as e:
            logger.error(f"Failed to get protocol fields: {e}")
            return HTMLResponse(content=f"<p>Error loading fields: {e}</p>")
    
    @app.get("/ui/status", response_class=HTMLResponse)
    async def status_page():
        """Status monitoring page"""
        try:
            # Database stats
            db_stats = await get_db_stats()
            
            # Broker status
            broker_status = {}
            if _broker_ref:
                broker_status = {
                    "status": "Running",
                    "active_calls": len(_broker_ref.active_calls),
                    "configured_accounts": len(_broker_ref.account_credentials),
                    "available_protocols": ", ".join(_broker_ref.plugin_manager.get_available_protocols()),
                }
            else:
                broker_status = {"status": "Not Connected"}
            
            return PageLayout(
                page_title="Status - Call Assist Broker",
                children=[
                    StatusCard("Database Statistics", db_stats),
                    StatusCard("Broker Status", broker_status)
                ]
            )
            
        except Exception as e:
            logger.error(f"Failed to load status page: {e}")
            return PageLayout(
                page_title="Status - Error",
                children=[p(f"Error loading status: {e}")]
            )
    
    @app.get("/ui/history", response_class=HTMLResponse)
    async def history_page():
        """Call history page"""
        try:
            call_logs = await get_call_history(50)
            logs_data = []
            
            for log in call_logs:
                logs_data.append({
                    "id": log.id,
                    "call_id": log.call_id,
                    "protocol": log.protocol,
                    "target_address": log.target_address,
                    "start_time": log.start_time.strftime("%Y-%m-%d %H:%M:%S") if log.start_time else "N/A",
                    "duration_seconds": log.duration_seconds,
                    "final_state": log.final_state,
                })
            
            return PageLayout(
                page_title="Call History - Call Assist Broker",
                children=[CallHistoryTable(call_logs=logs_data)]
            )
            
        except Exception as e:
            logger.error(f"Failed to load history page: {e}")
            return PageLayout(
                page_title="Call History - Error",
                children=[p(f"Error loading history: {e}")]
            )
    
    @app.get("/ui/settings", response_class=HTMLResponse)
    async def settings_page():
        """Settings page"""
        try:
            # Load current settings
            current_settings = {
                "web_ui_port": await get_setting("web_ui_port") or 8080,
                "web_ui_host": await get_setting("web_ui_host") or "0.0.0.0",
                "enable_call_history": await get_setting("enable_call_history") or True,
                "max_call_history_days": await get_setting("max_call_history_days") or 30,
                "auto_cleanup_logs": await get_setting("auto_cleanup_logs") or True,
            }
            
            return PageLayout(
                page_title="Settings - Call Assist Broker",
                children=[SettingsForm(settings=current_settings)]
            )
            
        except Exception as e:
            logger.error(f"Failed to load settings page: {e}")
            return PageLayout(
                page_title="Settings - Error",
                children=[p(f"Error loading settings: {e}")]
            )
    
    @app.post("/ui/settings")
    async def settings_submit(
        web_ui_host: str = Form(...),
        web_ui_port: int = Form(...),
        enable_call_history: bool = Form(False),
        max_call_history_days: int = Form(...),
        auto_cleanup_logs: bool = Form(False)
    ):
        """Submit settings changes"""
        try:
            # Save all settings
            await save_setting("web_ui_host", web_ui_host)
            await save_setting("web_ui_port", web_ui_port)
            await save_setting("enable_call_history", enable_call_history)
            await save_setting("max_call_history_days", max_call_history_days)
            await save_setting("auto_cleanup_logs", auto_cleanup_logs)
            
            # Redirect back to settings page
            return Response(
                status_code=302,
                headers={"Location": "/ui/settings", "HX-Redirect": "/ui/settings"}
            )
            
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            raise HTTPException(status_code=400, detail=str(e))