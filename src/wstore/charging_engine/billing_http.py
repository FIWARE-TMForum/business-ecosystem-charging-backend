# -*- coding: utf-8 -*-

# Copyright (c) 2025 Future Internet Consulting and Development Solutions S.L.

# This file belongs to the business-charging-backend
# of the Business API Ecosystem.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

import json

from django.conf import settings

from wstore.store_commons.resource import Resource
from wstore.store_commons.utils.http import build_response


class BillingSchedulerTrigger(Resource):

    def create(self, request):
        if not settings.BILLING_HTTP_ENABLED:
            return build_response(request, 403, "Not available")

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return build_response(request, 400, "Invalid JSON body")

        date = data.get("date")
        if not date:
            return build_response(request, 400, "Missing required field: date")

        try:
            from wstore.charging_engine.management.commands.billing_scheduler import Command
            cmd = Command()
            cmd.handle(date=date)
        except ValueError as e:
            return build_response(request, 400, str(e))
        except Exception as e:
            return build_response(request, 500, str(e))

        return build_response(request, 200, "Billing scheduler executed for date: " + date)


class PaymentSchedulerTrigger(Resource):

    def create(self, request):
        if not settings.BILLING_HTTP_ENABLED:
            return build_response(request, 403, "Not available")

        try:
            from wstore.charging_engine.management.commands.payment_scheduler import Command
            cmd = Command()
            cmd.handle()
        except Exception as e:
            return build_response(request, 500, str(e))

        return build_response(request, 200, "Payment scheduler executed")
