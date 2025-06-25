#!/usr/bin/env python3

from nicegui import ui
import logging

from addon.broker.models import Account
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

logger = logging.getLogger(__name__)

# Global state for the UI
ui_state = {
    "selected_account": None,
    "protocol_schemas": {},  # Will be populated from broker
    "broker_ref": None,  # Reference to the broker instance
}


def set_broker_reference(broker):
    """Set reference to the broker for accessing protocol schemas and other data"""
    ui_state["broker_ref"] = broker


async def get_protocol_schemas():
    """Get protocol schemas from broker's plugin manager"""
    if ui_state["broker_ref"]:
        try:
            # Access plugin manager directly since we're in the same process
            schemas_dict = ui_state["broker_ref"].plugin_manager.get_protocol_schemas()
            ui_state["protocol_schemas"] = schemas_dict
            return schemas_dict
        except Exception as e:
            logger.error(f"Failed to get protocol schemas: {e}")
            return {}
    return {}


@ui.page("/ui")
async def main_page():
    """Main dashboard page"""
    ui.page_title("Call Assist Broker")

    with ui.header().classes("items-center justify-between"):
        ui.label("Call Assist Broker").classes("text-h6")
        ui.button("Settings", on_click=lambda: ui.navigate.to("/ui/settings")).classes(
            "q-ml-auto"
        )

    with ui.tabs().classes("w-full") as tabs:
        accounts_tab = ui.tab("Accounts")
        status_tab = ui.tab("Status")
        history_tab = ui.tab("Call History")

    with ui.tab_panels(tabs, value=accounts_tab).classes("w-full"):
        with ui.tab_panel(accounts_tab):
            await accounts_page_content()

        with ui.tab_panel(status_tab):
            await status_page_content()

        with ui.tab_panel(history_tab):
            await history_page_content()


async def accounts_page_content():
    """Account management page content"""
    with ui.column().classes("w-full gap-4"):
        # Header with add button
        with ui.row().classes("w-full items-center"):
            ui.label("Accounts").classes("text-h5")
            ui.button(
                "Add Account",
                icon="add",
                on_click=lambda: ui.navigate.to("/ui/add-account"),
            ).classes("q-ml-auto")

        # Accounts table
        accounts_table = ui.table(
            columns=[
                {"name": "protocol", "label": "Protocol", "field": "protocol"},
                {"name": "account_id", "label": "Account ID", "field": "account_id"},
                {
                    "name": "display_name",
                    "label": "Display Name",
                    "field": "display_name",
                },
                {"name": "status", "label": "Status", "field": "is_valid"},
                {"name": "updated", "label": "Last Updated", "field": "updated_at"},
                {"name": "actions", "label": "Actions", "field": "actions"},
            ],
            rows=[],
            row_key="id",
        ).classes("w-full")

        async def load_accounts():
            """Load accounts from database"""
            try:
                accounts = await get_all_accounts()
                rows = []
                for account in accounts:
                    rows.append(
                        {
                            "id": account.id,
                            "protocol": account.protocol.title(),
                            "account_id": account.account_id,
                            "display_name": account.display_name,
                            "is_valid": (
                                "✅ Valid" if account.is_valid else "❌ Invalid"
                            ),
                            "updated_at": account.updated_at.strftime("%Y-%m-%d %H:%M"),
                            "actions": account,  # Store full account object for actions
                        }
                    )
                accounts_table.rows = rows
            except Exception as e:
                ui.notify(f"Failed to load accounts: {e}", type="negative")

        # Add action buttons for each row
        accounts_table.add_slot(
            "body-cell-actions",
            """
            <q-td :props="props">
                <q-btn size="sm" icon="edit" @click="$parent.$emit('edit', props.row)" />
                <q-btn size="sm" icon="delete" color="negative" @click="$parent.$emit('delete', props.row)" class="q-ml-sm" />
            </q-td>
        """,
        )

        # Handle table events
        async def on_edit(event):
            account_data = event.args
            ui.navigate.to(
                f'/ui/edit-account/{account_data["protocol"]}/{account_data["account_id"]}'
            )

        async def on_delete(event):
            account_data = event.args
            with ui.dialog() as dialog, ui.card():
                ui.label(f'Delete account {account_data["account_id"]}?')
                with ui.row():
                    ui.button("Cancel", on_click=dialog.close)
                    ui.button(
                        "Delete",
                        color="negative",
                        on_click=lambda: delete_account_handler(account_data, dialog),
                    )
            dialog.open()

        async def delete_account_handler(account_data, dialog):
            try:
                success = await delete_account(
                    account_data["protocol"].lower(), account_data["account_id"]
                )
                if success:
                    ui.notify("Account deleted successfully", type="positive")
                    await load_accounts()
                else:
                    ui.notify("Failed to delete account", type="negative")
            except Exception as e:
                ui.notify(f"Error deleting account: {e}", type="negative")
            dialog.close()

        accounts_table.on("edit", on_edit)
        accounts_table.on("delete", on_delete)

        # Load accounts on page load
        await load_accounts()


async def status_page_content():
    """Status monitoring page content"""
    with ui.column().classes("w-full gap-4"):
        ui.label("System Status").classes("text-h5")

        # Database stats
        stats_card = ui.card().classes("w-full")
        with stats_card:
            ui.label("Database Statistics").classes("text-h6")
            stats_content = ui.column()

        # Broker status
        broker_card = ui.card().classes("w-full")
        with broker_card:
            ui.label("Broker Status").classes("text-h6")
            broker_content = ui.column()

        async def load_status():
            """Load system status information"""
            try:
                # Database stats
                db_stats = await get_db_stats()
                stats_content.clear()
                with stats_content:
                    ui.label(f"Accounts: {db_stats.get('accounts', 0)}")
                    ui.label(f"Call Logs: {db_stats.get('call_logs', 0)}")
                    ui.label(f"Settings: {db_stats.get('settings', 0)}")
                    ui.label(f"Database Size: {db_stats.get('database_size_mb', 0)} MB")
                    ui.label(f"Database Path: {db_stats.get('database_path', 'N/A')}")

                # Broker status
                broker_content.clear()
                with broker_content:
                    if ui_state["broker_ref"]:
                        ui.label("✅ Broker Running")
                        ui.label(
                            f"Active Calls: {len(ui_state['broker_ref'].active_calls)}"
                        )
                        ui.label(
                            f"Configured Accounts: {len(ui_state['broker_ref'].account_credentials)}"
                        )
                        ui.label(
                            f"Available Protocols: {', '.join(ui_state['broker_ref'].plugin_manager.get_available_protocols())}"
                        )
                    else:
                        ui.label("❌ Broker Not Connected")

            except Exception as e:
                ui.notify(f"Failed to load status: {e}", type="negative")

        # Refresh button
        ui.button("Refresh Status", icon="refresh", on_click=load_status)

        # Load status on page load
        await load_status()


async def history_page_content():
    """Call history page content"""
    with ui.column().classes("w-full gap-4"):
        ui.label("Call History").classes("text-h5")

        # History table
        history_table = ui.table(
            columns=[
                {"name": "call_id", "label": "Call ID", "field": "call_id"},
                {"name": "protocol", "label": "Protocol", "field": "protocol"},
                {"name": "target", "label": "Target", "field": "target_address"},
                {"name": "start_time", "label": "Started", "field": "start_time"},
                {"name": "duration", "label": "Duration", "field": "duration"},
                {"name": "status", "label": "Status", "field": "final_state"},
            ],
            rows=[],
            row_key="id",
        ).classes("w-full")

        async def load_history():
            """Load call history from database"""
            try:
                call_logs = await get_call_history(50)
                rows = []
                for log in call_logs:
                    duration_str = "N/A"
                    if log.duration_seconds:
                        minutes = log.duration_seconds // 60
                        seconds = log.duration_seconds % 60
                        duration_str = f"{minutes}m {seconds}s"

                    rows.append(
                        {
                            "id": log.id,
                            "call_id": log.call_id,
                            "protocol": log.protocol.title(),
                            "target_address": log.target_address,
                            "start_time": log.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "duration": duration_str,
                            "final_state": log.final_state,
                        }
                    )
                history_table.rows = rows
                history_table.update()
            except Exception as e:
                ui.notify(f"Failed to load call history: {e}", type="negative")

        # Refresh button
        ui.button("Refresh History", icon="refresh", on_click=load_history)

        # Load history on page load
        await load_history()


@ui.page("/ui/add-account")
async def add_account_page():
    """Add new account page"""
    ui.page_title("Add Account - Call Assist Broker")

    with ui.header():
        ui.label("Add Account").classes("text-h6")
        ui.button(
            "Back", icon="arrow_back", on_click=lambda: ui.navigate.to("/ui")
        ).classes("q-ml-auto")

    await get_protocol_schemas()  # Load schemas

    with ui.column().classes("w-full max-w-lg mx-auto gap-4"):
        ui.label("Add New Account").classes("text-h5")

        # Protocol selection
        protocol_options = [
            {"label": schema["display_name"], "value": protocol}
            for protocol, schema in ui_state["protocol_schemas"].items()
        ]
        
        protocol_select = ui.select(
            label="Protocol",
            options=protocol_options,
            value=None,
        ).classes("w-full")

        # Dynamic form container
        form_container = ui.column().classes("w-full")
        current_form = None

        async def on_protocol_change():
            """Update form fields when protocol changes"""
            nonlocal current_form
            protocol = protocol_select.value
            if not protocol or protocol not in ui_state["protocol_schemas"]:
                form_container.clear()
                current_form = None
                return

            # Import form generator here to avoid circular imports
            from addon.broker.form_generator import create_account_form
            
            schema = ui_state["protocol_schemas"][protocol]
            form_container.clear()
            
            with form_container:
                current_form = create_account_form(schema)

                # Submit button
                ui.button("Add Account", on_click=submit_account).classes(
                    "w-full q-mt-md"
                )

        async def submit_account():
            """Submit new account"""
            try:
                if not current_form:
                    ui.notify("Please select a protocol", type="negative")
                    return

                # Validate form
                is_valid, errors = current_form.validate_form()
                if not is_valid:
                    current_form.show_validation_errors(errors)
                    return

                # Get form data
                form_data = current_form.get_form_data()
                protocol = protocol_select.value
                account_id = form_data.get("account_id")
                display_name = form_data.get("display_name")

                # Ensure we have required values
                if not protocol or not account_id or not display_name:
                    ui.notify("Please fill in all required fields", type="negative")
                    return

                # Extract credentials (all fields except account_id and display_name)
                credentials = {
                    key: value for key, value in form_data.items()
                    if key not in ["account_id", "display_name"]
                }

                # Check if account already exists
                existing = await get_account_by_protocol_and_id(protocol, account_id)
                if existing:
                    ui.notify("Account already exists", type="negative")
                    return

                # Create new account
                account = Account(
                    protocol=protocol,
                    account_id=account_id,
                    display_name=display_name,
                    credentials_json="",  # Will be set via property
                )
                account.credentials = credentials

                await save_account(account)
                ui.notify("Account added successfully", type="positive")
                ui.navigate.to("/ui")

            except Exception as e:
                logger.error(f"Failed to add account: {e}")
                ui.notify(f"Failed to add account: {e}", type="negative")

        protocol_select.on("change", on_protocol_change)


@ui.page("/ui/settings")
async def settings_page():
    """Settings page"""
    ui.page_title("Settings - Call Assist Broker")

    with ui.header():
        ui.label("Settings").classes("text-h6")
        ui.button(
            "Back", icon="arrow_back", on_click=lambda: ui.navigate.to("/ui")
        ).classes("q-ml-auto")

    with ui.column().classes("w-full max-w-lg mx-auto gap-4"):
        ui.label("Broker Settings").classes("text-h5")

        # Settings form
        settings_form = {}

        # Load current settings asynchronously
        current_settings = {
            "web_ui_port": await get_setting("web_ui_port") or 8080,
            "web_ui_host": await get_setting("web_ui_host") or "0.0.0.0",
            "enable_call_history": await get_setting("enable_call_history") or True,
            "max_call_history_days": await get_setting("max_call_history_days") or 30,
            "auto_cleanup_logs": await get_setting("auto_cleanup_logs") or True,
        }

        # Create form fields
        settings_form["web_ui_port"] = ui.number(
            label="Web UI Port",
            value=current_settings["web_ui_port"],
            min=1024,
            max=65535,
        ).classes("w-full")

        settings_form["web_ui_host"] = ui.input(
            label="Web UI Host", value=current_settings["web_ui_host"]
        ).classes("w-full")

        settings_form["enable_call_history"] = ui.checkbox(
            "Enable Call History", value=current_settings["enable_call_history"]
        )

        settings_form["max_call_history_days"] = ui.number(
            label="Max Call History (days)",
            value=current_settings["max_call_history_days"],
            min=1,
            max=365,
        ).classes("w-full")

        settings_form["auto_cleanup_logs"] = ui.checkbox(
            "Auto Cleanup Old Logs", value=current_settings["auto_cleanup_logs"]
        )

        async def save_settings():
            """Save settings to database"""
            try:
                for key, field in settings_form.items():
                    value = field.value
                    await save_setting(key, value)

                ui.notify("Settings saved successfully", type="positive")

            except Exception as e:
                logger.error(f"Failed to save settings: {e}")
                ui.notify(f"Failed to save settings: {e}", type="negative")

        ui.button("Save Settings", on_click=save_settings).classes("w-full q-mt-md")


def setup_ui_routes():
    """Set up all UI routes"""
    # Routes are defined using decorators above
    pass


if __name__ == "__main__":
    # For testing the UI standalone
    ui.run(port=8080, show=False)
