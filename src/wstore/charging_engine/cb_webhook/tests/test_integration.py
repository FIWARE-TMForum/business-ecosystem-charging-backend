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
from django.test import TestCase, RequestFactory
from mock import MagicMock, patch
from bson import ObjectId

from wstore.charging_engine.cb_webhook.views import CBListener
from wstore.ordering.ordering_management import OrderingManager


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
        result = om.complete_cb_webhook(customer_bill_id)

        calls = mock_db.wstore_order.find_one_and_update.call_args_list
        self.assertEqual(len(calls), 2)

        self.assertEqual(calls[1][0][0], {"_id": order_id})
        self.assertEqual(calls[1][0][1], {"$set": {"_lock": False}})
