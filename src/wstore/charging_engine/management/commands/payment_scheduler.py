# -*- coding: utf-8 -*-

# Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

# This file belongs to the business-charging-backend
# of the Business API Ecosystem.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import datetime
from logging import getLogger

from django.conf import settings
from django.core.management.base import BaseCommand

from wstore.charging_engine.charging.billing_client import BillingClient
from wstore.charging_engine.payment_client.payment_client import PaymentClient
from wstore.ordering.inventory_client import InventoryClient
from wstore.ordering.models import PaymentRecord, PendingTermination

logger = getLogger("wstore.default_logger")

CHAR_NAME_TO_TYPE = {
    'stripeCheckoutSessionId': 'stripe',
    'redsysPreAuthorizationId': 'redsys',
}


class Command(BaseCommand):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._billing_client = BillingClient()
        self._inventory_client = InventoryClient()

    def _close_expired_recovery(self, cb, record):
        """Run only after an existing payment attempt is confirmed failed."""
        grace = datetime.timedelta(hours=settings.PAYMENT_RECOVERY_GRACE_HOURS)
        first_failed_at = record.first_failed_at

        if datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) < first_failed_at + grace:
            return False

        product_id = self._billing_client.get_product_id_by_cb(cb['id'])
        if not product_id:
            return False

        product = self._inventory_client.get_product(product_id)

        terminated = product.get('status') == 'terminated'
        if not terminated:
            if PendingTermination.objects.filter(product_id=product_id).exists():
                logger.info("CB %s awaits existing termination recovery for product %s", cb['id'], product_id)
            else:
                # Existing termination invokes plugin cleanup and retains failed work for recovery.
                self._inventory_client.terminate_product(product_id)

        self._billing_client.close_unpaid_customer_bill(cb)
        logger.info("Closed payment recovery for CB %s, product %s", cb['id'], product_id)
        return True

    def _get_payment_info_from_cb(self, cb_id):
        product_id = self._billing_client.get_product_id_by_cb(cb_id)
        if not product_id:
            return None, None

        product = self._inventory_client.get_product(product_id)
        if not product:
            return None, None

        for char in product.get('productCharacteristic', []):
            # Skip user-created characteristics (they have valueType set)
            if char.get('valueType'):
                continue
            name = char.get('name', '')
            if name in CHAR_NAME_TO_TYPE:
                return CHAR_NAME_TO_TYPE[name], char.get('value')

        return None, None

    def _attempt_payment(self, cb, record, client: PaymentClient, pre_auth_id):
        amount = cb.get('taxIncludedAmount', {}).get('value')
        currency = cb.get('taxIncludedAmount', {}).get('unit')

        new_reference, status = client.charge_recurring(cb, record, pre_auth_id, amount, currency)

        if not new_reference:
            logger.warning(
                f"Payment provider returned no reference for CB {cb['id']}, "
                f"status: {status}"
            )
            return record, status

        cb_id = cb['id']
        PaymentRecord.increment_retry_count(cb_id)
        record = PaymentRecord.get_by_customer_bill_id(cb_id)

        if status == 'succeeded':
            self._billing_client.set_customer_bill('settled', cb_id)
            logger.info(f"CB {cb_id} settled after payment attempt")
        else:
            if status == 'failed':
                record.mark_failed(datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None))
            logger.info(f"CB {cb_id} payment attempt status: {status}, will retry later")

        return record, status

    def _process_cb(self, cb):
        cb_id = cb['id']

        try:
            record = PaymentRecord.get_by_customer_bill_id(cb_id)
        except PaymentRecord.DoesNotExist:
            payment_type, pre_auth_id = self._get_payment_info_from_cb(cb_id)
            if payment_type is None or pre_auth_id is None:
                logger.warning(f"Cannot determine payment information for CB {cb_id}, skipping")
                return

            p_client: PaymentClient = PaymentClient.get_payment_client_class(payment_type)(None)
            self._attempt_payment(cb, None, p_client, pre_auth_id)
            return

        p_client: PaymentClient = PaymentClient.get_payment_client_class(record.payment_type)(None)
        status = p_client.check_payment_status(record.payment_reference)

        if status == 'succeeded':
            self._billing_client.set_customer_bill('settled', cb_id)
            logger.info(f"CB {cb_id} settled")
        elif status == 'failed':
            record.mark_failed(datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None))
            if self._close_expired_recovery(cb, record):
                return

            payment_type, pre_auth_id = self._get_payment_info_from_cb(cb_id)

            # it should never show these logs, because it means some strong inconsistency
            if payment_type is None or pre_auth_id is None:
                logger.warning(f"Cannot determine payment information for CB {cb_id}, skipping retry")
                return

            if payment_type != record.payment_type:
                logger.error(
                    f"Payment type mismatch for CB {cb_id}: "
                    f"record={record.payment_type}, product={payment_type}"
                )
                return

            self._attempt_payment(cb, record, p_client, pre_auth_id)

    def handle(self, *args, **options):
        logger.info("Running payment scheduler")

        limit = 100
        offset = 0
        bills = []
        while True:
            cbs = self._billing_client.get_customer_bills_by_state('new', limit=limit, offset=offset)
            if not cbs:
                break

            bills.extend(cbs)
            if len(cbs) < limit:
                break
            offset += limit

        # Processing changes bill states, so collect pages before mutating the result set.
        for cb in bills:
            try:
                self._process_cb(cb)
            except Exception as e:
                logger.error(f"Error processing CB with id: {cb.get('id')}: {e}")

        logger.info("Payment scheduler finished")
