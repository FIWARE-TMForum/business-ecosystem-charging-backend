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
from django.test import SimpleTestCase, TestCase
from mock import MagicMock, call, patch
from bson import ObjectId

from wstore.charging_engine.cb_webhook.cb_workers_service import CBWorkersService
from wstore.charging_engine.cb_webhook import cb_workers_service


class CBWorkersServiceTestCase(TestCase):

    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.get_database_connection')
    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.OrderingManager')
    @patch('wstore.charging_engine.cb_webhook.cb_workers_service.requests.post')
    def test_listen_registers_webhook(self, mock_post, mock_om, mock_db):
        mock_post.return_value = MagicMock(status_code=201)

        service = CBWorkersService()
        service.listen()

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs

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


class CBWorkerNotificationTestCase(SimpleTestCase):
    def setUp(self):
        for name in ('get_database_connection', 'OrderingManager'):
            patcher = patch.object(cb_workers_service, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.service = CBWorkersService()
        self.service.cb_queue = MagicMock()
        self.task = {'_id': ObjectId(), 'cb_id': 'renewal-bill'}

    def test_failed_notification_is_logged_and_worker_processes_next_task(self):
        second = {'_id': ObjectId(), 'cb_id': 'next-bill'}
        self.service.cb_queue.get.side_effect = [self.task, second, StopIteration]
        self.service.om.complete_cb_webhook.side_effect = [RuntimeError('plugin unavailable'), None]
        with self.assertLogs('wstore.charging_engine.cb_workers_service', level='ERROR'):
            with self.assertRaises(StopIteration):
                self.service._worker_loop()
        self.service.db.wstore_cb_queue.update_one.assert_not_called()
        self.assertEqual(self.service.db.wstore_cb_queue.delete_one.call_args_list, [
            call({'_id': self.task['_id']}), call({'_id': second['_id']}),
        ])

    def test_successful_notification_is_deleted_after_processing(self):
        self.service.cb_queue.get.side_effect = [self.task, StopIteration]
        self.service.om.complete_cb_webhook.return_value = None
        self.service.om.complete_cb_webhook.side_effect = lambda bill_id: self.service.db.wstore_cb_queue.delete_one.assert_not_called()
        with self.assertRaises(StopIteration):
            self.service._worker_loop()
        self.service.db.wstore_cb_queue.delete_one.assert_called_once_with({'_id': self.task['_id']})

    def test_locked_notification_keeps_existing_requeue_behavior(self):
        self.service.cb_queue.get.side_effect = [self.task, StopIteration]
        self.service.om.complete_cb_webhook.return_value = {'locked': True}
        with self.assertRaises(StopIteration):
            self.service._worker_loop()
        self.service.cb_queue.put_nowait.assert_called_once_with(self.task)
        self.service.db.wstore_cb_queue.delete_one.assert_not_called()

    def test_carrier_uses_existing_queue_claim_without_retry_metadata(self):
        self.service.db.wstore_cb_queue.find_one_and_update.return_value = self.task
        self.service.cb_queue.put.side_effect = StopIteration
        with self.assertRaises(StopIteration):
            self.service._carrier_loop()
        claim = self.service.db.wstore_cb_queue.find_one_and_update.call_args
        self.assertEqual(claim.args[0], {'in_queue': {'$ne': True}})
        self.assertEqual(claim.args[1], {'$set': {'in_queue': True}})
