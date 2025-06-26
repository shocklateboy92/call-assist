#!/usr/bin/env python3
"""
Ludic-based web UI components for Call Assist Broker
"""

from typing import Any, Dict, List, Optional, Union, override
from datetime import datetime

from addon.broker.data_types import (
    AccountStatusData, CallStationStatusData, ProtocolSchemaDict,
    AvailableEntitiesData
)
from ludic.html import (
    html,
    head,
    body,
    title,
    meta,
    link,
    script,
    style,
    div,
    nav,
    main,
    header,
    footer,
    section,
    article,
    h1,
    h2,
    h3,
    h4,
    h5,
    h6,
    p,
    span,
    strong,
    a,
    button,
    form,
    input,
    label,
    select,
    option,
    textarea,
    fieldset,
    legend,
    table,
    thead,
    tbody,
    tr,
    th,
    td,
    ul,
    ol,
    li,
    dl,
    dt,
    dd,
    details,
    summary,
)
from ludic.attrs import GlobalAttrs
from ludic import Component
from ludic.types import AnyChildren, NoChildren
from ludic.styles import CSSProperties


class ErrorPage(Component[NoChildren, GlobalAttrs]):
    """Error page component for displaying exceptions"""

    classes = ["error-page"]
    styles = {
        ".error-page": {
            "max-width": "32rem",
            "margin": "2rem auto",
            "padding": "1rem",
            "text-align": "center",
        },
        ".error-page h1": {"margin-bottom": "1rem"},
        ".error-page p": {"margin-bottom": "0.5rem"},
        ".error-page .error-message": {"font-size": "1.1rem", "margin-bottom": "1rem"},
        ".error-page .error-code": {"color": "#6b7280", "font-size": "0.9rem"},
        ".error-page .error-details": {
            "font-family": "monospace",
            "background": "#f3f4f6",
            "padding": "1rem",
            "border-radius": "0.375rem",
            "font-size": "0.875rem",
        },
        ".error-page .error-navigation": {"margin-top": "2rem"},
        ".error-page .error-navigation a": {"text-decoration": "none"},
    }

    def __init__(
        self,
        error_title: str = "An Error Occurred",
        error_message: str = "Something went wrong",
        error_code: int = 500,
        show_details: bool = False,
        error_details: Optional[str] = None,
        **attrs: Any,
    ):
        self.error_title = error_title
        self.error_message = error_message
        self.error_code = error_code
        self.show_details = show_details
        self.error_details = error_details
        super().__init__(**attrs)

    def render(self) -> div:
        content = [
            h1(f"❌ {self.error_title}"),
            p(self.error_message, class_="error-message"),
            p(f"Error Code: {self.error_code}", class_="error-code"),
        ]

        if self.show_details and self.error_details:
            content.extend(
                [
                    details(
                        summary("Technical Details"),
                        p(self.error_details, class_="error-details"),
                    )
                ]
            )

        content.extend(
            [
                div(
                    a("← Back to Home", href="/ui"),
                    " | ",
                    a("Status Page", href="/ui/status"),
                    class_="error-navigation",
                )
            ]
        )

        return div(*content)


class PageLayout(Component[AnyChildren, GlobalAttrs]):
    """Base page layout with andreasphil design system CSS"""

    def __init__(
        self,
        page_title: str = "Call Assist Broker",
        *children: AnyChildren,
        **attrs: Any,
    ):
        self.page_title = page_title
        super().__init__(*children, **attrs)

    @override
    def render(self) -> html:
        return html(
            head(
                meta(charset="utf-8"),
                meta(name="viewport", content="width=device-width, initial-scale=1"),
                title(self.page_title),
                # andreasphil design system CSS
                link(
                    rel="stylesheet",
                    href="https://cdn.jsdelivr.net/gh/andreasphil/design-system@v0.47.0/dist/design-system.min.css",
                ),
                # HTMX for interactivity
                script(src="https://unpkg.com/htmx.org@1.9.10"),
            ),
            body(
                header(
                    nav(
                        strong("📹 Call Assist Broker"),
                        ul(
                            li(a("Accounts", href="/ui")),
                            li(a("Call Stations", href="/ui/call-stations")),
                            li(a("Status", href="/ui/status")),
                            li(a("Call History", href="/ui/history")),
                            li(a("Settings", href="/ui/settings")),
                        ),
                        data_variant="fixed",
                    ),
                ),
                main(*self.children, style=CSSProperties(padding="1rem")),
                **self.attrs,
            ),
        )


class AccountsTable(Component[NoChildren, GlobalAttrs]):
    """Accounts table component"""

    classes = ["accounts-table"]
    styles = {
        ".accounts-table .accounts-header": {
            "display": "flex",
            "align-items": "center",
            "margin-bottom": "1rem",
        },
        ".accounts-table .add-account-btn": {"margin-left": "auto"},
        ".accounts-table .account-actions": {"display": "flex", "gap": "0.5rem"},
        ".accounts-table .edit-btn": {"font-size": "0.875rem"},
        ".accounts-table .delete-btn": {
            "font-size": "0.875rem",
            "background": "var(--color-danger)",
        },
    }

    def __init__(self, accounts: List[AccountStatusData], **attrs: Any):
        self.accounts = accounts
        super().__init__(**attrs)

    def render(self) -> div:
        if not self.accounts:
            return div(
                p("No accounts configured yet."),
                a("Add Account", href="/ui/add-account", role="button"),
                class_="form-container",
            )

        return div(
            div(
                h2("Accounts"),
                a(
                    "Add Account",
                    href="/ui/add-account",
                    role="button",
                    class_="add-account-btn",
                ),
                class_="accounts-header",
            ),
            div(
                table(
                    thead(
                        tr(
                            th("Protocol"),
                            th("Account ID"),
                            th("Display Name"),
                            th("Status"),
                            th("Last Updated"),
                            th("Actions"),
                        )
                    ),
                    tbody(
                        *[self.render_account_row(account) for account in self.accounts]
                    ),
                ),
                class_="table-container",
            ),
            **self.attrs,
        )

    def render_account_row(self, account: AccountStatusData) -> tr:
        """Render a single account row"""
        status_class = "status-valid" if account.is_valid else "status-invalid"
        status_text = "✅ Valid" if account.is_valid else "❌ Invalid"

        return tr(
            td(account.protocol.title()),
            td(account.account_id),
            td(account.display_name),
            td(status_text, class_=status_class),
            td(account.updated_at),
            td(
                div(
                    a(
                        "Edit",
                        href=f"/ui/edit-account/{account.protocol}/{account.account_id}",
                        role="button",
                        class_="edit-btn",
                    ),
                    button(
                        "Delete",
                        class_="delete-btn",
                        hx_delete=f"/ui/delete-account/{account.protocol}/{account.account_id}",
                        hx_confirm="Are you sure you want to delete this account?",
                        hx_target="closest tr",
                        hx_swap="outerHTML",
                    ),
                    class_="account-actions",
                )
            ),
        )


class AccountForm(Component[None, GlobalAttrs]):
    """Account configuration form component"""

    def __init__(
        self,
        protocols: Dict[str, ProtocolSchemaDict],
        selected_protocol: Optional[str] = None,
        account_data: Optional[Dict[str, Any]] = None,
        is_edit: bool = False,
        **attrs: Any,
    ):
        self.protocols = protocols
        self.selected_protocol = selected_protocol
        self.account_data = account_data or {}
        self.is_edit = is_edit
        super().__init__(**attrs)

    def render(self) -> div:
        form_title = "Edit Account" if self.is_edit else "Add Account"
        form_action = (
            f"/ui/edit-account/{self.selected_protocol}/{self.account_data.get('account_id')}"
            if self.is_edit
            else "/ui/add-account"
        )

        return div(
            div(a("← Back to Accounts", href="/ui"), style="margin-bottom: 1rem;"),
            div(
                h2(form_title),
                form(
                    self.render_protocol_field(),
                    (
                        div(id="dynamic-fields")
                        if not self.is_edit
                        else self.render_account_fields()
                    ),
                    button(
                        "Update Account" if self.is_edit else "Add Account",
                        type="submit",
                        style="width: 100%; margin-top: 1rem;",
                    ),
                    method="post",
                    action=form_action,
                ),
                class_="form-container",
            ),
            **self.attrs,
        )

    def render_protocol_field(self) -> fieldset:
        """Render protocol selection field"""
        if self.is_edit:
            return fieldset(
                legend("Protocol"),
                input(type="hidden", name="protocol", value=self.selected_protocol),
                p(f"Protocol: {(self.selected_protocol or '').title()}"),
            )

        return fieldset(
            legend("Protocol"),
            select(
                option(
                    "Select a protocol...",
                    value="",
                    selected=not self.selected_protocol,
                ),
                *[
                    option(
                        schema.get("display_name", protocol.title()),
                        value=protocol,
                        selected=protocol == self.selected_protocol,
                    )
                    for protocol, schema in self.protocols.items()
                ],
                name="protocol",
                required=True,
                hx_get="/ui/api/protocol-fields",
                hx_target="#dynamic-fields",
                hx_include="[name='protocol']",
            ),
        )

    def render_account_fields(self) -> List[fieldset]:
        """Render account-specific fields for editing"""
        if not self.selected_protocol or self.selected_protocol not in self.protocols:
            return []

        schema = self.protocols[self.selected_protocol]
        fields = []

        # Basic fields
        fields.append(
            fieldset(
                legend("Account Information"),
                label("Account ID", for_="account_id"),
                input(
                    type="text",
                    name="account_id",
                    id="account_id",
                    value=self.account_data.get("account_id", ""),
                    required=True,
                ),
                label("Display Name", for_="display_name"),
                input(
                    type="text",
                    name="display_name",
                    id="display_name",
                    value=self.account_data.get("display_name", ""),
                    required=True,
                ),
            )
        )

        # Protocol-specific fields
        if "credential_fields" in schema:
            credential_fields = []
            for field_def in schema["credential_fields"]:
                field_name = field_def.get("key", "")
                if field_name in ["account_id", "display_name"]:
                    continue

                field_type = field_def.get("type", "text")
                field_label = field_def.get(
                    "display_name", field_name.replace("_", " ").title()
                )
                field_required = field_def.get("required", False)
                field_value = self.account_data.get(field_name, "")

                if field_type == "password":
                    credential_fields.append(label(field_label, for_=field_name))
                    credential_fields.append(
                        input(
                            type="password",
                            name=field_name,
                            id=field_name,
                            value=field_value,
                            required=field_required,
                        )
                    )
                elif field_type == "url":
                    credential_fields.append(label(field_label, for_=field_name))
                    credential_fields.append(
                        input(
                            type="url",
                            name=field_name,
                            id=field_name,
                            value=field_value,
                            required=field_required,
                        )
                    )
                else:
                    credential_fields.append(label(field_label, for_=field_name))
                    credential_fields.append(
                        input(
                            type="text",
                            name=field_name,
                            id=field_name,
                            value=field_value,
                            required=field_required,
                        )
                    )

            if credential_fields:
                fields.append(fieldset(legend("Credentials"), *credential_fields))

        return fields


class StatusCard(Component[None, GlobalAttrs]):
    """Status information card component"""

    def __init__(self, title: str, status_data: Dict[str, Any], **attrs: Any):
        self.title = title
        self.status_data = status_data
        super().__init__(**attrs)

    def render(self) -> section:
        return section(
            h3(self.title),
            dl(
                *[
                    [dt(key.replace("_", " ").title()), dd(str(value))]
                    for key, value in self.status_data.items()
                ]
            ),
            style="border: 1px solid var(--color-border); padding: 1rem; margin-bottom: 1rem; border-radius: 0.5rem;",
            **self.attrs,
        )


class CallHistoryTable(Component[None, GlobalAttrs]):
    """Call history table component"""

    def __init__(self, call_logs: List[Dict[str, Any]], **attrs: Any):
        self.call_logs = call_logs
        super().__init__(**attrs)

    def render(self) -> div:
        if not self.call_logs:
            return div(
                h2("Call History"), p("No call history available."), **self.attrs
            )

        return div(
            h2("Call History"),
            div(
                table(
                    thead(
                        tr(
                            th("Call ID"),
                            th("Protocol"),
                            th("Target"),
                            th("Started"),
                            th("Duration"),
                            th("Status"),
                        )
                    ),
                    tbody(*[self.render_call_row(log) for log in self.call_logs]),
                ),
                class_="table-container",
            ),
            **self.attrs,
        )

    def render_call_row(self, log: Dict[str, Any]) -> tr:
        """Render a single call history row"""
        duration = log.get("duration_seconds", 0)
        if duration:
            minutes = duration // 60
            seconds = duration % 60
            duration_str = f"{minutes}m {seconds}s"
        else:
            duration_str = "N/A"

        return tr(
            td(log.get("call_id", "")),
            td(log.get("protocol", "").title()),
            td(log.get("target_address", "")),
            td(log.get("start_time", "")),
            td(duration_str),
            td(log.get("final_state", "")),
        )


class SettingsForm(Component[None, GlobalAttrs]):
    """Settings configuration form component"""

    def __init__(self, settings: Dict[str, Any], **attrs: Any):
        self.settings = settings
        super().__init__(**attrs)

    def render(self) -> div:
        return div(
            div(a("← Back to Accounts", href="/ui"), style="margin-bottom: 1rem;"),
            div(
                h2("Broker Settings"),
                form(
                    fieldset(
                        legend("Web UI Configuration"),
                        label("Web UI Host", for_="web_ui_host"),
                        input(
                            type="text",
                            name="web_ui_host",
                            id="web_ui_host",
                            value=self.settings.get("web_ui_host", "0.0.0.0"),
                        ),
                        label("Web UI Port", for_="web_ui_port"),
                        input(
                            type="number",
                            name="web_ui_port",
                            id="web_ui_port",
                            value=self.settings.get("web_ui_port", 8080),
                            min="1024",
                            max="65535",
                        ),
                    ),
                    fieldset(
                        legend("Call History"),
                        label(
                            input(
                                type="checkbox",
                                name="enable_call_history",
                                checked=self.settings.get("enable_call_history", True),
                            ),
                            " Enable Call History",
                        ),
                        label("Max Call History (days)", for_="max_call_history_days"),
                        input(
                            type="number",
                            name="max_call_history_days",
                            id="max_call_history_days",
                            value=self.settings.get("max_call_history_days", 30),
                            min="1",
                            max="365",
                        ),
                        label(
                            input(
                                type="checkbox",
                                name="auto_cleanup_logs",
                                checked=self.settings.get("auto_cleanup_logs", True),
                            ),
                            " Auto Cleanup Old Logs",
                        ),
                    ),
                    button(
                        "Save Settings",
                        type="submit",
                        style="width: 100%; margin-top: 1rem;",
                    ),
                    method="post",
                    action="/ui/settings",
                ),
                class_="form-container",
            ),
            **self.attrs,
        )


class CallStationsTable(Component[NoChildren, GlobalAttrs]):
    """Call stations table component"""

    classes = ["call-stations-table"]
    styles = {
        ".call-stations-table .stations-header": {
            "display": "flex",
            "align-items": "center",
            "margin-bottom": "1rem",
        },
        ".call-stations-table .add-station-btn": {"margin-left": "auto"},
        ".call-stations-table .station-actions": {"display": "flex", "gap": "0.5rem"},
        ".call-stations-table .edit-btn": {"font-size": "0.875rem"},
        ".call-stations-table .delete-btn": {
            "font-size": "0.875rem",
            "background": "var(--color-danger)",
        },
        ".call-stations-table .status-available": {"color": "green"},
        ".call-stations-table .status-unavailable": {"color": "red"},
        ".call-stations-table .status-disabled": {"color": "gray"},
    }

    def __init__(self, call_stations: List[CallStationStatusData], **attrs: Any):
        self.call_stations = call_stations
        super().__init__(**attrs)

    def render(self) -> div:
        if not self.call_stations:
            return div(
                p("No call stations configured yet."),
                a("Add Call Station", href="/ui/add-call-station", role="button"),
                class_="form-container",
            )

        return div(
            div(
                h2("Call Stations"),
                a(
                    "Add Call Station",
                    href="/ui/add-call-station",
                    role="button",
                    class_="add-station-btn",
                ),
                class_="stations-header",
            ),
            div(
                table(
                    thead(
                        tr(
                            th("Station Name"),
                            th("Camera"),
                            th("Media Player"),
                            th("Enabled"),
                            th("Status"),
                            th("Last Updated"),
                            th("Actions"),
                        )
                    ),
                    tbody(
                        *[self.render_station_row(station) for station in self.call_stations]
                    ),
                ),
                class_="table-container",
            ),
            **self.attrs,
        )

    def render_station_row(self, station: CallStationStatusData) -> tr:
        """Render a single call station row"""
        # Determine status
        if not station.enabled:
            status_class = "status-disabled"
            status_text = "🔒 Disabled"
        elif station.is_available:
            status_class = "status-available"
            status_text = "✅ Available"
        else:
            status_class = "status-unavailable"
            reasons = []
            if not station.camera_available:
                reasons.append("camera offline")
            if not station.player_available:
                reasons.append("player offline")
            status_text = f"❌ Unavailable ({', '.join(reasons)})"

        enabled_text = "✓ Yes" if station.enabled else "✗ No"

        return tr(
            td(station.display_name),
            td(station.camera_name),
            td(station.player_name),
            td(enabled_text),
            td(status_text, class_=status_class),
            td(station.updated_at),
            td(
                div(
                    a(
                        "Edit",
                        href=f"/ui/edit-call-station/{station.station_id}",
                        role="button",
                        class_="edit-btn",
                    ),
                    button(
                        "Delete",
                        class_="delete-btn",
                        hx_delete=f"/ui/delete-call-station/{station.station_id}",
                        hx_confirm="Are you sure you want to delete this call station?",
                        hx_target="closest tr",
                        hx_swap="outerHTML",
                    ),
                    class_="station-actions",
                )
            ),
        )


class CallStationForm(Component[None, GlobalAttrs]):
    """Call station configuration form component"""

    def __init__(
        self,
        available_entities: Dict[str, List[Dict[str, str]]],
        station_data: Optional[Dict[str, Any]] = None,
        is_edit: bool = False,
        **attrs: Any,
    ):
        self.available_entities = available_entities
        self.station_data = station_data or {}
        self.is_edit = is_edit
        super().__init__(**attrs)

    def render(self) -> div:
        form_title = "Edit Call Station" if self.is_edit else "Add Call Station"
        form_action = (
            f"/ui/edit-call-station/{self.station_data.get('station_id')}"
            if self.is_edit
            else "/ui/add-call-station"
        )

        return div(
            div(a("← Back to Call Stations", href="/ui/call-stations"), style="margin-bottom: 1rem;"),
            div(
                h2(form_title),
                form(
                    fieldset(
                        legend("Station Information"),
                        label("Station ID", for_="station_id"),
                        input(
                            type="text",
                            name="station_id",
                            id="station_id",
                            value=self.station_data.get("station_id", ""),
                            required=True,
                            readonly=self.is_edit,
                            placeholder="e.g., living_room_station",
                        ),
                        label("Display Name", for_="display_name"),
                        input(
                            type="text",
                            name="display_name",
                            id="display_name",
                            value=self.station_data.get("display_name", ""),
                            required=True,
                            placeholder="e.g., Living Room Call Station",
                        ),
                    ),
                    fieldset(
                        legend("Entity Configuration"),
                        label("Camera", for_="camera_entity_id"),
                        select(
                            option("Select a camera...", value="", selected=not self.station_data.get("camera_entity_id")),
                            *[
                                option(
                                    f"{camera['name']} ({camera['entity_id']})",
                                    value=camera['entity_id'],
                                    selected=camera['entity_id'] == self.station_data.get("camera_entity_id"),
                                )
                                for camera in self.available_entities.get("cameras", [])
                            ],
                            name="camera_entity_id",
                            id="camera_entity_id",
                            required=True,
                        ),
                        label("Media Player", for_="media_player_entity_id"),
                        select(
                            option("Select a media player...", value="", selected=not self.station_data.get("media_player_entity_id")),
                            *[
                                option(
                                    f"{player['name']} ({player['entity_id']})",
                                    value=player['entity_id'],
                                    selected=player['entity_id'] == self.station_data.get("media_player_entity_id"),
                                )
                                for player in self.available_entities.get("media_players", [])
                            ],
                            name="media_player_entity_id",
                            id="media_player_entity_id",
                            required=True,
                        ),
                    ),
                    fieldset(
                        legend("Settings"),
                        label(
                            input(
                                type="checkbox",
                                name="enabled",
                                checked=self.station_data.get("enabled", True),
                            ),
                            " Enable this call station",
                        ),
                    ),
                    button(
                        "Update Call Station" if self.is_edit else "Add Call Station",
                        type="submit",
                        style="width: 100%; margin-top: 1rem;",
                    ),
                    method="post",
                    action=form_action,
                ),
                class_="form-container",
            ),
            **self.attrs,
        )
