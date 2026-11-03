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

from copy import deepcopy
from datetime import datetime
from urllib.parse import urlparse
from datetime import datetime, timezone
from bson.objectid import ObjectId
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase
from django.test.utils import override_settings
from mock import MagicMock, call, patch
from parameterized import parameterized

from wstore.models import Organization
from wstore.ordering import inventory_client, ordering_client, ordering_management
from wstore.ordering.errors import OrderingError, InventoryError
from wstore.ordering.models import Contract, Offering, Order
from wstore.ordering.tests.test_data import *


@override_settings(
    SITE="http://extpath.com:8080/",
    VERIFY_REQUESTS=True,
    BILLING="http://apis.docker:8080/DSBillingManagement",
    CATALOG="http://catalog.com"
)
class OrderingManagementTestCase(TestCase):
    tags = ("ordering", "order-manager")

    def setUp(self):
        self._customer = MagicMock()

        ordering_client_patch = patch.object(ordering_management, "OrderingClient")
        ordering_client_patch.start()
        self.addCleanup(ordering_client_patch.stop)

        # Mock order model
        ordering_management.Order = MagicMock()
        self._order_inst = MagicMock()
        ordering_management.Order.objects.create.return_value = self._order_inst
        ordering_management.Order.objects.get.return_value = self._order_inst

        # Mock Contract model
        ordering_management.Contract = MagicMock()
        self._contract_inst = MagicMock()
        self._contract_inst.offering = "5"
        ordering_management.Contract.return_value = self._contract_inst

        # Mock Charging Engine
        ordering_management.ChargingEngine = MagicMock()
        self._charging_inst = MagicMock()
        self._charging_inst.resolve_charging.return_value = "http://redirectionurl.com/"
        ordering_management.ChargingEngine.return_value = self._charging_inst

        # Mock requests
        ordering_management.requests = MagicMock()
        self._response = MagicMock()
        self._response.status_code = 200
        ordering_management.requests.get.return_value = self._response

        # Mock organization model
        self._org_inst = MagicMock()

        self._customer.userprofile.current_organization = self._org_inst
        self._customer.userprofile.access_token = "example_token"

        ordering_management.datetime = MagicMock()
        self._now = datetime(2016, 12, 3)
        ordering_management.datetime.datetime.utcnow.return_value = self._now

        # Mock billing client
        self._billing_instance = MagicMock()
        ordering_management.BillingClient = MagicMock()
        ordering_management.BillingClient.return_value = self._billing_instance

        self._billing_instance.get_billing_account.return_value = BILLING_ACCOUNT

    def _basic_add_checker(self):
        # Check contract creation
        ordering_management.Contract.assert_called_once_with(
            item_id="1",
            pricing_model={'id': 'urn:ProductOfferingPrice:1', 'href': 'urn:ProductOfferingPrice:1'},
            #revenue_class="productClass",
            offering="5",
            options=[]
        )

    def _free_add_checker(self):
        ordering_management.Contract.assert_called_once_with(
            item_id="1",
            pricing_model={},
            #revenue_class="productClass",
            offering='5',
            options=[]
        )

    def _invalid_billing(self):
        self._billing_instance.get_billing_account.side_effect = Exception('Billing error')

    def _missing_offering(self):
        self._response.status_code = 404

    def _missing_product(self):
        def get(url):
            result = self._response
            if url == "http://producturl.com/":
                result = MagicMock()
                result.status_code = 404
            return result

        ordering_management.requests.get = get

    def _missing_contact(self):
        new_cust = deepcopy(BILLING_ACCOUNT)
        new_cust["contact"] = []
        self._billing_instance.get_billing_account.return_value = new_cust

    def _missing_postal(self):
        new_cust = deepcopy(BILLING_ACCOUNT)
        new_cust["contact"] = [{
            "contactMedium": []
        }]
        self._billing_instance.get_billing_account.return_value = new_cust

    @parameterized.expand(
        [
            ("basic_add", BASIC_ORDER, BASIC_PRICING, _basic_add_checker),
            (
                "basic_add_terms_not_accepted",
                BASIC_ORDER,
                BASIC_PRICING,
                None,
                None,
                "OrderingError: You must accept the terms and conditions of the offering to acquire it",
                False,
            ),
            (
                "basic_add_terms_not_required",
                BASIC_ORDER,
                BASIC_PRICING,
                _basic_add_checker,
                None,
                None,
                False,
                OFFERING_NO_TERMS
            ),
            (
                "basic_add_invalid_billing",
                BASIC_ORDER,
                BASIC_PRICING,
                None,
                _invalid_billing,
                "OrderingError: Invalid billing account, billing account could not be loaded",
            ),
            (
                "recurring_add",
                BASIC_ORDER,
                RECURRING_PRICING,
                _basic_add_checker,
            ),
            (
                "usage_add",
                BASIC_ORDER,
                USAGE_PRICING,
                _basic_add_checker,
            ),
            (
                "pricing_not_found",
                BASIC_ORDER,
                BASIC_PRICING,
                None,
                None,
                "OrderingError: The product price included in productOrderItem 1 does not match with any of the prices included in the related offering",
                True,
                OFFERING_NO_PRICING
            ),
            # (
            #     "invalid_model",
            #     BASIC_ORDER,
            #     INVALID_MODEL_PRICING,
            #     None,
            #     None,
            #     "OrderingError: Invalid price model Invalid",
            # ),
            (
                "missing_billing",
                MISSING_BILLING_ORDER,
                {},
                None,
                None,
                "OrderingError: Missing billing account in product order",
            ),
            (
                "invalid_offering",
                BASIC_ORDER,
                {},
                None,
                _missing_offering,
                "OrderingError: The product offering specified in order item 1 does not exist",
            ),
            (
                "missing_postal_address",
                BASIC_ORDER,
                BASIC_PRICING,
                None,
                _missing_postal,
                "OrderingError: Provided Billing Account does not contain a Postal Address",
            ),
            (
                "missing_contact",
                BASIC_ORDER,
                BASIC_PRICING,
                None,
                _missing_contact,
                "OrderingError: Provided Billing Account does not contain a Postal Address",
            ),
            (
                "missing_order_pricing",
                FREE_ORDER,
                BASIC_PRICING,
                None,
                None,
                "OrderingError: The price model has not been included for productOrderItem 1",
            )
        ]
    )
    def test_process_order(
        self,
        name,
        order,
        pricing,
        checker,
        side_effect=None,
        err_msg=None,
        terms_accepted=True,
        offering=OFFERING
    ):

        ordering_management.OrderingClient = MagicMock()

        # Mock requests results
        self._response.json.side_effect = [
            offering,
            pricing
        ]

        if side_effect is not None:
            side_effect(self)

        ordering_manager = ordering_management.OrderingManager()
        error = None
        try:
            redirect_url = ordering_manager.process_order(self._customer, order, terms_accepted=terms_accepted)
        except OrderingError as e:
            error = e

        if err_msg is None:
            self.assertTrue(error is None)

            # Check returned value
            self.assertEquals("http://redirectionurl.com/", redirect_url)

            # Check common calls
            ordering_management.ChargingEngine.assert_called_once_with(self._order_inst)

            # Check order status update (now handled via root_state in update_items_state)
            ordering_management.OrderingClient().update_items_state.assert_called_once()

            # Check offering and product downloads
            self.assertEquals(2, ordering_management.requests.get.call_count)

            self.assertEquals(
                [
                    call(
                        "http://catalog.com/productOffering/urn:ProductOffering:20",
                        verify=True,
                    ),
                    call(
                        "http://catalog.com/productOfferingPrice/urn:ProductOfferingPrice:1",
                        verify=True,
                    ),
                ],
                ordering_management.requests.get.call_args_list,
            )

            self._billing_instance.get_billing_account.assert_called_once_with(BILLING_ACCOUNT["id"])

            contact_medium = BILLING_ACCOUNT["contact"][0]["contactMedium"][0]["characteristic"]

            ordering_management.Order.objects.create.assert_called_once_with(
                order_id="12",
                customer=self._customer,
                owner_organization=self._org_inst,
                date=self._now,
                state="pending",
                tax_address={
                    "street": contact_medium["street1"] + "\n" + contact_medium["street2"],
                    "postal": contact_medium["postCode"],
                    "city": contact_medium["city"],
                    "province": contact_medium["stateOrProvince"],
                    "country": contact_medium["country"],
                },
                contracts=[self._contract_inst],
                description="",
            )

            # Check particular calls
            checker(self)
        else:
            self.assertEquals(err_msg, str(error))


    @parameterized.expand([
        ("free_add", FREE_ORDER, _free_add_checker, OFFERING_NO_PRICING),
        ("free_add_without_prices_field", FREE_ORDER, _free_add_checker, OFFERING_WITHOUT_PRICING_FIELD),
        #("no_product_add", NOPRODUCT_ORDER, _free_add_checker)
    ])
    def test_process_free_order(self, name, order, validator, offering):
        self._response.json.side_effect = [
            offering
        ]

        # Mock ordering client
        ordering_management.OrderingClient = MagicMock()

        ordering_manager = ordering_management.OrderingManager()
        error = None
        try:
            redirect_url = ordering_manager.process_order(self._customer, order, terms_accepted=True)
        except OrderingError as e:
            error = e

        self.assertTrue(error is None)
        self.assertEquals("http://redirectionurl.com/", redirect_url)

        self.assertEquals([
            call("http://catalog.com/productOffering/20", verify=True),
        ],
            ordering_management.requests.get.call_args_list,
        )

        self._billing_instance.get_billing_account.assert_called_once_with(BILLING_ACCOUNT["id"])

        # Validate ordering client calls
        self.assertEquals([
            call(order, 'inProgress', root_state='inProgress', items=[{'id': '1', 'action': 'add', 'productOffering': {'id': '20', 'href': '20'}, 'product': {}}]),
        ], ordering_management.OrderingClient().update_items_state.call_args_list)

        validator(self)

    def test_custom_pricing_order(self):
        self._response.json.side_effect = [
            OFFERING,
            CUSTOM_PRICING
        ]

        ordering_manager = ordering_management.OrderingManager()
        result = ordering_manager.process_order(self._customer, BASIC_ORDER, terms_accepted=True)

        # The payment should not be called for custom pricing
        self.assertEquals(None, result)


    BASIC_MODIFY = {
        "id": "12",
        "state": "Acknowledged",
        "productOrderItem": [{"id": "1", "action": "modify", "product": {"id": "89"}}],
    }

    @parameterized.expand(
        [
            (
                "basic_modify",
                BASIC_MODIFY,
                {"subscription": [{"renovation_date": datetime(2016, 1, 1)}]},
                "new_pricing",
                "active",
            ),
            (
                "activated_modify",
                BASIC_MODIFY,
                {"subscription": [{"renovation_date": datetime(2016, 1, 1)}]},
                "new_pricing",
                "created",
                "OrderingError: It is not possible to modify a product without been activated previously",
            ),
            ("empty_pricing", BASIC_MODIFY, {}, {}, "active"),
            (
                "mix_error",
                {
                    "state": "Acknowledged",
                    "productOrderItem": [{"action": "modify"}, {"action": "add"}],
                },
                {},
                {},
                "active",
                "OrderingError: It is not possible to process mixed actions in the same order",
            ),
            (
                "multiple_mod",
                {
                    "state": "Acknowledged",
                    "productOrderItem": [{"action": "modify"}, {"action": "modify"}],
                },
                {},
                {},
                "active",
                "OrderingError: Only a modify item is supported per order item",
            ),
            (
                "missing_product",
                {"state": "Acknowledged", "productOrderItem": [{"action": "modify"}]},
                {},
                {},
                "active",
                "OrderingError: It is required to specify product information in modify order items",
            ),
            (
                "missing_product_id",
                {
                    "state": "Acknowledged",
                    "productOrderItem": [{"action": "modify", "product": {}}],
                },
                {},
                {},
                "active",
                "OrderingError: It is required to provide product id in modify order items",
            ),
            # (
            #     "product_not_exp",
            #     BASIC_MODIFY,
            #     {"subscription": [{"renovation_date": datetime(2050, 1, 1)}]},
            #     {},
            #     "OrderingError: You cannot modify a product with a recurring payment until the subscription expires",
            # ),
        ]
    )
    def test_modify_order(self, name, order, pricing, new_pricing, pr_status, err_msg=None):
        # Mock order method
        mock_contract = MagicMock()
        mock_contract.pricing_model = pricing
        mock_contract.revenue_class = "old_revenue"
        mock_contract.product_id = "89"
        self._order_inst.get_product_contract.return_value = mock_contract
        self._order_inst.claim_contract_for_modification.return_value = True
        self._order_inst.get_contracts.return_value = [mock_contract]
        self._order_inst.contracts = [mock_contract]
        ordering_management.Order.get_by_product_id.return_value = self._order_inst

        ordering_management.InventoryClient = MagicMock()
        ordering_management.InventoryClient().get_product.return_value = {
            "id": "1",
            "name": "oid=35",
            "status": pr_status,
        }

        ordering = ordering_management.OrderingManager()

        error = None
        try:
            ordering.process_order(self._customer, order)
        except OrderingError as e:
            error = e

        if err_msg is None:
            self.assertTrue(error is None)

            ordering_management.InventoryClient().get_product.assert_called_once_with("89")
            ordering_management.Order.get_by_product_id.assert_called_once_with("89")

            self._order_inst.get_product_contract.assert_called_once_with("89")

            ordering_management.ChargingEngine.assert_called_once_with(self._order_inst)
            mod_order = {**order, "productOrderItem": [{"id": "1", "action": "modify", "product": {"id": "89"}}]}
            self._charging_inst.resolve_charging.assert_called_once_with(
                type_="initial", related_contracts=[mock_contract], raw_order=mod_order
            )
        else:
            self.assertEquals(err_msg, str(error))


@override_settings(ORDERING="http://localhost:8080/")
class OrderingClientTestCase(TestCase):
    tags = ("ordering", "ordering-client")

    def setUp(self):
        ordering_client.settings.LOCAL_SITE = "http://testdomain.com"

        # Mock requests
        ordering_client.requests = MagicMock()
        self._response = MagicMock()
        self._response.status_code = 200
        self._response.json.return_value = {"id": "1"}
        ordering_client.requests.post.return_value = self._response
        ordering_client.requests.patch.return_value = self._response
        ordering_client.requests.get.return_value = self._response

    def test_ordering_subscription(self):
        client = ordering_client.OrderingClient()

        client.create_ordering_subscription()

        # Check calls
        ordering_client.requests.post.assert_called_once_with(
            "http://localhost:8080/productOrdering/v2/hub",
            {"callback": "http://testdomain.com/charging/api/orderManagement/orders"},
        )

    def test_ordering_subscription_error(self):
        client = ordering_client.OrderingClient()
        self._response.status_code = 400

        error = None
        try:
            client.create_ordering_subscription()
        except ImproperlyConfigured as e:
            error = e

        self.assertFalse(error is None)
        msg = "It hasn't been possible to create ordering subscription, "
        msg += "please check that the ordering API is correctly configured "
        msg += "and that the ordering API is up and running"

        self.assertEquals(msg, str(error))

    @parameterized.expand(
        [
            (
                "complete",
                {
                    "productOrderItem": [
                        {"id": "1", "state": "inProgress"},
                        {"id": "2", "state": "inProgress"},
                    ]
                },
            ),
            (
                "partial",
                {
                    "productOrderItem": [
                        {"id": "1", "state": "Acknowledged"},
                        {"id": "2", "state": "inProgress"},
                    ]
                },
                [{"id": "2"}],
            ),
        ]
    )
    def test_update_items_state(self, name, expected, items=None):
        client = ordering_client.OrderingClient()
        order = {
            "id": "20",
            "productOrderItem": [
                {"id": "1", "state": "Acknowledged"},
                {"id": "2", "state": "Acknowledged"},
            ],
        }
        client.update_items_state(order, "inProgress", items)

        self.assertEquals(
            [call("http://localhost:8080/productOrder/20", json=expected)],
            ordering_client.requests.patch.call_args_list,
        )

        self.assertEquals([call()], self._response.raise_for_status.call_args_list)

    def test_update_state(self):
        client = ordering_client.OrderingClient()
        new_state = "Failed"

        order = {"id": "7"}

        get_req = MagicMock()
        get_req.json.return_value = {
            "productOrderItem": []
        }

        patch_req = MagicMock()

        ordering_client.requests.get.return_value = get_req
        ordering_client.requests.patch.return_value = patch_req

        client.update_state(order, new_state)

        ordering_client.requests.get.assert_called_once_with(
            "http://localhost:8080/productOrder/" + order["id"],
        )

        ordering_client.requests.patch.assert_called_once_with(
            "http://localhost:8080/productOrder/" + order["id"],
            json={"state": new_state, "productOrderItem": []},
        )

        get_req.raise_for_status.assert_called_once_with()
        patch_req.raise_for_status.assert_called_once_with()

    def test_get_order(self):
        client = ordering_client.OrderingClient()

        response = client.get_order("1")

        self.assertEquals({"id": "1"}, response)

        ordering_client.requests.get.assert_called_once_with(
            "http://localhost:8080/productOrder/1"
        )
        self._response.raise_for_status.assert_called_once_with()


class OrderTestCase(TestCase):
    tags = ("ordering",)

    def setUp(self):
        # Build users and organizations
        customer = User.objects.create_user("test_user")

        owner_org = Organization.objects.create(name="test_org")

        # Build offerings and contracts
        offering1 = Offering(
            pk="61004aba5e05acc115f022f0",
            off_id="1",
            owner_organization=owner_org,
            name="Offering1",
            version="1.0",
            description="Offering1",
            is_custom=False
        )

        offering2 = Offering(
            pk="61004aba5e05acc115f022f1",
            off_id="2",
            owner_organization=owner_org,
            name="Offering2",
            version="1.0",
            description="Offering2",
            is_custom=False
        )

        self._contract1 = Contract(item_id="1", product_id="3", offering=offering1.pk)

        self._contract2 = Contract(item_id="2", product_id="4", offering=offering2.pk)

        # Build order
        self._order = Order.objects.create(
            description="",
            order_id="1",
            date=datetime.utcnow(),
            customer=customer,
            state="pending",
            contracts=[self._contract1, self._contract2],
        )

    def test_get_item_contract(self):
        contract = self._order.get_item_contract("2")
        self.assertEquals(self._contract2, contract)

    def test_get_item_contract_invalid(self):
        error = None
        try:
            self._order.get_item_contract("3")
        except OrderingError as e:
            error = e

        self.assertFalse(error is None)
        self.assertEquals("OrderingError: Invalid item id", str(error))

    def test_get_product(self):
        contract = self._order.get_product_contract("4")
        self.assertEquals(self._contract2, contract)

    def test_get_product_invalid(self):
        error = None
        try:
            self._order.get_product_contract("1")
        except OrderingError as e:
            error = e

        self.assertFalse(error is None)
        self.assertEquals("OrderingError: Invalid product id", str(error))

    def test_get_contracts(self):
        contracts = self._order.get_contracts()
        self.assertEquals([self._contract1, self._contract2], contracts)

    def test_get_by_customer_bill_id_success(self):
        from wstore.store_commons.database import get_database_connection
        from bson import ObjectId

        db = get_database_connection()

        customer_bill_id = "urn:ngsi-ld:customer-bill:test-12345"

        self._contract1.customer_bill = {"id": customer_bill_id, "href": "http://example.com"}
        self._order.contracts = [self._contract1, self._contract2]
        self._order.save()

        found_order = Order.get_by_customer_bill_id(customer_bill_id)

        self.assertIsNotNone(found_order)
        self.assertEquals(self._order.order_id, found_order.order_id)
        self.assertEquals(self._order.pk, found_order.pk)

    def test_get_by_customer_bill_id_not_found(self):
        customer_bill_id = "urn:ngsi-ld:customer-bill:nonexistent-99999"

        error = None
        try:
            Order.get_by_customer_bill_id(customer_bill_id)
        except OrderingError as e:
            error = e

        self.assertIsNotNone(error)
        self.assertIn("Order not found", str(error))

    def test_get_contract_by_cb_id_success(self):
        from wstore.store_commons.database import get_database_connection

        db = get_database_connection()

        customer_bill_id = "urn:ngsi-ld:customer-bill:contract-test-456"

        self._contract2.customer_bill = {"id": customer_bill_id, "href": "http://example.com"}
        self._order.contracts = [self._contract1, self._contract2]
        self._order.save()

        found_contract = self._order.get_contract_by_cb_id(customer_bill_id)

        self.assertIsNotNone(found_contract)
        self.assertEquals(self._contract2.item_id, found_contract.item_id)
        self.assertEquals(customer_bill_id, found_contract.customer_bill["id"])

    def test_get_contract_by_cb_id_not_found(self):
        customer_bill_id = "urn:ngsi-ld:customer-bill:nonexistent-contract"

        error = None
        try:
            self._order.get_contract_by_cb_id(customer_bill_id)
        except OrderingError as e:
            error = e

        self.assertIsNotNone(error)
        self.assertIn("Order item (contract) not found", str(error))

@override_settings(
    INVENTORY="http://localhost:8080",
    RESOURCE_INVENTORY="http://localhost:9090/resourceInventory",
    SERVICE_INVENTORY="http://localhost:7070/serviceInventory"
)
class InventoryClientTestCase(TestCase):
    tags = ("inventory",)
    
    build_char_return = {
            "id": "testing_uuid",
            "name": "testing_name",
            "valueType": "testing_type",
            "value": "testing_value"
            }
    def setUp(self):
        # Mock requests
        inventory_client.requests = MagicMock()
        self.response = MagicMock()
        self.response.status_code = 201
        inventory_client.requests.post.return_value = self.response
        inventory_client.requests.get.return_value = self.response

        inventory_client.settings.LOCAL_SITE = "http://localhost:8004/"

        now = datetime(2016, 1, 22, 4, 10, 25, 176751, tzinfo=timezone.utc)
        inventory_client.datetime = MagicMock()
        inventory_client.datetime.now.return_value = now

        inventory_client.PendingTermination = MagicMock()
        inventory_client.settings.RESOURCE_CATALOG = "http://testing-resource-catalog:8080"
        inventory_client.settings.SERVICE_CATALOG = "http://testing-service-catalog:8080"
        inventory_client.settings.VERIFY_REQUESTS = True
        
    @parameterized.expand(
        [
            ("basic", [{"callback": "http://site.com/event"}]),
            ("initial", []),
            (
                "registered",
                [
                    {"callback": "http://site.com/event"},
                    {"callback": "http://localhost:8004/charging/api/orderManagement/products"},
                ],
                False,
            ),
        ]
    )
    def test_create_subscription(self, name, callbacks, created=True):
        self.response.json.return_value = callbacks

        client = inventory_client.InventoryClient()
        client.create_inventory_subscription()

        inventory_client.requests.get.assert_called_once_with(
            "http://localhost:8080/hub"
        )

        if created:
            inventory_client.requests.post.assert_called_once_with(
                "http://localhost:8080/hub",
                json={"callback": "http://localhost:8004/charging/api/orderManagement/products"},
            )
        else:
            self.assertEquals(0, inventory_client.requests.post.call_count)

    def test_create_subscription_error(self):
        self.response.json.return_value = []
        self.response.status_code = 404

        error = None
        try:
            client = inventory_client.InventoryClient()
            client.create_inventory_subscription()
        except ImproperlyConfigured as e:
            error = e

        self.assertTrue(isinstance(error, ImproperlyConfigured))
        msg = "It hasn't been possible to create inventory subscription, "
        msg += "please check that the inventory API is correctly configured "
        msg += "and that the inventory API is up and running"
        self.assertEquals(msg, str(error))

    def test_get_service(self):
        service = {"id": "service-1", "serviceSpecification": {"id": "spec-1"}}
        self.response.json.return_value = service

        result = inventory_client.InventoryClient().get_service("service-1")

        inventory_client.requests.get.assert_called_once_with(
            "http://localhost:7070/serviceInventory/service/service-1", verify=True, timeout=30
        )
        self.response.raise_for_status.assert_called_once_with()
        self.assertEqual(service, result)

    def test_get_service_http_error_propagates(self):
        error = InventoryError("service inventory unavailable")
        self.response.raise_for_status.side_effect = error

        with self.assertRaises(InventoryError) as caught:
            inventory_client.InventoryClient().get_service("service-1")

        self.assertIs(error, caught.exception)
        self.response.json.assert_not_called()

    def test_activate_product(self):
        client = inventory_client.InventoryClient()
        client.activate_product("1")

        inventory_client.requests.patch.assert_called_once_with(
            "http://localhost:8080/product/1",
            json={"status": "active", "startDate": "2016-01-22T04:10:25.176751Z"},
        )
        inventory_client.requests.patch().raise_for_status.assert_called_once_with()

    def test_suspend_product(self):
        client = inventory_client.InventoryClient()
        client.suspend_product("1")

        inventory_client.requests.patch.assert_called_once_with(
            "http://localhost:8080/product/1",
            json={"status": "suspended"},
        )
        inventory_client.requests.patch().raise_for_status.assert_called_once_with()

    def test_terminate_product(self):
        client = inventory_client.InventoryClient()
        client.terminate_product("1")

        inventory_client.requests.patch.assert_called_once_with(
            "http://localhost:8080/product/1",
            json={
                "status": "terminated",
                "terminationDate": "2016-01-22T04:10:25.176751Z",
            },
        )
        inventory_client.requests.patch().raise_for_status.assert_called_once_with()

    def test_terminate_product_with_resource_and_service(self):
        inventory_client.requests.get.return_value.json.return_value = {
            "realizingResource": [{"id": "res-1"}],
            "realizingService": [{"id": "svc-1"}],
        }
        client = inventory_client.InventoryClient()
        client.terminate_product("1")

        calls = inventory_client.requests.patch.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0], call("http://localhost:9090/resourceInventory/resource/res-1", json={"resourceStatus": "suspended"}, verify=True))
        self.assertEqual(calls[1], call("http://localhost:7070/serviceInventory/service/svc-1", json={"state": "terminated"}, verify=True))
        self.assertEqual(calls[2][0][0], "http://localhost:8080/product/1")

    def test_terminate_product_rollback(self):
        inventory_client.requests.get.return_value.json.return_value = {
            "realizingResource": [{"id": "res-1"}],
            "realizingService": [{"id": "svc-1"}],
        }
        ok_response = MagicMock()
        fail_response = MagicMock()
        fail_response.raise_for_status.side_effect = Exception("api error")
        inventory_client.requests.patch.side_effect = [ok_response, ok_response, fail_response, ok_response, ok_response]

        client = inventory_client.InventoryClient()
        with self.assertRaises(inventory_client.InventoryError):
            client.terminate_product("1")

        calls = inventory_client.requests.patch.call_args_list
        self.assertEqual(len(calls), 5)
        self.assertEqual(calls[3], call("http://localhost:9090/resourceInventory/resource/res-1", json={"resourceStatus": "reserved"}, verify=True))
        self.assertEqual(calls[4], call("http://localhost:7070/serviceInventory/service/svc-1", json={"state": "reserved"}, verify=True))

    def test_get_product(self):
        client = inventory_client.InventoryClient()
        client.get_product("1")

        inventory_client.requests.get.assert_called_once_with(
            "http://localhost:8080/product/1"
        )
        inventory_client.requests.get().raise_for_status.assert_called_once_with()

    @parameterized.expand([("all", {}, ""), ("filtered", {"id": "1,2,3"}, "?id=1,2,3")])
    def test_get_products(self, name, query, qs):
        client = inventory_client.InventoryClient()
        products = client.get_products(query=query)

        inventory_client.requests.get.assert_called_once_with(
            "http://localhost:8080/product" + qs
        )
        inventory_client.requests.get().raise_for_status.assert_called_once_with()

        self.assertEquals(inventory_client.requests.get().json(), products)
    
    @parameterized.expand([("32", [{'id': 'party:1', 'role': 'Seller'}], {
        "name": "resource",
        "description": "testing",
        "resourceSpecCharacteristic": [{
            "resourceSpecCharacteristicValue": [{
                "value": "testing_value"
            }]
        }]
        
    })])
    def test_create_resource(self, spec_id, party, spec_res):
        inventory_client.urlparse = MagicMock()
        inventory_client.urlparse.return_value.scheme = "scheme"
        inventory_client.urlparse.return_value.netloc = "netloc"
        inventory_client.urlparse.return_value.path = "path"
        now_mock = MagicMock()
        now_mock.isoformat.return_value = "2024-03-19T11:49:50+00:00"
        inventory_client.datetime.now.return_value = now_mock

        operator_party = {'id': 'operator:1', 'role': 'SellerOperator'}
        inventory_client.get_operator_party_roles = MagicMock()
        inventory_client.get_operator_party_roles.return_value = [operator_party]
        inventory_client.normalize_party_ref = MagicMock()
        norm_party = {'id': 'party:1', 'role': 'Seller'}
        inventory_client.normalize_party_ref.side_effect = [norm_party, operator_party]

        client = inventory_client.InventoryClient()
        client.download_spec = MagicMock()
        client.download_spec.return_value = spec_res
        client.build_inventory_char = MagicMock()
        client.build_inventory_char.return_value = self.build_char_return
        client.create_resource(spec_id, party + [operator_party])

        expected_calls_post = [call("http://localhost:9090/resourceInventory/resource", json={
            "resourceSpecification": {
                "id": spec_id,
                "href": spec_id,
                "name": spec_res["name"],
            },
            "resourceCharacteristic": [self.build_char_return for _ in spec_res["resourceSpecCharacteristic"]],
            "relatedParty": [norm_party, operator_party],
            "resourceStatus": "reserved",
            "startOperatingDate": "2024-03-19T11:49:50Z",
            "name": spec_res["name"],
            "description": spec_res["description"]
            
            }, verify = inventory_client.settings.VERIFY_REQUESTS)]
        client.build_inventory_char.assert_called_once()
        inventory_client.requests.post.assert_has_calls(expected_calls_post, any_order=True)

        
    @parameterized.expand([("32", [{'id': 'party:1', 'role': 'Seller'}], {
        "name": "service",
        "description": "testing",
        "specCharacteristic": [{
            "characteristicValueSpecification": [{
                "value": "testing_value"
            }]
        }]
        
    })])
    def test_create_service(self, spec_id, party, spec_serv):
        inventory_client.urlparse = MagicMock()
        inventory_client.urlparse.return_value.scheme = "scheme"
        inventory_client.urlparse.return_value.netloc = "netloc"
        inventory_client.urlparse.return_value.path = "path"
        now_mock = MagicMock()
        now_mock.isoformat.return_value = "2024-03-19T11:49:50+00:00"
        inventory_client.datetime.now.return_value = now_mock

        operator_party = {'id': 'operator:1', 'role': 'SellerOperator'}
        inventory_client.get_operator_party_roles = MagicMock()
        inventory_client.get_operator_party_roles.return_value = [operator_party]
        norm_party = {'id': 'party:1', 'role': 'Seller'}
        inventory_client.normalize_party_ref = MagicMock(side_effect=[norm_party, operator_party])

        client = inventory_client.InventoryClient()
        client.download_spec = MagicMock()
        client.download_spec.return_value = spec_serv
        client.build_inventory_char = MagicMock()
        client.build_inventory_char.return_value = self.build_char_return
        client.create_service(spec_id, party + [operator_party])

        expected_calls_post = [call("http://localhost:7070/serviceInventory/service", json={
            "serviceSpecification": {
                "id": spec_id,
                "href": spec_id,
                "name": spec_serv["name"],
            },
            "serviceCharacteristic": [self.build_char_return for _ in spec_serv["specCharacteristic"]],
            "relatedParty": [norm_party, operator_party],
            "state": "reserved",
            "startDate": "2024-03-19T11:49:50Z",
            "name": spec_serv["name"],
            "description": spec_serv["description"]
            
            }, verify = inventory_client.settings.VERIFY_REQUESTS)]
        client.build_inventory_char.assert_called_once()
        inventory_client.requests.post.assert_has_calls(expected_calls_post, any_order=True)

    def test_inventory_creation_includes_specification_references_without_version(self):
        cases = (
            ("resource", "resourceSpecCharacteristic", "resourceInventory", "9090"),
            ("service", "specCharacteristic", "serviceInventory", "7070"),
        )
        for kind, characteristic_field, inventory_path, port in cases:
            spec_id = kind + "-specification-1"
            reference_field = kind + "Specification"

            for metadata in (
                {"name": kind + " specification", "href": "urn:ngsi-ld:" + reference_field + ":" + spec_id},
                {},
                {"href": ""},
            ):
                with self.subTest(kind=kind, metadata=metadata):
                    specification = {
                        "id": spec_id,
                        "version": "2.0",
                        characteristic_field: [],
                        **metadata,
                    }
                    original = deepcopy(specification)
                    client = inventory_client.InventoryClient()
                    inventory_client.requests.post.reset_mock()
                    self.response.json.return_value = {"id": kind + "-inventory-1"}

                    with patch.object(client, "download_spec", return_value=specification) as download:
                        result = getattr(client, "create_" + kind)(spec_id, [])

                    download.assert_called_once_with(kind + "_catalog", "/" + reference_field, spec_id)
                    inventory_client.requests.post.assert_called_once()
                    args, kwargs = inventory_client.requests.post.call_args
                    self.assertEqual((f"http://localhost:{port}/{inventory_path}/{kind}",), args)
                    self.assertTrue(kwargs["verify"])
                    reference = kwargs["json"][reference_field]
                    expected = {"id": spec_id, "href": metadata.get("href") or spec_id}
                    if "name" in metadata:
                        expected["name"] = metadata["name"]
                    self.assertEqual(expected, reference)
                    self.assertNotIn("version", reference)
                    self.assertEqual(kind + "-inventory-1", result)
                    self.assertEqual(original, specification)

    def test_single_primitive_value_is_copied_as_an_inventory_string(self):
        client = inventory_client.InventoryClient()

        for value, expected in (("file-id", "file-id"), (False, "False"), (12, "12"), (1.5, "1.5")):
            with self.subTest(value=value):
                specification = {
                    "name": "example",
                    "characteristicValueSpecification": [{"value": value}],
                }
                original = deepcopy(specification)

                characteristic = client.build_inventory_char(specification, "characteristicValueSpecification")

                self.assertEqual(expected, characteristic["value"])
                self.assertEqual("string", characteristic["valueType"])
                self.assertEqual(original, specification)

    def test_multiple_values_use_the_marked_default(self):
        client = inventory_client.InventoryClient()
        specification = {
            "name": "region",
            "characteristicValueSpecification": [
                {"value": "EU"},
                {"value": "US", "isDefault": True},
                {"value": "APAC", "isDefault": False},
            ],
        }

        characteristic = client.build_inventory_char(specification, "characteristicValueSpecification")

        self.assertEqual("US", characteristic["value"])

    def test_range_and_unit_conversion_is_preserved(self):
        client = inventory_client.InventoryClient()
        specification = {
            "name": "capacity",
            "characteristicValueSpecification": [{"valueFrom": 1, "valueTo": 10, "unitOfMeasure": "GB"}],
        }

        characteristic = client.build_inventory_char(specification, "characteristicValueSpecification")

        self.assertEqual("1 - 10 GB", characteristic["value"])

    def test_service_creation_keeps_file_and_category_ids_as_strings(self):
        client = inventory_client.InventoryClient()
        specification = {
            "specCharacteristic": [
                {"name": "Service Type", "characteristicValueSpecification": [{"value": "category-1"}]},
                {"name": "File", "characteristicValueSpecification": [{"value": "507f1f77bcf86cd799439011"}]},
            ],
        }
        original = deepcopy(specification)
        self.response.json.return_value = {"id": "service-1"}

        with patch.object(client, "download_spec", return_value=specification):
            self.assertEqual("service-1", client.create_service("specification-1", []))

        service = inventory_client.requests.post.call_args.kwargs["json"]
        values = {
            characteristic["name"]: characteristic["value"] for characteristic in service["serviceCharacteristic"]
        }
        self.assertEqual({"Service Type": "category-1", "File": "507f1f77bcf86cd799439011"}, values)
        self.assertTrue(
            all(characteristic["valueType"] == "string" for characteristic in service["serviceCharacteristic"])
        )
        self.assertEqual(original, specification)


    @parameterized.expand(
        [
            ("services", "iter_services", "http://localhost:7070/serviceInventory/service"),
            ("products", "iter_products", "http://localhost:8080/product"),
        ]
    )
    def test_inventory_search_passes_encoded_query_parameters(self, name, method, url):
        self.response.json.return_value = [{"id": "match"}]
        query = {"relatedParty.id": "urn:party:customer&name=other", "status": "active"}

        entries = list(getattr(inventory_client.InventoryClient(), method)(query=query))

        self.assertEqual([{"id": "match"}], entries)
        inventory_client.requests.get.assert_called_once_with(
            url, params={**query, "offset": 0, "limit": 100}, verify=True, timeout=30
        )
        self.response.raise_for_status.assert_called_once_with()
        self.assertNotIn("offset", query)


    def test_inventory_search_continues_through_filtered_pages(self):
        self.response.json.side_effect = [[{"id": str(i)} for i in range(100)], [{"id": "last-match"}]]
        query = {"serviceCharacteristic.value": "file-id"}

        entries = list(inventory_client.InventoryClient().iter_services(query=query))

        self.assertEqual(101, len(entries))
        self.assertEqual("last-match", entries[-1]["id"])
        self.assertEqual([0, 100], [c.kwargs["params"]["offset"] for c in inventory_client.requests.get.call_args_list])
        self.assertTrue(
            all(
                c.kwargs["params"]["serviceCharacteristic.value"] == "file-id"
                for c in inventory_client.requests.get.call_args_list
            )
        )


    def test_inventory_search_stops_fetching_when_the_caller_has_a_match(self):
        self.response.json.return_value = [{"id": str(i)} for i in range(100)]
        entries = inventory_client.InventoryClient().iter_products(query={"realizingService.id": "service-1"})

        self.assertEqual({"id": "0"}, next(entries))
        self.assertEqual(1, inventory_client.requests.get.call_count)


    def test_inventory_search_rejects_an_invalid_collection(self):
        self.response.json.return_value = {"error": "not a collection"}

        with self.assertRaises(InventoryError):
            list(inventory_client.InventoryClient().iter_services())


    def test_inventory_search_propagates_http_errors(self):
        from requests.exceptions import HTTPError

        self.response.raise_for_status.side_effect = HTTPError("offline")

        with self.assertRaises(HTTPError):
            list(inventory_client.InventoryClient().iter_products())

class NotifyItemCompletedTestCase(TestCase):
    tags = ("ordering", "notify-item")

    def setUp(self):
        patcher = patch.object(ordering_management, "on_product_activation")
        self.on_product_activation = patcher.start()
        self.addCleanup(patcher.stop)

        ordering_management.Order = MagicMock()

        # Mock order model
        self._order_model = MagicMock()
        self._order_model.sales_ids = ["sale_123", "sale_456"]
        self._order_model.mark_contract_as_processed = MagicMock()
        self._order_model.get_contracts.return_value = []
        ordering_management.Order.objects.get.return_value = self._order_model

        # Mock contract
        self._contract = MagicMock()
        self._contract.item_id = "item_1"
        self._contract.customer_bill = {"id": "cb_123", "href": "http://cb.com/123"}
        self._contract.product_id = None

        # Mock raw order
        self._raw_order = {
            "id": "order_123",
            "billingAccount": {"id": "ba_123"},
            "productOrderItem": [
                {
                    "id": "item_1",
                    "state": "inProgress",
                    "productOffering": {"id": "offering_1"},
                    "product": {}
                }
            ]
        }

        # Mock OrderingClient
        ordering_management.OrderingClient = MagicMock()
        self._ordering_client_inst = MagicMock()
        ordering_management.OrderingClient.return_value = self._ordering_client_inst

        # Mock InventoryClient
        ordering_management.InventoryClient = MagicMock()
        self._inventory_client_inst = MagicMock()
        ordering_management.InventoryClient.return_value = self._inventory_client_inst

        # Mock BillingClient
        ordering_management.BillingClient = MagicMock()
        self._billing_client_inst = MagicMock()
        ordering_management.BillingClient.return_value = self._billing_client_inst

        # Mock requests
        ordering_management.requests = MagicMock()
        self._response = MagicMock()
        self._response.status_code = 200
        ordering_management.requests.get.return_value = self._response

    def _offering_automatic(self):
        return {
            "id": "offering_1",
            "name": "Test Offering",
            "productOfferingTerm": [
                {"name": "procurement", "description": "automatic"}
            ]
        }

    def _offering_manual(self):
        return {
            "id": "offering_1",
            "name": "Test Offering",
            "productOfferingTerm": [
                {"name": "procurement", "description": "manual"}
            ]
        }

    def _offering_no_terms(self):
        return {
            "id": "offering_1",
            "name": "Test Offering"
        }

    @parameterized.expand([
        (
            "automatic_procurement",
            _offering_automatic,
            True,
            "completed"
        ),
        (
            "manual_procurement",
            _offering_manual,
            False,
            None
        ),
        (
            "no_terms",
            _offering_no_terms,
            True,
            "completed"
        ),
        (
            "multiple_items_partial",
            _offering_automatic,
            True,
            "inProgress",
            [
                {"id": "item_1", "state": "inProgress"},
                {"id": "item_2", "state": "inProgress"}
            ]
        ),
        (
            "all_completed",
            _offering_automatic,
            True,
            "completed",
            [
                {"id": "item_1", "state": "completed"}
            ]
        ),
        (
            "with_cancelled",
            _offering_automatic,
            True,
            "partial",
            [
                {"id": "item_1", "state": "inProgress"},
                {"id": "item_2", "state": "cancelled"}
            ]
        ),
    ])
    def test_notify_item_completed(
        self,
        name,
        offering_getter,
        should_process,
        expected_root_state,
        order_items=None
    ):
        # Setup offering response
        offering = offering_getter(self)
        self._response.json.return_value = offering

        # Setup order items if provided
        if order_items:
            self._raw_order["productOrderItem"] = order_items

        # Setup inventory client response
        self._inventory_client_inst.build_product_model.return_value = {
            "id": "product_123",
            "productOffering": {"id": "offering_1"},
            "relatedParty": []
        }
        self._inventory_client_inst.get_product_for_patch.return_value = {
            "id": "product_123",
            "productOffering": {"id": "offering_1"},
            "relatedParty": []
        }
        self._inventory_client_inst.patch_product.return_value = {
            "id": "product_123",
            "productOffering": {"id": "offering_1"}
        }

        # Mock activate_product
        ordering_manager = ordering_management.OrderingManager()
        ordering_manager.activate_product = MagicMock()
        ordering_manager.complete_inventory_product = MagicMock()
        ordering_manager.complete_inventory_product.return_value = {
            "id": "product_123",
            "productOffering": {"id": "offering_1"}
        }

        # Execute
        ordering_manager.notify_item_completed(
            self._order_model,
            self._contract,
            self._raw_order
        )

        # Verify offering was fetched
        ordering_management.requests.get.assert_called_once()

        if should_process:
            # Verify inventory product was created
            ordering_manager.complete_inventory_product.assert_called_once()

            # Verify billing was updated
            self._billing_client_inst.set_customer_bill.assert_called_once_with(
                "settled",
                "cb_123"
            )

            # Verify product was activated
            ordering_manager.activate_product.assert_called_once_with(
                self._raw_order["id"],
                {"id": "product_123", "productOffering": {"id": "offering_1"}}
            )

            # Verify contract was marked as processed
            self._order_model.mark_contract_as_processed.assert_called_once_with(
                self._contract.item_id
            )

            # Verify ordering client was called with correct state
            if expected_root_state:
                self._ordering_client_inst.update_items_state.assert_called_once()
                call_args = self._ordering_client_inst.update_items_state.call_args
                self.assertEqual(call_args[1]["root_state"], expected_root_state)
        else:
            # For manual procurement, only contract should be marked as processed
            self._order_model.mark_contract_as_processed.assert_called_once_with(
                self._contract.item_id
            )

            # No inventory or billing operations should occur
            ordering_manager.complete_inventory_product.assert_not_called()
            self._billing_client_inst.set_customer_bill.assert_not_called()
            ordering_manager.activate_product.assert_not_called()

    def test_notify_item_completed_with_internal_bill(self):
        # Setup for internal customer bill (should not be updated)
        self._contract.customer_bill = {
            "id": "cb_internal",
            "href": "http://cb.com/internal",
            "internal": True
        }

        offering = self._offering_automatic()
        self._response.json.return_value = offering

        # Setup inventory client
        self._inventory_client_inst.patch_product.return_value = {
            "id": "product_123",
            "productOffering": {"id": "offering_1"}
        }

        ordering_manager = ordering_management.OrderingManager()
        ordering_manager.activate_product = MagicMock()
        ordering_manager.complete_inventory_product = MagicMock()
        ordering_manager.complete_inventory_product.return_value = {
            "id": "product_123",
            "productOffering": {"id": "offering_1"}
        }

        # Execute
        ordering_manager.notify_item_completed(
            self._order_model,
            self._contract,
            self._raw_order
        )

        # Verify internal bill was NOT updated
        self._billing_client_inst.set_customer_bill.assert_not_called()

        # But product should still be activated
        ordering_manager.activate_product.assert_called_once()

    def test_notify_completed_with_external_bill(self):
        self._order_model.get_contracts.return_value = [self._contract]

        raw_order = deepcopy(self._raw_order)
        raw_order["productOrderItem"][0]["productOffering"] = {"href": "offering_1"}
        self._response.json.return_value = self._offering_automatic()

        ordering_manager = ordering_management.OrderingManager()
        ordering_manager.activate_product = MagicMock()
        ordering_manager.complete_inventory_product = MagicMock()
        ordering_manager.complete_inventory_product.return_value = {
            "id": "product_123",
            "productOffering": {"id": "offering_1"}
        }

        ordering_manager.notify_completed(raw_order)

        self._billing_client_inst.set_customer_bill.assert_called_once_with(
            "settled",
            "cb_123"
        )
        ordering_manager.activate_product.assert_called_once_with(
            raw_order["id"],
            {"id": "product_123", "productOffering": {"id": "offering_1"}}
        )

    def test_notify_completed_with_internal_bill(self):
        self._contract.customer_bill = {
            "id": "cb_internal",
            "href": "http://cb.com/internal",
            "internal": True
        }
        self._order_model.get_contracts.return_value = [self._contract]

        raw_order = deepcopy(self._raw_order)
        raw_order["productOrderItem"][0]["productOffering"] = {"href": "offering_1"}
        self._response.json.return_value = self._offering_automatic()

        ordering_manager = ordering_management.OrderingManager()
        ordering_manager.activate_product = MagicMock()
        ordering_manager.complete_inventory_product = MagicMock()
        ordering_manager.complete_inventory_product.return_value = {
            "id": "product_123",
            "productOffering": {"id": "offering_1"}
        }

        ordering_manager.notify_completed(raw_order)

        self._billing_client_inst.set_customer_bill.assert_not_called()
        ordering_manager.activate_product.assert_called_once_with(
            raw_order["id"],
            {"id": "product_123", "productOffering": {"id": "offering_1"}}
        )

    def test_notify_item_completed_without_customer_bill_id(self):
        # Setup contract without customer bill id
        self._contract.customer_bill = {"href": "http://cb.com/123"}

        offering = self._offering_automatic()
        self._response.json.return_value = offering

        # Setup inventory client
        self._inventory_client_inst.patch_product.return_value = {
            "id": "product_123",
            "productOffering": {"id": "offering_1"}
        }

        ordering_manager = ordering_management.OrderingManager()
        ordering_manager.activate_product = MagicMock()
        ordering_manager.complete_inventory_product = MagicMock()
        ordering_manager.complete_inventory_product.return_value = {
            "id": "product_123",
            "productOffering": {"id": "offering_1"}
        }

        # Execute
        ordering_manager.notify_item_completed(
            self._order_model,
            self._contract,
            self._raw_order
        )

        # Verify billing was NOT called (no id)
        self._billing_client_inst.set_customer_bill.assert_not_called()

        # But product should still be activated
        ordering_manager.activate_product.assert_called_once()

    @parameterized.expand(
        [
            (path + "_" + mode, path, mode)
            for path in ("batch", "item")
            for mode in ("automatic", "manual", "payment-automatic", "missing")
        ]
    )
    def test_activation_dispatch_respects_procurement(self, name, path, mode):
        manager, product = self._prepare_activation_completion(mode)
        sequence = MagicMock()
        sequence.attach_mock(manager.activate_product, "activate")
        sequence.attach_mock(self.on_product_activation, "notify")
        sequence.attach_mock(self._order_model.mark_contract_as_processed, "processed")

        self._run_activation_completion(manager, path)

        if mode == "automatic":
            self.on_product_activation.assert_called_once_with(product, self._raw_order, self._contract)
            self.assertEqual(["activate", "notify", "processed"], [entry[0] for entry in sequence.mock_calls])
        else:
            self.on_product_activation.assert_not_called()

    def _prepare_activation_completion(self, mode="automatic"):
        offering = self._offering_no_terms()
        if mode != "missing":
            offering["productOfferingTerm"] = [{"name": "procurement", "description": mode}]
        self._response.json.return_value = offering
        self._raw_order["productOrderItem"][0]["productOffering"]["href"] = "offering_1"
        self._order_model.get_contracts.return_value = [self._contract]
        product = {
            "id": "product_123",
            "productOffering": {"id": "offering_1"},
            "realizingService": [{"id": "service-1"}],
            "relatedParty": [
                {"id": "buyer-party", "role": "Buyer"},
                {"id": "operator-party", "role": "SellerOperator"},
                {"id": "seller-party", "role": "sElLeR"},
            ],
        }
        manager = ordering_management.OrderingManager()
        manager.complete_inventory_product = MagicMock(return_value=product)
        manager.activate_product = MagicMock()
        return manager, product

    def _run_activation_completion(self, manager, path):
        if path == "batch":
            manager.notify_completed(self._raw_order)
        else:
            manager.notify_item_completed(self._order_model, self._contract, self._raw_order)

    def test_batch_passes_each_product_and_contract_to_dispatcher(self):
        manager, first = self._prepare_activation_completion()
        second_contract = MagicMock(item_id="item_2", customer_bill={"id": "cb_456"})
        second = deepcopy(first)
        second["id"] = "product_456"
        second["relatedParty"] = [{"id": "other-seller", "role": "Seller"}]
        second["realizingService"] = [{"id": "service-2"}]
        self._raw_order["productOrderItem"].append(
            {"id": "item_2", "productOffering": {"href": "offering_2"}, "state": "inProgress"}
        )
        self._order_model.get_contracts.return_value = [self._contract, second_contract]
        manager.complete_inventory_product.side_effect = [first, second]

        self._run_activation_completion(manager, "batch")

        self.assertEqual(
            [
                call(first, self._raw_order, self._contract),
                call(second, self._raw_order, second_contract),
            ],
            self.on_product_activation.call_args_list,
        )
        self.assertEqual(2, self._order_model.mark_contract_as_processed.call_count)

    @parameterized.expand([("batch",), ("item",)])
    def test_real_dispatcher_continues_after_plugin_failure(self, path):
        from wstore.asset_manager.resource_plugins import decorators

        manager, product = self._prepare_activation_completion()
        product["realizingService"].append({"id": "service-2"})
        services = {
            f"service-{n}": {
                "id": f"service-{n}",
                "serviceCharacteristic": [{"name": "Service Type", "value": f"category-{n}"}],
            }
            for n in (1, 2)
        }
        inventory = MagicMock()
        inventory.get_service.side_effect = services.__getitem__
        plugins = {"category-1": MagicMock(), "category-2": MagicMock()}
        provider, buyer = object(), object()
        organizations = {"seller-party": provider, "buyer-party": buyer}
        plugins["category-1"].on_service_activation.side_effect = RuntimeError("provisioning failed")
        with patch.object(
            ordering_management, "on_product_activation", decorators.on_product_activation
        ), patch.object(decorators, "InventoryClient", return_value=inventory), patch.object(
            decorators, "_get_plugin_model", side_effect=lambda category_id: category_id
        ), patch.object(
            decorators, "_load_plugin_model", side_effect=plugins.get
        ), patch.object(
            decorators.Organization.objects, "get", side_effect=lambda actor_id: organizations[actor_id]
        ), self.assertLogs(
            "wstore.default_logger", level="ERROR"
        ):
            self._run_activation_completion(manager, path)

        for n in (1, 2):
            plugins[f"category-{n}"].on_service_activation.assert_called_once_with(
                provider,
                buyer,
                services[f"service-{n}"],
                product,
                self._raw_order,
                self._contract,
            )
        self._order_model.mark_contract_as_processed.assert_called_once_with(self._contract.item_id)
        self._ordering_client_inst.update_items_state.assert_called_once()
