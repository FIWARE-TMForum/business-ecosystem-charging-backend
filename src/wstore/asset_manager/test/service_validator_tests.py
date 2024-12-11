from importlib import reload

from parameterized import parameterized
from django.test.testcases import TestCase
from mock import MagicMock

from bson import ObjectId

from src.wstore.asset_manager import service_validator, catalog_validator
from wstore.asset_manager.errors import ServiceError
from wstore.asset_manager.test.service_validator_test_data import *

import wstore.asset_manager.resource_plugins.decorators

class SValidatorTestCase(TestCase):
    tags = ("service-validator",)
    
    def _mock_validator_imports(self, module):
        pass
        
    def setUp(self):
        reload(service_validator)
        reload(wstore.asset_manager.resource_plugins.decorators)
        reload(catalog_validator)
        # Mock Site
        service_validator.settings.SITE = "http://testlocation.org/"

        self._provider = MagicMock()
        
        self._plugin_instance = MagicMock()
        self._plugin_instance.media_types = ["application/x-widget"]
        self._plugin_instance.formats = ["FILE"]
        self._plugin_instance.module = "wstore.asset_manager.resource_plugins.plugin.Plugin"
        self._plugin_instance.form = {}
        self._plugin_instance.name = "Widget"
        wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects = MagicMock()
        wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.get.return_value = self._plugin_instance

        self._asset_instance = MagicMock()
        self._asset_instance.resource_type = "Widget"
        self._asset_instance.content_type = "application/x-widget"
        self._asset_instance.download_link = SERVICE_LOCATION
        self._asset_instance.provider = self._provider
        self._asset_instance.service_spec_id = None
        self._asset_instance.is_public = False
        self._asset_instance.pk = ObjectId("61004aba5e05acc115f022f0")
        wstore.asset_manager.resource_plugins.decorators.Resource.objects = MagicMock()
        wstore.asset_manager.resource_plugins.decorators.Resource.objects.filter.return_value = [self._asset_instance]
        wstore.asset_manager.resource_plugins.decorators.Resource.objects.get.return_value = self._asset_instance
        wstore.asset_manager.resource_plugins.decorators.Resource.objects.create.return_value = self._asset_instance
        
        
    def tearDown(self):
        reload(service_validator)
        reload(wstore.asset_manager.resource_plugins.decorators)
        reload(catalog_validator)
        
    def _not_existing(self):
        self._plugin_instance.formats = ["FILE", "URL"]
        service_validator.Resource.objects.filter.return_value = []

    def _not_supported(self):
        import wstore.asset_manager.resource_plugins.decorators

        wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.get.side_effect = Exception("Not found")
        self._mock_validator_imports(service_validator)
        
    def _inv_media(self):
        service_validator.Resource.objects.filter.return_value = []
        self._plugin_instance.media_types = ["text/plain"]
        self._plugin_instance.formats = ["URL"]
        
    def _not_owner(self):
        self._asset_instance.provider = MagicMock()

    def _diff_media(self):
        self._asset_instance.content_type = "text/plain"

    def _existing_asset(self):
        self._asset_instance.service_id = 27

    def _invalid_type(self):
        self._asset_instance.resource_type = "Mashup"

    def _metadata_plugin(self):
        self._plugin_instance.form = {"data": "data"}
        self._plugin_instance.formats = ["URL"]
        service_validator.Resource.objects.filter.return_value = []

    def _pub_asset(self):
        self._asset_instance.is_public = True

    def test_validate_creation_without_char(self):
        self._mock_validator_imports(service_validator)

        validator = service_validator.ServiceValidator()
        asset_id = validator.validate("create", self._provider, NO_CHARS_SERVICE)

        wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.get.assert_not_called()
        service_validator.Resource.objects.get.assert_not_called()
        service_validator.Resource.objects.get().save.assert_not_called()
        self.assertIsNone(asset_id)
        
    def test_validate_creation_registered_file(self):
        self._mock_validator_imports(service_validator)

        validator = service_validator.ServiceValidator()
        asset_id = validator.validate("create", self._provider, BASIC_SERVICE["service"])

        wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.get.assert_called_once_with(name="Widget")
        service_validator.Resource.objects.get.assert_called_once_with(pk=ObjectId("61004aba5e05acc115f022f0"))
        self.assertFalse(service_validator.Resource.objects.get().has_terms)
        service_validator.Resource.objects.get().save.assert_called_once_with()
        self.assertIsNone(asset_id)
        
    def test_validate_creation_without_term_automatic(self):
        self._mock_validator_imports(service_validator)
        service_validator.Resource.objects.get.return_value = []
        self._plugin_instance.formats = ["URL"]

        validator = service_validator.ServiceValidator()
        asset_id =validator.validate("create", self._provider, NO_ID_SERVICE["service"])
        
        service_validator.Resource.objects.get.assert_not_called()
        service_validator.Resource.objects.create.assert_called_once_with(
            has_terms=False,
            resource_path="",
            download_link=SERVICE_LOCATION,
            provider=self._provider,
            content_type="application/x-widget",
        )
        self.assertIsNotNone(asset_id)

    def test_validate_creation_new_url_automatic(self):
        self._mock_validator_imports(service_validator)
        service_validator.Resource.objects.get.return_value = []
        self._plugin_instance.formats = ["URL"]

        validator = service_validator.ServiceValidator()
        asset_id =validator.validate("create", self._provider, TERMS_SERVICE["service"])
        
        service_validator.Resource.objects.get.assert_not_called()
        service_validator.Resource.objects.create.assert_called_once_with(
            has_terms=True,
            resource_path="",
            download_link=SERVICE_LOCATION,
            provider=self._provider,
            content_type="application/x-widget",
        )
        self.assertIsNotNone(asset_id)

    def not_allowed_auto(self):
        self._plugin_instance.form = {"test": "test"}
        self._plugin_instance.formats = ["URL"]
        
    def custom_format(self):
        self._plugin_instance.formats = ["CUSTOM"]

    @parameterized.expand([
        ("service spec invalid terms", INVALID_TERMS, ServiceError, "The characteristic License must not contain multiple values"),
        ("service spec multiple terms", MULTIPLE_TERMS, ServiceError, "The service specification must not contain more than one license characteristic"),
        ("service spec invalid action", INVALID_ACTION, ValueError, "The provided action (invalid) is not valid. Allowed values are create, attach, update, upgrade, and delete"),
        ("service spec missing media", MISSING_MEDIA, ServiceError, "Digital service specifications must contain a media type characteristic"),
        ("service spec missing asset type", MISSING_TYPE, ServiceError, "Digital service specifications must contain a asset type characteristic"),
        ("service spec missing location", MISSING_LOCATION, ServiceError, "Digital service specifications must contain a location characteristic"),
        ("service spec automatic creation not allowed due to form", MISSING_ASSET_ID, ServiceError, "Automatic creation of digital assets with metadata is not supported", not_allowed_auto),
        ("service spec automatic creation missing url format", MISSING_ASSET_ID, ServiceError, "The asset should support URL format", custom_format),
        ("service spec automatic creation not allowed due to url format", MISSING_ASSET_ID, ServiceError, "The URL specified in the location characteristic does not point to a valid digital asset"),
        ("service spec automatic multiple location", MULTIPLE_LOCATION, ServiceError, "The service specification must not contain more than one location characteristic"),    
        ("service spec automatic multiple value", MULTIPLE_VALUES, ServiceError, "The characteristic Location must not contain multiple values"),    
        ("service spec automatic invalid location", INVALID_LOCATION, ServiceError, "The location characteristic included in the service specification is not a valid URL"),    
        ("service spec automatic not allowed bundle creation", BUNDLE_CREATION, ServiceError, "Service spec bundles are not supported"),    
        ])    
    def test_create_service_validation_errors(self, name, service_spec, exception_t, msg, init = None):
        if init:
            init(self)
        error = None
        try:
            validator = service_validator.ServiceValidator()
            asset_id = validator.validate(service_spec["action"], self._provider, service_spec["service"])
        except Exception as e:
            error=e
        self.assertIsNotNone(error)
        self.assertIsInstance(error, exception_t)
        self.assertEquals(str(exception_t(msg)), str(error))
        
    def _attached(self):
        self._asset_instance.state = "attached"

    def _inv_service_id(self):
        self._asset_instance.state = "upgrading"
        self._asset_instance.service_id = "10"

    def _set_asset_params(self):
        self._asset_instance.state = "upgrading"
        self._asset_instance.service_id = UPGRADE_SERVICE["service"]["id"]

    def _high_asset_version(self):
        self._set_asset_params()
        self._asset_instance.old_versions = [MagicMock(version="3.0")]
        self._asset_instance.resource_path = ""
        
    def _mock_upgrading_asset(self, version):
        self._asset_instance.state = "upgrading"
        self._asset_instance.service_spec_id = UPGRADE_SERVICE["service"]["id"]
        self._asset_instance.version = version
        self._asset_instance.old_versions = [{"version":"1.0"}] 
        
    def _mock_document_lock(self):
        document_lock = MagicMock()
        service_validator.DocumentLock = MagicMock(return_value=document_lock)
        return document_lock
    @parameterized.expand(
        [
            ("digital_asset", BASIC_SERVICE["service"], True),
            ("non_digital", {"isBundle": False}),
        ]
    )
    def test_attach_info(
        self,
        name,
        service_spec,
        is_digital=False,
    ):
        self._mock_validator_imports(service_validator)
        validator = service_validator.ServiceValidator()

        digital_chars = (
            ("type", "media", "http://location", "61004aba5e05acc115f022f0") if is_digital else (None, None, None, None)
        )
        validator.parse_spec_characteristics = MagicMock(return_value=digital_chars)
        error = None
        try:
            validator.validate("attach", self._provider, service_spec)
        except Exception as e:
            error=e

        # Check calls
        validator.parse_spec_characteristics.assert_called_once_with(service_spec)
        if is_digital:
            service_validator.Resource.objects.get.assert_called_once_with(pk=ObjectId(digital_chars[3]))
            wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.get.assert_called_once_with(name=digital_chars[0])
            self.assertEquals(0, service_validator.Resource.objects.filter.call_count)
            self.assertEquals(service_spec["id"], self._asset_instance.service_spec_id)
            self.assertEquals(service_spec["version"], self._asset_instance.version)
            self.assertEquals(digital_chars[0], self._asset_instance.resource_type)
            self.assertEquals("attached", self._asset_instance.state)

            self._asset_instance.save.assert_called_once_with()
            self.assertIsNone(error)
        else:
            self.assertIsNotNone(error)
            self.assertIsInstance(error, ServiceError)
            self.assertEquals(0, self._asset_instance.save.call_count)

    
    def test_validate_upgrade(self):
        self._mock_validator_imports(service_validator)
        self._mock_upgrading_asset("")

        doc_lock = self._mock_document_lock()

        validator = service_validator.ServiceValidator()
        validator.validate("upgrade", self._provider, UPGRADE_SERVICE["service"])

        self.assertEquals(UPGRADE_SERVICE["service"]["version"], self._asset_instance.version)
        self.assertEquals("upgrading", self._asset_instance.state)
        self._asset_instance.save.assert_called_once_with()

        service_validator.DocumentLock.assert_called_once_with("wstore_resource", self._asset_instance.pk, "asset") # type: ignore
        doc_lock.wait_document.assert_called_once_with()
        doc_lock.unlock_document.assert_called_once_with()
    
    def test_attach_upgrade(self):
        self._mock_validator_imports(service_validator)
        self._mock_upgrading_asset(UPGRADE_SERVICE["service"]["version"])

        doc_lock = self._mock_document_lock()

        # Mock inventory upgrader class
        service_validator.ServiceInventoryUpgrader = MagicMock()

        validator = service_validator.ServiceValidator()
        validator.validate("attach_upgrade", self._provider, UPGRADE_SERVICE["service"])

        self.assertEquals("attached", self._asset_instance.state)

        service_validator.ServiceInventoryUpgrader.assert_called_once_with(self._asset_instance)
        service_validator.ServiceInventoryUpgrader().start.assert_called_once_with()

        self._asset_instance.save.assert_called_once_with()

        service_validator.DocumentLock.assert_called_once_with("wstore_resource", self._asset_instance.pk, "asset") # type: ignore
        doc_lock.wait_document.assert_called_once_with()
        doc_lock.unlock_document.assert_called_once_with()
    
        