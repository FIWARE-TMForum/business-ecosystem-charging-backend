# -*- coding: utf-8 -*-

# Copyright (c) 2025 Future Internet Consulting and Development Solutions S.L.

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

import json
from django.test import TestCase, SimpleTestCase, RequestFactory
from mock import MagicMock, patch
from bson import ObjectId

from wstore.charging_engine.cb_webhook.views import CBListener
from wstore.ordering.ordering_management import OrderingManager
from wstore.ordering import ordering_management
from wstore.ordering.errors import OrderingError


class CBWebhookIntegrationTestCase(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    @patch('wstore.charging_engine.cb_webhook.views.get_database_connection')
    def test_webhook_receives_real_payload_settled(self, mock_db):
        mock_db_instance = MagicMock()
        mock_db.return_value = mock_db_instance

        listener = CBListener(permitted_methods=("POST",))

        real_payload = {
            "eventId": "07e179fc-49b6-4ea0-97fe-b27cf2ad1b04",
            "eventTime": "2026-01-07T19:36:51.135186Z",
            "eventType": "CustomerBillStateChangeEvent",
            "event": {
                "customerBill": {
                    "id": "urn:ngsi-ld:customer-bill:fd89dd2d-85ec-4322-9e15-5a0da3fdcb70",
                    "href": "urn:ngsi-ld:customer-bill:fd89dd2d-85ec-4322-9e15-5a0da3fdcb70",
                    "billDate": "2025-12-11T16:56:42Z",
                    "lastUpdate": "2026-01-07T19:36:50.721368Z",
                    "appliedPayment": [],
                    "state": "settled",
                    "taxExcludedAmount": {
                        "unit": "EUR",
                        "value": 110
                    },
                    "taxIncludedAmount": {
                        "unit": "EUR",
                        "value": 110
                    }
                }
            }
        }

        request = self.factory.post(
            '/charging/webhook/customerBill/notify',
            data=json.dumps(real_payload),
            content_type='application/json'
        )

        response = listener.create(request)

        mock_db_instance.wstore_cb_queue.insert_one.assert_called_once_with({
            "cb_id": "urn:ngsi-ld:customer-bill:fd89dd2d-85ec-4322-9e15-5a0da3fdcb70"
        })
        self.assertEqual(response.status_code, 200)

    @patch('wstore.charging_engine.cb_webhook.views.get_database_connection')
    def test_webhook_receives_real_payload_new_state(self, mock_db):
        mock_db_instance = MagicMock()
        mock_db.return_value = mock_db_instance

        listener = CBListener(permitted_methods=("POST",))

        real_payload = {
            "eventId": "07e179fc-49b6-4ea0-97fe-b27cf2ad1b04",
            "eventTime": "2026-01-07T19:36:51.135186Z",
            "eventType": "CustomerBillStateChangeEvent",
            "event": {
                "customerBill": {
                    "id": "urn:ngsi-ld:customer-bill:fd89dd2d-85ec-4322-9e15-5a0da3fdcb70",
                    "href": "urn:ngsi-ld:customer-bill:fd89dd2d-85ec-4322-9e15-5a0da3fdcb70",
                    "billDate": "2025-12-11T16:56:42Z",
                    "lastUpdate": "2026-01-07T19:36:50.721368Z",
                    "appliedPayment": [],
                    "state": "new",
                    "taxExcludedAmount": {
                        "unit": "EUR",
                        "value": 110
                    },
                    "taxIncludedAmount": {
                        "unit": "EUR",
                        "value": 110
                    }
                }
            }
        }

        request = self.factory.post(
            '/charging/webhook/customerBill/notify',
            data=json.dumps(real_payload),
            content_type='application/json'
        )

        response = listener.create(request)

        mock_db_instance.wstore_cb_queue.insert_one.assert_not_called()
        self.assertEqual(response.status_code, 200)

    @patch('wstore.ordering.ordering_management.get_database_connection')
    @patch('wstore.ordering.ordering_management.Order.get_by_customer_bill_id')
    def test_lock_prevents_concurrent_processing(self, mock_get_order, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        order_id = ObjectId()
        customer_bill_id = "cb-12345"

        mock_order = MagicMock()
        mock_order.pk = order_id
        mock_order.order_id = "order-123"
        mock_get_order.return_value = mock_order

        om = OrderingManager()

        mock_db.wstore_order.find_one_and_update.return_value = {
            "_id": order_id,
            "_lock": True
        }

        result = om.complete_cb_webhook(customer_bill_id)

        self.assertEqual(result, {"locked": True})

        mock_db.wstore_order.find_one_and_update.assert_called_once_with(
            {"_id": order_id},
            {"$set": {"_lock": True}}
        )

    @patch('wstore.ordering.ordering_management.get_database_connection')
    @patch('wstore.ordering.ordering_management.Order.get_by_customer_bill_id')
    def test_lock_acquired_and_released_on_success(self, mock_get_order, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        order_id = ObjectId()
        customer_bill_id = "cb-12345"

        mock_order = MagicMock()
        mock_order.pk = order_id
        mock_order.order_id = "order-123"
        mock_get_order.return_value = mock_order

        mock_db.wstore_order.find_one_and_update.side_effect = [
            {"_id": order_id, "_lock": False},
            {"_id": order_id, "_lock": True}
        ]

        mock_contract = MagicMock()
        mock_contract.processed = True
        mock_order.get_contract_by_cb_id.return_value = mock_contract

        om = OrderingManager()
        result = om.complete_cb_webhook(customer_bill_id)

        calls = mock_db.wstore_order.find_one_and_update.call_args_list
        self.assertEqual(len(calls), 2)

        self.assertEqual(calls[0][0][0], {"_id": order_id})
        self.assertEqual(calls[0][0][1], {"$set": {"_lock": True}})

        self.assertEqual(calls[1][0][0], {"_id": order_id})
        self.assertEqual(calls[1][0][1], {"$set": {"_lock": False}})

    @patch('wstore.ordering.ordering_management.get_database_connection')
    @patch('wstore.ordering.ordering_management.Order.get_by_customer_bill_id')
    def test_lock_released_even_on_exception(self, mock_get_order, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        order_id = ObjectId()
        customer_bill_id = "cb-12345"

        mock_order = MagicMock()
        mock_order.pk = order_id
        mock_get_order.return_value = mock_order

        mock_db.wstore_order.find_one_and_update.side_effect = [
            {"_id": order_id, "_lock": False},
            {"_id": order_id, "_lock": True}
        ]

        mock_order.get_contract_by_cb_id.side_effect = Exception("Test exception")

        om = OrderingManager()
        with self.assertRaisesRegex(Exception, "Test exception"):
            om.complete_cb_webhook(customer_bill_id)

        calls = mock_db.wstore_order.find_one_and_update.call_args_list
        self.assertEqual(len(calls), 2)

        self.assertEqual(calls[1][0][0], {"_id": order_id})
        self.assertEqual(calls[1][0][1], {"$set": {"_lock": False}})


class SettledBillRenewalTestCase(SimpleTestCase):
    def setUp(self):
        for name in ('get_database_connection', 'Order', 'BillingClient', 'OrderingClient', 'on_product_renewal'):
            patcher = patch.object(ordering_management, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.db = self.get_database_connection.return_value
        self.order = MagicMock(pk=ObjectId(), order_id='order-1')
        self.contract = MagicMock(product_id='product-1', processed=True)
        self.order.get_product_contract.return_value = self.contract
        self.order.get_contract_by_cb_id.return_value = self.contract
        self.Order.get_by_customer_bill_id.side_effect = OrderingError('Order not found.')
        self.BillingClient.return_value.get_product_id_by_cb.return_value = 'product-1'
        self.Order.get_by_product_id.return_value = self.order
        self.db.wstore_order.find_one_and_update.return_value = {'_lock': False}
        self.manager = OrderingManager()
        self.manager.notify_item_completed = MagicMock()

    def test_recurring_bill_resolves_purchase_through_product_and_notifies_renewal(self):
        self.manager.complete_cb_webhook('renewal-bill')
        self.BillingClient.return_value.get_product_id_by_cb.assert_called_once_with('renewal-bill')
        self.Order.get_by_product_id.assert_called_once_with('product-1')
        self.on_product_renewal.assert_called_once_with(self.order, self.contract, 'renewal-bill')
        self.manager.notify_item_completed.assert_not_called()
        self.order.get_contract_by_cb_id.assert_not_called()
        self.db.wstore_order.find_one_and_update.assert_not_called()
        self.order.save.assert_not_called()

    def test_initial_bill_preserves_existing_completion_path(self):
        self.Order.get_by_customer_bill_id.side_effect = None
        self.Order.get_by_customer_bill_id.return_value = self.order
        self.contract.processed = False
        self.manager.complete_cb_webhook('initial-bill')
        self.manager.notify_item_completed.assert_called_once_with(
            self.order, self.contract, self.OrderingClient.return_value.get_order.return_value
        )
        self.on_product_renewal.assert_not_called()
        self.BillingClient.assert_not_called()

    def test_repeated_initial_settlement_does_not_become_renewal(self):
        self.Order.get_by_customer_bill_id.side_effect = None
        self.Order.get_by_customer_bill_id.return_value = self.order
        self.manager.complete_cb_webhook('initial-bill')
        self.manager.notify_item_completed.assert_not_called()
        self.on_product_renewal.assert_not_called()

    def test_initial_provisioning_failure_still_propagates_and_releases_order_lock(self):
        self.Order.get_by_customer_bill_id.side_effect = None
        self.Order.get_by_customer_bill_id.return_value = self.order
        self.contract.processed = False
        self.manager.notify_item_completed.side_effect = RuntimeError('activation unavailable')
        with self.assertRaisesRegex(RuntimeError, 'activation unavailable'):
            self.manager.complete_cb_webhook('initial-bill')
        self.on_product_renewal.assert_not_called()
        self.assertEqual(self.db.wstore_order.find_one_and_update.call_args.args[1], {'$set': {'_lock': False}})

    def test_plugin_notification_failure_does_not_interrupt_settled_bill_processing(self):
        from wstore.asset_manager.resource_plugins import decorators
        with patch.object(ordering_management, 'on_product_renewal', decorators.on_product_renewal), \
                patch.object(decorators, 'InventoryClient'), patch.object(decorators, 'OrderingClient'), \
                patch.object(decorators, '_notify_inventory_plugins', side_effect=RuntimeError('plugin unavailable')):
            with self.assertLogs('wstore.default_logger', level='ERROR'):
                self.manager.complete_cb_webhook('renewal-bill')
        self.db.wstore_order.find_one_and_update.assert_not_called()
        self.order.save.assert_not_called()

    def test_renewal_dispatch_does_not_acquire_purchase_completion_lock(self):
        self.db.wstore_order.find_one_and_update.return_value = {'_lock': True}
        self.manager.complete_cb_webhook('renewal-bill')
        self.on_product_renewal.assert_called_once_with(self.order, self.contract, 'renewal-bill')
        self.db.wstore_order.find_one_and_update.assert_not_called()
        self.manager.notify_item_completed.assert_not_called()

    def test_lookup_failure_is_not_misclassified_as_an_external_bill(self):
        self.Order.get_by_customer_bill_id.side_effect = RuntimeError('database unavailable')
        with self.assertRaisesRegex(RuntimeError, 'database unavailable'):
            self.manager.complete_cb_webhook('bill-1')
        self.BillingClient.assert_not_called()

    def test_bill_without_a_local_product_is_ignored(self):
        self.BillingClient.return_value.get_product_id_by_cb.return_value = None
        self.manager.complete_cb_webhook('other-bill')
        self.on_product_renewal.assert_not_called()
        self.db.wstore_order.find_one_and_update.assert_not_called()

    def test_external_purchase_without_local_order_is_ignored(self):
        self.Order.get_by_product_id.side_effect = OrderingError('No local purchase')
        self.manager.complete_cb_webhook('external-bill')
        self.on_product_renewal.assert_not_called()
        self.db.wstore_order.find_one_and_update.assert_not_called()
