# -*- coding: utf-8 -*-

# Copyright (c) 2025 Future Internet Consulting and Development Solutions S.L.

# This file belongs to the business-charging-backend
# of the Business API Ecosystem.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

import logging

from django.core.management.base import BaseCommand

from wstore.ordering.inventory_client import InventoryClient
from wstore.ordering.models import PendingTermination

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        """
        Periodic task that retries product terminations left pending due to a server crash
        """
        pending_list = list(PendingTermination.objects.all())

        if not pending_list:
            self.stdout.write("No pending terminations found")
            return

        self.stdout.write(f"Found {len(pending_list)} pending termination(s)")

        client = InventoryClient()
        for pending in pending_list:
            self.stdout.write(f"Retrying termination for product {pending.product_id}")
            try:
                client._do_terminate(
                    pending.product_id,
                    pending.realizing_resources,
                    pending.realizing_services,
                )
                pending.delete()
                self.stdout.write(self.style.SUCCESS(f"Termination succeeded for product {pending.product_id}"))
            except Exception as e:
                logger.exception("Termination recovery failed for product %s", pending.product_id)
                self.stderr.write(f"Termination failed for product {pending.product_id}: {e}")
