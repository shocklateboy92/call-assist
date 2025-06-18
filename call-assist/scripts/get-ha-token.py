#!/usr/bin/env python3

"""
Script to get or create a Home Assistant long-lived access token for testing.
Logs in with test credentials and creates a token programmatically.
"""

import asyncio
import aiohttp
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HA_BASE_URL = "http://homeassistant:8123"
USERNAME = "test"
PASSWORD = "test"

async def login_and_get_token():
    """Login to Home Assistant and get a long-lived access token."""
    async with aiohttp.ClientSession() as session:
        try:
            # Step 1: Get auth providers
            async with session.get(f"{HA_BASE_URL}/auth/providers") as resp:
                if resp.status != 200:
                    logger.error(f"Failed to get auth providers: {resp.status}")
                    return None
                
                providers = await resp.json()
                logger.info("✅ Got auth providers")
            
            # Step 2: Start login flow
            async with session.post(f"{HA_BASE_URL}/auth/login_flow", 
                                   json={"handler": ["homeassistant", None]}) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to start login flow: {resp.status}")
                    return None
                
                flow_result = await resp.json()
                flow_id = flow_result.get("flow_id")
                logger.info(f"✅ Started login flow: {flow_id}")
            
            # Step 3: Submit credentials
            login_data = {
                "username": USERNAME,
                "password": PASSWORD
            }
            
            async with session.post(f"{HA_BASE_URL}/auth/login_flow/{flow_id}", 
                                   json=login_data) as resp:
                if resp.status != 200:
                    logger.error(f"Login failed: {resp.status}")
                    response_text = await resp.text()
                    logger.error(f"Response: {response_text}")
                    return None
                
                login_result = await resp.json()
                logger.info("✅ Login successful")
                
                # Check if we got an auth code
                auth_code = login_result.get("result")
                if not auth_code:
                    logger.error("No auth code in login response")
                    return None
            
            # Step 4: Exchange auth code for access token
            token_data = {
                "grant_type": "authorization_code",
                "code": auth_code
            }
            
            async with session.post(f"{HA_BASE_URL}/auth/token", json=token_data) as resp:
                if resp.status != 200:
                    logger.error(f"Token exchange failed: {resp.status}")
                    response_text = await resp.text()
                    logger.error(f"Response: {response_text}")
                    return None
                
                token_result = await resp.json()
                access_token = token_result.get("access_token")
                
                if access_token:
                    logger.info("✅ Got access token")
                    
                    # Test the token
                    headers = {"Authorization": f"Bearer {access_token}"}
                    async with session.get(f"{HA_BASE_URL}/api/", headers=headers) as resp:
                        if resp.status == 200:
                            api_info = await resp.json()
                            logger.info(f"✅ Token is valid - HA version: {api_info.get('version')}")
                            return access_token
                        else:
                            logger.error(f"Token validation failed: {resp.status}")
                            return None
                else:
                    logger.error("No access token in response")
                    return None
                    
        except Exception as ex:
            logger.error(f"❌ Error during login: {ex}")
            return None

async def main():
    """Main function."""
    logger.info("🔑 Getting Home Assistant access token...")
    
    token = await login_and_get_token()
    
    if token:
        logger.info("\n🎉 Successfully obtained access token!")
        logger.info(f"Token: {token}")
        logger.info("\nYou can use this token in your tests by updating DEFAULT_AUTH_TOKEN")
    else:
        logger.error("❌ Failed to get access token")

if __name__ == "__main__":
    asyncio.run(main())