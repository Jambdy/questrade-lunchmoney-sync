import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple
from .questrade import QuestradeClient
from .lunchmoney import LunchMoneyClient

logger = logging.getLogger(__name__)


class TransactionSync:
    """Handles syncing transactions from Questrade to Lunch Money."""

    def __init__(
        self,
        questrade_client: QuestradeClient,
        lunchmoney_client: LunchMoneyClient,
        asset_id: int = None
    ):
        """
        Initialize the sync handler.

        Args:
            questrade_client: Questrade API client
            lunchmoney_client: Lunch Money API client
            asset_id: Lunch Money asset ID to associate transactions with
        """
        self.questrade = questrade_client
        self.lunchmoney = lunchmoney_client
        self.asset_id = asset_id

    def _map_activity_to_transaction(self, activity: Dict, account_id: str) -> Dict:
        """
        Map a Questrade activity to a Lunch Money transaction.

        Args:
            activity: Questrade activity dictionary
            account_id: Questrade account ID

        Returns:
            Lunch Money transaction dictionary
        """
        # Extract fields from Questrade activity
        transaction_date = activity.get('tradeDate') or activity.get('transactionDate')
        net_amount = activity.get('netAmount', 0)
        description = activity.get('description', '')
        activity_type = activity.get('type', '')
        symbol = activity.get('symbol', '')

        # Build notes with relevant information
        notes_parts = [
            f"Type: {activity_type}",
            f"Account: {account_id}"
        ]

        if symbol:
            notes_parts.append(f"Symbol: {symbol}")

        if activity.get('quantity'):
            notes_parts.append(f"Quantity: {activity['quantity']}")

        if activity.get('price'):
            notes_parts.append(f"Price: ${activity['price']}")

        if activity.get('commission'):
            notes_parts.append(f"Commission: ${activity['commission']}")

        notes = " | ".join(notes_parts)

        # Build transaction
        transaction = {
            'date': transaction_date,
            'amount': float(net_amount),
            'payee': description or f"Questrade - {activity_type}",
            'currency': 'cad',  # Questrade is Canadian
            'notes': notes,
            'status': 'cleared'
        }

        # Add asset ID if provided
        if self.asset_id:
            transaction['asset_id'] = self.asset_id

        return transaction

    def _generate_transaction_key(self, transaction: Dict) -> str:
        """
        Generate a unique key for a transaction for duplicate detection.

        Args:
            transaction: Transaction dictionary

        Returns:
            Unique key string
        """
        date = transaction.get('date', '')
        amount = transaction.get('amount', 0)
        payee = transaction.get('payee', '')
        return f"{date}|{amount}|{payee}"

    def _get_existing_transaction_keys(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Set[str]:
        """
        Get keys for existing transactions in Lunch Money.

        Args:
            start_date: Start date for search
            end_date: End date for search

        Returns:
            Set of transaction keys
        """
        existing = self.lunchmoney.get_transactions(
            start_date=start_date,
            end_date=end_date,
            asset_id=self.asset_id
        )

        keys = set()
        for txn in existing:
            # Convert Lunch Money transaction to same format for key generation
            key = self._generate_transaction_key({
                'date': txn.get('date'),
                'amount': float(txn.get('amount', 0)),
                'payee': txn.get('payee', '')
            })
            keys.add(key)

        return keys

    def sync_account(
        self,
        account_id: str,
        days_back: int = 31
    ) -> Tuple[int, int]:
        """
        Sync transactions for a specific Questrade account.

        Args:
            account_id: Questrade account ID
            days_back: Number of days to look back (max 31)

        Returns:
            Tuple of (new_transactions_count, skipped_duplicates_count)
        """
        logger.info(f"Starting sync for account {account_id}")

        # Calculate date range (limit to 31 days per Questrade API)
        end_date = datetime.now()
        days_back = min(days_back, 31)
        start_date = end_date - timedelta(days=days_back)

        # Fetch activities from Questrade
        logger.info(f"Fetching activities from {start_date.date()} to {end_date.date()}")
        activities = self.questrade.get_account_activities(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date
        )

        if not activities:
            logger.info("No activities found")
            return 0, 0

        logger.info(f"Found {len(activities)} activities")

        # Get existing transactions to avoid duplicates
        existing_keys = self._get_existing_transaction_keys(start_date, end_date)
        logger.info(f"Found {len(existing_keys)} existing transactions in Lunch Money")

        # Map and filter activities
        new_transactions = []
        skipped = 0

        for activity in activities:
            transaction = self._map_activity_to_transaction(activity, account_id)
            key = self._generate_transaction_key(transaction)

            if key in existing_keys:
                skipped += 1
                logger.debug(f"Skipping duplicate: {transaction['payee']} on {transaction['date']}")
                continue

            new_transactions.append(transaction)

        # Create transactions in Lunch Money
        if new_transactions:
            logger.info(f"Creating {len(new_transactions)} new transactions")
            result = self.lunchmoney.create_transactions(new_transactions)
            logger.info(f"Successfully created transactions: {result}")
        else:
            logger.info("No new transactions to create")

        return len(new_transactions), skipped

    def sync_multiple_accounts(
        self,
        account_ids: List[str],
        days_back: int = 31
    ) -> Dict[str, Tuple[int, int]]:
        """
        Sync transactions for multiple Questrade accounts.

        Args:
            account_ids: List of Questrade account IDs
            days_back: Number of days to look back

        Returns:
            Dictionary mapping account_id to (new_count, skipped_count)
        """
        results = {}

        for account_id in account_ids:
            try:
                new_count, skipped_count = self.sync_account(account_id, days_back)
                results[account_id] = (new_count, skipped_count)
            except Exception as e:
                logger.error(f"Error syncing account {account_id}: {str(e)}")
                results[account_id] = (0, 0)

        return results
