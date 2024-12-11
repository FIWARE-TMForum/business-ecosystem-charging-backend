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

SERVICE_LOCATION = "http://testlocation.org/media/resources/test_user/widget.wgt"

NO_ID_SERVICE = {
    "action": "create",
    "service": {
        "id": "2",
        "version": "1.0",
        "lastUpdate": "2013-04-19T16:42:23-04:00",
        "name": "Basic dataset",
        "description": "An example dataset",
        "isBundle": False,
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
        "resourceSpecification": [],
        "specCharacteristic": [
            {
                "id": "42",
                "name": "Custom char",
                "description": "Custom characteristic of the service",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "characteristicValueSpecification": [
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
                "description": "Media type of the service",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": SERVICE_LOCATION,
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

BASIC_SERVICE = deepcopy(NO_ID_SERVICE)
BASIC_SERVICE["service"]["specCharacteristic"].append(
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
                "characteristicValueSpecification": [
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
            })

UPGRADE_SERVICE = {
    "action": "upgrade",
    "service": {
        "id": "2",
        "version": "2.0",
        "specCharacteristic": [
            {
                "id": "42",
                "name": "Custom char",
                "description": "Custom characteristic of the service",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "characteristicValueSpecification": [
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
                "description": "Media type of the service",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": SERVICE_LOCATION,
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
                "characteristicValueSpecification": [
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

UPGRADE_SERVICE_INV_VERSION = deepcopy(UPGRADE_SERVICE)
UPGRADE_SERVICE_INV_VERSION["service"]["version"] = "inv"

TERMS_SERVICE = deepcopy(NO_ID_SERVICE)
TERMS_SERVICE["service"]["specCharacteristic"].append(
    {
        "id": "34",
        "name": "License",
        "description": "Text of the license",
        "valueType": "string",
        "configurable": False,
        "validFor": {"startDateTime": "2013-04-19T16:42:23-04:00", "endDateTime": ""},
        "characteristicValueSpecification": [
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

INVALID_TERMS = deepcopy(NO_ID_SERVICE)
INVALID_TERMS["service"]["specCharacteristic"].append(
    {
        "id": "34",
        "name": "License",
        "description": "Text of the license",
        "valueType": "string",
        "configurable": False,
        "validFor": {"startDateTime": "2013-04-19T16:42:23-04:00", "endDateTime": ""},
        "characteristicValueSpecification": [
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

MULTIPLE_TERMS = deepcopy(TERMS_SERVICE)
MULTIPLE_TERMS["service"]["specCharacteristic"].append(
    {
        "id": "34",
        "name": "License",
        "description": "Text of the license",
        "valueType": "string",
        "configurable": False,
        "validFor": {"startDateTime": "2013-04-19T16:42:23-04:00", "endDateTime": ""},
        "characteristicValueSpecification": [
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

INVALID_ACTION = {"action": "invalid", "service": {}}

MISSING_CHAR = {"action": "create", "service": {}}

MISSING_MEDIA = {
    "action": "create",
    "service": {
        "specCharacteristic": [
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
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": SERVICE_LOCATION,
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
                "characteristicValueSpecification": [
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
        ]
    },
}

MISSING_TYPE = {
    "action": "create",
    "service": {
        "specCharacteristic": [
            {
                "id": "42",
                "name": "media type",
                "description": "Media type of the service",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "characteristicValueSpecification": [
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
                "name": "Location",
                "description": "URL pointing to the digital asset",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "characteristicValueSpecification": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": SERVICE_LOCATION,
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
                "characteristicValueSpecification": [
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
        ]
    },
}

MISSING_LOCATION = {
    "action": "create",
    "service": {
        "specCharacteristic": [
            {
                "id": "42",
                "name": "media type",
                "description": "Media type of the service",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
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
                "name": "Asset",
                "description": "ID of the asset",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "characteristicValueSpecification": [
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
        ]
    },
}

MISSING_ASSET_ID = {
    "action": "create",
    "service": {
        "specCharacteristic": [
            {
                "id": "42",
                "name": "media type",
                "description": "Media type of the service",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": SERVICE_LOCATION,
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
        ]
    },
}

MULTIPLE_LOCATION = {
    "action": "create",
    "service": {
        "specCharacteristic": [
            {
                "id": "42",
                "name": "media type",
                "description": "Media type of the service",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": SERVICE_LOCATION,
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
                "characteristicValueSpecification": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": SERVICE_LOCATION,
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
        ]
    },
}

MULTIPLE_VALUES = {
    "action": "create",
    "service": {
        "specCharacteristic": [
            {
                "id": "42",
                "name": "media type",
                "description": "Media type of the service",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": SERVICE_LOCATION,
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
                        "default": False,
                        "value": SERVICE_LOCATION,
                        "unitOfMeasure": "",
                        "valueFrom": "",
                        "valueTo": "",
                        "validFor": {
                            "startDateTime": "2013-04-19T16:42:23-04:00",
                            "endDateTime": "",
                        },
                    },
                ],
            },
        ]
    },
}

INVALID_LOCATION = {
    "action": "create",
    "service": {
        "isBundle": False,
        "specCharacteristic": [
            {
                "id": "42",
                "name": "media type",
                "description": "Media type of the service",
                "valueType": "string",
                "configurable": False,
                "validFor": {
                    "startDateTime": "2013-04-19T16:42:23-04:00",
                    "endDateTime": "",
                },
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
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
                "characteristicValueSpecification": [
                    {
                        "valueType": "string",
                        "default": True,
                        "value": "invalid location",
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
                "characteristicValueSpecification": [
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

BUNDLE_CREATION = {
    "action": "create",
    "service": {
        "id": "1",
        "isBundle": True,
        "version": "1.0",
        "lifecycleStatus": "Active"
    },
}


NO_CHARS_SERVICE = {
    "version": "1.0",
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
    "resourceSpecification": []
}

EMPTY_CHARS_SERVICE = {

    "version": "1.0",
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
    "resourceSpecification": [],
    "specCharacteristic": [
        {
            "id": "42",
            "name": "Custom char",
            "description": "Custom characteristic of the service",
            "valueType": "string",
            "configurable": False,
            "validFor": {
                "startDateTime": "2013-04-19T16:42:23-04:00",
                "endDateTime": "",
            },
            "characteristicValueSpecification": [
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


