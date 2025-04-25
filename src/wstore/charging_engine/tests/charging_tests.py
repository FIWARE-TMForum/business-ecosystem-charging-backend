# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

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


import json
from copy import deepcopy
from datetime import datetime
from importlib import reload

from bson.objectid import ObjectId
from django.test import TestCase
from django.test.client import RequestFactory
from mock import MagicMock, call
from parameterized import parameterized

import wstore.store_commons.utils.http
from wstore.charging_engine import charging_engine, views
from wstore.charging_engine.payment_client import payment_client as payment_client_module
from wstore.ordering.errors import OrderingError
from wstore.store_commons.utils.testing import decorator_mock


def mock_payment_client(self, module):
    # Mock payment client
    payment_client_class_mock = MagicMock()
    self._payment_class = MagicMock(name="PaymentClass", __name__="PaymentClass")
    self._payment_inst = MagicMock(name="PaymentInstance", __name__="PaymentInstance")
    module.PaymentClient = payment_client_class_mock

    self._payment_class.return_value = self._payment_inst
    payment_client_class_mock.get_payment_client_class.return_value = self._payment_class
    charging_engine.PaymentClient = payment_client_class_mock


INVOICE_PATH = "/media/invoice/invoice1.pdf"


# class ChargingEngineTestCase(TestCase):
#     tags = ("ordering", "charging-engine")
#     _paypal_url = "http://paypalurl.com"

#     def setUp(self):
#         # Mock order
#         self._order = MagicMock()
#         self._order.owner_organization.acquired_offerings = []

#         # Mock payment client
#         mock_payment_client(self, charging_engine)
#         self._payment_inst.get_checkout_url.return_value = self._paypal_url

#         # Mock threading
#         charging_engine.threading = MagicMock()

#         self._thread = MagicMock()
#         charging_engine.threading.Timer.return_value = self._thread

#         # Mock invoice builder
#         charging_engine.InvoiceBuilder = MagicMock()
#         charging_engine.InvoiceBuilder.return_value.generate_invoice.return_value = INVOICE_PATH

#         # Mock CDR Manager
#         charging_engine.CDRManager = MagicMock()

#         # Mock datetime
#         now = datetime(2016, 1, 20, 13, 12, 39)
#         charging_engine.datetime = MagicMock()
#         charging_engine.datetime.utcnow.return_value = now

#         charging_engine.NotificationsHandler = MagicMock()

#         self._charge = MagicMock()
#         charging_engine.Charge = MagicMock()
#         charging_engine.Charge.return_value = self._charge

#         charging_engine.BillingClient = MagicMock()
#         charging_engine.Offering = MagicMock()

#     def _get_single_payment(self):
#         return {
#             "general_currency": "EUR",
#             "single_payment": [
#                 {
#                     "value": "12",
#                     "unit": "one time",
#                     "tax_rate": "20.00",
#                     "duty_free": "10.00",
#                 }
#             ],
#         }

#     def _get_subscription(self, renovation_date=None):
#         pricing = {
#             "general_currency": "EUR",
#             "subscription": [
#                 {
#                     "value": "12.00",
#                     "unit": "month",
#                     "tax_rate": "20.00",
#                     "duty_free": "10.00",
#                 }
#             ],
#         }

#         if renovation_date is not None:
#             pricing["subscription"][0]["renovation_date"] = renovation_date

#         return pricing

#     def _get_pay_use(self):
#         return {
#             "general_currency": "EUR",
#             "pay_per_use": [
#                 {
#                     "value": "10.00",
#                     "unit": "call",
#                     "tax_rate": "20.00",
#                     "duty_free": "8.33",
#                 }
#             ],
#         }

#     def _mock_contract(self, info):
#         contract = MagicMock()
#         contract.item_id = info["item_id"]
#         contract.charges = []
#         contract.pricing_model = info["pricing"]
#         contract.product_id = info["product_id"]
#         contract.offering = info["offering_pk"]

#         offering = MagicMock(description=info["description"], pk=info["offering_pk"])

#         return contract, offering

#     def _set_initial_contracts(self):
#         contract1, offering1 = self._mock_contract(
#             {
#                 "description": "Offering 1 description",
#                 "offering_pk": "61004aba5e05acc115f022f0",
#                 "item_id": "1",
#                 "pricing": self._get_single_payment(),
#                 "product_id": "product1",
#             }
#         )
#         contract2, offering2 = self._mock_contract(
#             {
#                 "description": "Offering 2 description",
#                 "offering_pk": "61004aba5e05acc115f022f1",
#                 "item_id": "2",
#                 "pricing": self._get_subscription(),
#                 "product_id": "product2",
#             }
#         )
#         contract3, offering3 = self._mock_contract(
#             {
#                 "description": "Offering 3 description",
#                 "offering_pk": "61004aba5e05acc115f022f2",
#                 "item_id": "3",
#                 "pricing": {},
#                 "product_id": "product3",
#             }
#         )

#         contracts = [contract1, contract2, contract3]
#         self._order.get_contracts.return_value = contracts
#         # Mock get contracts
#         self._order.get_item_contract.side_effect = contracts

#         charging_engine.Offering = MagicMock()
#         charging_engine.Offering.objects.get.side_effect = [
#             offering1,
#             offering2,
#             offering3,
#         ]

#         return (
#             [
#                 {
#                     "price": "12.00",
#                     "duty_free": "10.00",
#                     "description": "Offering 1 description",
#                     "currency": "EUR",
#                     "related_model": {
#                         "single_payment": [
#                             {
#                                 "value": "12",
#                                 "unit": "one time",
#                                 "tax_rate": "20.00",
#                                 "duty_free": "10.00",
#                             }
#                         ]
#                     },
#                     "item": "1",
#                 },
#                 {
#                     "price": "12.00",
#                     "duty_free": "10.00",
#                     "description": "Offering 2 description",
#                     "currency": "EUR",
#                     "related_model": {
#                         "subscription": [
#                             {
#                                 "value": "12.00",
#                                 "unit": "month",
#                                 "tax_rate": "20.00",
#                                 "duty_free": "10.00",
#                             }
#                         ]
#                     },
#                     "item": "2",
#                 },
#             ],
#             [contract3],
#         )

#     def _set_renovation_contracts(self):
#         contract1, offering1 = self._mock_contract(
#             {
#                 "description": "Offering 1 description",
#                 "offering_pk": "61004aba5e05acc115f022f0",
#                 "item_id": "1",
#                 "pricing": self._get_single_payment(),
#                 "product_id": "product1",
#             }
#         )
#         contract2, offering2 = self._mock_contract(
#             {
#                 "description": "Offering 2 description",
#                 "offering_pk": "61004aba5e05acc115f022f1",
#                 "item_id": "2",
#                 "pricing": self._get_subscription(datetime(2015, 10, 1, 10, 10)),
#                 "product_id": "product2",
#             }
#         )
#         contract3, offering3 = self._mock_contract(
#             {
#                 "description": "Offering 3 description",
#                 "offering_pk": "61004aba5e05acc115f022f2",
#                 "item_id": "3",
#                 "pricing": self._get_subscription(datetime.utcnow()),
#                 "product_id": "product3",
#             }
#         )

#         self._order.get_contracts.return_value = [contract1, contract2, contract3]
#         # Mock get contracts
#         self._order.get_item_contract.side_effect = [contract2]

#         charging_engine.Offering = MagicMock()
#         charging_engine.Offering.objects.get.side_effect = [offering2, offering3]

#         return (
#             [
#                 {
#                     "price": "12.00",
#                     "duty_free": "10.00",
#                     "description": "Offering 2 description",
#                     "currency": "EUR",
#                     "related_model": {
#                         "subscription": [
#                             {
#                                 "value": "12.00",
#                                 "unit": "month",
#                                 "tax_rate": "20.00",
#                                 "duty_free": "10.00",
#                                 "renovation_date": datetime(2015, 10, 1, 10, 10),
#                             }
#                         ]
#                     },
#                     "item": "2",
#                 }
#             ],
#             [],
#         )

#     def _set_subscription_contract(self):
#         contract, offering = self._mock_contract(
#             {
#                 "description": "Offering 3 description",
#                 "offering_pk": "61004aba5e05acc115f022f2",
#                 "item_id": "3",
#                 "pricing": self._get_subscription(datetime.utcnow()),
#                 "product_id": "product1",
#             }
#         )

#         self._order.get_contracts.return_value = [contract]

#         charging_engine.Offering = MagicMock()
#         charging_engine.Offering.objects.get.return_value = offering
#         return ([], [])

#     def _set_free_contract(self):
#         contract = MagicMock()
#         contract.offering.description = "Offering description"
#         contract.item_id = "1"
#         contract.pricing_model = {}

#         self._order.get_contracts.return_value = [contract]

#     def _set_usage_contracts(self):
#         contract, offering = self._mock_contract(
#             {
#                 "description": "Offering description",
#                 "offering_pk": "61004aba5e05acc115f022f0",
#                 "item_id": "1",
#                 "pricing": self._get_pay_use(),
#                 "product_id": "product1",
#             }
#         )

#         charging_engine.Offering = MagicMock()
#         charging_engine.Offering.objects.get.return_value = offering

#         # Mock usage client
#         charging_engine.UsageClient = MagicMock()
#         charging_engine.UsageClient().get_customer_usage.return_value = [
#             {"id": "1"},
#             {"id": "2"},
#             {"id": "3"},
#         ]

#         charging_engine.SDRManager = MagicMock()
#         charging_engine.SDRManager().get_sdr_values.side_effect = [
#             {"unit": "call", "value": "10"},
#             {"unit": "invocation", "value": "1"},
#             {"unit": "call", "value": "10"},
#         ]
#         contract.applied_sdrs = []
#         self._order.get_contracts.return_value = [contract]
#         self._order.date = datetime(2016, 1, 20, 13, 12, 39)
#         self._order.get_item_contract.side_effect = [contract]

#         return (
#             [
#                 {
#                     "price": "200.00",
#                     "duty_free": "166.60",
#                     "description": "Offering description",
#                     "currency": "EUR",
#                     "related_model": {
#                         "pay_per_use": [
#                             {
#                                 "value": "10.00",
#                                 "unit": "call",
#                                 "tax_rate": "20.00",
#                                 "duty_free": "8.33",
#                             }
#                         ]
#                     },
#                     "item": "1",
#                     "applied_accounting": [
#                         {
#                             "model": {
#                                 "value": "10.00",
#                                 "unit": "call",
#                                 "tax_rate": "20.00",
#                                 "duty_free": "8.33",
#                             },
#                             "accounting": [
#                                 {
#                                     "usage_id": "1",
#                                     "price": "100.00",
#                                     "duty_free": "83.30",
#                                     "value": "10",
#                                 },
#                                 {
#                                     "usage_id": "3",
#                                     "price": "100.00",
#                                     "duty_free": "83.30",
#                                     "value": "10",
#                                 },
#                             ],
#                             "price": "200.00",
#                             "duty_free": "166.60",
#                         }
#                     ],
#                 }
#             ],
#             [],
#         )

#     def _set_usage_alteration_contracts(self):
#         contract1, offering1 = self._mock_contract(
#             {
#                 "description": "Offering description",
#                 "offering_pk": "61004aba5e05acc115f022f0",
#                 "item_id": "1",
#                 "pricing": self._get_pay_use(),
#                 "product_id": "product1",
#             }
#         )

#         contract2, offering2 = self._mock_contract(
#             {
#                 "description": "Offering description",
#                 "offering_pk": "61004aba5e05acc115f022f1",
#                 "item_id": "2",
#                 "pricing": {
#                     "general_currency": "EUR",
#                     "pay_per_use": [
#                         {
#                             "value": "10.00",
#                             "unit": "callmin",
#                             "tax_rate": "20.00",
#                             "duty_free": "8.33",
#                         }
#                     ],
#                     "alteration": {
#                         "type": "fee",
#                         "period": "recurring",
#                         "value": {"value": "20.00", "duty_free": "20.00"},
#                         "condition": {"operation": "lt", "value": "20.00"},
#                     },
#                 },
#                 "product_id": "product2",
#             }
#         )

#         charging_engine.Offering = MagicMock()
#         charging_engine.Offering.objects.get.side_effect = [offering1, offering2]

#         # Mock usage client
#         charging_engine.UsageClient = MagicMock()
#         charging_engine.UsageClient().get_customer_usage.return_value = [
#             {"id": "1"},
#             {"id": "2"},
#             {"id": "3"},
#             {"id": "4"},
#         ]

#         charging_engine.SDRManager = MagicMock()
#         charging_engine.SDRManager().get_sdr_values.side_effect = [
#             {"unit": "call", "value": "10"},
#             {"unit": "invocation", "value": "1"},
#             {"unit": "callmin", "value": "1"},
#             {"unit": "call", "value": "10"},
#             {"unit": "call", "value": "10"},
#             {"unit": "invocation", "value": "1"},
#             {"unit": "callmin", "value": "1"},
#             {"unit": "call", "value": "10"},
#         ]
#         contract1.applied_sdrs = []
#         contract2.applied_sdrs = []
#         self._order.get_contracts.return_value = [contract1, contract2]
#         self._order.date = datetime(2016, 1, 20, 13, 12, 39)
#         self._order.get_item_contract.side_effect = [contract1, contract2]

#         return (
#             [
#                 {
#                     "price": "200.00",
#                     "duty_free": "166.60",
#                     "description": "Offering description",
#                     "currency": "EUR",
#                     "related_model": {
#                         "pay_per_use": [
#                             {
#                                 "value": "10.00",
#                                 "unit": "call",
#                                 "tax_rate": "20.00",
#                                 "duty_free": "8.33",
#                             }
#                         ]
#                     },
#                     "item": "1",
#                     "applied_accounting": [
#                         {
#                             "model": {
#                                 "value": "10.00",
#                                 "unit": "call",
#                                 "tax_rate": "20.00",
#                                 "duty_free": "8.33",
#                             },
#                             "accounting": [
#                                 {
#                                     "usage_id": "1",
#                                     "price": "100.00",
#                                     "duty_free": "83.30",
#                                     "value": "10",
#                                 },
#                                 {
#                                     "usage_id": "4",
#                                     "price": "100.00",
#                                     "duty_free": "83.30",
#                                     "value": "10",
#                                 },
#                             ],
#                             "price": "200.00",
#                             "duty_free": "166.60",
#                         },
#                         {
#                             "model": {
#                                 "value": "10.00",
#                                 "unit": "callmin",
#                                 "tax_rate": "20.00",
#                                 "duty_free": "8.33",
#                             },
#                             "accounting": [
#                                 {
#                                     "price": "10.00",
#                                     "value": "1",
#                                     "usage_id": "3",
#                                     "duty_free": "8.33",
#                                 }
#                             ],
#                             "price": "10.00",
#                             "duty_free": "8.33",
#                         },
#                     ],
#                 },
#                 {
#                     "price": "30.00",
#                     "duty_free": "28.33",
#                     "description": "Offering description",
#                     "currency": "EUR",
#                     "related_model": {
#                         "pay_per_use": [
#                             {
#                                 "value": "10.00",
#                                 "unit": "callmin",
#                                 "tax_rate": "20.00",
#                                 "duty_free": "8.33",
#                             }
#                         ],
#                         "alteration": {
#                             "type": "fee",
#                             "period": "recurring",
#                             "value": {"value": "20.00", "duty_free": "20.00"},
#                             "condition": {"operation": "lt", "value": "20.00"},
#                         },
#                     },
#                     "item": "2",
#                     "applied_accounting": [
#                         {
#                             "model": {
#                                 "value": "10.00",
#                                 "unit": "call",
#                                 "tax_rate": "20.00",
#                                 "duty_free": "8.33",
#                             },
#                             "accounting": [
#                                 {
#                                     "usage_id": "1",
#                                     "price": "100.00",
#                                     "duty_free": "83.30",
#                                     "value": "10",
#                                 },
#                                 {
#                                     "usage_id": "4",
#                                     "price": "100.00",
#                                     "duty_free": "83.30",
#                                     "value": "10",
#                                 },
#                             ],
#                             "price": "200.00",
#                             "duty_free": "166.60",
#                         },
#                         {
#                             "model": {
#                                 "value": "10.00",
#                                 "unit": "callmin",
#                                 "tax_rate": "20.00",
#                                 "duty_free": "8.33",
#                             },
#                             "accounting": [
#                                 {
#                                     "price": "10.00",
#                                     "value": "1",
#                                     "usage_id": "3",
#                                     "duty_free": "8.33",
#                                 }
#                             ],
#                             "price": "10.00",
#                             "duty_free": "8.33",
#                         },
#                     ],
#                 },
#             ],
#             [],
#         )

    # def _set_alterations(self, name, unit="one time", renovation_date=None):
    #     component = {
    #         "value": "10.00",
    #         "unit": unit,
    #         "tax_rate": "0.00",
    #         "duty_free": "10.00",
    #     }

    #     if renovation_date is not None:
    #         component["renovation_date"] = renovation_date

    #     alteration_fee = {
    #         "type": "fee",
    #         "period": "recurring",
    #         "value": {"value": "5.00", "duty_free": "5.00"},
    #         "condition": {"operation": "gt", "value": "5.00"},
    #     }

    #     alteration_fixed_discount = {
    #         "type": "discount",
    #         "period": "recurring",
    #         "value": "10.00",
    #     }

    #     alteration_only_once = {
    #         "type": "discount",
    #         "period": "one time",
    #         "value": {"value": "1.00", "duty_free": "1.00"},
    #     }

    #     # Create contracts
    #     contract1, offering1 = self._mock_contract(
    #         {
    #             "description": "Offering 1 description",
    #             "offering_pk": "61004aba5e05acc115f022f0",
    #             "item_id": "1",
    #             "pricing": {
    #                 "general_currency": "EUR",
    #                 name: [deepcopy(component), deepcopy(component)],
    #             },
    #             "product_id": "product1",
    #         }
    #     )

    #     # Conditional fee
    #     contract2, offering2 = self._mock_contract(
    #         {
    #             "description": "Offering 2 description",
    #             "offering_pk": "61004aba5e05acc115f022f1",
    #             "item_id": "2",
    #             "pricing": {
    #                 "general_currency": "EUR",
    #                 name: [deepcopy(component)],
    #                 "alteration": deepcopy(alteration_fee),
    #             },
    #             "product_id": "product2",
    #         }
    #     )

    #     # Fixed percentage discount
    #     contract3, offering3 = self._mock_contract(
    #         {
    #             "description": "Offering 3 description",
    #             "offering_pk": "61004aba5e05acc115f022f2",
    #             "item_id": "3",
    #             "pricing": {
    #                 "general_currency": "EUR",
    #                 name: [deepcopy(component)],
    #                 "alteration": deepcopy(alteration_fixed_discount),
    #             },
    #             "product_id": "product3",
    #         }
    #     )

    #     # Non applicable discount
    #     contract4, offering4 = self._mock_contract(
    #         {
    #             "description": "Offering 4 description",
    #             "offering_pk": "61004aba5e05acc115f022f3",
    #             "item_id": "4",
    #             "pricing": {
    #                 "general_currency": "EUR",
    #                 name: [deepcopy(component)],
    #                 "alteration": {
    #                     "type": "discount",
    #                     "value": "10.00",
    #                     "period": "recurring",
    #                     "condition": {"operation": "gt", "value": "50.00"},
    #                 },
    #             },
    #             "product_id": "product4",
    #         }
    #     )

    #     contract5, offering5 = self._mock_contract(
    #         {
    #             "description": "Offering 5 description",
    #             "offering_pk": "61004aba5e05acc115f022f4",
    #             "item_id": "5",
    #             "pricing": {
    #                 "general_currency": "EUR",
    #                 name: [deepcopy(component)],
    #                 "alteration": alteration_only_once,
    #             },
    #             "product_id": "product4",
    #         }
    #     )

    #     contracts = [contract1, contract2, contract3, contract4, contract5]
    #     self._order.get_contracts.return_value = contracts

    #     # Mock get contracts
    #     self._order.get_item_contract.side_effect = contracts

    #     charging_engine.Offering = MagicMock()
    #     charging_engine.Offering.objects.get.side_effect = [
    #         offering1,
    #         offering2,
    #         offering3,
    #         offering4,
    #         offering5,
    #     ]

    #     item_only_once = {
    #         "price": "9.00",
    #         "duty_free": "9.00",
    #         "description": "Offering 5 description",
    #         "currency": "EUR",
    #         "related_model": {
    #             name: [deepcopy(component)],
    #             "alteration": deepcopy(alteration_only_once),
    #         },
    #         "item": "5",
    #     }

    #     # The alteration will have effect only in single payment
    #     if name != "single_payment":
    #         item_only_once["price"] = "10.00"
    #         item_only_once["duty_free"] = "10.00"
    #         del item_only_once["related_model"]["alteration"]

    #     return [
    #         {
    #             "price": "20.00",
    #             "duty_free": "20.00",
    #             "description": "Offering 1 description",
    #             "currency": "EUR",
    #             "related_model": {name: [deepcopy(component), deepcopy(component)]},
    #             "item": "1",
    #         },
    #         {
    #             "price": "15.00",
    #             "duty_free": "15.00",
    #             "description": "Offering 2 description",
    #             "currency": "EUR",
    #             "related_model": {
    #                 name: [deepcopy(component)],
    #                 "alteration": deepcopy(alteration_fee),
    #             },
    #             "item": "2",
    #         },
    #         {
    #             "price": "9.00",
    #             "duty_free": "9.00",
    #             "description": "Offering 3 description",
    #             "currency": "EUR",
    #             "related_model": {
    #                 name: [deepcopy(component)],
    #                 "alteration": deepcopy(alteration_fixed_discount),
    #             },
    #             "item": "3",
    #         },
    #         {
    #             "price": "10.00",
    #             "duty_free": "10.00",
    #             "description": "Offering 4 description",
    #             "currency": "EUR",
    #             "related_model": {name: [deepcopy(component)]},
    #             "item": "4",
    #         },
    #         item_only_once,
    #     ]

    # def _set_initial_alteration_contracts(self):
    #     return self._set_alterations("single_payment", "one time"), []

    # def _set_renovation_alteration_contracts(self):
    #     return (
    #         self._set_alterations("subscription", "month", datetime(2015, 10, 1, 10, 10)),
    #         [],
    #     )

    # @parameterized.expand(
    #     [
    #         ("initial", _set_initial_contracts),
    #         ("initial", _set_initial_alteration_contracts),
    #         ("recurring", _set_renovation_contracts),
    #         ("recurring", _set_renovation_alteration_contracts),
    #         ("usage", _set_usage_contracts),
    #         ("usage", _set_usage_alteration_contracts),
    #     ]
    # )
    # def test_payment(self, name, contract_gen):
    #     self._order.state = "pending"
    #     transactions, free_contracts = contract_gen(self)

    #     charging = charging_engine.ChargingEngine(self._order)
    #     redirect_url = charging.resolve_charging(name)

    #     self.assertEquals(self._paypal_url, redirect_url)

    #     # Check payment client loading call
    #     self._payment_class.assert_called_once_with(self._order)
    #     self._payment_inst.start_redirection_payment.assert_called_once_with(transactions)

    #     # Check timer call
    #     charging_engine.threading.Timer.assert_called_once_with(300, charging._timeout_handler)
    #     self._thread.start.assert_called_once_with()

    #     # Check payment saving
    #     self.assertEquals(
    #         {
    #             "transactions": transactions,
    #             "free_contracts": free_contracts,
    #             "concept": name,
    #         },
    #         self._order.pending_payment,
    #     )
    #     self.assertEquals("pending", self._order.state)
    #     self._order.save.assert_called_once_with()

    # def test_renovation_error(self):
    #     self._order.state = "pending"
    #     self._set_subscription_contract()

    #     charging = charging_engine.ChargingEngine(self._order)

    #     error = None
    #     try:
    #         charging.resolve_charging("recurring")
    #     except OrderingError as e:
    #         error = e

    #     self.assertTrue(error is not None)
    #     self.assertEquals("OrderingError: There is not recurring payments to renovate", str(error))

    # def test_free_charge(self):
    #     self._set_free_contract()

    #     charging = charging_engine.ChargingEngine(self._order)
    #     redirect_url = charging.resolve_charging()

    #     # Check return value
    #     self.assertTrue(redirect_url is None)

    #     # Check invoice generation calls
    #     charging_engine.InvoiceBuilder.assert_called_once_with(self._order)
    #     self.assertEquals(charging_engine.InvoiceBuilder().generate_invoice.call_count, 0)
    #     self.assertEquals(charging_engine.BillingClient().create_charge.call_count, 0)

    #     # Check order status
    #     self.assertEquals("paid", self._order.state)
    #     self.assertEquals(None, self._order.pending_payment)
    #     self._order.save.assert_called_once_with()

    # def _validate_subscription_calls(self):
    #     self.assertEquals(
    #         {
    #             "general_currency": "EUR",
    #             "subscription": [
    #                 {
    #                     "value": "12.00",
    #                     "unit": "month",
    #                     "tax_rate": "20.00",
    #                     "duty_free": "10.00",
    #                     "renovation_date": datetime(2016, 2, 19, 13, 12, 39),
    #                 }
    #             ],
    #         },
    #         self._order.get_contracts()[1].pricing_model,
    #     )

    # def _validate_end_initial_payment(self, transactions):
    #     self.assertEquals([call("1"), call("2")], self._order.get_item_contract.call_args_list)

    #     self.assertEquals(
    #         [
    #             "61004aba5e05acc115f022f0",
    #             "61004aba5e05acc115f022f1",
    #             "61004aba5e05acc115f022f2",
    #         ],
    #         self._order.owner_organization.acquired_offerings,
    #     )
    #     self.assertEquals([call(), call(), call()], self._order.owner_organization.save.call_args_list)

    #     # self.assertEquals(
    #     #     [
    #     #         call(self._order, self._order.get_contracts()[0]),
    #     #         call(self._order, self._order.get_contracts()[1]),
    #     #     ],
    #     #     charging_engine.CDRManager.call_args_list,
    #     # )

    #     # self.assertEquals(
    #     #     [
    #     #         call(transactions[0]["related_model"], "2016-01-20T13:12:39Z"),
    #     #         call(transactions[1]["related_model"], "2016-01-20T13:12:39Z"),
    #     #     ],
    #     #     charging_engine.CDRManager().generate_cdr.call_args_list,
    #     # )

    #     charging_engine.NotificationsHandler().send_acquired_notification.assert_called_once_with(self._order)

    #     self.assertEquals(
    #         [
    #             call(self._order, self._order.get_contracts()[0]),
    #             call(self._order, self._order.get_contracts()[1]),
    #             call(self._order, self._order.get_contracts()[2]),
    #         ],
    #         charging_engine.NotificationsHandler().send_provider_notification.call_args_list,
    #     )

    #     basic_charge_call = call(
    #         date=datetime(2016, 1, 20, 13, 12, 39),
    #         cost="12.00",
    #         currency="EUR",
    #         concept="initial",
    #         duty_free="10.00",
    #         invoice=INVOICE_PATH,
    #     )

    #     self.assertEquals(
    #         [basic_charge_call, basic_charge_call],
    #         charging_engine.Charge.call_args_list,
    #     )

    #     self.assertEquals([self._charge], self._order.get_contracts()[0].charges)
    #     self.assertEquals([self._charge], self._order.get_contracts()[1].charges)

    #     self.assertEquals(0, charging_engine.BillingClient.call_count)

    #     self._validate_subscription_calls()

    # def _validate_end_initial_alteration_payment(self, transactions):
    #     self.assertEquals(
    #         [call("1"), call("2"), call("3"), call("4"), call("5")],
    #         self._order.get_item_contract.call_args_list,
    #     )

    #     self.assertEquals(
    #         [
    #             "61004aba5e05acc115f022f0",
    #             "61004aba5e05acc115f022f1",
    #             "61004aba5e05acc115f022f2",
    #             "61004aba5e05acc115f022f3",
    #             "61004aba5e05acc115f022f4",
    #         ],
    #         self._order.owner_organization.acquired_offerings,
    #     )

    #     self.assertEquals(
    #         [call(), call(), call(), call(), call(), call()],
    #         self._order.owner_organization.save.call_args_list,
    #     )

    #     # self.assertEquals(
    #     #     [call(self._order, contract) for contract in self._order.get_contracts()],
    #     #     charging_engine.CDRManager.call_args_list,
    #     # )

    #     # self.assertEquals(
    #     #     [call(trans["related_model"], "2016-01-20T13:12:39Z") for trans in transactions],
    #     #     charging_engine.CDRManager().generate_cdr.call_args_list,
    #     # )

    #     def charge_call(c, d):
    #         return call(
    #             date=datetime(2016, 1, 20, 13, 12, 39),
    #             cost=c,
    #             currency="EUR",
    #             concept="initial",
    #             duty_free=d,
    #             invoice=INVOICE_PATH,
    #         )

    #     self.assertEquals(
    #         [
    #             charge_call("20.00", "20.00"),
    #             charge_call("15.00", "15.00"),
    #             charge_call("9.00", "9.00"),
    #             charge_call("10.00", "10.00"),
    #             charge_call("9.00", "9.00"),
    #         ],
    #         charging_engine.Charge.call_args_list,
    #     )

    #     self.assertEquals(
    #         [[self._charge] for x in range(len(self._order.get_contracts()))],
    #         [x.charges for x in self._order.get_contracts()],
    #     )

    #     self.assertEquals(0, charging_engine.BillingClient.call_count)

    # def _validate_end_renovation_payment(self, transactions):
    #     self.assertEquals([call("2")], self._order.get_item_contract.call_args_list)

    #     #charging_engine.CDRManager.assert_called_once_with(self._order, self._order.get_contracts()[1])
    #     #charging_engine.CDRManager().generate_cdr.assert_called_once_with(
    #     #    transactions[0]["related_model"], "2016-01-20T13:12:39Z"
    #     #)

    #     # No new offering has been included
    #     self.assertEquals([], self._order.owner_organization.acquired_offerings)

    #     self.assertEquals(0, self._order.get_contracts()[0].call_count)
    #     self.assertEquals(0, self._order.get_contracts()[2].call_count)

    #     self.assertEquals([], self._order.get_contracts()[0].charges)

    #     charging_engine.NotificationsHandler().send_renovation_notification.assert_called_once_with(
    #         self._order, transactions
    #     )

    #     charging_engine.Charge.assert_called_once_with(
    #         date=datetime(2016, 1, 20, 13, 12, 39),
    #         cost="12.00",
    #         currency="EUR",
    #         concept="recurring",
    #         duty_free="10.00",
    #         invoice=INVOICE_PATH,
    #     )

    #     self.assertEquals([self._charge], self._order.get_contracts()[1].charges)

    #     self.assertEquals([], self._order.get_contracts()[2].charges)

    #     charging_engine.BillingClient.assert_called_once_with()
    #     charging_engine.BillingClient().create_charge.assert_called_once_with(
    #         self._charge,
    #         self._order.get_contracts()[1].product_id,
    #         start_date=None,
    #         end_date=datetime(2016, 2, 19, 13, 12, 39),
    #     )

    #     self._validate_subscription_calls()

    # def _validate_end_renovation_alteration_payment(self, transactions):
    #     self.assertEquals(
    #         [call(str(x + 1)) for x in range(5)],
    #         self._order.get_item_contract.call_args_list,
    #     )

    #     self.assertEquals([], self._order.owner_organization.acquired_offerings)
    #     self.assertEquals([call()], self._order.owner_organization.save.call_args_list)

    #     # self.assertEquals(
    #     #     [call(self._order, contract) for contract in self._order.get_contracts()],
    #     #     charging_engine.CDRManager.call_args_list,
    #     # )

    #     # self.assertEquals(
    #     #     [call(trans["related_model"], "2016-01-20T13:12:39Z") for trans in transactions],
    #     #     charging_engine.CDRManager().generate_cdr.call_args_list,
    #     # )

    #     def charge_call(c, d):
    #         return call(
    #             date=datetime(2016, 1, 20, 13, 12, 39),
    #             cost=c,
    #             currency="EUR",
    #             concept="recurring",
    #             duty_free=d,
    #             invoice=INVOICE_PATH,
    #         )

    #     self.assertEquals(
    #         [
    #             charge_call("20.00", "20.00"),
    #             charge_call("15.00", "15.00"),
    #             charge_call("9.00", "9.00"),
    #             charge_call("10.00", "10.00"),
    #             charge_call("10.00", "10.00"),
    #         ],
    #         charging_engine.Charge.call_args_list,
    #     )

    #     self.assertEquals(
    #         [[self._charge] for x in range(len(self._order.get_contracts()))],
    #         [x.charges for x in self._order.get_contracts()],
    #     )

    #     self.assertEquals(1, charging_engine.BillingClient.call_count)

    #     def validate_sub(c, d, n=1, alt=None):
    #         temp = {
    #             "general_currency": "EUR",
    #             "subscription": [
    #                 {
    #                     "value": c,
    #                     "unit": "month",
    #                     "tax_rate": "0.00",
    #                     "duty_free": d,
    #                     "renovation_date": datetime(2016, 2, 19, 13, 12, 39),
    #                 }
    #                 for _ in range(n)
    #             ],
    #         }
    #         if alt is not None:
    #             temp["alteration"] = alt
    #         return temp

    #     self.assertEquals(
    #         [
    #             validate_sub("10.00", "10.00", 2),
    #             validate_sub(
    #                 "10.00",
    #                 "10.00",
    #                 1,
    #                 {
    #                     "value": {"duty_free": "5.00", "value": "5.00"},
    #                     "type": "fee",
    #                     "period": "recurring",
    #                     "condition": {"operation": "gt", "value": "5.00"},
    #                 },
    #             ),
    #             validate_sub(
    #                 "10.00",
    #                 "10.00",
    #                 1,
    #                 {"type": "discount", "period": "recurring", "value": "10.00"},
    #             ),
    #             validate_sub(
    #                 "10.00",
    #                 "10.00",
    #                 1,
    #                 {
    #                     "condition": {"operation": "gt", "value": "50.00"},
    #                     "type": "discount",
    #                     "period": "recurring",
    #                     "value": "10.00",
    #                 },
    #             ),
    #             validate_sub(
    #                 "10.00",
    #                 "10.00",
    #                 1,
    #                 {
    #                     "type": "discount",
    #                     "period": "one time",
    #                     "value": {"value": "1.00", "duty_free": "1.00"},
    #                 },
    #             ),
    #         ],
    #         [x.pricing_model for x in self._order.get_contracts()],
    #     )

    # def _validate_end_usage_payment(self, transactions):
    #     self.assertEquals(
    #         [
    #             call(
    #                 "1",
    #                 str(datetime(2016, 1, 20, 13, 12, 39)),
    #                 "83.30",
    #                 "100.00",
    #                 "20.00",
    #                 "EUR",
    #                 self._order.get_contracts()[0].product_id,
    #             ),
    #             call(
    #                 "3",
    #                 str(datetime(2016, 1, 20, 13, 12, 39)),
    #                 "83.30",
    #                 "100.00",
    #                 "20.00",
    #                 "EUR",
    #                 self._order.get_contracts()[0].product_id,
    #             ),
    #         ],
    #         charging_engine.UsageClient().rate_usage.call_args_list,
    #     )

    #     charging_engine.BillingClient.assert_called_once_with()
    #     charging_engine.BillingClient().create_charge.assert_called_once_with(
    #         self._charge,
    #         self._order.get_contracts()[0].product_id,
    #         start_date=datetime(2016, 1, 20, 13, 12, 39),
    #         end_date=None,
    #     )

    # @parameterized.expand(
    #     [
    #         ("initial", _set_initial_contracts, _validate_end_initial_payment),
    #         (
    #             "initial",
    #             _set_initial_alteration_contracts,
    #             _validate_end_initial_alteration_payment,
    #         ),
    #         ("recurring", _set_renovation_contracts, _validate_end_renovation_payment),
    #         (
    #             "recurring",
    #             _set_renovation_alteration_contracts,
    #             _validate_end_renovation_alteration_payment,
    #         ),
    #         ("usage", _set_usage_contracts, _validate_end_usage_payment),
    #     ]
    # )
    # def test_end_payment(self, name, contract_gen, validator):
    #     self._order.state = "pending"
    #     transactions, free_contracts = contract_gen(self)

    #     charging = charging_engine.ChargingEngine(self._order)
    #     charging.end_charging(transactions, free_contracts, name)

    #     charging_engine.NotificationsHandler.assert_called_once_with()
    #     validator(self, transactions)

    #     # Validate calls
    #     self.assertEquals("paid", self._order.state)

    #     self.assertEquals([call(), call()], self._order.save.call_args_list)

    # def test_invalid_concept(self):
    #     charging = charging_engine.ChargingEngine(self._order)

    #     error = None
    #     try:
    #         charging.resolve_charging(type_="invalid")
    #     except ValueError as e:
    #         error = e

    #     self.assertFalse(error is None)
    #     self.assertEquals("Invalid charge type, must be `initial`, `recurring`, or `usage`", str(error))


PAYPAL_DATA_BASE = {"action": "confirm", "confirm_action": "accept", "client": "paypal"}

BASIC_PAYPAL = {**PAYPAL_DATA_BASE, "reference": "111111111111111111111111", "PayerID": "payer", "paymentId": "payment"}

MISSING_REF = {**PAYPAL_DATA_BASE, "PayerID": "payer", "paymentId": "payment"}

MISSING_PAYER = {**PAYPAL_DATA_BASE, "reference": "111111111111111111111111", "paymentId": "payment"}

MISSING_PAYMENT = {**PAYPAL_DATA_BASE, "reference": "111111111111111111111111", "PayerID": "payer"}

MISSING_RESP = {
    "result": "error",
    "error": "Invalid request: Missing required field. It must contain ['paymentId', 'PayerID', 'reference'] field(s).",
}

LOCK_CLOSED_RESP = {
    "result": "error",
    "error": "The payment has timed out: PaymentTimeoutError: The timeout set to process the payment has finished",
}


class PaymentConfirmationTestCase(TestCase):
    tags = ("ordering", "paypal-conf")

    def setUp(self):
        # Mock Authentication decorator
        wstore.store_commons.utils.http.authentication_required = decorator_mock
        reload(views)

        # Create a Mock user
        self.user = MagicMock()
        org = MagicMock()
        self.user.userprofile.current_organization = org

        # Create request factory
        self.factory = RequestFactory()

        # Mock ordering client
        self._ordering_inst = MagicMock()
        self._raw_order = {"id": "1", "productOrderItem": [{"id": "1"}, {"id": "2"}]}
        self._ordering_inst.get_order.return_value = self._raw_order

        views.OrderingClient = MagicMock()
        views.OrderingClient.return_value = self._ordering_inst

        # Mock database connection
        views.get_database_connection = MagicMock()
        self._connection_inst = MagicMock()
        self._connection_inst.wstore_order.find_one_and_update.return_value = {
            "_lock": False,
            "state": "pending",
        }
        views.get_database_connection.return_value = self._connection_inst

        # Mock Order
        views.Order = MagicMock()
        self._free_contracts = [MagicMock(item_id="3"), MagicMock(item_id="4")]
        self._order_inst = MagicMock()
        self._order_inst.order_id = "1"
        self._order_inst.owner_organization = org
        self._order_inst.customer = self.user
        self._order_inst.state = "pending"

        self._payment = {}
        self._payment["transactions"] = [{"item": "1"}, {"item": "2"}]
        self._payment["free_contracts"] = self._free_contracts
        self._payment["concept"] = "initial"

        self._order_inst.pending_payment = self._payment

        order_filter_mock = MagicMock(**{"first.return_value": self._order_inst})
        views.Order.objects.filter.return_value = order_filter_mock
        views.Order.objects.get.return_value = self._order_inst

        offering_mock = MagicMock()
        offering_mock.is_digital = True

        views.Offering = MagicMock()
        views.Offering.objects.get.return_value = offering_mock

        contract_mock = MagicMock()
        contract_mock.offering = "111111111111111111111111"
        self._order_inst.get_item_contract.return_value = contract_mock

        # Mock payment client
        mock_payment_client(self, views)
        self._payment_class.END_PAYMENT_PARAMS = ("paymentId", "PayerID")

        # Mock Charging engine
        views.ChargingEngine = MagicMock()
        self._charging_inst = MagicMock()
        views.ChargingEngine.return_value = self._charging_inst

        payment_client_module.settings.PAYMENT_CLIENT = (
            "wstore.charging_engine.payment_client.payment_client.PaymentClient"
        )

    def tearDown(self):
        reload(wstore.store_commons.utils.http)
        reload(views)

    def _invalid_ref(self):
        order_filter_mock = MagicMock(**{"first.return_value": None})
        views.Order.objects.filter.return_value = order_filter_mock

    def _lock_closed(self):
        self._connection_inst.wstore_order.find_one_and_update.return_value = {"_lock": True}

    def _timeout(self):
        self._connection_inst.wstore_order.find_one_and_update.return_value = {
            "_lock": False,
            "state": "paid",
        }

    def _unauthorized(self):
        self.user.userprofile.current_organization = MagicMock()

    def _exception(self):
        self._charging_inst.end_charging.side_effect = Exception("Unexpected")

    def _non_digital_assets(self):
        offering_mock = MagicMock()
        offering_mock.is_digital = False

        views.Offering = MagicMock()
        views.Offering.objects.get.return_value = offering_mock

        contract_mock = MagicMock()
        contract_mock.offering = "111111111111111111111111"
        self._order_inst.get_item_contract.return_value = contract_mock

    @parameterized.expand(
        [
            (
                "basic",
                BASIC_PAYPAL,
                {"result": "correct", "message": "Ok"},
                [{"id": "1"}, {"id": "2"}],
            ),
            # (
            #     "non_digital",
            #     BASIC_PAYPAL,
            #     {"result": "correct", "message": "Ok"},
            #     [],
            #     _non_digital_assets,
            # ),
            ("missing_ref", MISSING_REF, MISSING_RESP, None, None, True),
            ("missing_payerid", MISSING_PAYER, MISSING_RESP, None, None, True),
            ("missing_payment_id", MISSING_PAYMENT, MISSING_RESP, None, None, True),
            (
                "invalid_ref",
                BASIC_PAYPAL,
                {
                    "result": "error",
                    "error": "Invalid request: The provided reference does not identify a valid order",
                },
                None,
                _invalid_ref,
                True,
            ),
            ("lock_closed", BASIC_PAYPAL, LOCK_CLOSED_RESP, None, _lock_closed, True),
            # (
            #     "timeout_finished",
            #     BASIC_PAYPAL,
            #     LOCK_CLOSED_RESP,
            #     None,
            #     _timeout,
            #     True,
            #     True,
            # ),
            (
                "unauthorized",
                BASIC_PAYPAL,
                {
                    "result": "error",
                    "error": "The payment has been canceled: PaymentError: You are not authorized to execute the payment",
                },
                None,
                _unauthorized,
                True,
                True,
            ),
            (
                "exception",
                BASIC_PAYPAL,
                {
                    "result": "error",
                    "error": "The payment has been canceled due to an unexpected error.",
                },
                None,
                _exception,
                True,
                True,
            ),
        ]
    )
    def test_paypal_confirmation(
        self,
        name,
        data,
        expected_resp,
        completed=None,
        side_effect=None,
        error=False,
        to_del=False,
    ):
        if side_effect is not None:
            side_effect(self)

        # Create request
        request = self.factory.post(
            "charging/api/orderManagement/orders/confirm/",
            json.dumps(data),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        request.user = self.user

        # Build class
        # __import__("ipdb").sset_trace()
        paypal_view = views.PaymentConfirmation(permitted_methods=("POST",))

        response = paypal_view.create(request)

        # Check response
        resp = json.loads(response.content)
        self.assertEquals(expected_resp, resp)

        # Check calls
        views.OrderingClient.assert_called_once_with()

        if not error:
            views.get_database_connection.assert_called_once_with()
            self.assertEquals(
                [
                    call(
                        {"_id": ObjectId("111111111111111111111111")},
                        {"$set": {"_lock": True}},
                    ),
                    call(
                        {"_id": ObjectId("111111111111111111111111")},
                        {"$set": {"_lock": False}},
                    ),
                ],
                self._connection_inst.wstore_order.find_one_and_update.call_args_list,
            )

            views.Order.objects.filter.assert_called_once_with(pk=ObjectId("111111111111111111111111"))

            self._payment_class.assert_called_once_with(self._order_inst)
            self._payment_inst.end_redirection_payment.assert_called_once_with(**data)

            views.ChargingEngine.assert_called_once_with(self._order_inst)
            self._charging_inst.end_charging.assert_called_once_with(
                [{"item": "1"}, {"item": "2"}], self._free_contracts, "initial"
            )

            self._ordering_inst.get_order.assert_called_once_with("1")

            self.assertEquals(
                [call("1"), call("2")],
                self._order_inst.get_item_contract.call_args_list,
            )

            # self.assertEquals(
            #     [call(self._raw_order, "completed", completed)],
            #     self._ordering_inst.update_items_state.call_args_list,
            # )

        elif to_del:
            self.assertEquals(
                [call(self._raw_order, "failed")],
                self._ordering_inst.update_items_state.call_args_list,
            )
            self._order_inst.delete.assert_called_once_with()


MISSING_FIELD_RESP = {
    "result": "error",
    "message": "Missing required field, it must contain: orderId, productId, customer, correlationNumber, timestamp, recordType, unit, and value",
}

BASIC_SDR = {
    "id": "1",
    "orderId": "1",
    "productId": "2",
    "customer": "test_user",
    "correlationNumber": "56",
    "recordType": "event",
    "unit": "call",
    "value": "50",
    "timestamp": "2016-02-09T11:33:07.8",
}

INV_ORDERID_RESP = {
    "result": "error",
    "error": "Invalid orderId, the order does not exists",
}

INV_PRODUCTID_RESP = {
    "result": "error",
    "error": "Invalid productId, the contract does not exist",
}

MANAGER_DENIED_RESP = {"result": "error", "error": "Permission denied"}

MANAGER_VALUE_RESP = {"result": "error", "error": "Value error"}


class PaymentRefundTestCase(TestCase):
    tags = ("ordering", "refund")

    def setUp(self):
        # Mock Authentication decorator
        wstore.store_commons.utils.http.authentication_required = decorator_mock
        reload(views)

        # Create request factory
        self.factory = RequestFactory()

        # Create a Mock user
        self.user = MagicMock()
        org = MagicMock()
        self.user.userprofile.current_organization = org

        # Mock Order
        views.Order = MagicMock()
        self._order_inst = MagicMock()
        self._order_inst.order_id = "1"
        self._order_inst.owner_organization = org
        self._order_inst.get_contracts.return_value = []
        views.Order.objects.get.return_value = self._order_inst

        # Mock CDR Manager
        views.CDRManager = MagicMock()

        # Mock payment client
        mock_payment_client(self, views)

        payment_client_module.settings.PAYMENT_CLIENT = (
            "wstore.charging_engine.payment_client.payment_client.PaymentClient"
        )

    def tearDown(self):
        reload(wstore.store_commons.utils.http)
        reload(views)

    @parameterized.expand(
        [
            ([], [MagicMock(charges=[])]),
            (
                [1],
                [
                    MagicMock(
                        charges=[
                            {
                                "cost": "10",
                                "duty_free": "8",
                                "date": datetime(2016, 10, 20),
                            }
                        ]
                    )
                ],
            ),
            (
                [1, 2],
                [
                    MagicMock(
                        charges=[
                            {
                                "cost": "10",
                                "duty_free": "8",
                                "date": datetime(2016, 10, 20),
                            }
                        ]
                    ),
                    MagicMock(
                        charges=[
                            {
                                "cost": "10",
                                "duty_free": "8",
                                "date": datetime(2016, 10, 20),
                            }
                        ]
                    ),
                ],
            ),
            (
                [1, 2],
                [
                    MagicMock(
                        charges=[
                            {
                                "cost": "10",
                                "duty_free": "8",
                                "date": datetime(2016, 10, 20),
                            }
                        ]
                    ),
                    MagicMock(
                        charges=[
                            {
                                "cost": "10",
                                "duty_free": "8",
                                "date": datetime(2016, 10, 20),
                            }
                        ]
                    ),
                ],
                True,
            ),
        ]
    )
    def test_refund_sales(self, sales_ids, contracts, refund_fail=False):
        # Mock
        self._order_inst.sales_ids = sales_ids
        self._order_inst.get_contracts.return_value = contracts

        if refund_fail:
            self._payment_inst.refund.side_effect = Exception("unexpected")

        # Create request
        request = self.factory.post(
            "charging/api/orderManagement/orders/accept/",
            json.dumps({"orderId": 7}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        request.user = self.user

        # Build class
        paypal_view = views.PaymentRefund(permitted_methods=("POST",))
        response = paypal_view.create(request)

        # Check response
        resp = json.loads(response.content)

        if not refund_fail:
            self.assertEquals(resp, {"message": "Ok", "result": "correct"})

            calls = [call(sale_id) for sale_id in sales_ids]
            self.assertEquals(calls, self._payment_inst.refund.call_args_list)

            cdr_manager_calls = [
                call(self._order_inst, contract) for contract in contracts if len(contract.charges) > 0
            ]
            self.assertEquals(cdr_manager_calls, views.CDRManager.call_args_list)

            cdr_refund_calls = [
                call(
                    contract.charges[0]["cost"],
                    contract.charges[0]["duty_free"],
                    "2016-10-20T00:00:00Z",
                )
                for contract in contracts
                if len(contract.charges) > 0
            ]
            self.assertEquals(cdr_refund_calls, views.CDRManager().refund_cdrs.call_args_list)

        else:
            self.assertEquals(resp, {"error": "Sales cannot be refunded", "result": "error"})
