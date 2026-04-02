# -*- coding: utf-8 -*-

# Copyright (c) 2025 Future Internet Consulting and Development Solutions S.L.

# This file belongs to the business-charging-backend
# of the Business API Ecosystem.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

from django.test import TestCase
from mock import MagicMock, call, patch

from wstore.ordering.management.commands import retry_pending_terminations


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

    def test_no_pending_terminations(self):
        retry_pending_terminations.PendingTermination.objects.all.return_value = []

        command = retry_pending_terminations.Command()
        command.handle()

        retry_pending_terminations.InventoryClient().assert_not_called()

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
