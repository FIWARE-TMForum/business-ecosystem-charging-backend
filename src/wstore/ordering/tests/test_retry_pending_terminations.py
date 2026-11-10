# -*- coding: utf-8 -*-

# Copyright (c) 2025 Future Internet Consulting and Development Solutions S.L.

# This file belongs to the business-charging-backend
# of the Business API Ecosystem.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

from io import StringIO

from django.core.management import call_command, get_commands
from django.test import TestCase
from mock import ANY, MagicMock, call, patch

from wstore.management.commands import retry_pending_terminations


def _build_pending(product_id, resources, services):
    pending = MagicMock()
    pending.product_id = product_id
    pending.realizing_resources = resources
    pending.realizing_services = services
    return pending


class RetryPendingTerminationsTestCase(TestCase):
    tags = ("retry-pending-terminations",)

    def setUp(self):
        retry_pending_terminations.PendingTermination = MagicMock()
        retry_pending_terminations.InventoryClient = MagicMock()
        for name, target in (
            ("get_order", "wstore.ordering.models.Order.get_by_product_id"),
            ("on_product_termination", "wstore.asset_manager.resource_plugins.decorators.on_product_termination"),
        ):
            patcher = patch(target)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def use_real_inventory_termination(self):
        from wstore.ordering.inventory_client import InventoryClient

        client = InventoryClient()
        client.patch_product = MagicMock()
        retry_pending_terminations.InventoryClient.return_value = client
        return client

    def test_no_pending_terminations(self):
        retry_pending_terminations.PendingTermination.objects.all.return_value = []

        command = retry_pending_terminations.Command()
        command.handle()

        retry_pending_terminations.InventoryClient().assert_not_called()
        self.get_order.assert_not_called()
        self.on_product_termination.assert_not_called()

    def test_registered_command_retries_pending_terminations(self):
        pending = _build_pending("product-1", ["res-1"], ["svc-1"])
        retry_pending_terminations.PendingTermination.objects.all.return_value = [pending]
        output = StringIO()

        self.assertEqual("wstore", get_commands()["retry_pending_terminations"])
        call_command("retry_pending_terminations", stdout=output)

        retry_pending_terminations.InventoryClient.return_value._do_terminate.assert_called_once_with(
            "product-1", ["res-1"], ["svc-1"]
        )
        pending.delete.assert_called_once()
        self.assertIn("Termination succeeded for product product-1", output.getvalue())

    def test_single_pending_termination_success(self):
        pending = _build_pending("product-1", ["res-1"], ["svc-1"])
        retry_pending_terminations.PendingTermination.objects.all.return_value = [pending]

        command = retry_pending_terminations.Command()
        command.handle()

        retry_pending_terminations.InventoryClient()._do_terminate.assert_called_once_with(
            "product-1", ["res-1"], ["svc-1"]
        )
        pending.delete.assert_called_once()

    def test_multiple_pending_terminations_all_succeed(self):
        pending1 = _build_pending("product-1", ["res-1"], [])
        pending2 = _build_pending("product-2", [], ["svc-1"])
        retry_pending_terminations.PendingTermination.objects.all.return_value = [pending1, pending2]

        command = retry_pending_terminations.Command()
        command.handle()

        client = retry_pending_terminations.InventoryClient()
        self.assertEqual(client._do_terminate.call_count, 2)
        client._do_terminate.assert_any_call("product-1", ["res-1"], [])
        client._do_terminate.assert_any_call("product-2", [], ["svc-1"])
        pending1.delete.assert_called_once()
        pending2.delete.assert_called_once()

    def test_plugin_failure_keeps_pending_and_other_products_continue(self):
        pending1 = _build_pending("product-1", [], [])
        pending2 = _build_pending("product-2", [], [])
        retry_pending_terminations.PendingTermination.objects.all.return_value = [pending1, pending2]
        client = self.use_real_inventory_termination()
        self.on_product_termination.side_effect = [RuntimeError("cleanup failed"), None]
        with self.assertLogs("wstore.management.commands.retry_pending_terminations", level="ERROR"):
            retry_pending_terminations.Command().handle()
        pending1.delete.assert_not_called()
        pending2.delete.assert_called_once()
        client.patch_product.assert_called_once_with("product-2", ANY)
        self.assertEqual(2, self.on_product_termination.call_count)

    def test_retry_runs_plugins_before_inventory_and_deletes_only_after_success(self):
        pending = _build_pending("product-1", [], [])
        retry_pending_terminations.PendingTermination.objects.all.return_value = [pending]
        client = self.use_real_inventory_termination()
        sequence = MagicMock()
        sequence.attach_mock(self.on_product_termination, "cleanup")
        sequence.attach_mock(client.patch_product, "inventory")
        sequence.attach_mock(pending.delete, "done")
        self.on_product_termination.side_effect = [RuntimeError("cleanup failed"), None]
        command = retry_pending_terminations.Command()
        with self.assertLogs("wstore.management.commands.retry_pending_terminations", level="ERROR"):
            command.handle()
        order = self.get_order.return_value
        cleanup = call.cleanup(order, order.get_product_contract.return_value)
        self.assertEqual([cleanup], sequence.mock_calls)
        command.handle()
        self.assertEqual([
            cleanup, cleanup, call.inventory("product-1", ANY), call.done()
        ], sequence.mock_calls)

    def test_context_lookup_failure_keeps_pending_without_inventory_updates(self):
        pending = _build_pending("product-1", [], [])
        retry_pending_terminations.PendingTermination.objects.all.return_value = [pending]
        client = self.use_real_inventory_termination()
        self.get_order.side_effect = RuntimeError("order unavailable")
        with self.assertLogs("wstore.management.commands.retry_pending_terminations", level="ERROR"):
            retry_pending_terminations.Command().handle()
        self.on_product_termination.assert_not_called()
        client.patch_product.assert_not_called()
        pending.delete.assert_not_called()

    def test_termination_failure_does_not_delete_and_continues(self):
        pending1 = _build_pending("product-1", [], [])
        pending2 = _build_pending("product-2", [], [])

        client_mock = MagicMock()
        client_mock._do_terminate.side_effect = [Exception("API error"), None]
        retry_pending_terminations.InventoryClient.return_value = client_mock
        retry_pending_terminations.PendingTermination.objects.all.return_value = [pending1, pending2]

        command = retry_pending_terminations.Command()
        command.handle()

        # Failed one is not deleted, successful one is
        pending1.delete.assert_not_called()
        pending2.delete.assert_called_once()
