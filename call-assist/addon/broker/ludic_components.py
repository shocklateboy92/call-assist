#!/usr/bin/env python3
"""
Ludic-based web UI components for Call Assist Broker
"""

from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from ludic.html import (
    html, head, body, title, meta, link, script, style,
    div, nav, main, header, footer, section, article,
    h1, h2, h3, h4, h5, h6, p, span, a, button,
    form, input_, label, select, option, textarea, fieldset, legend,
    table, thead, tbody, tr, th, td,
    ul, ol, li, dl, dt, dd,
    details, summary,
)
from ludic.attrs import GlobalAttrs
from ludic.base import Component
from ludic.types import AnyChildren


class PageLayout(Component[AnyChildren, GlobalAttrs]):
    """Base page layout with andreasphil design system CSS"""
    
    def __init__(
        self,
        page_title: str = "Call Assist Broker",
        show_nav: bool = True,
        *children: AnyChildren,
        **attrs: Any
    ):
        self.page_title = page_title
        self.show_nav = show_nav
        super().__init__(*children, **attrs)
    
    def render(self) -> html:
        return html(
            head(
                meta(charset="utf-8"),
                meta(name="viewport", content="width=device-width, initial-scale=1"),
                title(self.page_title),
                # andreasphil design system CSS
                link(
                    rel="stylesheet",
                    href="https://cdn.jsdelivr.net/gh/andreasphil/design-system@main/dist/index.min.css"
                ),
                # HTMX for interactivity
                script(src="https://unpkg.com/htmx.org@1.9.10"),
                # Custom CSS for Call Assist branding
                style("""
                    :root {
                        --color-primary: #2563eb;
                        --color-primary-variant: #1d4ed8;
                    }
                    .call-assist-header {
                        background: var(--color-primary);
                        color: white;
                        padding: 1rem;
                        margin-bottom: 1rem;
                    }
                    .status-valid { color: #059669; }
                    .status-invalid { color: #dc2626; }
                    .account-actions { display: flex; gap: 0.5rem; }
                    .form-container { max-width: 32rem; margin: 0 auto; }
                    .table-container { overflow-x: auto; }
                """)
            ),
            body(
                header(
                    h1("📹 Call Assist Broker"),
                    class_="call-assist-header"
                ) if self.show_nav else None,
                self.render_navigation() if self.show_nav else None,
                main(*self.children, style="padding: 1rem;"),
                **self.attrs
            )
        )
    
    def render_navigation(self) -> nav:
        """Render navigation menu"""
        return nav(
            ul(
                li(a("Accounts", href="/ui")),
                li(a("Status", href="/ui/status")),
                li(a("Call History", href="/ui/history")),
                li(a("Settings", href="/ui/settings")),
            ),
            style="padding: 0 1rem; margin-bottom: 1rem;"
        )


class AccountsTable(Component[None, GlobalAttrs]):
    """Accounts table component"""
    
    def __init__(self, accounts: List[Dict[str, Any]], **attrs: Any):
        self.accounts = accounts
        super().__init__(**attrs)
    
    def render(self) -> div:
        if not self.accounts:
            return div(
                p("No accounts configured yet."),
                a("Add Account", href="/ui/add-account", role="button"),
                class_="form-container"
            )
        
        return div(
            div(
                h2("Accounts"),
                a("Add Account", href="/ui/add-account", role="button", style="margin-left: auto;"),
                style="display: flex; align-items: center; margin-bottom: 1rem;"
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
                    )
                ),
                class_="table-container"
            ),
            **self.attrs
        )
    
    def render_account_row(self, account: Dict[str, Any]) -> tr:
        """Render a single account row"""
        status_class = "status-valid" if account.get("is_valid") else "status-invalid"
        status_text = "✅ Valid" if account.get("is_valid") else "❌ Invalid"
        
        return tr(
            td(account.get("protocol", "").title()),
            td(account.get("account_id", "")),
            td(account.get("display_name", "")),
            td(status_text, class_=status_class),
            td(account.get("updated_at", "")),
            td(
                div(
                    a("Edit", href=f"/ui/edit-account/{account.get('protocol')}/{account.get('account_id')}", role="button", style="font-size: 0.875rem;"),
                    button(
                        "Delete",
                        style="font-size: 0.875rem; background: var(--color-danger);",
                        **{
                            "hx-delete": f"/ui/delete-account/{account.get('protocol')}/{account.get('account_id')}",
                            "hx-confirm": "Are you sure you want to delete this account?",
                            "hx-target": "closest tr",
                            "hx-swap": "outerHTML"
                        }
                    ),
                    class_="account-actions"
                )
            )
        )


class AccountForm(Component[None, GlobalAttrs]):
    """Account configuration form component"""
    
    def __init__(
        self,
        protocols: Dict[str, Dict[str, Any]],
        selected_protocol: Optional[str] = None,
        account_data: Optional[Dict[str, Any]] = None,
        is_edit: bool = False,
        **attrs: Any
    ):
        self.protocols = protocols
        self.selected_protocol = selected_protocol
        self.account_data = account_data or {}
        self.is_edit = is_edit
        super().__init__(**attrs)
    
    def render(self) -> div:
        form_title = "Edit Account" if self.is_edit else "Add Account"
        form_action = f"/ui/edit-account/{self.selected_protocol}/{self.account_data.get('account_id')}" if self.is_edit else "/ui/add-account"
        
        return div(
            div(
                a("← Back to Accounts", href="/ui"),
                style="margin-bottom: 1rem;"
            ),
            div(
                h2(form_title),
                form(
                    self.render_protocol_field(),
                    div(id="dynamic-fields") if not self.is_edit else self.render_account_fields(),
                    button(
                        "Update Account" if self.is_edit else "Add Account",
                        type="submit",
                        style="width: 100%; margin-top: 1rem;"
                    ),
                    method="post",
                    action=form_action,
                ),
                class_="form-container"
            ),
            **self.attrs
        )
    
    def render_protocol_field(self) -> fieldset:
        """Render protocol selection field"""
        if self.is_edit:
            return fieldset(
                legend("Protocol"),
                input_(
                    type="hidden",
                    name="protocol",
                    value=self.selected_protocol
                ),
                p(f"Protocol: {(self.selected_protocol or '').title()}")
            )
        
        return fieldset(
            legend("Protocol"),
            select(
                option("Select a protocol...", value="", selected=not self.selected_protocol),
                *[
                    option(
                        schema.get("display_name", protocol.title()),
                        value=protocol,
                        selected=protocol == self.selected_protocol
                    )
                    for protocol, schema in self.protocols.items()
                ],
                name="protocol",
                required=True,
                **{"hx-get": "/ui/api/protocol-fields", "hx-target": "#dynamic-fields", "hx-include": "[name='protocol']"}
            )
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
                input_(
                    type="text",
                    name="account_id",
                    id="account_id",
                    value=self.account_data.get("account_id", ""),
                    required=True
                ),
                label("Display Name", for_="display_name"),
                input_(
                    type="text",
                    name="display_name",
                    id="display_name",
                    value=self.account_data.get("display_name", ""),
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
                field_value = self.account_data.get(field_name, "")
                
                if field_type == "password":
                    credential_fields.append(label(field_label, for_=field_name))
                    credential_fields.append(
                        input_(
                            type="password",
                            name=field_name,
                            id=field_name,
                            value=field_value,
                            required=field_required
                        )
                    )
                elif field_type == "url":
                    credential_fields.append(label(field_label, for_=field_name))
                    credential_fields.append(
                        input_(
                            type="url",
                            name=field_name,
                            id=field_name,
                            value=field_value,
                            required=field_required
                        )
                    )
                else:
                    credential_fields.append(label(field_label, for_=field_name))
                    credential_fields.append(
                        input_(
                            type="text",
                            name=field_name,
                            id=field_name,
                            value=field_value,
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
            **self.attrs
        )


class CallHistoryTable(Component[None, GlobalAttrs]):
    """Call history table component"""
    
    def __init__(self, call_logs: List[Dict[str, Any]], **attrs: Any):
        self.call_logs = call_logs
        super().__init__(**attrs)
    
    def render(self) -> div:
        if not self.call_logs:
            return div(
                h2("Call History"),
                p("No call history available."),
                **self.attrs
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
                    tbody(
                        *[self.render_call_row(log) for log in self.call_logs]
                    )
                ),
                class_="table-container"
            ),
            **self.attrs
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
            div(
                a("← Back to Accounts", href="/ui"),
                style="margin-bottom: 1rem;"
            ),
            div(
                h2("Broker Settings"),
                form(
                    fieldset(
                        legend("Web UI Configuration"),
                        label("Web UI Host", for_="web_ui_host"),
                        input_(
                            type="text",
                            name="web_ui_host",
                            id="web_ui_host",
                            value=self.settings.get("web_ui_host", "0.0.0.0")
                        ),
                        label("Web UI Port", for_="web_ui_port"),
                        input_(
                            type="number",
                            name="web_ui_port",
                            id="web_ui_port",
                            value=self.settings.get("web_ui_port", 8080),
                            min="1024",
                            max="65535"
                        )
                    ),
                    fieldset(
                        legend("Call History"),
                        label(
                            input_(
                                type="checkbox",
                                name="enable_call_history",
                                checked=self.settings.get("enable_call_history", True)
                            ),
                            " Enable Call History"
                        ),
                        label("Max Call History (days)", for_="max_call_history_days"),
                        input_(
                            type="number",
                            name="max_call_history_days",
                            id="max_call_history_days",
                            value=self.settings.get("max_call_history_days", 30),
                            min="1",
                            max="365"
                        ),
                        label(
                            input_(
                                type="checkbox",
                                name="auto_cleanup_logs",
                                checked=self.settings.get("auto_cleanup_logs", True)
                            ),
                            " Auto Cleanup Old Logs"
                        )
                    ),
                    button(
                        "Save Settings",
                        type="submit",
                        style="width: 100%; margin-top: 1rem;"
                    ),
                    method="post",
                    action="/ui/settings"
                ),
                class_="form-container"
            ),
            **self.attrs
        )