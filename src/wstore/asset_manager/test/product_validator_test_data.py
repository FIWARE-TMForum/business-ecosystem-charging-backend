# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid

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

PRODUCT_LOCATION = "http://testlocation.org/media/resources/test_user/widget.wgt"

BASIC_PRODUCT = {
    "action": "create",
    "product": {
        "id": "2",
        "productNumber": "I42-340-DX",
        "version": "2.0",
        "lastUpdate": "2013-04-19T16:42:23-04:00",
        "name": "Basic dataset",
        "description": "An example dataset",
        "isBundle": False,
        "brand": "CoNWeT",
        "lifecycleStatus": "Active",
        "validFor": {
            "startDateTime": "2013-04-19T16:42:23-04:00",
            "endDateTime": "2013-06-19T00:00:00-04:00",
        },
        "relatedParty": [
            {
                "role": "Owner",
                "id": "test_user",
                "href": "http ://serverLocation:port/partyManagement/partyRole/1234",
            }
        ],
        "attachment": [
            {
                "id": "22",
                "href": "http://serverlocation:port/documentManagement/attachment/22",
                "type": "Picture",
                "url": "http://xxxxx",
            }
        ],
        "bundledProductSpecification": [],
        "serviceSpecification": [
            {
            "id": "id",
            "href": "id",
            "version": "1.0"
        }
            ],
        "resourceSpecification": [],
        "productSpecCharacteristic": [],
    },
}

UPGRADE_PRODUCT = {
    "action": "upgrade",
    "product": {
        "id": "2",
        "version": "2.0",
        "productSpecCharacteristic": [
            {
                "id": "42",
                "name": "Custom char",
                "description": "Custom characteristic of the product",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "productSpecCharacteristicValue": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": "Custom value",
                        "unitOfMeasure": "",
                        "valueFrom": "",
                        "valueTo": "",
                        "validFor": {
                            "startDateTime": "2013-04-19T16:42:23-04:00",
                            "endDateTime": "",
                        },
                    }
                ],
            },
            {
                "id": "42",
                "name": "media type",
                "description": "Media type of the product",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "productSpecCharacteristicValue": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": "application/x-widget",
                        "unitOfMeasure": "",
                        "valueFrom": "",
                        "valueTo": "",
                        "validFor": {
                            "startDateTime": "2013-04-19T16:42:23-04:00",
                            "endDateTime": "",
                        },
                    }
                ],
            },
            {
                "id": "34",
                "name": "Asset type",
                "description": "Type of digital asset being provided",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "productSpecCharacteristicValue": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": "Widget",
                        "unitOfMeasure": "",
                        "valueFrom": "",
                        "valueTo": "",
                        "validFor": {
                            "startDateTime": "2013-04-19T16:42:23-04:00",
                            "endDateTime": "",
                        },
                    }
                ],
            },
            {
                "id": "34",
                "name": "Location",
                "description": "URL pointing to the digital asset",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "productSpecCharacteristicValue": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": PRODUCT_LOCATION,
                        "unitOfMeasure": "",
                        "valueFrom": "",
                        "valueTo": "",
                        "validFor": {
                            "startDateTime": "2013-04-19T16:42:23-04:00",
                            "endDateTime": "",
                        },
                    }
                ],
            },
            {
                "id": "34",
                "name": "Asset",
                "description": "ID of the asset",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "productSpecCharacteristicValue": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": "61004aba5e05acc115f022f0",
                        "unitOfMeasure": "",
                        "valueFrom": "",
                        "valueTo": "",
                        "validFor": {
                            "startDateTime": "2013-04-19T16:42:23-04:00",
                            "endDateTime": "",
                        },
                    }
                ],
            },
        ],
    },
}

TERMS_PRODUCT = deepcopy(BASIC_PRODUCT)
TERMS_PRODUCT["product"]["productSpecCharacteristic"].append(
    {
        "id": "34",
        "name": "License",
        "description": "Text of the license",
        "valueType": "string",
        "configurable": False,
        "validFor": {"startDateTime": "2013-04-19T16:42:23-04:00", "endDateTime": ""},
        "productSpecCharacteristicValue": [
            {
                "valueType": "string",
                "default": True,
                "value": "license title",
                "unitOfMeasure": "",
                "valueFrom": "",
                "valueTo": "",
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
            }
        ],
    }
)

INVALID_TERMS = deepcopy(BASIC_PRODUCT)
INVALID_TERMS["product"]["productSpecCharacteristic"].append(
    {
        "id": "34",
        "name": "License",
        "description": "Text of the license",
        "valueType": "string",
        "configurable": False,
        "validFor": {"startDateTime": "2013-04-19T16:42:23-04:00", "endDateTime": ""},
        "productSpecCharacteristicValue": [
            {
                "valueType": "string",
                "default": True,
                "value": "license title",
                "unitOfMeasure": "",
                "valueFrom": "",
                "valueTo": "",
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
            },
            {
                "valueType": "string",
                "default": True,
                "value": "license title",
                "unitOfMeasure": "",
                "valueFrom": "",
                "valueTo": "",
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
            },
        ],
    }
)

MULTIPLE_TERMS = deepcopy(TERMS_PRODUCT)
MULTIPLE_TERMS["product"]["productSpecCharacteristic"].append(
    {
        "id": "34",
        "name": "License",
        "description": "Text of the license",
        "valueType": "string",
        "configurable": False,
        "validFor": {"startDateTime": "2013-04-19T16:42:23-04:00", "endDateTime": ""},
        "productSpecCharacteristicValue": [
            {
                "valueType": "string",
                "default": True,
                "value": "license title",
                "unitOfMeasure": "",
                "valueFrom": "",
                "valueTo": "",
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
            }
        ],
    }
)

INVALID_P_ACTION = {"action": "invalid", "product": {}}

INVALID_BUNDLE_CREATION = {
    "action": "create",
    "product": {
        "id": "1",
        "isBundle": True,
        "version": "1.0",
        "lifecycleStatus": "Active",
    },
}

BASIC_BUNDLE_CREATION = {
    "action": "create",
    "product": {
        "id": "1",
        "isBundle": True,
        "version": "1.0",
        "lifecycleStatus": "Active",
        "bundledProductSpecification": [{"id": "1"}, {"id": "2"}],
    },
}


NO_CHARS_PRODUCT = {
    "productNumber": "I42-340-DX",
    "version": "2.0",
    "lastUpdate": "2013-04-19T16:42:23-04:00",
    "name": "Basic dataset",
    "description": "An example dataset",
    "isBundle": False,
    "brand": "CoNWeT",
    "lifecycleStatus": "Active",
    "validFor": {
        "startDateTime": "2013-04-19T16:42:23-04:00",
        "endDateTime": "2013-06-19T00:00:00-04:00",
    },
    "relatedParty": [
        {
            "role": "Owner",
            "id": "test_user",
            "href": "http ://serverLocation:port/partyManagement/partyRole/1234",
        }
    ],
    "attachment": [
        {
            "id": "22",
            "href": "http://serverlocation:port/documentManagement/attachment/22",
            "type": "Picture",
            "url": "http://xxxxx",
        }
    ],
    "bundledProductSpecification": [],
    "serviceSpecification": [],
    "resourceSpecification": [],
}

EMPTY_CHARS_PRODUCT = {
    "productNumber": "I42-340-DX",
    "version": "2.0",
    "lastUpdate": "2013-04-19T16:42:23-04:00",
    "name": "Basic dataset",
    "description": "An example dataset",
    "isBundle": False,
    "brand": "CoNWeT",
    "lifecycleStatus": "Active",
    "validFor": {
        "startDateTime": "2013-04-19T16:42:23-04:00",
        "endDateTime": "2013-06-19T00:00:00-04:00",
    },
    "relatedParty": [
        {
            "role": "Owner",
            "id": "test_user",
            "href": "http ://serverLocation:port/partyManagement/partyRole/1234",
        }
    ],
    "attachment": [
        {
            "id": "22",
            "href": "http://serverlocation:port/documentManagement/attachment/22",
            "type": "Picture",
            "url": "http://xxxxx",
        }
    ],
    "bundledProductSpecification": [],
    "serviceSpecification": [],
    "resourceSpecification": [],
    "productSpecCharacteristic": [
        {
            "id": "42",
            "name": "Custom char",
            "description": "Custom characteristic of the product",
            "valueType": "string",
            "configurable": False,
            "validFor": {
                "startDateTime": "2013-04-19T16:42:23-04:00",
                "endDateTime": "",
            },
            "productSpecCharacteristicValue": [
                {
                    "valueType": "string",
                    "default": True,
                    "value": "Custom value",
                    "unitOfMeasure": "",
                    "valueFrom": "",
                    "valueTo": "",
                    "validFor": {
                        "startDateTime": "2013-04-19T16:42:23-04:00",
                        "endDateTime": "",
                    },
                }
            ],
        }
    ],
}

OFFER_PS_ID = "20"

BASIC_OFFERING = {
    "id": "3",
    "href": "http://catalog.com/offerin3",
    "isBundle": False,
    "name": "TestOffering",
    "version": "1.0",
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [
        {
            "name": "plan",
            "priceType": "one time",
            "price": {
                "taxIncludedAmount": {
                    "unit": "EUR",
                    "value": "1.0"
                }
            },
        }
    ],
}

OPEN_OFFERING = {
    "id": "3",
    "href": "http://catalog.com/offerin3",
    "isBundle": False,
    "name": "TestOffering",
    "version": "1.0",
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [{
        "id": "urn:priceid:1234",
        "name": "open",
        "description": "Open offering"
    }],
}

ZERO_OFFERING = {
    "id": "3",
    "href": "http://catalog.com/offerin3",
    "isBundle": False,
    "name": "TestOffering",
    "version": "1.0",
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [
        {
            "name": "plan",
            "priceType": "one time",
            "price": {
                "taxIncludedAmount": {
                    "unit": "EUR",
                    "value": "0"
                }
            },
        }
    ],
}

FREE_OFFERING = {
    "isBundle": False,
    "name": "TestOffering",
    "version": "1.0",
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
}

CUSTOM_PRICING_OFFERING = {
    "id": "3",
    "href": "http://catalog.com/offerin3",
    "isBundle": False,
    "name": "TestOffering",
    "version": "1.0",
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [
        {
            "name": "The custom pricing",
            "priceType": "custom",
            "description": "Custom pricing description"
        }
    ],
}

CUSTOM_PRICING_OFFERING_MULTIPLE = {
    "id": "3",
    "href": "http://catalog.com/offerin3",
    "isBundle": False,
    "name": "TestOffering",
    "version": "1.0",
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [
        {
            "name": "The custom pricing",
            "priceType": "custom",
            "description": "Custom pricing description"
        },
        {
            "name": "The custom pricing 2",
            "priceType": "custom",
            "description": "Custom pricing description"
        }
    ],
}

CUSTOM_MULTIPLE = {
    "id": "3",
    "href": "http://catalog.com/offerin3",
    "isBundle": False,
    "name": "TestOffering",
    "version": "1.0",
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [
        {
            "name": "The custom pricing",
            "priceType": "custom",
            "description": "Custom pricing description"
        },
        {
            "name": "plan",
            "priceType": "one time",
            "price": {
                "taxIncludedAmount": {
                    "unit": "EUR",
                    "value": "1"
                }
            },
        }
    ],
}

BUNDLE_OFFERING = {
    "isBundle": True,
    "name": "TestOffering",
    "version": "1.0",
    "productSpecification": {},
    "bundledProductOffering": [{"id": "6"}, {"id": "7"}],
}

OPEN_BUNDLE = {
    "isBundle": True,
    "name": "TestOffering",
    "version": "1.0",
    "productSpecification": {},
    "bundledProductOffering": [{"id": "6"}, {"id": "7"}],
    "productOfferingPrice": [{"id": "urn:priceid:1234", "name": "open", "description": "Open offering"}],
}

BUNDLE_MISSING_FIELD = {
    "isBundle": True,
    "name": "TestOffering",
    "version": "1.0",
    "productSpecification": {},
}

BUNDLE_MISSING_ELEMS = {
    "isBundle": True,
    "name": "TestOffering",
    "version": "1.0",
    "productSpecification": {},
    "bundledProductOffering": [{"id": "6"}],
}


MISSING_PRICETYPE = {
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [{"name": "plan", "price": {"currencyCode": "EUR"}}],
}

INVALID_PRICETYPE = {
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [{"name": "plan", "priceType": "invalid", "price": {"currencyCode": "EUR"}}],
}

MISSING_PERIOD = {
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [{
        "name": "plan",
        "priceType": "recurring",
        "price": {"currencyCode": "EUR"}
    }],
}

INVALID_PERIOD = {
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [
        {
            "name": "plan",
            "priceType": "recurring",
            "recurringChargePeriod": "invalid",
            "price": {"currencyCode": "EUR"},
        }
    ],
}

MISSING_PRICE = {
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [{"name": "plan", "priceType": "recurring", "recurringChargePeriod": "monthly"}],
}

MISSING_CURRENCY = {
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [
        {
            "name": "plan",
            "priceType": "recurring",
            "recurringChargePeriod": "monthly",
            "price": {},
        }
    ],
}

INVALID_CURRENCY = {
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [
        {
            "name": "plan",
            "priceType": "recurring",
            "recurringChargePeriod": "monthly",
            "price": {
                "taxIncludedAmount": {
                    "unit": "invalid"
                }
            },
        }
    ],
}

MISSING_NAME = {
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [{"priceType": "recurring", "recurringChargePeriod": "monthly", "price": {}}],
}

MULTIPLE_NAMES = {
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [
        {
            "name": "plan",
            "priceType": "one time",
            "price": {
                "taxIncludedAmount": {
                    "unit": "EUR",
                    "value": "1.0"
                }
            },
        },
        {
            "name": "Plan",
            "priceType": "one time",
            "price": {
                "taxIncludedAmount": {
                    "unit": "EUR",
                    "value": "1.0"
                }
            },
        },
    ],
}

OPEN_MIXED = {
    "id": "3",
    "href": "http://catalog.com/offerin3",
    "isBundle": False,
    "name": "TestOffering",
    "version": "1.0",
    "productSpecification": {"id": OFFER_PS_ID, "href": "http://catalog.com/products/20"},
    "productOfferingPrice": [
        {"id": "urn:price:1234", "name": "open", "description": "Open offering"},
        {
            "name": "single",
            "priceType": "one time",
            "price": {
                "taxIncludedAmount": {
                    "unit": "EUR",
                    "value": "1.0"
                }},
        },
    ],
}
