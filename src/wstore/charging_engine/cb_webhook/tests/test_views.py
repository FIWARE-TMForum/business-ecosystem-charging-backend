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

from wstore.charging_engine.cb_webhook.views import CBListener


class CBListenerTestCase(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    @patch('wstore.charging_engine.cb_webhook.views.get_database_connection')
    def test_create_webhook_inserts_to_mongodb(self, mock_db):
        mock_db_instance = MagicMock()
        mock_db.return_value = mock_db_instance

        listener = CBListener(permitted_methods=("POST",))

        customer_bill_data = {
            "event": {
                "customerBill": {
                    "id": "cb-12345",
                    "state": "settled"
                }
            }
        }

        request = self.factory.post(
            '/hub',
            data=json.dumps(customer_bill_data),
            content_type='application/json'
        )

        response = listener.create(request)

        mock_db_instance.wstore_cb_queue.insert_one.assert_called_once_with({
            "cb_id": "cb-12345"
        })
        self.assertEqual(response.status_code, 200)

    @patch('wstore.charging_engine.cb_webhook.views.get_database_connection')
    def test_create_webhook_ignores_non_settled(self, mock_db):
        mock_db_instance = MagicMock()
        mock_db.return_value = mock_db_instance

        listener = CBListener(permitted_methods=("POST",))

        customer_bill_data = {
            "event": {
                "customerBill": {
                    "id": "cb-12345",
                    "state": "sent"
                }
            }
        }

        request = self.factory.post(
            '/hub',
            data=json.dumps(customer_bill_data),
            content_type='application/json'
        )

        response = listener.create(request)

        mock_db_instance.wstore_cb_queue.insert_one.assert_not_called()
        self.assertEqual(response.status_code, 200)
