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

from os import environ, path
from runpy import run_path
from unittest.mock import call, patch

from django.conf import settings
from django.test import SimpleTestCase

from wstore.charging_engine.management.commands import accounting_scheduler


class AccountingSchedulerTests(SimpleTestCase):
    def setUp(self):
        for name in ("InventoryClient", "ProductCatalog", "on_usage_refreshed", "has_pull_accounting_plugins"):
            patcher = patch.object(accounting_scheduler, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

        self.has_pull_accounting_plugins.return_value = True

        self.command = accounting_scheduler.Command()
        self.inventory = self.InventoryClient.return_value
        self.catalog = self.ProductCatalog.return_value

        self.product = {"id": "product-1", "productPrice": [
            {"productOfferingPrice": {"id": "usage-price"}},
        ]}

        self.catalog.get_price.return_value = {"id": "usage-price", "priceType": "usage"}

    def test_collects_usage_without_waiting_for_a_billing_period(self):
        self.command._process_product(self.product)

        self.catalog.get_price.assert_called_once_with("usage-price")
        self.on_usage_refreshed.assert_called_once_with(self.product)
        self.inventory.get_service.assert_not_called()
        self.inventory.get_resource.assert_not_called()

    def test_free_product_does_not_load_prices_or_dispatch_accounting(self):
        self.command._process_product({"id": "free"})

        self.catalog.get_price.assert_not_called()
        self.on_usage_refreshed.assert_not_called()

    def test_non_usage_prices_do_not_dispatch_accounting(self):
        for price_type in ("one time", "recurring", "recurring-prepaid"):
            with self.subTest(price_type=price_type):
                self.catalog.get_price.return_value = {"priceType": price_type}

                self.command._process_product(self.product)

        self.on_usage_refreshed.assert_not_called()

    def test_bundle_and_recurring_prices_are_skipped_before_usage_component(self):
        product = {**self.product, "productPrice": [
            {"productOfferingPrice": {"id": price_id}}
            for price_id in ("bundle", "recurring", "usage-price", "second-usage-price")
        ]}
        self.catalog.get_price.side_effect = [
            {"id": "bundle", "isBundle": True},
            {"id": "recurring", "priceType": "recurring"},
            {"id": "usage-price", "priceType": "Usage"},
        ]

        self.command._process_product(product)

        self.assertEqual([call("bundle"), call("recurring"), call("usage-price")],
                         self.catalog.get_price.call_args_list)
        self.on_usage_refreshed.assert_called_once_with(product)

    def test_paginates_active_products(self):
        products = [{**self.product, "id": f"product-{i}"} for i in range(101)]
        self.inventory.get_products.side_effect = [products[:100], products[100:]]

        self.command.handle()

        self.assertEqual([
            call({"status": "active", "limit": 100, "offset": 0}),
            call({"status": "active", "limit": 100, "offset": 100}),
        ], self.inventory.get_products.call_args_list)
        self.assertEqual([call(product) for product in products], self.on_usage_refreshed.call_args_list)
        self.has_pull_accounting_plugins.assert_called_once_with()

    def test_no_pull_plugins_skips_inventory_catalog_and_dispatch(self):
        self.has_pull_accounting_plugins.return_value = False

        self.command.handle()

        self.has_pull_accounting_plugins.assert_called_once_with()
        self.inventory.get_products.assert_not_called()
        self.catalog.get_price.assert_not_called()
        self.on_usage_refreshed.assert_not_called()

    def test_registry_is_checked_again_on_the_next_run(self):
        self.has_pull_accounting_plugins.side_effect = [False, True]
        self.inventory.get_products.return_value = [self.product]

        self.command.handle()

        self.inventory.get_products.assert_not_called()

        self.command.handle()

        self.assertEqual(2, self.has_pull_accounting_plugins.call_count)
        self.on_usage_refreshed.assert_called_once_with(self.product)

    def test_empty_page_stops_collection(self):
        self.inventory.get_products.return_value = []

        self.command.handle()

        self.inventory.get_products.assert_called_once()
        self.on_usage_refreshed.assert_not_called()

    def test_failed_product_does_not_prevent_collecting_the_next_product(self):
        other = {**self.product, "id": "product-2"}
        self.inventory.get_products.return_value = [self.product, other]
        self.on_usage_refreshed.side_effect = [RuntimeError("accounting unavailable"), None]

        with self.assertLogs("wstore.default_logger", level="ERROR"):
            self.command.handle()

        self.assertEqual([call(self.product), call(other)], self.on_usage_refreshed.call_args_list)


class AccountingScheduleConfigurationTests(SimpleTestCase):
    def test_daily_collection_is_registered_once_for_local_billing(self):
        with patch.dict(environ, {"BAE_CB_BILLING_ENGINE": "local"}):
            configuration = run_path(path.join(settings.BASEDIR, "settings.py"))

        jobs = [job for job in configuration["CRONJOBS"] if job[2] == ["accounting_scheduler"]]

        self.assertEqual([("0 0 * * *", "django.core.management.call_command", ["accounting_scheduler"])], jobs)

    def test_external_billing_has_no_accounting_billing_or_payment_schedules(self):
        with patch.dict(environ, {"BAE_CB_BILLING_ENGINE": "dome"}):
            configuration = run_path(path.join(settings.BASEDIR, "settings.py"))

        commands = [job[2][0] for job in configuration["CRONJOBS"]]

        for command in ("accounting_scheduler", "billing_scheduler", "payment_scheduler"):
            self.assertNotIn(command, commands)
