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
import time
import threading
from logging import getLogger
import requests
import settings

from wstore.ordering.ordering_management import OrderingManager
from wstore.store_commons.database import get_database_connection

logger = getLogger("wstore.charging_engine.cb_workers_service")


class CBWorkersService:

    def __init__(self):
        self.om = OrderingManager()
        self.workers = []
        self.num_workers = 3
        self.cb_queue = queue.Queue(maxsize=100)
        self.db = get_database_connection()

    def listen(self):
        payload = {
            "callback": f"{settings.LOCAL_SITE}charging/webhook/customerBill/notify",
            "query": "eventType=CustomerBillStateChangeEvent"
        }
        result = requests.post(f"{settings.BILLING}/hub", json=payload, verify=settings.VERIFY_REQUESTS)
        if result.status_code ==201 or result.status_code == 409:
            logger.info(f"start listening to {settings.BILLING}")
        else:
            logger.warning("customer bill api is not available, charging will not be able to listen the webhook")

    def _worker_loop(self):
        while True:
            task = self.cb_queue.get()
            logger.info(f"[{threading.current_thread().name}] Processing {task['cb_id']}")

            result = self.om.complete_cb_webhook(task['cb_id'])

            if result and result.get("locked", False):
                try:
                    self.cb_queue.put_nowait(task)
                    logger.debug(f"[{threading.current_thread().name}] Re-enqueued {task['cb_id']} for retry")
                except queue.Full:
                    self.db.wstore_cb_queue.update_one(
                        {"_id": task["_id"]},
                        {"$set": {"in_queue": False}}
                    )
                    logger.warning(f"[{threading.current_thread().name}] Queue full, unmarked {task['cb_id']} for retry")
            else:
                self.db.wstore_cb_queue.delete_one({"_id": task["_id"]})
                logger.info(f"[{threading.current_thread().name}] Completed {task['cb_id']}")

    def _carrier_loop(self):
        while True:
            task = self.db.wstore_cb_queue.find_one_and_update(
                {"in_queue": {"$ne": True}},
                {"$set": {"in_queue": True}},
                sort=[("_id", 1)]
            )
            if task:
                self.cb_queue.put(task)
                logger.debug(f"Carrier moved {task['cb_id']} to queue")
            else:
                time.sleep(0.5)

    def start(self):
        recovered = self.db.wstore_cb_queue.update_many(
            {"in_queue": True},
            {"$set": {"in_queue": False}}
        )
        if recovered.modified_count > 0:
            logger.info(f"Recovered {recovered.modified_count} pending items from previous crash")

        for i in range(self.num_workers):
            worker = threading.Thread(target=self._worker_loop, name=f"CB_Worker-{i}", daemon=True)
            worker.start()
            self.workers.append(worker)
            logger.info(f"Started {worker.name}")

        carrier = threading.Thread(target=self._carrier_loop, name="CB_Carrier", daemon=True)
        carrier.start()
        logger.info(f"Started {carrier.name}")
