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

        billing_acc_ref = {"id": "billing-account-1"}
        party = [{"id": "party-1", "role": "Customer"}]

        def mock_create_cb_api(unit, taxIncluded, taxExcluded, billing_acc_ref, current_time, party):
            return{
                "id": "123",
                "taxIncludedAmount":{
                    "value": expected_cb.get("taxIncludedAmount", 0),
                },
                "taxExcludedAmount": {
                    "value":expected_cb.get("taxExcludedAmount", 0)
                }
            }

        client._create_cb_api = MagicMock(side_effect=mock_create_cb_api)
        client.set_acbrs_cb = MagicMock()

        # Execute
        result = client.create_customer_bill(acbrs, billing_acc_ref, party)
        if expected_cb["acbr_count"] != 0:
            self.assertEqual(result["taxIncludedAmount"], expected_cb["taxIncludedAmount"])
            self.assertEqual(result["taxExcludedAmount"], expected_cb["taxExcludedAmount"])
            self.assertEqual(result["unit"], "EUR")
        self.assertEqual(len(result["acbrRefs"]), expected_cb["acbr_count"])

        # Verify _create_cb_api was called only once
        client._create_cb_api.assert_called_once()

        # Verify set_acbrs_cb was called correctly
        client.set_acbrs_cb.assert_called_once()
