import requests
from typing import Dict, List, Optional
from datetime import datetime


class LunchMoneyClient:
    """Client for interacting with the Lunch Money API."""

    BASE_URL = "https://dev.lunchmoney.app/v1"

    def __init__(self, api_token: str):
        """Initialize the Lunch Money client with an API token."""
        self.api_token = api_token
        self.headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json'
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict:
        """Make an authenticated request to the Lunch Money API."""
        url = f"{self.BASE_URL}{endpoint}"

        response = requests.request(
            method=method,
            url=url,
            headers=self.headers,
            json=data,
            params=params
        )
        response.raise_for_status()

        return response.json()

    def get_transactions(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        asset_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Get transactions from Lunch Money.

        Args:
            start_date: Start date for transactions
            end_date: End date for transactions
            asset_id: Filter by specific asset ID

        Returns:
            List of transaction dictionaries
        """
        params = {}
        if start_date:
            params['start_date'] = start_date.strftime('%Y-%m-%d')
        if end_date:
            params['end_date'] = end_date.strftime('%Y-%m-%d')
        if asset_id:
            params['asset_id'] = asset_id

        data = self._make_request('GET', '/transactions', params=params)
        return data.get('transactions', [])

    def create_transaction(self, transaction: Dict) -> Dict:
        """
        Create a single transaction in Lunch Money.

        Args:
            transaction: Transaction dictionary with required fields:
                - date: Transaction date (YYYY-MM-DD)
                - amount: Transaction amount (positive for income, negative for expense)
                - payee: Payee/description
                - currency: Currency code (default: 'usd')
                - asset_id: Optional asset ID
                - category_id: Optional category ID
                - notes: Optional notes
                - status: Optional status (cleared, uncleared, pending)

        Returns:
            Response from API
        """
        return self._make_request('POST', '/transactions', data=transaction)

    def create_transactions(self, transactions: List[Dict]) -> Dict:
        """
        Create multiple transactions in Lunch Money.

        Args:
            transactions: List of transaction dictionaries

        Returns:
            Response from API with created transaction IDs
        """
        # Lunch Money accepts an array of transactions
        payload = {
            'transactions': transactions
        }
        return self._make_request('POST', '/transactions', data=payload)

    def get_assets(self) -> List[Dict]:
        """
        Get all assets (investment accounts, etc.).

        Returns:
            List of asset dictionaries
        """
        data = self._make_request('GET', '/assets')
        return data.get('assets', [])

    def get_asset_by_name(self, name: str) -> Optional[Dict]:
        """
        Find an asset by name.

        Args:
            name: Asset name to search for

        Returns:
            Asset dictionary if found, None otherwise
        """
        assets = self.get_assets()
        for asset in assets:
            if asset.get('name', '').lower() == name.lower():
                return asset
        return None

    def update_asset_balance(self, asset_id: int, balance: float, currency: str = 'cad') -> Dict:
        """
        Update an asset's balance.

        Args:
            asset_id: Lunch Money asset ID
            balance: New balance amount
            currency: Currency code (default: 'cad')

        Returns:
            Response from API
        """
        payload = {
            'balance': str(balance),
            'currency': currency
        }
        return self._make_request('PUT', f'/assets/{asset_id}', data=payload)
