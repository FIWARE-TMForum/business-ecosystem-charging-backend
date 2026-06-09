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
import requests
from decimal import Decimal
from django.test import TestCase
from parameterized import parameterized
from mock import MagicMock, patch

from wstore.charging_engine.charging import billing_client


# Test data for ACBRs (Applied Customer Billing Rates)
# Single one time ACBR
ACBR_SINGLE_ONETIME = [
    {
        "id": "acbr-1",
        "type": "one time",
        "taxIncludedAmount": {"unit": "EUR", "value": 12.10},
        "taxExcludedAmount": {"unit": "EUR", "value": 10.0},
        "periodCoverage": {"startDateTime": "2024-01-15T00:00:00Z"}
    }
]

# Multiple one time ACBRs with same period (should aggregate)
ACBR_MULTIPLE_ONETIME_SAME_PERIOD = [
    {
        "id": "acbr-1",
        "type": "one time",
        "taxIncludedAmount": {"unit": "EUR", "value": 12.10},
        "taxExcludedAmount": {"unit": "EUR", "value": 10.0},
        "periodCoverage": {"startDateTime": "2024-01-15T00:00:00Z"}
    },
    {
        "id": "acbr-2",
        "type": "one time",
        "taxIncludedAmount": {"unit": "EUR", "value": 6.05},
        "taxExcludedAmount": {"unit": "EUR", "value": 5.0},
        "periodCoverage": {"startDateTime": "2024-01-15T00:00:00Z"}
    }
]

# Mixed types with same period (should NOT aggregate together)
ACBR_MIXED_TYPES_SAME_PERIOD = [
    {
        "id": "acbr-5",
        "type": "one time",
        "taxIncludedAmount": {"unit": "EUR", "value": 12.10},
        "taxExcludedAmount": {"unit": "EUR", "value": 10.0},
        "periodCoverage": {"startDateTime": "2024-01-15T00:00:00Z"}
    },
    {
        "id": "acbr-6",
        "type": "recurring-prepaid",
        "taxIncludedAmount": {"unit": "EUR", "value": 18.15},
        "taxExcludedAmount": {"unit": "EUR", "value": 15.0},
        "periodCoverage": {
            "startDateTime": "2024-01-15T00:00:00Z",
            "endDateTime": "2024-02-14T00:00:00Z"
        }
    }
]

# Same type but different periods (should NOT aggregate)
ACBR_SAME_TYPE_DIFF_PERIOD = [
    {
        "id": "acbr-7",
        "type": "recurring-prepaid",
        "taxIncludedAmount": {"unit": "EUR", "value": 18.15},
        "taxExcludedAmount": {"unit": "EUR", "value": 15.0},
        "periodCoverage": {
            "startDateTime": "2024-01-15T00:00:00Z",
            "endDateTime": "2024-02-14T00:00:00Z"
        }
    },
    {
        "id": "acbr-8",
        "type": "recurring-prepaid",
        "taxIncludedAmount": {"unit": "EUR", "value": 18.15},
        "taxExcludedAmount": {"unit": "EUR", "value": 15.0},
        "periodCoverage": {
            "startDateTime": "2024-02-15T00:00:00Z",
            "endDateTime": "2024-03-16T00:00:00Z"
        }
    }
]


class BillingClientTestCase(TestCase):
    tags = ("billing", "customer_bill", "aggregation")
    maxDiff = None

    @parameterized.expand([
        (
            "single_onetime",
            ACBR_SINGLE_ONETIME,
                {
                    "taxIncludedAmount": 12.10,
                    "taxExcludedAmount": 10.0,
                    "acbr_count": 1
                }
        ),
        (
            "multiple_onetime_same_period_aggregates",
            ACBR_MULTIPLE_ONETIME_SAME_PERIOD,
            {
                "taxIncludedAmount": 18.15,  # 12.10 + 6.05
                "taxExcludedAmount": 15.0,    # 10.0 + 5.0
                "acbr_count": 2
            }
        ),
        (
            "mixed_types_same_period_no_aggregate",
            ACBR_MIXED_TYPES_SAME_PERIOD,
            
                {
                    "taxIncludedAmount": 30.25, # 12.10 + 18.15
                    "taxExcludedAmount": 25, # 10 + 15
                    "acbr_count": 2
                }
        ),
        (
            "same_type_diff_period_no_aggregate",
            ACBR_SAME_TYPE_DIFF_PERIOD,
            
                {
                    "type": "recurring",
                    "taxIncludedAmount": 36.30, # 18.15 + 18.15
                    "taxExcludedAmount": 30.0,
                    "acbr_count": 2
                }
        )
    ])
    def test_create_customer_bill_aggregation(self, name, acbrs, expected_cb):
        # Mock libs
        billing_client.get_operator_party_roles = MagicMock(return_value={})
        billing_client.normalize_party_ref = MagicMock(return_value={})

        client = billing_client.BillingClient()

        cb_model = {
            "taxIncludedAmount": {"value": 0, "unit": "EUR"},
            "taxExcludedAmount": {"value": 0, "unit": "EUR"},
            "billingAccount": {"id": "billing-account-1"},
            "relatedParty": [{"id": "party-1", "role": "Customer"}]
        }

        def mock_create_cb_api(cb_model):
            return {
                "id": "123",
                "taxIncludedAmount": {"value": expected_cb.get("taxIncludedAmount", 0)},
                "taxExcludedAmount": {"value": expected_cb.get("taxExcludedAmount", 0)}
            }

        client._create_cb_api = MagicMock(side_effect=mock_create_cb_api)
        client.set_acbrs_cb = MagicMock()

        # Execute
        result = client.create_customer_bill(acbrs, cb_model)
        if expected_cb["acbr_count"] != 0:
            self.assertEqual(result["taxIncludedAmount"], expected_cb["taxIncludedAmount"])
            self.assertEqual(result["taxExcludedAmount"], expected_cb["taxExcludedAmount"])
            self.assertEqual(result["unit"], "EUR")
            client.set_acbrs_cb.assert_called_once_with(acbrs, "123")

        # Verify _create_cb_api was called only once
        client._create_cb_api.assert_called_once()

    def test_create_customer_bill_empty_acbrs_returns_empty(self):
        client = billing_client.BillingClient()
        cb_model = {"taxIncludedAmount": {"value": 0, "unit": "EUR"}}
        result = client.create_customer_bill([], cb_model)
        self.assertEqual(result, {})

    def test_set_customer_bill_invalid_state_raises(self):
        client = billing_client.BillingClient()
        with self.assertRaises(ValueError):
            client.set_customer_bill("invalid_state", "bill-123")

    @patch("wstore.charging_engine.charging.billing_client.get_service_url")
    def test_set_customer_bill_valid_state(self, mock_url):
        mock_url.return_value = "http://billing/customerBill/bill-123"
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        client = billing_client.BillingClient()
        client._session = MagicMock()
        billing_client.requests = MagicMock()
        billing_client.requests.patch.return_value = mock_response

        client.set_customer_bill("settled", "bill-123")

        call_kwargs = billing_client.requests.patch.call_args
        self.assertEqual(call_kwargs[0][0], "http://billing/customerBill/bill-123")
        self.assertEqual(call_kwargs[1]["json"], {"state": "settled"})
        mock_response.raise_for_status.assert_called_once()

    @patch("wstore.charging_engine.charging.billing_client.get_service_url")
    def test_set_customer_bill_http_error_raises(self, mock_url):
        mock_url.return_value = "http://billing/customerBill/bill-123"
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500")

        client = billing_client.BillingClient()
        billing_client.requests = MagicMock()
        billing_client.requests.patch.return_value = mock_response
        billing_client.requests.exceptions.HTTPError = requests.exceptions.HTTPError

        with self.assertRaises(requests.exceptions.HTTPError):
            client.set_customer_bill("settled", "bill-123")

    @parameterized.expand([
        ("percentage_string", "21.0", "0.21"),
        ("percentage_decimal", "21", "0.21"),
        ("already_decimal", "0.21", "0.21"),
    ])
    @patch("wstore.charging_engine.charging.billing_client.requests.post")
    @patch("wstore.charging_engine.charging.billing_client.get_service_url")
    def test_create_customer_rate_normalizes_tax_rate(self, name, input_tax_rate, expected_decimal_rate, mock_get_service_url, mock_post):
        mock_get_service_url.return_value = "http://billing.test/appliedCustomerBillingRate"
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "acbr-1"}
        mock_post.return_value = mock_response

        client = billing_client.BillingClient()
        result = client.create_customer_rate(
            name="Test Rate",
            description="Test rate description",
            rate_type="one time",
            currency="EUR",
            tax_rate=input_tax_rate,
            tax="2.10",
            tax_included="12.10",
            tax_excluded="10.00",
            billing_account={"id": "ba-1"},
            product_id="urn:ngsi-ld:product:1",
            party=None,
        )

        self.assertEqual(result, {"id": "acbr-1"})
        mock_get_service_url.assert_called_once_with("billing", "appliedCustomerBillingRate")
        mock_post.assert_called_once()

        sent_body = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_body["appliedTax"][0]["taxRate"], Decimal(expected_decimal_rate))
