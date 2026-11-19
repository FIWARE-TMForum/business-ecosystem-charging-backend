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
from django.test import SimpleTestCase, TestCase
from django.test.utils import override_settings

from parameterized import parameterized
from mock import MagicMock, patch

from wstore.charging_engine import pricing_engine


SIMPLE_POP = {"isBundle": False, "name": "Simple POP", "description": "Simple POP description", "priceType": "one time", "price": {"value": 10.0, "unit": "EUR"}}

RECURRING_POP = {
    "isBundle": False,
    "priceType": "recurring",
    "recurringChargePeriodType": "month",
    "recurringChargePeriodLength": 1,
    "price": {"value": 15.0, "unit": "EUR"},
}

TAILORED_POP = {
    "isBundle": False,
    "priceType": "recurring-prepaid",
    "recurringChargePeriodType": "month",
    "recurringChargePeriodLength": 1,
    "price": {"value": 0.01, "unit": "EUR"},
    "prodSpecCharValueUse": [{"name": "tailored", "productSpecCharacteristicValue": [{"valueFrom": 0, "valueTo": 100}]}],
}

MULTIPLE_POP = {
    "isBundle": True,
    "bundledPopRelationship": [
        {
            "id": "urn:ngsi-ld:productOfferingPrice:2",
        },
        {
            "id": "urn:ngsi-ld:productOfferingPrice:3",
        },
        {
            "id": "urn:ngsi-ld:productOfferingPrice:4",
        },
    ],
}

FILTER_POP_1 = {
    "isBundle": False,
    "priceType": "recurring",
    "recurringChargePeriodType": "month",
    "recurringChargePeriodLength": 1,
    "price": {"value": 15.0, "unit": "EUR"},
    "prodSpecCharValueUse": [{"name": "tailored", "productSpecCharacteristicValue": [{"value": 25}]}],
}

FILTER_POP_2 = {
    "isBundle": False,
    "priceType": "recurring",
    "recurringChargePeriodType": "month",
    "recurringChargePeriodLength": 1,
    "price": {"value": 20.0, "unit": "EUR"},
    "prodSpecCharValueUse": [{"name": "tailored", "productSpecCharacteristicValue": [{"value": 30}]}],
}

MULTIPLE_POP_FILTER = {
    "isBundle": True,
    "bundledPopRelationship": [
        {
            "id": "urn:ngsi-ld:productOfferingPrice:2",
        },
        {
            "id": "urn:ngsi-ld:productOfferingPrice:3",
        },
    ],
}

USAGE_POP = {
    "isBundle": False,
    "name": "Usage POP",
    "description": "Usage POP description",
    "priceType": "usage",
    "price": {"value": 0.5, "unit": "EUR"},
    "unitOfMeasure": {"units": "ram_gb"},
    "usageSpecId": "urn:ngsi-ld:usageSpecification:1",
}

USAGE_TAILORED_POP = {
    "isBundle": False,
    "priceType": "usage",
    "price": {"value": 0.01, "unit": "EUR"},
    "unitOfMeasure": {"units": "ram_gb"},
    "usageSpecId": "urn:ngsi-ld:usageSpecification:1",
    "prodSpecCharValueUse": [{"name": "tailored", "productSpecCharacteristicValue": [{"valueFrom": 0, "valueTo": 100}]}],
}

SIMPLE_POP_2 = {"isBundle": False, "name": "Simple POP 2", "description": "Simple POP 2 description", "priceType": "one time", "price": {"value": 5.0, "unit": "EUR"}}

USAGE_POP_2 = {
    "isBundle": False,
    "name": "Usage POP 2",
    "description": "Usage POP 2 description",
    "priceType": "usage",
    "price": {"value": 0.3, "unit": "EUR"},
    "unitOfMeasure": {"units": "ram_gb"},
    "usageSpecId": "urn:ngsi-ld:usageSpecification:1",
}

MULTIPLE_POP_SAME_TYPE = {
    "isBundle": True,
    "bundledPopRelationship": [
        {
            "id": "urn:ngsi-ld:productOfferingPrice:5",
        },
        {
            "id": "urn:ngsi-ld:productOfferingPrice:6",
        },
    ],
}

MULTIPLE_POP_USAGE_SAME_TYPE = {
    "isBundle": True,
    "bundledPopRelationship": [
        {
            "id": "urn:ngsi-ld:productOfferingPrice:7",
        },
        {
            "id": "urn:ngsi-ld:productOfferingPrice:8",
        },
    ],
}

BASE_DATA = {
    "productOrderItem": [
        {
            "itemTotalPrice": [
                {
                    "productOfferingPrice": {
                        "id": "urn:ngsi-ld:productOfferingPrice:1",
                    }
                }
            ]
        }
    ],
    "relatedParty": [],
    "billingAccount": {"resolved": {}}
}

DATA_WITH_OPTIONS = {
    "productOrderItem": [
        {
            "itemTotalPrice": [
                {
                    "productOfferingPrice": {
                        "id": "urn:ngsi-ld:productOfferingPrice:1",
                    }
                }
            ],
            "product": {"productCharacteristic": [{"name": "tailored", "value": 25}]},
        }
    ],
    "relatedParty": [],
    "billingAccount": {"resolved": {}}
}

RESULT_SIMPLE_POP = [
    {
        "priceType": "one time",
        "recurringChargePeriod": "onetime",
        "price": {
            "taxRate": "20.0",
            "dutyFreeAmount": {"unit": "EUR", "value": "10.0"},
            "taxIncludedAmount": {"unit": "EUR", "value": "12.00"},
        },
        "priceAlteration": [],
    }
]

RESULT_SIMPLE_POP_DECIMAL_TAX = [
    {
        "priceType": "one time",
        "recurringChargePeriod": "onetime",
        "price": {
            "taxRate": "20.1",
            "dutyFreeAmount": {"unit": "EUR", "value": "10.0"},
            "taxIncludedAmount": {"unit": "EUR", "value": "12.01"},
        },
        "priceAlteration": [],
    }
]

RESULT_MULTIPLE_POP = [
    {
        "priceType": "one time",
        "recurringChargePeriod": "onetime",
        "price": {
            "taxRate": "0",
            "dutyFreeAmount": {"unit": "EUR", "value": "10.0"},
            "taxIncludedAmount": {"unit": "EUR", "value": "10.00"},
        },
        "priceAlteration": [],
    },
    {
        "priceType": "recurring",
        "recurringChargePeriod": "1 month",
        "price": {
            "taxRate": "0",
            "dutyFreeAmount": {"unit": "EUR", "value": "15.0"},
            "taxIncludedAmount": {"unit": "EUR", "value": "15.00"},
        },
        "priceAlteration": [],
    },
    {
        "priceType": "recurring-prepaid",
        "recurringChargePeriod": "1 month",
        "price": {
            "taxRate": "0",
            "dutyFreeAmount": {"unit": "EUR", "value": "0.25"},
            "taxIncludedAmount": {"unit": "EUR", "value": "0.25"},
        },
        "priceAlteration": [],
    },
]

RESULT_FILTER_POP = [
    {
        "priceType": "recurring",
        "recurringChargePeriod": "1 month",
        "price": {
            "taxRate": "0",
            "dutyFreeAmount": {"unit": "EUR", "value": "15.0"},
            "taxIncludedAmount": {"unit": "EUR", "value": "15.00"},
        },
        "priceAlteration": [],
    }
]

RESULT_USAGE_POP = [
    {
        "priceType": "usage",
        "recurringChargePeriod": "1 month",
        "price": {
            "taxRate": "0",
            "dutyFreeAmount": {"unit": "EUR", "value": "5.0"},
            "taxIncludedAmount": {"unit": "EUR", "value": "5.00"},
        },
        "priceAlteration": [],
    }
]

RESULT_MULTIPLE_USAGE_POP = [
    {
        "priceType": "usage",
        "recurringChargePeriod": "1 month",
        "price": {
            "taxRate": "0",
            "dutyFreeAmount": {"unit": "EUR", "value": "2.50"},
            "taxIncludedAmount": {"unit": "EUR", "value": "2.50"},
        },
        "priceAlteration": [],
    },
    {
        "priceType": "one time",
        "recurringChargePeriod": "onetime",
        "price": {
            "taxRate": "0",
            "dutyFreeAmount": {"unit": "EUR", "value": "10.0"},
            "taxIncludedAmount": {"unit": "EUR", "value": "10.00"},
        },
        "priceAlteration": [],
    },
]

# Results for preview=False (individual prices without aggregation)
# Two onetime components should return 2 separate results, not aggregated
RESULT_MULTIPLE_ONETIME_NO_PREVIEW = [
    {
        "name": "Simple POP",
        "description": "Simple POP description",
        "priceType": "one time",
        "recurringChargePeriod": "onetime",
        "price": {
            "taxRate": "20.0",
            "dutyFreeAmount": {"unit": "EUR", "value": "10.0"},
            "taxIncludedAmount": {"unit": "EUR", "value": "12.00"},
        },
        "priceAlteration": [],
    },
    {
        "name": "Simple POP 2",
        "description": "Simple POP 2 description",
        "priceType": "one time",
        "recurringChargePeriod": "onetime",
        "price": {
            "taxRate": "20.0",
            "dutyFreeAmount": {"unit": "EUR", "value": "5.0"},
            "taxIncludedAmount": {"unit": "EUR", "value": "6.00"},
        },
        "priceAlteration": [],
    },
]

# Two usage components should return 2 separate results, not aggregated
RESULT_MULTIPLE_USAGE_NO_PREVIEW = [
    {
        "name": "Usage POP",
        "description": "Usage POP description",
        "priceType": "usage",
        "recurringChargePeriod": "1 month",
        "price": {
            "taxRate": "0",
            "dutyFreeAmount": {"unit": "EUR", "value": "5.0"},
            "taxIncludedAmount": {"unit": "EUR", "value": "5.00"},
        },
        "priceAlteration": [],
    },
    {
        "name": "Usage POP 2",
        "description": "Usage POP 2 description",
        "priceType": "usage",
        "recurringChargePeriod": "1 month",
        "price": {
            "taxRate": "0",
            "dutyFreeAmount": {"unit": "EUR", "value": "3.0"},
            "taxIncludedAmount": {"unit": "EUR", "value": "3.00"},
        },
        "priceAlteration": [],
    },
]

SIMPLE_POP_NO_NAME = {"isBundle": False, "priceType": "one time", "price": {"value": 10.0, "unit": "EUR"}}

RESULT_ONETIME_NO_PREVIEW_DEFAULT_NAME = [
    {
        "name": "empty name",
        "description": "empty description",
        "priceType": "one time",
        "recurringChargePeriod": "onetime",
        "price": {
            "taxRate": "20.0",
            "dutyFreeAmount": {"unit": "EUR", "value": "10.0"},
            "taxIncludedAmount": {"unit": "EUR", "value": "12.00"},
        },
        "priceAlteration": [],
    },
]

USAGE_1 = [
    {
        "usageSpecification": {"id": "urn:ngsi-ld:usageSpecification:1"},
        "usageCharacteristic": [{"name": "ram_gb", "value": 10}],
    }
]

OFFPARTY = [
    {
        "id": "urn:ngsi-ld:organization:mocked",
        "role": "Customer",
        "href": "urn:ngsi-ld:organization:mocked",
        "@referredType": "organization",
    },
    {
        "id": "urn:ngsi-ld:organization:mocked",
        "role": "Seller",
        "href": "urn:ngsi-ld:organization:mocked",
        "@referredType": "organization",
    },
]
OFFPARTY_IND_1 = [
    {
        "id": "urn:ngsi-ld:individual:mocked",
        "role": "Customer",
        "href": "urn:ngsi-ld:individual:mocked",
        "@referredType": "organization",
    },
    {
        "id": "urn:ngsi-ld:organization:mocked",
        "role": "Seller",
        "href": "urn:ngsi-ld:organization:mocked",
        "@referredType": "organization",
    },
]
OFFPARTY_IND_2 = [
    {
        "id": "urn:ngsi-ld:individual:mocked",
        "role": "Customer",
        "href": "urn:ngsi-ld:individual:mocked",
        "@referredType": "organization",
    },
    {
        "id": "urn:ngsi-ld:individual:mocked",
        "role": "Seller",
        "href": "urn:ngsi-ld:individual:mocked",
        "@referredType": "organization",
    },
]
OFFPARTY_ONLY_SELLER = [
    {
        "id": "urn:ngsi-ld:organization:mocked",
        "role": "Seller",
        "href": "urn:ngsi-ld:organization:mocked",
        "@referredType": "organization",
    }
]
OFFPARTY_ONLY_CUSTOMER = [
    {
        "id": "urn:ngsi-ld:organization:mocked",
        "role": "Customer",
        "href": "urn:ngsi-ld:organization:mocked",
        "@referredType": "organization",
    },
]
OFFPARTY_EMPTY = []

ST_VAT = {
    "memberState": "ES",
    "type": "STANDARD",
    "rate": {"type": "DEFAULT", "value": 21.0},
    "situationOn": datetime.date(2025, 7, 1),
    "cnCodes": None,
    "cpaCodes": None,
    "category": None,
    "comment": None,
}

ST_VAT_DECIMAL = {
    "memberState": "ES",
    "type": "STANDARD",
    "rate": {"type": "DEFAULT", "value": 20.2},
    "situationOn": datetime.date(2025, 7, 1),
    "cnCodes": None,
    "cpaCodes": None,
    "category": None,
    "comment": None,
}

ST_VAT_SCND = {
    "memberState": "ES",
    "type": "STANDARD",
    "rate": {"type": "DEFAULT", "value": 7.0},
    "situationOn": datetime.date(2025, 7, 1),
    "cnCodes": None,
    "cpaCodes": None,
    "category": None,
    "comment": "VAT - Canary Islands - ",
}

RD_VAT = {
    "memberState": "ES",
    "type": "REDUCED",
    "rate": {"type": "REDUCED_RATE", "value": 10.0},
    "situationOn": datetime.date(2025, 7, 1),
    "cnCodes": None,
    "cpaCodes": None,
    "category": {"identifier": "mock id", "description": "mock description"},
    "comment": "mock comment",
}

NOW = datetime.date(2024, 1, 1)


@override_settings(
    ADMIN_ROLE="provider",
    PROVIDER_ROLE="seller",
    CUSTOMER_ROLE="customer"
)
class ChargingEngineTestCase(TestCase):
    tags = ("ordering", "billing", "pricing")
    maxDiff = None

    def _mock_simple_pop(self):
        pricing_engine.requests = MagicMock()
        pricing_engine.requests.get.return_value.json.return_value = SIMPLE_POP

    def _mock_multiple_pop(self):
        pricing_engine.requests = MagicMock()
        plan_call = MagicMock()
        plan_call.json.return_value = MULTIPLE_POP

        onetime_call = MagicMock()
        onetime_call.json.return_value = SIMPLE_POP

        recurring_call = MagicMock()
        recurring_call.json.return_value = RECURRING_POP

        tailored_call = MagicMock()
        tailored_call.json.return_value = TAILORED_POP

        pricing_engine.requests.get.side_effect = [plan_call, onetime_call, recurring_call, tailored_call]

    def _mock_multiple_filter_pop(self):
        pricing_engine.requests = MagicMock()
        plan_call = MagicMock()
        plan_call.json.return_value = MULTIPLE_POP_FILTER

        filter_call1 = MagicMock()
        filter_call1.json.return_value = FILTER_POP_1

        filter_call2 = MagicMock()
        filter_call2.json.return_value = FILTER_POP_2

        pricing_engine.requests.get.side_effect = [plan_call, filter_call1, filter_call2]

    def _mock_usage_pop(self):
        pricing_engine.requests = MagicMock()
        pricing_engine.requests.get.return_value.json.return_value = USAGE_POP

    def _mock_multiple_usage_pop(self):
        pricing_engine.requests = MagicMock()
        plan_call = MagicMock()
        plan_call.json.return_value = MULTIPLE_POP_FILTER

        usage_call1 = MagicMock()
        usage_call1.json.return_value = USAGE_TAILORED_POP

        usage_call2 = MagicMock()
        usage_call2.json.return_value = SIMPLE_POP

        pricing_engine.requests.get.side_effect = [plan_call, usage_call1, usage_call2]

    def _mock_multiple_onetime_pop(self):
        pricing_engine.requests = MagicMock()
        plan_call = MagicMock()
        plan_call.json.return_value = MULTIPLE_POP_SAME_TYPE

        onetime_call1 = MagicMock()
        onetime_call1.json.return_value = SIMPLE_POP

        onetime_call2 = MagicMock()
        onetime_call2.json.return_value = SIMPLE_POP_2

        pricing_engine.requests.get.side_effect = [plan_call, onetime_call1, onetime_call2]

    def _mock_simple_pop_no_name(self):
        pricing_engine.requests = MagicMock()
        pricing_engine.requests.get.return_value.json.return_value = SIMPLE_POP_NO_NAME

    def _mock_multiple_usage_same_type_pop(self):
        pricing_engine.requests = MagicMock()
        plan_call = MagicMock()
        plan_call.json.return_value = MULTIPLE_POP_USAGE_SAME_TYPE

        usage_call1 = MagicMock()
        usage_call1.json.return_value = USAGE_POP

        usage_call2 = MagicMock()
        usage_call2.json.return_value = USAGE_POP_2

        pricing_engine.requests.get.side_effect = [plan_call, usage_call1, usage_call2]

    @parameterized.expand(
        [
            ("single_component_no_options", BASE_DATA, _mock_simple_pop, RESULT_SIMPLE_POP, 20.0),
            (
                "single_component_no_options_decimal_tax",
                BASE_DATA,
                _mock_simple_pop,
                RESULT_SIMPLE_POP_DECIMAL_TAX,
                20.1,
            ),
            ("multiple_component_options", DATA_WITH_OPTIONS, _mock_multiple_pop, RESULT_MULTIPLE_POP, 0),
            ("multiple_component_filter", DATA_WITH_OPTIONS, _mock_multiple_filter_pop, RESULT_FILTER_POP, 0),
            ("single_component_usage", BASE_DATA, _mock_usage_pop, RESULT_USAGE_POP, 0, USAGE_1),
            (
                "multiple_component_usage_tailored",
                DATA_WITH_OPTIONS,
                _mock_multiple_usage_pop,
                RESULT_MULTIPLE_USAGE_POP,
                0,
                USAGE_1,
            ),
            ("onetime_no_preview_default_name", BASE_DATA, _mock_simple_pop_no_name, RESULT_ONETIME_NO_PREVIEW_DEFAULT_NAME, 20.0, [], False),
            ("multiple_onetime_no_preview", BASE_DATA, _mock_multiple_onetime_pop, RESULT_MULTIPLE_ONETIME_NO_PREVIEW, 20.0, [], False),
            ("multiple_usage_no_preview", BASE_DATA, _mock_multiple_usage_same_type_pop, RESULT_MULTIPLE_USAGE_NO_PREVIEW, 0, USAGE_1, False),
        ]
    )
    def test_calculate_prices(self, name, data, mock_method, expected_result, tax, usage=[], preview=True):
        mock_method(self)

        to_test = pricing_engine.PriceEngine()
        to_test._calculate_taxes = MagicMock()
        to_test._calculate_taxes.return_value = tax
        result = to_test.calculate_prices(data, usage=usage, preview=preview)

        self.assertEquals(result, expected_result)

    CUSTOMER_ROLE = "customer"
    PROVIDER_ROLE = "provider"
    ORG = "organization"
    IND = "individual"

    def build_mock_party(self, country_code, party):
        return (
            (
                [
                    {"name": "description", "value": None},
                    {"name": "website", "value": None},
                    {"name": "country", "value": country_code},
                ]
            )
            if party == "organization"
            else []
        )

    @parameterized.expand(
        [
            ("offering_party", OFFPARTY, ("ES", ORG), ("DE", ORG), "ES", "DE"),
            ("offering_party_1_individual", OFFPARTY_IND_1, (None, IND), ("DE", ORG), None, "DE"),
            ("offering_party_2_individuals", OFFPARTY_IND_2, (None, IND), ("DE", IND), None, None),
            ("offering_party_only_seller", OFFPARTY_ONLY_SELLER, (None, None), ("ES", ORG), None, "ES"),
            ("offering_party_only_customer", OFFPARTY_ONLY_CUSTOMER, ("ES", ORG), (None, None), "ES", None),
            ("offering_party_empty", OFFPARTY_EMPTY, ("ES", ORG), ("ES", ORG), None, None),
        ]
    )
    def test_get_customer_seller(self, _name, related_party, customer_call, seller_call, expected_customer, expected_provider):
        engine = pricing_engine.PriceEngine()

        # Build side effects based on party roles
        side_effects = []
        customer_id = None
        seller_id = None

        for party in related_party:
            if "role" in party and party["role"].lower() == "customer":
                customer_id = party["id"]
                side_effects.append((self.build_mock_party(*customer_call), customer_call[1]))
            elif "role" in party and party["role"].lower() == "seller":
                seller_id = party["id"]
                side_effects.append((self.build_mock_party(*seller_call), seller_call[1]))

        engine._get_party_char = MagicMock()
        engine._get_party_char.side_effect = side_effects

        result = engine._get_customer_seller(related_party)

        expected_result = (
            {"country": expected_customer,
             "type": customer_call[1] if customer_id else None,
             "id": customer_id},
            {"country": expected_provider,
             "type": seller_call[1] if seller_id else None,
             "id": seller_id}
        )

        self.assertEqual(result, expected_result)

    @parameterized.expand(
        [
            ("individual_success", "urn:ngsi-ld:individual:123", "individual", {"partyCharacteristic": []}, [], None),
            (
                "organization_success",
                "urn:ngsi-ld:organization:456",
                "organization",
                {"partyCharacteristic": [{"name": "country", "value": "FR"}]},
                [{"name": "country", "value": "FR"}],
                None,
            ),
            ("request_fails", "urn:ngsi-ld:individual:999", "individual", Exception("Request fails"), None, ValueError),
        ]
    )
    def test_get_party_char(
        self, _name, party_id, user_type, mock_response_or_exception, expected_output, expected_exception
    ):
        fake_url = f"http://mocked.com/{user_type}/{party_id}"
        engine = pricing_engine.PriceEngine()

        with patch("wstore.charging_engine.pricing_engine.get_service_url") as mock_get_service_url, patch(
            "wstore.charging_engine.pricing_engine.requests.get"
        ) as mock_requests_get:
            mock_get_service_url.return_value = fake_url

            if isinstance(mock_response_or_exception, Exception):
                mock_requests_get.side_effect = mock_response_or_exception
            else:
                mock_response = MagicMock()
                mock_response.raise_for_status.return_value = None
                mock_response.json.return_value = mock_response_or_exception
                mock_requests_get.return_value = mock_response

            if expected_exception:
                with self.assertRaises(expected_exception):
                    engine._get_party_char(party_id)
            else:
                resultado = engine._get_party_char(party_id)
                self.assertEqual(resultado, (expected_output, user_type))

            mock_get_service_url.assert_called_once_with("party", f"/{user_type}/{party_id}")
            mock_requests_get.assert_called_once_with(fake_url)

    @parameterized.expand(
        [
            (
                "same_country",
                ("ES", "ES"),
                [ST_VAT, ST_VAT_SCND, RD_VAT],
                21.0,
                {"memberStates": {"isoCode": "ES"}, "situationOn": NOW},
                None,
            ),
            ("+different_country", ("ES", "DE"), [], 0, None, None),
            ("no_country", (None, "DE"), [], 0, None, None),
            (
                "error_no_st_vat",
                ("DE", "DE"),
                [RD_VAT],
                0,
                {"memberStates": {"isoCode": "DE"}, "situationOn": NOW},
                ValueError,
            ),
        ]
    )
    def test_search_ue_taxes(
        self, name, tuple_countries, vat_results, expected_result, ret_vat_params, expected_exception
    ):
        engine = pricing_engine.PriceEngine()

        pricing_engine.datetime = MagicMock()
        pricing_engine.datetime.now.return_value.date.return_value.isoformat.return_value = NOW

        pricing_engine.Client = MagicMock()
        mockRetrieveVat = pricing_engine.Client.return_value.service.retrieveVatRates
        if not expected_exception:
            mockRetrieveVat.return_value.vatRateResults = vat_results
        else:
            mockRetrieveVat.side_effects = expected_exception

        customer_country, seller_country = tuple_countries
        if expected_exception:
            with self.assertRaises(expected_exception):
                engine._search_ue_taxes(OFFPARTY, customer_country, seller_country)
        else:
            result = engine._search_ue_taxes(OFFPARTY, customer_country, seller_country)
            if ret_vat_params:
                mockRetrieveVat.assert_called_once_with(**ret_vat_params)
            self.assertEquals(result, expected_result)

    @parameterized.expand([
        (
            "organization_individual_taxes",
            {"country": "ES", "type": "organization", "id": "org1"},
            {"country": "ES", "type": "organization", "id": "org2"},
            None,
            21.0
        ),
        (
            "individual_with_billing_address",
            {"country": None, "type": "individual", "id": "ind1"},
            {"country": "DE", "type": "organization", "id": "org1"},
            {"contact": [{"contactMedium": [{"mediumType": "PostalAddress", "characteristic": {"country": "FR"}}]}]},
            0  # Different countries
        ),
        (
            "individual_no_billing_address",
            {"country": None, "type": "individual", "id": "ind1"},
            {"country": "DE", "type": "organization", "id": "org1"},
            None,
            0  # No customer country
        )
    ])
    def test_calculate_taxes(self, name, customer_data, seller_data, billing_account, expected_result):
        engine = pricing_engine.PriceEngine()
        engine._get_customer_seller = MagicMock()
        engine._get_customer_seller.return_value = (customer_data, seller_data)

        engine._search_ue_taxes = MagicMock()
        engine._search_ue_taxes.return_value = expected_result

        result = engine._calculate_taxes(OFFPARTY, billing_account)
        self.assertEquals(result, expected_result)


class UsageAggregationTestCase(SimpleTestCase):
    def setUp(self):
        self.engine = pricing_engine.PriceEngine()
        self.engine._calculate_taxes = MagicMock(return_value=21)

    def _usage(self, value, specification_id=USAGE_POP["usageSpecId"], metric="ram_gb"):
        return {"usageSpecification": {"id": specification_id},
                "usageCharacteristic": [{"name": metric, "value": value}]}

    def test_all_daily_measurements_return_one_decimal_price(self):
        usages = [self._usage("20") for _ in range(31)]
        total = self.engine._process_usage_value(USAGE_POP, usages)
        self.assertIsInstance(total, Decimal)
        self.assertEqual(Decimal("310"), total)

    def test_specification_and_metric_both_have_to_match(self):
        usages = [self._usage("2"), self._usage("100", specification_id="other-spec"),
                  self._usage("200", metric="requests"), self._usage("4")]
        self.assertEqual(Decimal("3"), self.engine._process_usage_value(USAGE_POP, usages))

    def test_numeric_strings_keep_decimal_precision(self):
        component = {**USAGE_POP, "price": {"unit": "EUR", "value": "0.1"}}
        usages = [self._usage("0.1234567890123456789"), self._usage("0.2")]
        self.assertEqual(Decimal("0.03234567890123456789"), self.engine._process_usage_value(component, usages))

    def test_empty_zero_and_single_measurement(self):
        for usages, expected in [([], "0"), ([self._usage("0")], "0"), ([self._usage("20")], "10")]:
            with self.subTest(usages=usages):
                result = self.engine._process_usage_value(USAGE_POP, usages)
                self.assertIsInstance(result, Decimal)
                self.assertEqual(Decimal(expected), result)

    def test_aggregate_is_used_by_preview_and_individual_component_pricing(self):
        component = {**USAGE_POP, "id": "usage-price"}
        usages = [self._usage("20") for _ in range(31)]
        for preview in (True, False):
            with self.subTest(preview=preview):
                result = self.engine.calculate_prices(BASE_DATA, usage=usages, preview=preview, pop_components=[component])
                self.assertEqual(1, len(result))
                self.assertEqual("310.0", result[0]["price"]["dutyFreeAmount"]["value"])
                self.assertEqual("375.10", result[0]["price"]["taxIncludedAmount"]["value"])
                self.assertEqual("usage", result[0]["priceType"])
                self.assertEqual("1 month", result[0]["recurringChargePeriod"])
                self.assertEqual("usage-price" if not preview else None, result[0].get("priceId"))

    def test_each_specification_with_the_same_metric_gets_its_own_total(self):
        components = [{**USAGE_POP, "id": "price-1"}, {**USAGE_POP, "id": "price-2", "usageSpecId": "spec-2"}]
        usages = [self._usage("20"), self._usage("30", specification_id="spec-2"),
                  self._usage("10"), self._usage("50", specification_id="spec-2")]
        result = self.engine.calculate_prices(BASE_DATA, usage=usages, preview=False, pop_components=components)
        self.assertEqual(["price-1", "price-2"], [price["priceId"] for price in result])
        self.assertEqual(["15.0", "40.0"], [price["price"]["dutyFreeAmount"]["value"] for price in result])

    def test_tailored_multiplier_and_taxes_apply_to_aggregate(self):
        usages = [self._usage("20"), self._usage("40")]
        for preview in (True, False):
            with self.subTest(preview=preview):
                result = self.engine.calculate_prices(
                    DATA_WITH_OPTIONS, usage=usages, preview=preview, pop_components=[USAGE_TAILORED_POP],
                )
                self.assertEqual("15.00", result[0]["price"]["dutyFreeAmount"]["value"])
                self.assertEqual("18.15", result[0]["price"]["taxIncludedAmount"]["value"])
