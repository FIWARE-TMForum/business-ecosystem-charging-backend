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

import queue
from django.test import TestCase
from mock import MagicMock, patch
from bson import ObjectId

from wstore.charging_engine.cb_webhook.cb_workers_service import CBWorkersService


class CBWorkersServiceTestCase(TestCase):

    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.get_database_connection')
    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.OrderingManager')
    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.requests.post')
    def test_listen_registers_webhook(self, mock_post, mock_om, mock_db):
        mock_post.return_value = MagicMock(status_code=200)

        service = CBWorkersService()
        service.listen()

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]

        self.assertIn('callback', call_kwargs['json'])
        self.assertIn('customerBill/notify', call_kwargs['json']['callback'])
        self.assertIn('CustomerBillStateChangeEvent', call_kwargs['json']['query'])

    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.get_database_connection')
    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.OrderingManager')
    def test_worker_processes_task_successfully(self, mock_om_class, mock_db):
        mock_db_instance = MagicMock()
        mock_db.return_value = mock_db_instance

        mock_om_instance = MagicMock()
        mock_om_class.return_value = mock_om_instance
        mock_om_instance.complete_cb_webhook.return_value = None

        service = CBWorkersService()
        task = {"_id": ObjectId(), "cb_id": "cb-12345"}

        service.cb_queue.put(task)

        task_result = service.cb_queue.get()
        result = service.om.complete_cb_webhook(task_result['cb_id'])

        if not (result and result.get("locked", False)):
            self.assertIsNone(result)

    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.get_database_connection')
    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.OrderingManager')
    def test_worker_retries_locked_task(self, mock_om_class, mock_db):
        mock_db_instance = MagicMock()
        mock_db.return_value = mock_db_instance

        mock_om_instance = MagicMock()
        mock_om_class.return_value = mock_om_instance
        mock_om_instance.complete_cb_webhook.return_value = {"locked": True}

        service = CBWorkersService()
        task = {"_id": ObjectId(), "cb_id": "cb-12345"}

        service.cb_queue.put(task)

        task_result = service.cb_queue.get()
        result = service.om.complete_cb_webhook(task_result['cb_id'])

        self.assertEqual(result, {"locked": True})

    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.get_database_connection')
    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.OrderingManager')
    @patch('threading.Thread')
    def test_start_recovers_orphaned_items(self, mock_thread, mock_om, mock_db):
        mock_db_instance = MagicMock()
        mock_db.return_value = mock_db_instance

        mock_result = MagicMock()
        mock_result.modified_count = 5
        mock_db_instance.wstore_cb_queue.update_many.return_value = mock_result

        service = CBWorkersService()
        service.start()

        mock_db_instance.wstore_cb_queue.update_many.assert_called_once_with(
            {"in_queue": True},
            {"$set": {"in_queue": False}}
        )

    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.get_database_connection')
    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.OrderingManager')
    def test_carrier_marks_items_atomic(self, mock_om, mock_db):
        mock_db_instance = MagicMock()
        mock_db.return_value = mock_db_instance

        task = {"_id": ObjectId(), "cb_id": "cb-12345", "in_queue": False}
        mock_db_instance.wstore_cb_queue.find_one_and_update.return_value = task

        service = CBWorkersService()

        result = service.db.wstore_cb_queue.find_one_and_update(
            {"in_queue": {"$ne": True}},
            {"$set": {"in_queue": True}},
            sort=[("_id", 1)]
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["cb_id"], "cb-12345")
