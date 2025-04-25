# -*- coding: utf-8 -*-

# Copyright (c) 2015 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2024 Future Internet Consulting and Development Solutions S.L.

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

from copy import deepcopy

BILLING_ACCOUNT_HREF = "http://serverlocation:port/billingManagement/billingAccount/1789"

OFFERING = {
    "id": "5",
    "href": "5",
    "name": "Example offering",
    "version": "1.0",
    "description": "Example offering description",
    "productSpecification": {"href": "http://producturl.com/"},
    "serviceCandidate": {"id": "productClass"},
    "productOfferingPrice": [{
        "id": "urn:ProductOfferingPrice:1",
        "href": "urn:ProductOfferingPrice:1"
    }],
    "productOfferingTerm": [{
        "name": "Terms and conditions",
        "description": "Terms and conditions"
    },
    {
        "name": "procurement",
        "description": "automatic"
    }]
}


OFFERING_NO_TERMS = deepcopy(OFFERING)
OFFERING_NO_TERMS["productOfferingTerm"] = [{
    "name": "procurement",
    "description": "automatic"
}]

OFFERING_NO_PRICING = deepcopy(OFFERING)
OFFERING_NO_PRICING["productOfferingPrice"] = []


PRODUCT = {
    "id": "5",
    "relatedParty": [
        {"id": "test_user", "role": "Owner"},
        {"id": "test_user2", "role": "Partner"},
    ],
}

BILLING_ACCOUNT = {
    "id": "1789",
    "contact": [{
        "contactMedium": [
        {
            "mediumType": "PostalAddress",
            "characteristic": {
                "street1": "Campus de Montegancedo",
                "street2": "s/n",
                "postCode": "28660",
                "city": "Madrid",
                "stateOrProvince": "Madrid",
                "country": "Spain",
            }
        }
    ]
    }]
}

BASIC_ORDER = {
    "id": "12",
    "state": "Acknowledged",
    "description": "",
    "billingAccount": {"id": "1789", "href": BILLING_ACCOUNT_HREF},
    "productOrderItem": [{
        "id": "1",
        "action": "add",
        "productOffering": {
            "id": "urn:ProductOffering:20",
            "href": "urn:ProductOffering:20",
        },
        "itemTotalPrice": [{
            "productOfferingPrice": {
                "id": "urn:ProductOfferingPrice:1",
                "href": "urn:ProductOfferingPrice:1"
            }
        }],
        "product": {}
    }]
}


BASIC_PRICING = {
    "id": "urn:ProductOfferingPrice:1",
    "href": "urn:ProductOfferingPrice:1",
    "priceType": "one time",
    "price": {
        "value": "10.00",
        "unit": "EUR",
    },
    "name": "One Time",
}


CUSTOM_PRICING = {
    "id": "urn:ProductOfferingPrice:1",
    "href": "urn:ProductOfferingPrice:1",
    "priceType": "custom",
    "name": "Custom price",
    "description": "A custom price"
}


RECURRING_PRICING = {
    "id": "urn:ProductOfferingPrice:1",
    "href": "urn:ProductOfferingPrice:1",
    "priceType": "recurring",
    "price": {
        "value": "10.00",
        "unit": "EUR"
    },
    "recurringChargePeriodType": "monthly",
    "name": "Recurring Monthly Charge",
    "description": "A monthly recurring payment",
}

USAGE_PRICING = {
    "id": "urn:ProductOfferingPrice:1",
    "href": "urn:ProductOfferingPrice:1",
    "priceType": "Usage",
    "unitOfMeasure": {
        "units": "megabyte"
    },
    "price": {
        "value": "10.00",
        "unit": "EUR"
    },
    "name": "Recurring Monthly Charge",
    "description": "A monthly recurring payment",
    "validFor": {
        "startDateTime": "2013-04-19T20:42:23.000+0000",
        "endDateTime": "2013-06-19T04:00:00.000+0000",
    }
}

FREE_ORDER = {
    "id": "12",
    "state": "Acknowledged",
    "billingAccount": {"id": "1789", "href": BILLING_ACCOUNT_HREF},
    "productOrderItem": [
        {
            "id": "1",
            "action": "add",
            "productOffering": {
                "id": "20",
                "href": "20",
            },
            "product": {},
        }
    ],
}

NOPRODUCT_ORDER = {
    "id": "12",
    "state": "Acknowledged",
    "billingAccount": {"id": "1789", "href": BILLING_ACCOUNT_HREF},
    "productOrderItem": [
        {
            "id": "1",
            "action": "add",
            "productOffering": {
                "id": "20",
                "href": "20",
            },
        }
    ],
}

DISCOUNT_PRICING = {
    "priceType": "Usage",
    "unitOfMeasure": "megabyte",
    "price": {
        "taxIncludedAmount": "12.00",
        "dutyFreeAmount": "10.00",
        "taxRate": "20.00",
        "currencyCode": "EUR",
        "percentage": 0,
    },
    "recurringChargePeriod": "",
    "name": "Recurring Monthly Charge",
    "description": "A monthly recurring payment",
    "validFor": {
        "startDateTime": "2013-04-19T20:42:23.000+0000",
        "endDateTime": "2013-06-19T04:00:00.000+0000",
    },
    "productOfferPriceAlteration": {
        "name": "Shipping Discount",
        "description": "One time shipping discount",
        "validFor": {"startDateTime": "2013-04-19T16:42:23.0Z"},
        "priceType": "one time",
        "unitOfMeasure": "",
        "price": {"percentage": 50},
        "recurringChargePeriod": "",
        "priceCondition": "",
    },
}

RECURRING_FEE_PRICING = {
    "priceType": "Usage",
    "unitOfMeasure": "megabyte",
    "price": {
        "taxIncludedAmount": "12.00",
        "dutyFreeAmount": "10.00",
        "taxRate": "20.00",
        "currencyCode": "EUR",
        "percentage": 0,
    },
    "recurringChargePeriod": "",
    "name": "Recurring Monthly Charge",
    "description": "A monthly recurring payment",
    "validFor": {
        "startDateTime": "2013-04-19T20:42:23.000+0000",
        "endDateTime": "2013-06-19T04:00:00.000+0000",
    },
    "productOfferPriceAlteration": {
        "name": "Recurring Fee",
        "description": "A fixed fee added in every charge",
        "validFor": {"startDateTime": "2013-04-19T16:42:23.0Z"},
        "priceType": "recurring",
        "unitOfMeasure": "",
        "price": {
            "taxIncludedAmount": "1.00",
            "dutyFreeAmount": "0.80",
            "taxRate": "20.00",
            "currencyCode": "EUR",
            "percentage": 0,
        },
        "recurringChargePeriod": "",
        "priceCondition": "gt 300.00",
    },
}

DOUBLE_PRICE_PRICING = {
    "priceType": "Usage",
    "unitOfMeasure": "megabyte",
    "price": {
        "taxIncludedAmount": "12.00",
        "dutyFreeAmount": "10.00",
        "taxRate": "20.00",
        "currencyCode": "EUR",
        "percentage": 0,
    },
    "recurringChargePeriod": "",
    "name": "Recurring Monthly Charge",
    "description": "A monthly recurring payment",
    "validFor": {
        "startDateTime": "2013-04-19T20:42:23.000+0000",
        "endDateTime": "2013-06-19T04:00:00.000+0000",
    },
    "productOfferPriceAlteration": {
        "name": "Initial fee",
        "description": "An initial fee for the charge",
        "validFor": {"startDateTime": "2013-04-19T16:42:23.0Z"},
        "priceType": "one time",
        "unitOfMeasure": "",
        "price": {
            "taxIncludedAmount": "8.00",
            "dutyFreeAmount": "6.00",
            "taxRate": "20.00",
            "currencyCode": "EUR",
            "percentage": 0,
        },
        "recurringChargePeriod": "",
    },
}

DOUBLE_USAGE_PRICING = {
    "priceType": "Usage",
    "unitOfMeasure": "megabyte",
    "price": {
        "taxIncludedAmount": "12.00",
        "dutyFreeAmount": "10.00",
        "taxRate": "20.00",
        "currencyCode": "EUR",
        "percentage": 0,
    },
    "recurringChargePeriod": "",
    "name": "Recurring Monthly Charge",
    "description": "A monthly recurring payment",
    "validFor": {
        "startDateTime": "2013-04-19T20:42:23.000+0000",
        "endDateTime": "2013-06-19T04:00:00.000+0000",
    },
    "productOfferPriceAlteration": {
        "name": "Initial fee",
        "description": "An initial fee for the charge",
        "validFor": {"startDateTime": "2013-04-19T16:42:23.0Z"},
        "priceType": "usage",
        "unitOfMeasure": "second",
        "price": {
            "taxIncludedAmount": "8.00",
            "dutyFreeAmount": "6.00",
            "taxRate": "20.00",
            "currencyCode": "EUR",
            "percentage": 0,
        },
        "recurringChargePeriod": "",
    },
}

USAGE_ALTERATION_PRICING = {
    "priceType": "Usage",
    "unitOfMeasure": "megabyte",
    "price": {
        "taxIncludedAmount": "12.00",
        "dutyFreeAmount": "10.00",
        "taxRate": "20.00",
        "currencyCode": "EUR",
        "percentage": 0,
    },
    "recurringChargePeriod": "",
    "name": "Recurring Monthly Charge",
    "description": "A monthly recurring payment",
    "validFor": {
        "startDateTime": "2013-04-19T20:42:23.000+0000",
        "endDateTime": "2013-06-19T04:00:00.000+0000",
    },
    "productOfferPriceAlteration": {
        "name": "Initial fee",
        "priceType": "usage",
        "unitOfMeasure": "",
        "price": {
            "taxIncludedAmount": "8.00",
            "dutyFreeAmount": "6.00",
            "taxRate": "20.00",
            "currencyCode": "EUR",
            "percentage": 0,
        },
        "recurringChargePeriod": "",
        "priceCondition": "gt 300",
    },
}

INV_CONDITION_PRICING = {
    "priceType": "Usage",
    "unitOfMeasure": "megabyte",
    "price": {
        "taxIncludedAmount": "12.00",
        "dutyFreeAmount": "10.00",
        "taxRate": "20.00",
        "currencyCode": "EUR",
        "percentage": 0,
    },
    "recurringChargePeriod": "",
    "name": "Recurring Monthly Charge",
    "description": "A monthly recurring payment",
    "validFor": {
        "startDateTime": "2013-04-19T20:42:23.000+0000",
        "endDateTime": "2013-06-19T04:00:00.000+0000",
    },
    "productOfferPriceAlteration": {
        "name": "Initial fee",
        "priceType": "recurring",
        "unitOfMeasure": "",
        "price": {"percentage": 20},
        "recurringChargePeriod": "",
        "priceCondition": "gty 300",
    },
}

INV_ALTERATION_PRICING = {
    "priceType": "Usage",
    "unitOfMeasure": "megabyte",
    "price": {
        "taxIncludedAmount": "12.00",
        "dutyFreeAmount": "10.00",
        "taxRate": "20.00",
        "currencyCode": "EUR",
        "percentage": 0,
    },
    "recurringChargePeriod": "",
    "name": "Recurring Monthly Charge",
    "description": "A monthly recurring payment",
    "validFor": {
        "startDateTime": "2013-04-19T20:42:23.000+0000",
        "endDateTime": "2013-06-19T04:00:00.000+0000",
    },
    "productOfferPriceAlteration": {"name": "an alteration"},
}

INVALID_STATE_ORDER = {"id": "12", "state": "inProgress"}

INVALID_MODEL_PRICING = {
    "id": "urn:ProductOfferingPrice:1",
    "href": "urn:ProductOfferingPrice:1",
    "priceType": "Invalid",
    "unitOfMeasure": {
        "units": "megabyte"
    },
    "price": {
        "value": "10.00",
        "unit": "EUR"
    },
    "name": "Recurring Monthly Charge",
    "description": "A monthly recurring payment",
    "validFor": {
        "startDateTime": "2013-04-19T20:42:23.000+0000",
        "endDateTime": "2013-06-19T04:00:00.000+0000",
    }
}

MISSING_BILLING_ORDER = {
    "id": "12",
    "state": "Acknowledged",
    "productOrderItem": [
        {
            "id": "1",
            "action": "add",
            "productOffering": {
                "id": "20",
                "href": "20",
            },
            "product": {},
        }
    ],
}