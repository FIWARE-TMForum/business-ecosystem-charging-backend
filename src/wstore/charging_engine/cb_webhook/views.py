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
from logging import getLogger

from wstore.store_commons.resource import Resource
from wstore.store_commons.utils.http import build_response
from wstore.store_commons.database import get_database_connection

logger = getLogger("wstore.charging_engine.cb_webhook")


class CBListener(Resource):

    def create(self, request):
        logger.debug(f"Received CustomerBill webhook notification")
        db = get_database_connection()

        data = json.loads(request.body)
        customer_bill = data["event"]["customerBill"]
        logger.debug(f"Customer bill: {customer_bill}")

        if customer_bill["state"].lower() == "settled":
            db.wstore_cb_queue.insert_one({
                "cb_id": customer_bill["id"]
            })
            logger.info(f"Queued customer bill {customer_bill['id']} for processing")

        return build_response(request, 200, "OK")
