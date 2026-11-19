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

from logging import getLogger

from django.core.management.base import BaseCommand

from wstore.asset_manager.resource_plugins.decorators import has_pull_accounting_plugins, on_usage_refreshed
from wstore.ordering.inventory_client import InventoryClient
from wstore.store_commons.product_catalog import ProductCatalog

logger = getLogger("wstore.default_logger")


class Command(BaseCommand):
    help = "Collect pending plugin accounting for active products with usage pricing."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._inventory_client = InventoryClient()
        self._catalog = ProductCatalog()

    def _process_product(self, product):
        for price in product.get("productPrice", []):
            component = self._catalog.get_price(price["productOfferingPrice"]["id"])

            # Purchased productPrice includes the bundle's individual components.
            if not component.get("isBundle", False) and component.get("priceType", "").lower() == "usage":
                on_usage_refreshed(product)
                return

    def handle(self, *args, **options):
        if not has_pull_accounting_plugins():
            return

        logger.info("Running accounting scheduler")
        offset, limit = 0, 100

        while True:
            products = self._inventory_client.get_products({"status": "active", "limit": limit, "offset": offset})

            if not products:
                break

            for product in products:
                try:
                    self._process_product(product)
                except Exception:
                    logger.exception("Error collecting accounting for product %s", product.get("id"))

            if len(products) < limit:
                break

            offset += limit

        logger.info("Accounting scheduler finished")
