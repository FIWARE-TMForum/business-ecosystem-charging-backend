from django.test.testcases import TestCase
from wstore.asset_manager import offering_validator, service_validator
from mock import MagicMock, call
import wstore.asset_manager.resource_plugins.decorators
import wstore.ordering.models
from wstore.asset_manager import offering_validator, product_validator, catalog_validator
from importlib import reload
from wstore.asset_manager.test.product_validator_test_data import *
from wstore.asset_manager.test.service_validator_test_data import *
from bson import ObjectId
from parameterized import parameterized

class ValidatorTestCase(TestCase):
    tags = ("offering-validator", )
    
    def _mock_validator_imports(self, module):
        pass
        
    
    def setUp(self):
        reload(offering_validator)
        reload(catalog_validator)
        reload(wstore.asset_manager.resource_plugins.decorators)
        self._provider = MagicMock()
        
        self._asset_instance = MagicMock(name="asset_instance")
        self._asset_instance.resource_type = "Widget"
        self._asset_instance.content_type = "application/x-widget"
        self._asset_instance.provider = self._provider
        self._asset_instance.service_spec_id = None
        self._asset_instance.is_public = False
        self._asset_instance.pk = ObjectId("61004aba5e05acc115f022f0")
        wstore.asset_manager.resource_plugins.decorators.Resource.objects = MagicMock()
        wstore.asset_manager.resource_plugins.decorators.Resource.objects.filter.return_value = [self._asset_instance]
        wstore.asset_manager.resource_plugins.decorators.Resource.objects.create.return_value = self._asset_instance
        
        self._plugin_instance = MagicMock()
        self._plugin_instance.media_types = ["application/x-widget"]
        self._plugin_instance.formats = ["FILE"]
        self._plugin_instance.module = "wstore.asset_manager.resource_plugins.plugin.Plugin"
        self._plugin_instance.form = {}
        self._plugin_instance.name = "Widget"
        wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects = MagicMock()
        wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.get.return_value = self._plugin_instance

        # Mock Site
        product_validator.settings.CATALOG = "http://testlocation.org/"

    def tearDown(self):
        reload(offering_validator)
        reload(catalog_validator)
        reload(wstore.asset_manager.resource_plugins.decorators)
    
    
    
    def _validate_offering_calls(self, offering, service_spec_id, assets, is_digital, is_open=False, is_custom=False):
        # Check resource retrieving if needed
        offering_validator.Resource.objects.filter.assert_called_once_with(
            service_spec_id=service_spec_id
        )

        # Check offering creation
        offering_validator.Offering.objects.create.assert_called_once_with(
            owner_organization=self._provider,
            name=offering["name"],
            description="",
            version=offering["version"],
            is_open=is_open,
            is_custom=is_custom,
            bundled_offerings=[]
        )
        self.offering.save.assert_called_once()
        self.offering.asset.set.assert_called_once_with(assets)

    def _validate_single_offering_calls(self, offering, service_spec_id):
        self._validate_offering_calls(offering, service_spec_id, [self._asset_instance], True)

    def _validate_physical_offering_calls(self, offering, service_spec_id):
        self._validate_offering_calls(offering, service_spec_id, [], False)

    def _validate_bundle_offering_calls(self, offering, is_open=False):
        self.assertEquals(
            [call(off_id=off["id"]) for off in offering["bundledProductOffering"]],
            offering_validator.Offering.objects.filter.call_args_list,
        )

        # Validate offering creation
        offering_validator.Offering.objects.create.assert_called_once_with(
            owner_organization=self._provider,
            name=offering["name"],
            description="",
            version=offering["version"],
            is_open=is_open,
            is_custom=False,
            bundled_offerings=[off[0].pk for off in self._bundles],
        )
        self.offering.save.assert_called_once()
        self.offering.asset.set.assert_called_once_with([])

    def _validate_bundle_digital_offering_calls(self, offering, _):
        self._validate_bundle_offering_calls(offering)

    def _validate_bundle_physical_offering_calls(self, offering, _):
        self._validate_bundle_offering_calls(offering)

    def _validate_open_offering_calls(self, offering, service_spec_id):
        self._validate_offering_calls(offering, service_spec_id, [self._asset_instance], True, is_open=True)
        self.assertTrue(self._asset_instance.is_public)
        self._asset_instance.save.assert_called_once_with()

    def _validate_open_bundle_calls(self, offering, _):
        self._validate_bundle_offering_calls(offering, True)

    def _validate_custom_pricing_calls(self, offering, service_spec_id):
        self._validate_offering_calls(offering, service_spec_id, [self._asset_instance], True, False, True)

    def _mock_product_spec_request(self, id):
        product_spec = deepcopy(BASIC_PRODUCT["product"])
        product_spec["id"] = id
        resp = MagicMock()
        resp.json.return_value = [product_spec]
        resp.status_code = 200

        catalog_validator.requests = MagicMock()
        catalog_validator.requests.get.return_value = resp

    def _mock_offering_bundle(self, offering):
        wstore.ordering.models.Offering.objects = MagicMock()

        self._bundles = (
            []
            if "bundledProductOffering" not in offering
            else [[MagicMock(id=off["id"])] for off in offering["bundledProductOffering"]]
        )

    def _non_digital_offering(self):
        offering_validator.Resource.objects.filter.return_value = []

    def _non_digital_bundle(self):
        self._mock_offering_bundle(BUNDLE_OFFERING)

    def _invalid_bundled(self):
        offering_validator.Offering.objects.filter.side_effect = None
        offering_validator.Offering.objects.filter.return_value = []

    def _open_bundled(self):
        for bundle_resp in self._bundles:
            for bundle in bundle_resp:
                bundle.is_open = True

    def _open_existing(self):
        offering_responses = [bund for bund in self._bundles]
        offering_responses.append([MagicMock(id="6"), MagicMock(id="8")])
        offering_validator.Offering.objects.filter.side_effect = offering_responses

    def _catalog_api_error(self):
        offering_validator.requests.get.status_code = 500

    def _non_open_bundled(self):
        for bundle_resp in self._bundles:
            for bundle in bundle_resp:
                bundle.is_open = False

    @parameterized.expand(
        [
            ("valid_pricing", BASIC_OFFERING, _validate_single_offering_calls, None),
            (
                "zero_offering",
                ZERO_OFFERING,
                None,
                None,
                "Invalid price, it must be greater than zero.",
            ),
            (
                "free_offering",
                FREE_OFFERING,
                _validate_physical_offering_calls,
                _non_digital_offering,
            ),
            (
                "bundle_offering",
                BUNDLE_OFFERING,
                _validate_bundle_digital_offering_calls,
                None,
            ),
            # ("open_offering", OPEN_OFFERING, _validate_open_offering_calls, None),
            # ("open_bundle", OPEN_BUNDLE, _validate_open_bundle_calls, _open_bundled),
            ("custom_pricing", CUSTOM_PRICING_OFFERING, _validate_custom_pricing_calls, None),
            ("custom_pricing_multiple", CUSTOM_PRICING_OFFERING_MULTIPLE, _validate_custom_pricing_calls, None),
            (
                "missing_type",
                MISSING_PRICETYPE,
                None,
                None,
                "Missing required field priceType in productOfferingPrice",
            ),
            (
                "invalid_type",
                INVALID_PRICETYPE,
                None,
                None,
                "Invalid priceType, it must be one time, recurring, usage, or custom",
            ),
            (
                "missing_charge_period",
                MISSING_PERIOD,
                None,
                None,
                "Missing required field recurringChargePeriod for recurring priceType",
            ),
            (
                "invalid_period",
                INVALID_PERIOD,
                None,
                None,
                "Unrecognized recurringChargePeriod: invalid",
            ),
            (
                "missing_price",
                MISSING_PRICE,
                None,
                None,
                "Missing required field price in productOfferingPrice",
            ),
            (
                "missing_currency",
                MISSING_CURRENCY,
                None,
                None,
                "Missing currency code in price",
            ),
            (
                "invalid_currency",
                INVALID_CURRENCY,
                None,
                None,
                "Unrecognized currency: invalid",
            ),
            (
                "missing_name",
                MISSING_NAME,
                None,
                None,
                "Missing required field name in productOfferingPrice",
            ),
            (
                "multiple_names",
                MULTIPLE_NAMES,
                None,
                None,
                "Price plans names must be unique (Plan)",
            ),
            (
                "bundle_missing",
                BUNDLE_MISSING_FIELD,
                None,
                None,
                "Offering bundles must contain a bundledProductOffering field",
            ),
            (
                "bundle_invalid_number",
                BUNDLE_MISSING_ELEMS,
                None,
                None,
                "Offering bundles must contain at least two bundled offerings",
            ),
            (
                "bundle_inv_bundled",
                BUNDLE_OFFERING,
                None,
                _invalid_bundled,
                "The bundled offering 6 is not registered",
            ),
            (
                "open_mixed",
                OPEN_MIXED,
                None,
                None,
                "Open offerings cannot include price plans",
            ),
            (
                "custom_pricing_error",
                CUSTOM_MULTIPLE,
                None,
                None,
                "Custom pricing offerings cannot include processed price plans",
            ),
            # (
            #     "open_multiple_offers",
            #     OPEN_OFFERING,
            #     None,
            #     _open_existing,
            #     "Assets of open offerings cannot be monetized in other offerings",
            # ),
            # (
            #     "open_non_digital",
            #     OPEN_OFFERING,
            #     None,
            #     _non_digital_offering,
            #     "Non digital products cannot be open",
            # ),
            # (
            #     "open_bundle_mixed",
            #     OPEN_BUNDLE,
            #     None,
            #     _non_open_bundled,
            #     "If a bundle is open all the bundled offerings must be open",
            # ),
        ]
    )
    def test_create_offering_validation(self, name, offering, checker, side_effect, msg=None):
        
        self._mock_product_spec_request(OFFER_PS_ID)
        self._mock_offering_bundle(offering)
        # Add the extra call for open search
        offering_responses = []
        offering_responses = [bund for bund in self._bundles]
        offering_responses.append([])
        wstore.ordering.models.Offering.objects.filter.side_effect = offering_responses
        self.offering = MagicMock(name = "offer")
        wstore.ordering.models.Offering.objects.create.return_value = self.offering
        if side_effect is not None:
            side_effect(self)

        error = None
        try:
            validator = offering_validator.OfferingValidator()
            validator.validate("create", self._provider, offering)
        except Exception as e:
            error = e

        if msg is not None:
            self.assertTrue(isinstance(error, ValueError))
            self.assertEquals(msg, str(error))
        else:
            self.assertEquals(error, None)

            # Validate calls
            checker(self, offering, "id")

    def test_offering_attachment(self):
        offering = MagicMock()
        offering_validator.Offering = MagicMock()
        offering_validator.Offering.objects.filter.return_value = [offering]

        validator = offering_validator.OfferingValidator()
        validator.validate("attach", self._provider, BASIC_OFFERING)

        self.assertEquals(BASIC_OFFERING["href"], offering.href)
        self.assertEquals(BASIC_OFFERING["id"], offering.off_id)

        offering.save.assert_called_once_with()

    def test_offering_attachment_missing(self):
        offering_validator.Offering = MagicMock()
        offering_validator.Offering.objects.filter.return_value = []

        error = None
        try:
            validator = offering_validator.OfferingValidator()
            validator.validate("attach", self._provider, BASIC_OFFERING)
        except ValueError as e:
            error = e

        self.assertEquals("The specified offering has not been registered", str(error))

    # def _mock_non_attached(self):
    #     self._asset_instance.product_id = None

    # def _mock_non_upgraded(self):
    #     self._asset_instance.product_id = BASIC_PRODUCT["product"]["id"]
    #     self._asset_instance.state = "upgrading"
    #     self._asset_instance.resource_path = ""
    #     self._asset_instance.old_versions = [
    #         MagicMock(
    #             version="1.0",
    #             content_type="type",
    #             resource_path="/old/path",
    #             download_link="http://host/old/path",
    #         )
    #     ]

    # def _mock_attached(self):
    #     self._asset_instance.product_id = BASIC_PRODUCT["product"]["id"]

    # def _mock_wrong_product(self):
    #     self._asset_instance.product_id = "10"
    #     self._asset_instance.resource_path = "/new/path"

    # def _validate_non_attached(self):
    #     self._asset_instance.delete.assert_called_once_with()

    # def _validate_non_upgraded(self):
    #     self.assertEquals("1.0", self._asset_instance.version)
    #     self.assertEquals("type", self._asset_instance.content_type)
    #     self.assertEquals("/old/path", self._asset_instance.resource_path)
    #     self.assertEquals("http://host/old/path", self._asset_instance.download_link)
    #     self._asset_instance.save.assert_called_once_with()

    # def _validate_not_called(self):
    #     self.assertEquals(0, self._asset_instance.delete.call_count)

    # def _validate_non_downgraded(self):
    #     self.assertEquals("/new/path", self._asset_instance.resource_path)

    # @parameterized.expand(
    #     [
    #         (
    #             "create_non_att",
    #             "rollback_create",
    #             BASIC_PRODUCT["product"],
    #             _mock_non_attached,
    #             _validate_non_attached,
    #         ),
    #         (
    #             "upgrade_saved",
    #             "rollback_upgrade",
    #             BASIC_PRODUCT["product"],
    #             _mock_non_upgraded,
    #             _validate_non_upgraded,
    #         ),
    #         ("create_non_dig", "rollback_create", {}, None, _validate_not_called),
    #         (
    #             "create_attached",
    #             "rollback_create",
    #             BASIC_PRODUCT["product"],
    #             _mock_attached,
    #             _validate_not_called,
    #         ),
    #         (
    #             "upgrade_wrong_id",
    #             "rollback_upgrade",
    #             BASIC_PRODUCT["product"],
    #             _mock_wrong_product,
    #             _validate_non_downgraded,
    #         ),
    #     ]
    # )
    # def test_rollback_handler(self, name, action, data, mocker, test_validator):
    #     self._mock_validator_imports(product_validator)

    #     if mocker is not None:
    #         mocker(self)

    #     validator = product_validator.ProductValidator()
    #     validator.validate(action, self._provider, data)

    #     test_validator(self)

    def _mock_offering_update(self):
        self._mock_validator_imports(offering_validator)
        offering_validator.Resource.objects.filter.return_value = [self._asset_instance]

        self._mock_product_spec_request(OFFER_PS_ID)

        offering_validator.Offering = MagicMock()
        offering_validator.Offering.objects.filter.return_value = []

    def test_update_offering_validator(self):
        self._mock_offering_update()

        validator = offering_validator.OfferingValidator()
        validator.validate("update", self._provider, BASIC_OFFERING)

        # Validate calls
        self.assertEquals(0, offering_validator.Offering.objects.filter.call_count)
        self.assertFalse(self._asset_instance.is_public)
        # Unsupported at this moment
        # self._asset_instance.save.assert_called_once_with()

    # def test_update_open_offering(self):
    #     self._mock_offering_update()

    #     validator = offering_validator.OfferingValidator()
    #     validator.validate("update", self._provider, OPEN_OFFERING)

    #     # Validate calls
    #     offering_validator.Offering.objects.filter.assert_called_once_with(asset=self._asset_instance)
    #     self.assertTrue(self._asset_instance.is_public)
    #     self._asset_instance.save.assert_called_once_with()

    # def test_update_open_offering_multiple_error(self):
    #     self._mock_offering_update()

    #     offering_validator.Offering.objects.filter.return_value = [
    #         MagicMock(),
    #         MagicMock(),
    #     ]
    #     error = None
    #     try:
    #         validator = offering_validator.OfferingValidator()
    #         validator.validate("update", self._provider, OPEN_OFFERING)
    #     except Exception as e:
    #         error = e

    #     self.assertTrue(isinstance(error, ValueError))
    #     self.assertEqual(
    #         str(error),
    #         "Assets of open offerings cannot be monetized in other offerings",
    #     )
