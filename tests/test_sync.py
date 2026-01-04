import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.sync import TransactionSync
from src.questrade import QuestradeClient
from src.lunchmoney import LunchMoneyClient


class TestTransactionSync(unittest.TestCase):
    """Test cases for TransactionSync."""

    def setUp(self):
        """Set up test fixtures."""
        self.questrade_client = Mock(spec=QuestradeClient)
        self.lunchmoney_client = Mock(spec=LunchMoneyClient)
        self.sync = TransactionSync(
            questrade_client=self.questrade_client,
            lunchmoney_client=self.lunchmoney_client,
            asset_id=123
        )

    def test_map_activity_to_transaction_basic(self):
        """Test mapping a basic Questrade activity to Lunch Money transaction."""
        activity = {
            'transactionDate': '2024-01-15',
            'netAmount': 100.50,
            'description': 'Dividend Payment',
            'type': 'Dividends',
            'symbol': 'AAPL'
        }

        transaction = self.sync._map_activity_to_transaction(activity, '12345678')

        self.assertEqual(transaction['date'], '2024-01-15')
        self.assertEqual(transaction['amount'], 100.50)
        self.assertEqual(transaction['payee'], 'Dividend Payment')
        self.assertEqual(transaction['currency'], 'cad')
        self.assertEqual(transaction['status'], 'cleared')
        self.assertEqual(transaction['asset_id'], 123)
        self.assertIn('Type: Dividends', transaction['notes'])
        self.assertIn('Symbol: AAPL', transaction['notes'])

    def test_map_activity_to_transaction_trade(self):
        """Test mapping a trade activity with quantity and price."""
        activity = {
            'tradeDate': '2024-01-15',
            'netAmount': -1050.00,
            'description': 'Bought TSLA',
            'type': 'Trades',
            'symbol': 'TSLA',
            'quantity': 10,
            'price': 105.00,
            'commission': 5.00
        }

        transaction = self.sync._map_activity_to_transaction(activity, '12345678')

        self.assertEqual(transaction['amount'], -1050.00)
        self.assertIn('Quantity: 10', transaction['notes'])
        self.assertIn('Price: $105.0', transaction['notes'])
        self.assertIn('Commission: $5.0', transaction['notes'])

    def test_generate_transaction_key(self):
        """Test transaction key generation for duplicate detection."""
        transaction = {
            'date': '2024-01-15',
            'amount': 100.50,
            'payee': 'Test Transaction'
        }

        key = self.sync._generate_transaction_key(transaction)
        expected_key = '2024-01-15|100.5|Test Transaction'

        self.assertEqual(key, expected_key)

    def test_sync_account_no_activities(self):
        """Test syncing when no activities are found."""
        self.questrade_client.get_account_activities.return_value = []

        new_count, skipped_count = self.sync.sync_account('12345678', days_back=7)

        self.assertEqual(new_count, 0)
        self.assertEqual(skipped_count, 0)
        self.questrade_client.get_account_activities.assert_called_once()

    def test_sync_account_with_new_transactions(self):
        """Test syncing with new transactions."""
        activities = [
            {
                'transactionDate': '2024-01-15',
                'netAmount': 100.00,
                'description': 'Transaction 1',
                'type': 'Dividends'
            },
            {
                'transactionDate': '2024-01-16',
                'netAmount': 200.00,
                'description': 'Transaction 2',
                'type': 'Dividends'
            }
        ]

        self.questrade_client.get_account_activities.return_value = activities
        self.lunchmoney_client.get_transactions.return_value = []
        self.lunchmoney_client.create_transactions.return_value = {'ids': [1, 2]}

        new_count, skipped_count = self.sync.sync_account('12345678', days_back=7)

        self.assertEqual(new_count, 2)
        self.assertEqual(skipped_count, 0)
        self.lunchmoney_client.create_transactions.assert_called_once()

    def test_sync_account_with_duplicates(self):
        """Test syncing with duplicate detection."""
        activities = [
            {
                'transactionDate': '2024-01-15',
                'netAmount': 100.00,
                'description': 'Transaction 1',
                'type': 'Dividends'
            }
        ]

        # Mock existing transaction in Lunch Money
        existing_transactions = [
            {
                'date': '2024-01-15',
                'amount': '100.00',
                'payee': 'Transaction 1'
            }
        ]

        self.questrade_client.get_account_activities.return_value = activities
        self.lunchmoney_client.get_transactions.return_value = existing_transactions

        new_count, skipped_count = self.sync.sync_account('12345678', days_back=7)

        self.assertEqual(new_count, 0)
        self.assertEqual(skipped_count, 1)
        self.lunchmoney_client.create_transactions.assert_not_called()

    def test_sync_multiple_accounts(self):
        """Test syncing multiple accounts."""
        activities = [
            {
                'transactionDate': '2024-01-15',
                'netAmount': 100.00,
                'description': 'Transaction',
                'type': 'Dividends'
            }
        ]

        self.questrade_client.get_account_activities.return_value = activities
        self.lunchmoney_client.get_transactions.return_value = []
        self.lunchmoney_client.create_transactions.return_value = {'ids': [1]}

        results = self.sync.sync_multiple_accounts(['123', '456'], days_back=7)

        self.assertEqual(len(results), 2)
        self.assertEqual(results['123'], (1, 0))
        self.assertEqual(results['456'], (1, 0))


if __name__ == '__main__':
    unittest.main()
