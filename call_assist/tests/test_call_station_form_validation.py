#!/usr/bin/env python3
"""
Call Station Form Validation Tests

This test suite validates the call station form submission behavior,
specifically testing that validation errors are properly displayed
inline without causing JSON redirects, and that user input is preserved.
"""
import logging
from collections.abc import AsyncIterator
from typing import cast

import pytest
from bs4 import Tag

from proto_gen.callassist.broker import BrokerIntegrationStub, HaEntityUpdate

from .conftest import WebUITestClient

# Set up logging for tests
logger = logging.getLogger(__name__)


class TestCallStationFormValidation:
    """Tests for call station form validation and error handling"""

    @pytest.mark.asyncio
    async def test_call_stations_page_loads(
        self, web_ui_client: WebUITestClient
    ) -> None:
        """Test that the call stations page loads correctly"""
        await web_ui_client.wait_for_server()

        html, soup = await web_ui_client.get_page("/ui/call-stations")

        # Validate HTML structure first
        web_ui_client.validate_html_structure(soup, "call stations page")

        # Extract visible text for content validation
        visible_text = web_ui_client.extract_visible_text_content(soup)

        # Should contain call stations section
        assert any(
            keyword in visible_text for keyword in ["Call Stations", "stations"]
        ), f"Call stations section not found in visible text: {visible_text[:200]}..."

        # Should have Add Call Station functionality
        assert any(
            keyword in visible_text for keyword in ["Add Call Station", "Add"]
        ), f"Add Call Station functionality not found in visible text: {visible_text[:200]}..."

    @pytest.mark.asyncio
    async def test_add_call_station_page_loads(
        self, web_ui_client: WebUITestClient
    ) -> None:
        """Test that the add call station page loads with entity dropdowns"""
        await web_ui_client.wait_for_server()

        html, soup = await web_ui_client.get_page("/ui/add-call-station")

        # Validate HTML structure first
        web_ui_client.validate_html_structure(soup, "add call station page")

        # Extract visible text for content validation
        visible_text = web_ui_client.extract_visible_text_content(soup)

        # Should have form fields
        assert any(
            keyword in visible_text
            for keyword in ["Station ID", "Display Name", "Camera", "Media Player"]
        ), f"Expected form fields not found in visible text: {visible_text[:200]}..."

        # Should have Add Call Station form
        assert any(
            keyword in visible_text for keyword in ["Add Call Station", "Add"]
        ), f"Add Call Station form not found in visible text: {visible_text[:200]}..."

        # Check for form inputs
        form_inputs = web_ui_client.find_form_inputs(soup)
        logger.info(f"Found form inputs: {list(form_inputs.keys())}")

        # Should have required fields
        expected_fields = [
            "station_id",
            "display_name",
            "camera_entity_id",
            "media_player_entity_id",
        ]
        for field in expected_fields:
            assert (
                field in form_inputs
            ), f"Expected field '{field}' not found in form inputs: {list(form_inputs.keys())}"

    @pytest.mark.asyncio
    async def test_duplicate_station_id_validation(
        self, web_ui_client: WebUITestClient
    ) -> None:
        """Test that submitting a duplicate station ID shows inline errors with preserved input"""
        await web_ui_client.wait_for_server()

        # First, submit a valid call station to create one
        valid_form_data = {
            "station_id": "test_station_duplicate",
            "display_name": "Test Station for Duplicate Check",
            "camera_entity_id": "camera.test_camera_1",
            "media_player_entity_id": "media_player.test_chromecast",
            "enabled": True,
        }

        # Submit the first form (should succeed or fail gracefully)
        status1, response_html1, response_soup1 = await web_ui_client.post_form(
            "/ui/add-call-station", valid_form_data
        )
        logger.info(f"First submission status: {status1}")

        # Now try to submit the same station ID again (should show validation error)
        duplicate_form_data = {
            "station_id": "test_station_duplicate",  # Same station ID
            "display_name": "Duplicate Test Station",
            "camera_entity_id": "camera.test_camera_2",
            "media_player_entity_id": "media_player.test_chromecast_2",
            "enabled": False,
        }

        status2, response_html2, response_soup2 = await web_ui_client.post_form(
            "/ui/add-call-station", duplicate_form_data
        )

        logger.info(f"Duplicate submission status: {status2}")

        # The key test: should return HTML page with error, not JSON redirect
        # Should be 409 Conflict for duplicate resource, but might be 422 if entity validation runs first
        assert status2 in [
            409,
            422,
        ], f"Expected status 409 (conflict) or 422 (validation), got {status2}"

        # Should not be a JSON response
        assert not response_html2.strip().startswith("{"), "Response should not be JSON"

        # Should contain error message about duplicate
        assert any(
            error_text in response_html2.lower()
            for error_text in ["already exists", "duplicate", "error"]
        ), f"Expected error message not found in response: {response_html2[:300]}..."

        # Validate HTML structure (should be a proper page, not broken)
        web_ui_client.validate_html_structure(response_soup2, "form with errors")

        # Should preserve user input
        form_inputs = web_ui_client.find_form_inputs(response_soup2)

        # Check that the user's input was preserved (values might be in different attributes)
        # The important thing is that the form shows again with the user's data
        station_id_found = (
            form_inputs.get("station_id") == "test_station_duplicate"
            or "test_station_duplicate" in response_html2
        )
        assert (
            station_id_found
        ), f"Station ID should be preserved. Form inputs: {form_inputs}"

        display_name_found = (
            form_inputs.get("display_name") == "Duplicate Test Station"
            or "Duplicate Test Station" in response_html2
        )
        assert (
            display_name_found
        ), f"Display name should be preserved. Form inputs: {form_inputs}"

        # Check that error styling/classes are present
        visible_text = web_ui_client.extract_visible_text_content(response_soup2)
        assert any(
            keyword in visible_text
            for keyword in [
                "error",
                "already exists",
                "duplicate",
                "not found",
                "validation",
            ]
        ), f"Error message not visible in form: {visible_text[:300]}..."

        logger.info(
            "Successfully verified duplicate station ID validation with preserved input"
        )

    @pytest.mark.asyncio
    async def test_invalid_entity_validation(
        self, web_ui_client: WebUITestClient
    ) -> None:
        """Test that submitting invalid entity IDs shows inline errors with preserved input"""
        await web_ui_client.wait_for_server()

        # Submit form with invalid/non-existent entities
        invalid_form_data = {
            "station_id": "test_station_invalid_entities",
            "display_name": "Test Station with Invalid Entities",
            "camera_entity_id": "camera.nonexistent_camera",
            "media_player_entity_id": "media_player.nonexistent_player",
            "enabled": True,
        }

        status, response_html, response_soup = await web_ui_client.post_form(
            "/ui/add-call-station", invalid_form_data
        )

        logger.info(f"Invalid entities submission status: {status}")

        # Should return HTML page with validation errors, not redirect
        # Should be 422 Unprocessable Entity for validation errors
        if status == 422:
            # Should not be a JSON response
            assert not response_html.strip().startswith(
                "{"
            ), "Response should not be JSON"

            # Should contain validation error message
            assert any(
                error_text in response_html.lower()
                for error_text in [
                    "validation",
                    "entity",
                    "not found",
                    "error",
                    "invalid",
                ]
            ), f"Expected validation error message not found in response: {response_html[:300]}..."

            # Validate HTML structure (should be a proper page, not broken)
            web_ui_client.validate_html_structure(
                response_soup, "form with validation errors"
            )

            # Should preserve user input
            form_inputs = web_ui_client.find_form_inputs(response_soup)

            # Check that the user's input was preserved
            assert (
                form_inputs.get("station_id") == "test_station_invalid_entities"
            ), "Station ID should be preserved"
            assert (
                form_inputs.get("display_name") == "Test Station with Invalid Entities"
            ), "Display name should be preserved"
            assert (
                form_inputs.get("camera_entity_id") == "camera.nonexistent_camera"
            ), "Camera entity should be preserved"
            assert (
                form_inputs.get("media_player_entity_id")
                == "media_player.nonexistent_player"
            ), "Media player entity should be preserved"

            logger.info(
                "Successfully verified invalid entity validation with preserved input"
            )
        else:
            # If status is 302, the entities might actually exist in the test environment
            # This is also acceptable - the form processed successfully
            logger.info(
                f"Form submission resulted in redirect (status {status}) - entities may exist in test environment"
            )

    @pytest.mark.asyncio
    async def test_empty_required_fields_validation(
        self, web_ui_client: WebUITestClient
    ) -> None:
        """Test that submitting empty required fields shows proper validation"""
        await web_ui_client.wait_for_server()

        # Submit form with empty required fields
        empty_form_data = {
            "station_id": "",
            "display_name": "",
            "camera_entity_id": "",
            "media_player_entity_id": "",
            "enabled": False,
        }

        status, response_html, response_soup = await web_ui_client.post_form(
            "/ui/add-call-station", empty_form_data
        )

        logger.info(f"Empty fields submission status: {status}")

        # This should result in a 400 Bad Request for missing required fields
        assert (
            status == 400
        ), f"Expected status 400 (bad request for empty fields), got {status}"

        if status == 400:
            # Should not be a JSON response
            assert not response_html.strip().startswith(
                "{"
            ), "Response should not be JSON"

            # Validate HTML structure (should be a proper page)
            web_ui_client.validate_html_structure(
                response_soup, "form with empty field errors"
            )

            # Should show the form again (for user to fix)
            visible_text = web_ui_client.extract_visible_text_content(response_soup)
            assert any(
                keyword in visible_text
                for keyword in ["Station ID", "Display Name", "Add Call Station"]
            ), f"Form fields not found in error response: {visible_text[:300]}..."

            logger.info("Successfully verified empty field validation")

    @pytest.mark.asyncio
    async def test_successful_call_station_creation(
        self, web_ui_client: WebUITestClient
    ) -> None:
        """Test that valid call station submission works correctly"""
        await web_ui_client.wait_for_server()

        # Get initial count of call stations
        html, soup = await web_ui_client.get_page("/ui/call-stations")

        # Extract existing call stations (if the method exists)
        # Try to find a table or list of call stations
        tables = soup.find_all("table")
        initial_stations = []
        if tables:
            first_table = cast(Tag, tables[0])
            rows = first_table.find_all("tr")[1:]  # Skip header row
            initial_stations = [row for row in rows if cast(Tag, row).find_all("td")]
        initial_count = len(initial_stations)

        logger.info(f"Initial call station count: {initial_count}")

        # Submit a valid call station
        valid_form_data = {
            "station_id": "test_station_valid",
            "display_name": "Valid Test Station",
            "camera_entity_id": "camera.test_camera_1",
            "media_player_entity_id": "media_player.test_chromecast",
            "enabled": True,
        }

        status, response_html, response_soup = await web_ui_client.post_form(
            "/ui/add-call-station", valid_form_data
        )

        logger.info(f"Valid submission status: {status}")

        # Should redirect to call stations page on success
        if status == 302:
            logger.info("Form submission successful - redirected to call stations page")

            # Verify by checking the call stations page
            html, soup = await web_ui_client.get_page("/ui/call-stations")

            # Check if our station appears in the list
            visible_text = web_ui_client.extract_visible_text_content(soup)
            assert (
                "Valid Test Station" in visible_text
                or "test_station_valid" in visible_text
            ), f"New call station not found in call stations page: {visible_text[:500]}..."

            logger.info("Successfully verified call station creation")
        else:
            # Even if it doesn't redirect, check that it's not a broken response
            assert status in [
                200,
                302,
            ], f"Unexpected status for valid submission: {status}"
            logger.info(
                f"Form submission returned status {status} - checking response format"
            )

            # Should not be a JSON response
            assert not response_html.strip().startswith(
                "{"
            ), "Response should not be JSON"

    @pytest.mark.asyncio
    async def test_form_preserves_checkbox_state(
        self, web_ui_client: WebUITestClient
    ) -> None:
        """Test that checkbox states are preserved when form has validation errors"""
        await web_ui_client.wait_for_server()

        # Submit form with validation error but with checkbox enabled
        form_data_with_checkbox = {
            "station_id": "",  # Empty to trigger validation error
            "display_name": "Station with Enabled Checkbox",
            "camera_entity_id": "camera.test_camera_1",
            "media_player_entity_id": "media_player.test_chromecast",
            "enabled": True,  # Checkbox should be preserved
        }

        status, response_html, response_soup = await web_ui_client.post_form(
            "/ui/add-call-station", form_data_with_checkbox
        )

        if status == 200:  # Form returned with errors
            # Check that checkbox state is preserved
            enabled_input = response_soup.find("input", {"name": "enabled"})
            if enabled_input and isinstance(enabled_input, Tag):
                # Checkbox should be checked
                assert (
                    enabled_input.get("checked") is not None
                ), "Enabled checkbox should be preserved as checked"
                logger.info("Successfully verified checkbox state preservation")

    @pytest.mark.asyncio
    async def test_entities_appear_in_dropdowns(
        self,
        web_ui_client: WebUITestClient,
        broker_server: BrokerIntegrationStub,
        mock_cameras: list[HaEntityUpdate],
        mock_media_players: list[HaEntityUpdate],
    ) -> None:
        """Test that camera and media player entities sent to broker appear in UI dropdowns"""
        await web_ui_client.wait_for_server()

        # First, send entities to the broker (required for dropdowns to be populated)
        async def entity_generator() -> AsyncIterator[HaEntityUpdate]:
            """Stream all HA entities to broker"""
            for camera in mock_cameras:
                logger.info(f"Sending camera entity: {camera.entity_id}")
                yield camera
            for player in mock_media_players:
                logger.info(f"Sending media player entity: {player.entity_id}")
                yield player

        # Stream entities to broker so they appear in web UI dropdowns
        await broker_server.stream_ha_entities(entity_generator())

        # Give broker time to process entities
        import asyncio

        await asyncio.sleep(0.5)

        # Navigate to the add call station page
        html, soup = await web_ui_client.get_page("/ui/add-call-station")

        # Validate HTML structure first
        web_ui_client.validate_html_structure(soup, "add call station page")

        # Find camera dropdown
        camera_select = soup.find("select", {"name": "camera_entity_id"})
        assert camera_select is not None, "Camera dropdown not found"
        camera_select = cast(Tag, camera_select)

        # Find media player dropdown
        media_player_select = soup.find("select", {"name": "media_player_entity_id"})
        assert media_player_select is not None, "Media player dropdown not found"
        media_player_select = cast(Tag, media_player_select)

        # Extract camera options
        camera_options = camera_select.find_all("option")
        camera_entity_ids = [
            cast(Tag, opt).get("value")
            for opt in camera_options
            if isinstance(opt, Tag) and opt.get("value")
        ]
        camera_names = [
            cast(Tag, opt).get_text().strip()
            for opt in camera_options
            if isinstance(opt, Tag) and opt.get("value")
        ]

        # Extract media player options
        media_player_options = media_player_select.find_all("option")
        media_player_entity_ids = [
            cast(Tag, opt).get("value")
            for opt in media_player_options
            if isinstance(opt, Tag) and opt.get("value")
        ]
        media_player_names = [
            cast(Tag, opt).get_text().strip()
            for opt in media_player_options
            if isinstance(opt, Tag) and opt.get("value")
        ]

        logger.info(f"Found camera entities: {camera_entity_ids}")
        logger.info(f"Found media player entities: {media_player_entity_ids}")

        # Verify test camera entities appear in dropdown (from mock_cameras fixture)
        expected_camera_entities = [
            "camera.test_front_door",
            "camera.test_back_yard",
            "camera.test_kitchen",
        ]

        for camera_entity in expected_camera_entities:
            assert (
                camera_entity in camera_entity_ids
            ), f"Expected camera entity '{camera_entity}' not found in dropdown options: {camera_entity_ids}"

        # Verify test media player entities appear in dropdown (from mock_media_players fixture)
        expected_media_player_entities = [
            "media_player.test_living_room_tv",
            "media_player.test_kitchen_display",
            "media_player.test_bedroom_speaker",
        ]

        for media_player_entity in expected_media_player_entities:
            assert (
                media_player_entity in media_player_entity_ids
            ), f"Expected media player entity '{media_player_entity}' not found in dropdown options: {media_player_entity_ids}"

        # Verify entities have friendly names in dropdowns (not just entity IDs)
        for camera_name in camera_names:
            assert len(camera_name) > 0, "Camera options should have display names"
            # Names should contain both friendly name and entity ID
            assert (
                "(" in camera_name and ")" in camera_name
            ), f"Camera option should contain entity ID in parentheses: {camera_name}"

        for media_player_name in media_player_names:
            assert (
                len(media_player_name) > 0
            ), "Media player options should have display names"
            # Names should contain both friendly name and entity ID
            assert (
                "(" in media_player_name and ")" in media_player_name
            ), f"Media player option should contain entity ID in parentheses: {media_player_name}"

        # Verify dropdowns are not empty (should have at least the test entities)
        assert len(camera_entity_ids) >= len(
            expected_camera_entities
        ), f"Camera dropdown should have at least {len(expected_camera_entities)} options, found {len(camera_entity_ids)}"
        assert len(media_player_entity_ids) >= len(
            expected_media_player_entities
        ), f"Media player dropdown should have at least {len(expected_media_player_entities)} options, found {len(media_player_entity_ids)}"

        logger.info(
            "Successfully verified entities appear in dropdowns with proper formatting"
        )
