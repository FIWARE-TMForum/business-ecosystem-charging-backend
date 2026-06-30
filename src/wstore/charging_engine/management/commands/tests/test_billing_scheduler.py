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

import datetime
from decimal import Decimal
from unittest.mock import ANY, MagicMock, patch, call

from django.test import TestCase

from wstore.charging_engine.management.commands.billing_scheduler import Command


BUNDLE_POP_ID = "urn:ngsi-ld:product-offering-price:bundle-1"
RECURRING_POP_ID = "urn:ngsi-ld:product-offering-price:recurring-1"
USAGE_POP_ID = "urn:ngsi-ld:product-offering-price:usage-1"
ONETIME_POP_ID = "urn:ngsi-ld:product-offering-price:onetime-1"
PRODUCT_ID = "urn:ngsi-ld:product:product-1"
PRODUCT_START_DATE = "2026-03-01T00:00:00Z"

BUNDLE_POP = {
    "id": BUNDLE_POP_ID,
    "isBundle": True,
    "bundledPopRelationship": [{"id": RECURRING_POP_ID, "href": RECURRING_POP_ID, "name": "Monthly charge"}],
}

RECURRING_POP = {
    "id": RECURRING_POP_ID,
    "isBundle": False,
    "priceType": "recurring",
    "recurringChargePeriodLength": 1,
    "recurringChargePeriodType": "month",
    "price": {"unit": "EUR", "value": 10.0},
    "name": "Monthly charge",
    "description": "Monthly recurring charge",
}

USAGE_POP = {
    "id": USAGE_POP_ID,
    "isBundle": False,
    "priceType": "usage",
    "price": {"unit": "EUR", "value": 0.5},
    "name": "Usage charge",
    "description": "Pay per use",
    "unitOfMeasure": {"amount": 1.0, "units": "mins"},
}

ONETIME_POP = {
    "id": ONETIME_POP_ID,
    "isBundle": False,
    "priceType": "one time",
    "price": {"unit": "EUR", "value": 5.0},
    "name": "One time charge",
}

PRODUCT = {
    "id": PRODUCT_ID,
    "status": "active",
    "startDate": PRODUCT_START_DATE,
    "productPrice": [
        {"productOfferingPrice": {"id": BUNDLE_POP_ID, "href": BUNDLE_POP_ID}},
        {"productOfferingPrice": {"id": RECURRING_POP_ID, "href": RECURRING_POP_ID}},
    ],
    "billingAccount": {"id": "billing-acc-1", "href": "billing-acc-1"},
    "relatedParty": [{"id": "party-1", "role": "customer", "@referredType": "Organization"}],
}

ACBR_EXPIRED = {
    "id": "acbr-1",
    "date": "2026-04-01T00:00:00Z",
    "isBilled": True,
    "periodCoverage": {
        "startDateTime": "2026-04-01T00:00:00Z",
        "endDateTime": "2026-04-30T23:59:59Z",
    },
}

ACBR_NOT_EXPIRED = {
    "id": "acbr-2",
    "date": "2026-05-01T00:00:00Z",
    "isBilled": True,
    "periodCoverage": {
        "startDateTime": "2026-05-01T00:00:00Z",
        "endDateTime": "2026-05-31T23:59:59Z",
    },
}

PRICE = {
    "priceId": RECURRING_POP_ID,
    "priceType": "recurring",
    "recurringChargePeriod": "1 month",
    "name": "Monthly charge",
    "description": "Monthly recurring charge",
    "price": {
        "taxRate": "21",
        "dutyFreeAmount": {"unit": "EUR", "value": "10.00"},
        "taxIncludedAmount": {"unit": "EUR", "value": "12.10"},
    },
}

TODAY = datetime.datetime(2026, 5, 31, tzinfo=datetime.timezone.utc)


class BillingSchedulerGetPopComponentsTestCase(TestCase):

    def setUp(self):
        self.command = Command.__new__(Command)
        self.command._inventory_client = MagicMock()
        self.command._billing_client = MagicMock()
        self.command._price_engine = MagicMock()
        self.command._usage_client = MagicMock()
        self.command._local_engine = MagicMock()

    def test_returns_only_non_bundle_components(self):
        self.command._inventory_client.get_price_component.side_effect = [BUNDLE_POP, RECURRING_POP]

        result = self.command._get_pop_components(PRODUCT["productPrice"])

        self.assertEqual(result, [RECURRING_POP])

    def test_returns_multiple_components(self):
        product_prices = [
            {"productOfferingPrice": {"id": BUNDLE_POP_ID}},
            {"productOfferingPrice": {"id": RECURRING_POP_ID}},
            {"productOfferingPrice": {"id": USAGE_POP_ID}},
        ]
        self.command._inventory_client.get_price_component.side_effect = [BUNDLE_POP, RECURRING_POP, USAGE_POP]

        result = self.command._get_pop_components(product_prices)

        self.assertEqual(result, [RECURRING_POP, USAGE_POP])

    def test_returns_empty_when_all_bundles(self):
        self.command._inventory_client.get_price_component.return_value = BUNDLE_POP

        result = self.command._get_pop_components(PRODUCT["productPrice"])

        self.assertEqual(result, [])


class BillingSchedulerGetPopsToBillTestCase(TestCase):

    def setUp(self):
        self.command = Command.__new__(Command)
        self.command._inventory_client = MagicMock()
        self.command._billing_client = MagicMock()
        self.command._price_engine = MagicMock()
        self.command._usage_client = MagicMock()
        self.command._local_engine = MagicMock()
        self.command._local_engine._build_period_coverage.return_value = {
            "startDateTime": "2026-05-01T00:00:01Z",
            "endDateTime": "2026-05-31T23:59:59Z",
        }

    def test_skips_onetime_pops(self):
        self.command._billing_client.get_acbrs.return_value = [ACBR_EXPIRED]

        pops_to_bill, usage_period, pops_to_process = self.command._get_pops_to_bill(
            PRODUCT_ID, [ONETIME_POP], TODAY, PRODUCT_START_DATE
        )

        self.assertEqual(pops_to_bill, {})
        self.assertIsNone(usage_period)
        self.assertEqual(pops_to_process, [])
        self.command._billing_client.get_acbrs.assert_not_called()

    def test_skips_pop_with_no_acbrs_and_first_period_not_expired(self):
        self.command._billing_client.get_acbrs.return_value = []

        pops_to_bill, usage_period, pops_to_process = self.command._get_pops_to_bill(
            PRODUCT_ID, [RECURRING_POP], TODAY, PRODUCT_START_DATE
        )

        self.assertEqual(pops_to_bill, {})
        self.assertIsNone(usage_period)
        self.assertEqual(pops_to_process, [])

    def test_skips_pop_with_no_end_date(self):
        acbr_no_end = {**ACBR_EXPIRED, "periodCoverage": {"startDateTime": "2026-04-01T00:00:00Z"}}
        self.command._billing_client.get_acbrs.return_value = [acbr_no_end]

        pops_to_bill, usage_period, pops_to_process = self.command._get_pops_to_bill(
            PRODUCT_ID, [RECURRING_POP], TODAY, PRODUCT_START_DATE
        )

        self.assertEqual(pops_to_bill, {})

    def test_skips_pop_not_expired(self):
        self.command._billing_client.get_acbrs.return_value = [ACBR_NOT_EXPIRED]

        pops_to_bill, usage_period, pops_to_process = self.command._get_pops_to_bill(
            PRODUCT_ID, [RECURRING_POP], TODAY, PRODUCT_START_DATE
        )

        self.assertEqual(pops_to_bill, {})
        self.assertIsNone(usage_period)
        self.assertEqual(pops_to_process, [])

    def test_includes_expired_recurring_pop(self):
        next_period = {"startDateTime": "2026-05-01T00:00:01Z", "endDateTime": "2026-05-30T23:59:59Z"}
        self.command._local_engine._build_period_coverage.return_value = next_period
        self.command._billing_client.get_acbrs.return_value = [ACBR_EXPIRED]

        pops_to_bill, usage_period, pops_to_process = self.command._get_pops_to_bill(
            PRODUCT_ID, [RECURRING_POP], TODAY, PRODUCT_START_DATE
        )

        self.assertIn(RECURRING_POP_ID, pops_to_bill)
        self.assertEqual(pops_to_bill[RECURRING_POP_ID]["periodCoverage"], next_period)
        self.assertEqual(pops_to_bill[RECURRING_POP_ID]["type"], "recurring")
        self.assertIsNone(usage_period)
        self.assertEqual(pops_to_process, [RECURRING_POP])
        self.command._local_engine._build_period_coverage.assert_called_once_with("1 month", ANY)

    def test_sets_usage_period_for_usage_pop(self):
        next_period = {"startDateTime": "2026-05-01T00:00:01Z", "endDateTime": "2026-05-30T23:59:59Z"}
        self.command._local_engine._build_period_coverage.return_value = next_period
        self.command._billing_client.get_acbrs.return_value = [ACBR_EXPIRED]

        pops_to_bill, usage_period, pops_to_process = self.command._get_pops_to_bill(
            PRODUCT_ID, [USAGE_POP], TODAY, PRODUCT_START_DATE
        )

        self.assertIn(USAGE_POP_ID, pops_to_bill)
        self.assertEqual(usage_period, next_period)
        self.assertEqual(pops_to_process, [USAGE_POP])

    def test_multiple_pops_some_expired(self):
        self.command._local_engine._build_period_coverage.return_value = {
            "startDateTime": "2026-05-01T00:00:01Z",
            "endDateTime": "2026-05-30T23:59:59Z",
        }
        self.command._billing_client.get_acbrs.side_effect = [
            [ACBR_EXPIRED],
            [ACBR_NOT_EXPIRED],
        ]

        pops_to_bill, _, pops_to_process = self.command._get_pops_to_bill(
            PRODUCT_ID, [RECURRING_POP, USAGE_POP], TODAY, PRODUCT_START_DATE
        )

        self.assertIn(RECURRING_POP_ID, pops_to_bill)
        self.assertNotIn(USAGE_POP_ID, pops_to_bill)
        self.assertEqual(pops_to_process, [RECURRING_POP])


class BillingSchedulerProcessProductTestCase(TestCase):

    def setUp(self):
        self.command = Command.__new__(Command)
        self.command._inventory_client = MagicMock()
        self.command._billing_client = MagicMock()
        self.command._price_engine = MagicMock()
        self.command._usage_client = MagicMock()
        self.command._local_engine = MagicMock()

        self.next_period = {"startDateTime": "2026-05-01T00:00:01Z", "endDateTime": "2026-05-30T23:59:59Z"}
        self.command._local_engine._build_period_coverage.return_value = self.next_period
        self.command._inventory_client.get_price_component.side_effect = [BUNDLE_POP, RECURRING_POP]
        self.command._billing_client.get_acbrs.return_value = [ACBR_EXPIRED]
        self.command._price_engine.calculate_prices.return_value = [PRICE]
        self.command._billing_client.create_customer_rate.return_value = {"id": "new-acbr-1"}

    def test_skips_product_with_no_product_price(self):
        product = {**PRODUCT, "productPrice": []}

        self.command._process_product(product, TODAY)

        self.command._billing_client.create_customer_bill.assert_not_called()

    def test_skips_product_when_no_pops_to_bill(self):
        self.command._billing_client.get_acbrs.return_value = [ACBR_NOT_EXPIRED]

        self.command._process_product(PRODUCT, TODAY)

        self.command._billing_client.create_customer_bill.assert_not_called()

    def test_creates_acbr_and_customer_bill(self):
        self.command._process_product(PRODUCT, TODAY)

        self.command._billing_client.create_customer_rate.assert_called_once()
        self.command._billing_client.create_customer_bill.assert_called_once()
        _, kwargs = self.command._billing_client.create_customer_bill.call_args
        self.assertEqual(kwargs.get("cb_state") or self.command._billing_client.create_customer_bill.call_args[0][2], "new")

    def test_customer_bill_created_with_state_new(self):
        self.command._process_product(PRODUCT, TODAY)

        args, kwargs = self.command._billing_client.create_customer_bill.call_args
        cb_state = kwargs.get("cb_state", args[2] if len(args) > 2 else None)
        self.assertEqual(cb_state, "new")

    def test_gets_usages_for_usage_pop(self):
        self.command._inventory_client.get_price_component.side_effect = [BUNDLE_POP, USAGE_POP]
        usage_price = {**PRICE, "priceId": USAGE_POP_ID, "priceType": "usage"}
        self.command._price_engine.calculate_prices.return_value = [usage_price]
        self.command._usage_client.get_customer_usage_in_period.return_value = [{"id": "usage-1"}]

        self.command._process_product(PRODUCT, TODAY)

        self.command._usage_client.get_customer_usage_in_period.assert_called_once_with(
            PRODUCT_ID,
            self.next_period["startDateTime"],
            self.next_period["endDateTime"],
        )

    def test_skips_prices_not_in_pops_to_bill(self):
        other_price = {**PRICE, "priceId": "other-pop-id"}
        self.command._price_engine.calculate_prices.return_value = [other_price]

        self.command._process_product(PRODUCT, TODAY)

        self.command._billing_client.create_customer_rate.assert_not_called()
        self.command._billing_client.create_customer_bill.assert_not_called()

    def test_passes_pop_components_to_calculate_prices(self):
        self.command._process_product(PRODUCT, TODAY)

        _, kwargs = self.command._price_engine.calculate_prices.call_args
        self.assertIn("pop_components", kwargs)
        self.assertEqual(kwargs["pop_components"], [RECURRING_POP])


USAGE_POP_WITH_SPEC = {
    "id": USAGE_POP_ID,
    "isBundle": False,
    "priceType": "usage",
    "price": {"unit": "EUR", "value": 0.5},
    "name": "Usage charge",
    "description": "Pay per use",
    "unitOfMeasure": {"amount": 1.0, "units": "mins"},
    "usageSpecId": "urn:ngsi-ld:usageSpecification:spec-1",
}

REAL_USAGES = [
    {
        "usageSpecification": {"id": "urn:ngsi-ld:usageSpecification:spec-1"},
        "usageCharacteristic": [{"name": "mins", "value": 20}],
    }
]

UNMATCHED_USAGES = [
    {
        "usageSpecification": {"id": "urn:ngsi-ld:usageSpecification:OTHER"},
        "usageCharacteristic": [{"name": "mins", "value": 20}],
    }
]


class BillingSchedulerFullFlowTestCase(TestCase):
    """Integration-style tests that run the full logic without mocking internal methods.
    Only external dependencies (HTTP clients) are mocked."""

    def setUp(self):
        self.command = Command.__new__(Command)
        self.command._inventory_client = MagicMock()
        self.command._billing_client = MagicMock()
        self.command._price_engine = MagicMock()
        self.command._usage_client = MagicMock()

        from wstore.charging_engine.engines.local_engine import LocalEngine
        self.command._local_engine = LocalEngine(None)

    def _setup_product(self, pop_components, acbrs_by_pop_id, prices, created_acbr_id="new-acbr-1"):
        self.command._inventory_client.get_price_component.side_effect = [BUNDLE_POP] + pop_components
        self.command._billing_client.get_acbrs.side_effect = [
            acbrs_by_pop_id.get(pop["id"], []) for pop in pop_components
        ]
        self.command._price_engine.calculate_prices.return_value = prices
        self.command._billing_client.create_customer_rate.return_value = {"id": created_acbr_id}
        self.command._billing_client.create_customer_bill.return_value = {"id": "new-cb-1"}

    def test_full_flow_creates_acbr_for_expired_recurring_pop(self):
        self._setup_product(
            pop_components=[RECURRING_POP],
            acbrs_by_pop_id={RECURRING_POP_ID: [ACBR_EXPIRED]},
            prices=[PRICE]
        )

        self.command._process_product(PRODUCT, TODAY)

        self.command._billing_client.create_customer_rate.assert_called_once()
        call_kwargs = self.command._billing_client.create_customer_rate.call_args[1]
        self.assertEqual(call_kwargs["rate_type"], "recurring")
        self.assertEqual(call_kwargs["product_id"], PRODUCT_ID)
        self.assertEqual(call_kwargs["priceId"], RECURRING_POP_ID)

        self.command._billing_client.create_customer_bill.assert_called_once()
        cb_args = self.command._billing_client.create_customer_bill.call_args
        self.assertEqual(cb_args[0][0], [{"id": "new-acbr-1"}])
        self.assertEqual(cb_args[1].get("cb_state") or cb_args[0][2], "new")

    def test_full_flow_no_acbr_for_non_expired_pop(self):
        self._setup_product(
            pop_components=[RECURRING_POP],
            acbrs_by_pop_id={RECURRING_POP_ID: [ACBR_NOT_EXPIRED]},
            prices=[PRICE],
        )

        self.command._process_product(PRODUCT, TODAY)

        self.command._billing_client.create_customer_rate.assert_not_called()
        self.command._billing_client.create_customer_bill.assert_not_called()

    def test_full_flow_only_bills_expired_pops_when_mixed(self):
        product_with_two_pops = {
            **PRODUCT,
            "productPrice": [
                {"productOfferingPrice": {"id": BUNDLE_POP_ID, "href": BUNDLE_POP_ID}},
                {"productOfferingPrice": {"id": RECURRING_POP_ID, "href": RECURRING_POP_ID}},
                {"productOfferingPrice": {"id": USAGE_POP_ID, "href": USAGE_POP_ID}},
            ],
        }
        usage_price = {**PRICE, "priceId": USAGE_POP_ID, "priceType": "usage"}

        self.command._inventory_client.get_price_component.side_effect = [
            BUNDLE_POP, RECURRING_POP, USAGE_POP
        ]
        self.command._billing_client.get_acbrs.side_effect = [
            [ACBR_EXPIRED],      # recurring → expired → should bill
            [ACBR_NOT_EXPIRED],  # usage → not expired → should skip
        ]
        self.command._price_engine.calculate_prices.return_value = [PRICE, usage_price]
        self.command._billing_client.create_customer_rate.return_value = {"id": "new-acbr-1"}
        self.command._billing_client.create_customer_bill.return_value = {"id": "new-cb-1"}

        self.command._process_product(product_with_two_pops, TODAY)

        self.assertEqual(self.command._billing_client.create_customer_rate.call_count, 1)
        call_kwargs = self.command._billing_client.create_customer_rate.call_args[1]
        self.assertEqual(call_kwargs["priceId"], RECURRING_POP_ID)

    def test_full_flow_skips_onetime_pop(self):
        self.command._inventory_client.get_price_component.side_effect = [BUNDLE_POP, ONETIME_POP]
        self.command._billing_client.get_acbrs.return_value = [ACBR_EXPIRED]

        self.command._process_product(PRODUCT, TODAY)

        self.command._billing_client.get_acbrs.assert_not_called()
        self.command._billing_client.create_customer_rate.assert_not_called()

    def test_full_flow_period_coverage_built_correctly(self):
        self._setup_product(
            pop_components=[RECURRING_POP],
            acbrs_by_pop_id={RECURRING_POP_ID: [ACBR_EXPIRED]},
            prices=[PRICE],
        )

        self.command._process_product(PRODUCT, TODAY)

        call_kwargs = self.command._billing_client.create_customer_rate.call_args[1]
        period = call_kwargs["coverage_period"]
        self.assertIn("startDateTime", period)
        self.assertIn("endDateTime", period)
        # next period starts exactly at ACBR_EXPIRED endDateTime (no +1s adjustment)
        self.assertEqual(period["startDateTime"], "2026-04-30T23:59:59Z")



class BillingSchedulerHandleTestCase(TestCase):

    def setUp(self):
        self.command = Command.__new__(Command)
        self.command._inventory_client = MagicMock()
        self.command._billing_client = MagicMock()
        self.command._price_engine = MagicMock()
        self.command._usage_client = MagicMock()
        self.command._local_engine = MagicMock()
        self.command._process_product = MagicMock()

    def test_paginates_until_page_smaller_than_limit(self):
        page1 = [PRODUCT] * 100
        page2 = [PRODUCT] * 50
        self.command._inventory_client.get_products.side_effect = [page1, page2]

        self.command.handle()

        self.assertEqual(self.command._inventory_client.get_products.call_count, 2)
        self.command._inventory_client.get_products.assert_any_call({"status": "active", "limit": 100, "offset": 0})
        self.command._inventory_client.get_products.assert_any_call({"status": "active", "limit": 100, "offset": 100})

    def test_stops_on_empty_page(self):
        self.command._inventory_client.get_products.return_value = []

        self.command.handle()

        self.command._inventory_client.get_products.assert_called_once()
        self.command._process_product.assert_not_called()

    def test_processes_each_product(self):
        products = [PRODUCT, {**PRODUCT, "id": "product-2"}]
        self.command._inventory_client.get_products.side_effect = [products, []]

        self.command.handle()

        self.assertEqual(self.command._process_product.call_count, 2)

    def test_continues_on_product_error(self):
        product2 = {**PRODUCT, "id": "product-2"}
        self.command._inventory_client.get_products.side_effect = [[PRODUCT, product2], []]
        self.command._process_product.side_effect = [Exception("something failed"), None]

        self.command.handle()

        self.assertEqual(self.command._process_product.call_count, 2)


PRODUCT_USAGE_ONLY = {
    "id": PRODUCT_ID,
    "status": "active",
    "startDate": PRODUCT_START_DATE,
    "productPrice": [
        {"productOfferingPrice": {"id": USAGE_POP_ID, "href": USAGE_POP_ID}},
    ],
    "billingAccount": {"id": "billing-acc-1", "href": "billing-acc-1"},
    "relatedParty": [{"id": "party-1", "role": "customer", "@referredType": "Organization"}],
}


class BillingSchedulerSystemTestCase(TestCase):
    """System tests: only handle() is called. HTTP clients are mocked,
    PriceEngine and LocalEngine run for real so usage matching is exercised."""

    def setUp(self):
        from wstore.charging_engine.pricing_engine import PriceEngine
        from wstore.charging_engine.engines.local_engine import LocalEngine

        self.command = Command.__new__(Command)
        self.command._inventory_client = MagicMock()
        self.command._billing_client = MagicMock()
        self.command._usage_client = MagicMock()
        self.command._local_engine = LocalEngine(None)

        self.price_engine = PriceEngine()
        self.price_engine._calculate_taxes = MagicMock(return_value=0)
        self.command._price_engine = self.price_engine

        self.command._inventory_client.get_products.side_effect = [[PRODUCT_USAGE_ONLY], []]
        self.command._inventory_client.get_price_component.return_value = USAGE_POP_WITH_SPEC
        self.command._billing_client.get_acbrs.return_value = [ACBR_EXPIRED]
        self.command._billing_client.create_customer_rate.return_value = {"id": "new-acbr-1"}
        self.command._billing_client.create_customer_bill.return_value = {"id": "new-cb-1"}

    def _get_acbr_kwargs(self):
        return self.command._billing_client.create_customer_rate.call_args[1]

    def test_acbr_price_correct_when_usage_matches(self):
        # 20 mins * 0.5 EUR/min = 10.0 EUR, tax 0%
        self.command._usage_client.get_customer_usage_in_period.return_value = REAL_USAGES

        self.command.handle()

        self.command._billing_client.create_customer_rate.assert_called_once()
        kwargs = self._get_acbr_kwargs()
        self.assertEqual(kwargs["priceId"], USAGE_POP_ID)
        self.assertEqual(kwargs["tax_excluded"], "10.0")
        self.assertEqual(kwargs["tax_included"], "10.00")
        self.assertEqual(kwargs["tax_rate"], "0")
        self.assertEqual(kwargs["tax"], "0.00")

    def test_acbr_price_correct_with_tax(self):
        # 20 mins * 0.5 EUR/min = 10.0 EUR, tax 21% → 12.10 EUR
        self.price_engine._calculate_taxes.return_value = 21
        self.command._usage_client.get_customer_usage_in_period.return_value = REAL_USAGES

        self.command.handle()

        kwargs = self._get_acbr_kwargs()
        self.assertEqual(kwargs["tax_excluded"], "10.0")
        self.assertEqual(kwargs["tax_included"], "12.10")
        self.assertEqual(kwargs["tax_rate"], "21")
        self.assertEqual(kwargs["tax"], "2.10")

    def test_acbr_price_is_zero_when_usage_spec_not_matched(self):
        # usageSpecification.id no coincide con usageSpecId del POP → 0 EUR
        self.command._usage_client.get_customer_usage_in_period.return_value = UNMATCHED_USAGES

        self.command.handle()

        kwargs = self._get_acbr_kwargs()
        self.assertEqual(kwargs["tax_excluded"], "0")
        self.assertEqual(kwargs["tax_included"], "0.00")
