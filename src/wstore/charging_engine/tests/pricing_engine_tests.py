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

from django.test import TestCase

from parameterized import parameterized
from mock import MagicMock

from wstore.charging_engine import pricing_engine


SIMPLE_POP = {
    "isBundle": False,
    "priceType": "onetime",
    "price": {
        "value": 10.0,
        "unit": "EUR"
    }
}

RECURRING_POP = {
    "isBundle": False,
    "priceType": "recurring",
    "recurringChargePeriodType": "month",
    "recurringChargePeriodLength": 1,
    "price": {
        "value": 15.0,
        "unit": "EUR"
    }
}

TAILORED_POP = {
    "isBundle": False,
    "priceType": "recurring-prepaid",
    "recurringChargePeriodType": "month",
    "recurringChargePeriodLength": 1,
    "price": {
        "value": 0.01,
        "unit": "EUR"
    },
    "prodSpecCharValueUse": [{
        "name": "tailored"
    }]
}

MULTIPLE_POP = {
    "isBundle": True,
    "bundledPopRelationship": [{
        "id": "urn:ngsi-ld:productOfferingPrice:2",
    }, {
        "id": "urn:ngsi-ld:productOfferingPrice:3",
    }, {
        "id": "urn:ngsi-ld:productOfferingPrice:4",
    }]
}

FILTER_POP_1 = {
    "isBundle": False,
    "priceType": "recurring",
    "recurringChargePeriodType": "month",
    "recurringChargePeriodLength": 1,
    "price": {
        "value": 15.0,
        "unit": "EUR"
    },
    "prodSpecCharValueUse": [{
        "name": "tailored",
        "productSpecCharacteristicValue": [{
            "value": 25
        }]
    }]
}

FILTER_POP_2 = {
    "isBundle": False,
    "priceType": "recurring",
    "recurringChargePeriodType": "month",
    "recurringChargePeriodLength": 1,
    "price": {
        "value": 20.0,
        "unit": "EUR"
    },
    "prodSpecCharValueUse": [{
        "name": "tailored",
        "productSpecCharacteristicValue": [{
            "value": 30
        }]
    }]
}

MULTIPLE_POP_FILTER = {
    "isBundle": True,
    "bundledPopRelationship": [{
        "id": "urn:ngsi-ld:productOfferingPrice:2",
    }, {
        "id": "urn:ngsi-ld:productOfferingPrice:3",
    }]
}

USAGE_POP = {
    "isBundle": False,
    "priceType": "usage",
    "price": {
        "value": 0.5,
        "unit": "EUR"
    },
    "unitOfMeasure": {
        "units": "ram_gb"
    },
    "usageSpecId": "urn:ngsi-ld:usageSpecification:1"
}

USAGE_TAILORED_POP = {
    "isBundle": False,
    "priceType": "usage",
    "price": {
        "value": 0.01,
        "unit": "EUR"
    },
    "unitOfMeasure": {
        "units": "ram_gb"
    },
    "usageSpecId": "urn:ngsi-ld:usageSpecification:1",
    "prodSpecCharValueUse": [{
        "name": "tailored"
    }]
}

BASE_DATA = {
    "productOrderItem": [{
        "itemTotalPrice": [{
            "productOfferingPrice": {
                "id": "urn:ngsi-ld:productOfferingPrice:1",
            }
        }]
    }]
}

DATA_WITH_OPTIONS = {
    "productOrderItem": [{
        "itemTotalPrice": [{
            "productOfferingPrice": {
                "id": "urn:ngsi-ld:productOfferingPrice:1",
            }
        }],
        "product": {
            "productCharacteristic": [{
                "name": "tailored",
                "value": 25
            }]
        }
    }]
}

RESULT_SIMPLE_POP = [{
    "priceType": "onetime",
    "recurringChargePeriod": "onetime",
    "price": {
        "taxRate": 0,
        "dutyFreeAmount": {
            "unit": "EUR",
            "value": "10.0"
        },
        "taxIncludedAmount": {
            "unit": "EUR",
            "value": "10.0"
        }
    },
    "priceAlteration": []
}]

RESULT_MULTIPLE_POP = [{
    "priceType": "onetime",
    "recurringChargePeriod": "onetime",
    "price": {
        "taxRate": 0,
        "dutyFreeAmount": {
            "unit": "EUR",
            "value": "10.0"
        },
        "taxIncludedAmount": {
            "unit": "EUR",
            "value": "10.0"
        }
    },
    "priceAlteration": []
}, {
    "priceType": "recurring",
    "recurringChargePeriod": "1 month",
    "price": {
        "taxRate": 0,
        "dutyFreeAmount": {
            "unit": "EUR",
            "value": "15.0"
        },
        "taxIncludedAmount": {
            "unit": "EUR",
            "value": "15.0"
        }
    },
    "priceAlteration": []
}, {
    "priceType": "recurring-prepaid",
    "recurringChargePeriod": "1 month",
    "price": {
        "taxRate": 0,
        "dutyFreeAmount": {
            "unit": "EUR",
            "value": "0.25"
        },
        "taxIncludedAmount": {
            "unit": "EUR",
            "value": "0.25"
        }
    },
    "priceAlteration": []
}]

RESULT_FILTER_POP = [{
    "priceType": "recurring",
    "recurringChargePeriod": "1 month",
    "price": {
        "taxRate": 0,
        "dutyFreeAmount": {
            "unit": "EUR",
            "value": "15.0"
        },
        "taxIncludedAmount": {
            "unit": "EUR",
            "value": "15.0"
        }
    },
    "priceAlteration": []
}]

RESULT_USAGE_POP = [{
    "priceType": "usage",
    "recurringChargePeriod": "month",
    "price": {
        "taxRate": 0,
        "dutyFreeAmount": {
            "unit": "EUR",
            "value": "5.0"
        },
        "taxIncludedAmount": {
            "unit": "EUR",
            "value": "5.0"
        }
    },
    "priceAlteration": []
}]

RESULT_MULTIPLE_USAGE_POP = [{
    "priceType": "usage",
    "recurringChargePeriod": "month",
    "price": {
        "taxRate": 0,
        "dutyFreeAmount": {
            "unit": "EUR",
            "value": "2.50"
        },
        "taxIncludedAmount": {
            "unit": "EUR",
            "value": "2.50"
        }
    },
    "priceAlteration": []
}, {
    "priceType": "onetime",
    "recurringChargePeriod": "onetime",
    "price": {
        "taxRate": 0,
        "dutyFreeAmount": {
            "unit": "EUR",
            "value": "10.0"
        },
        "taxIncludedAmount": {
            "unit": "EUR",
            "value": "10.0"
        }
    },
    "priceAlteration": []
}]

USAGE_1 = [{
    "usageSpecification": {
        "id": "urn:ngsi-ld:usageSpecification:1"
    },
    "usageCharacteristic": [{
        "name": "ram_gb",
        "value": 10
    }]
}]

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

        pricing_engine.requests.get.side_effect = [
            plan_call,
            onetime_call,
            recurring_call,
            tailored_call
        ]

    def _mock_multiple_filter_pop(self):
        pricing_engine.requests = MagicMock()
        plan_call = MagicMock()
        plan_call.json.return_value = MULTIPLE_POP_FILTER

        filter_call1 = MagicMock()
        filter_call1.json.return_value = FILTER_POP_1

        filter_call2 = MagicMock()
        filter_call2.json.return_value = FILTER_POP_2

        pricing_engine.requests.get.side_effect = [
            plan_call,
            filter_call1,
            filter_call2
        ]

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

        pricing_engine.requests.get.side_effect = [
            plan_call,
            usage_call1,
            usage_call2
        ]

    @parameterized.expand([
        ('single_component_no_options', BASE_DATA, _mock_simple_pop, RESULT_SIMPLE_POP),
        ('multiple_component_options', DATA_WITH_OPTIONS, _mock_multiple_pop, RESULT_MULTIPLE_POP),
        ('multiple_component_filter', DATA_WITH_OPTIONS, _mock_multiple_filter_pop, RESULT_FILTER_POP),
        ('single_component_usage', BASE_DATA, _mock_usage_pop, RESULT_USAGE_POP, USAGE_1),
        ('multiple_component_usage_tailored', DATA_WITH_OPTIONS, _mock_multiple_usage_pop, RESULT_MULTIPLE_USAGE_POP, USAGE_1)
    ])
    def test_calculate_prices(self, name, data, mock_method, expected_result, usage=[]):

        mock_method(self)

        to_test = pricing_engine.PriceEngine()
        result = to_test.calculate_prices(data, usage=usage)

        self.assertEquals(result, expected_result)
