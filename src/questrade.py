import os
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class QuestradeClient:
    """Client for interacting with the Questrade API."""

    def __init__(self, refresh_token: str):
        """Initialize the Questrade client with a refresh token."""
        self.refresh_token = refresh_token
        self.access_token: Optional[str] = None
        self.api_server: Optional[str] = None
        self.token_expiry: Optional[datetime] = None

    def _refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token."""
        url = "https://login.questrade.com/oauth2/token"
        params = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }

        response = requests.post(url, params=params)
        response.raise_for_status()

        data = response.json()
        self.access_token = data['access_token']
        self.api_server = data['api_server']
        self.refresh_token = data['refresh_token']  # Update refresh token

        # Set token expiry (usually 30 minutes)
        expires_in = data.get('expires_in', 1800)
        self.token_expiry = datetime.now() + timedelta(seconds=expires_in)

    def _ensure_valid_token(self) -> None:
        """Ensure we have a valid access token."""
        if not self.access_token or not self.token_expiry or datetime.now() >= self.token_expiry:
            self._refresh_access_token()

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make an authenticated request to the Questrade API."""
        self._ensure_valid_token()

        # Remove trailing slash from api_server and leading slash from endpoint to avoid double slashes
        api_server = self.api_server.rstrip('/')
        endpoint = endpoint.lstrip('/')
        url = f"{api_server}/{endpoint}"
        headers = {
            'Authorization': f'Bearer {self.access_token}'
        }

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        return response.json()

    def get_accounts(self) -> List[Dict]:
        """Get all accounts."""
        data = self._make_request('/v1/accounts')
        return data.get('accounts', [])

    def get_account_activities(
        self,
        account_id: str,
        start_date: datetime,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Get account activities for a specific account.

        Args:
            account_id: The account ID to fetch activities for
            start_date: Start date for activities
            end_date: End date for activities (defaults to today)

        Returns:
            List of activity dictionaries
        """
        if end_date is None:
            end_date = datetime.now()

        # Questrade API has a 31-day limit per request
        activities = []
        current_start = start_date

        while current_start < end_date:
            current_end = min(current_start + timedelta(days=31), end_date)

            params = {
                'startTime': current_start.strftime('%Y-%m-%dT%H:%M:%S-05:00'),
                'endTime': current_end.strftime('%Y-%m-%dT%H:%M:%S-05:00')
            }

            data = self._make_request(f'/v1/accounts/{account_id}/activities', params)
            activities.extend(data.get('activities', []))

            current_start = current_end

        return activities

    def get_current_refresh_token(self) -> str:
        """Get the current refresh token (may have been updated)."""
        return self.refresh_token
