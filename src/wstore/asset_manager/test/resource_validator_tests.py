from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
import json

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase, RequestFactory
from django.urls import resolve
from parameterized import parameterized

from wstore.asset_manager.errors import ResourceError
from wstore.asset_manager.models import Resource
from wstore.asset_manager.resource_validator import ResourceValidator
from wstore.asset_manager.resource_plugins import decorators
from wstore.asset_manager.resource_plugins.plugin_error import PluginError
from wstore.store_commons.resource_catalog import ResourceCatalogError


def characteristic(name, value):
    return {"name": name, "resourceSpecCharacteristicValue": [{"value": value}]}


class ResourceSpecificationValidationTests(SimpleTestCase):
    def setUp(self):
        self.provider = SimpleNamespace(pk="seller")
        self.validator = ResourceValidator()
        self.validator._catalog = Mock()
        self.spec = {
            "id": "resource-spec-1",
            "version": "1.0",
            "resourceSpecCharacteristic": [
                characteristic("Resource Type", "resource-category"),
            ],
        }
        self.validator._catalog.get_specification.return_value = deepcopy(self.spec)
        self.model = SimpleNamespace(requires_file=False, media_types=["application/json"], form={})
        self.plugin = Mock(_model=self.model)
        self.file_id = "507f1f77bcf86cd799439011"
        self.upload = SimpleNamespace(
            provider_id="seller",
            resource_path="media/assets/seller/data.json",
            content_type="application/json",
        )
        for target, attribute, value in (
            (decorators.ResourcePlugin.objects, "filter", [self.model]),
            (decorators, "_load_plugin_model", self.plugin),
            (Resource.objects, "get", self.upload),
        ):
            patcher = patch.object(target, attribute, return_value=value)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
            if attribute == "filter":
                self.registry = mock
            elif attribute == "get":
                self.file_lookup = mock

    def validate(self, action="create", spec=None):
        self.validator.validate(action, self.provider, self.spec if spec is None else spec)

    def test_resource_schema_resolves_typed_plugin_and_runs_pre_post_before_write(self):
        original = deepcopy(self.spec)
        self.validate()
        self.registry.assert_called_once_with(category_id="resource-category", type="resource")
        self.assertEqual(
            ["on_pre_resource_spec_validation", "on_post_resource_spec_validation"],
            [call[0] for call in self.plugin.method_calls],
        )
        self.plugin.on_pre_resource_spec_validation.assert_called_once_with(self.provider, self.spec)
        self.plugin.on_post_resource_spec_validation.assert_called_once_with(self.provider, self.spec)
        self.file_lookup.assert_not_called()
        self.validator._catalog.get_specification.assert_not_called()
        self.assertEqual(original, self.spec)

    @parameterized.expand([("create",), ("update",)])
    def test_ordinary_resources_skip_plugin_file_and_catalog_checks(self, action):
        spec = {"resourceSpecCharacteristic": [characteristic("File", "not-an-upload-id")]}
        with patch.object(self.validator, "parse_spec_characteristics") as parse:
            self.validate(action, spec)
            parse.assert_not_called()
        self.registry.assert_not_called()
        self.file_lookup.assert_not_called()
        self.validator._catalog.get_specification.assert_not_called()
        self.assertEqual([], self.plugin.method_calls)

    def test_uninstalled_resource_category_skips_plugin_validation(self):
        self.registry.return_value = []
        self.model.requires_file = True
        self.validate()
        self.file_lookup.assert_not_called()
        self.assertEqual([], self.plugin.method_calls)

    def test_service_characteristic_encoding_does_not_opt_resource_into_validation(self):
        self.validate(
            spec={
                "specCharacteristic": [
                    {
                        "name": "Service Type",
                        "characteristicValueSpecification": [{"value": "resource-category"}],
                    }
                ]
            }
        )
        self.registry.assert_not_called()

    def test_ambiguous_resource_category_is_rejected(self):
        self.registry.return_value = [self.model, self.model]
        with self.assertRaises(ResourceError):
            self.validate()
        self.assertEqual([], self.plugin.method_calls)

    @parameterized.expand([("empty", ""), ("object", {"id": "category"}), ("number", 1), ("null", None)])
    def test_resource_type_requires_a_string_category_id(self, name, value):
        self.spec["resourceSpecCharacteristic"] = [characteristic("Resource Type", value)]
        with self.assertRaises(ResourceError):
            self.validate()
        self.registry.assert_not_called()

    def test_duplicate_or_multivalued_resource_type_is_rejected(self):
        entry = characteristic("Resource Type", "category")
        for entries in (
            [entry, entry],
            [{"name": "Resource Type", "resourceSpecCharacteristicValue": []}],
            [{"name": "Resource Type", "resourceSpecCharacteristicValue": [{"value": "a"}, {"value": "b"}]}],
        ):
            with self.subTest(entries=entries):
                with self.assertRaises(ResourceError):
                    self.validate(spec={"resourceSpecCharacteristic": entries})

    def test_characteristic_names_are_case_insensitive(self):
        self.spec["resourceSpecCharacteristic"][0]["name"] = " RESOURCE TYPE "
        self.validate()
        self.plugin.on_post_resource_spec_validation.assert_called_once()

    def test_required_upload_uses_stored_metadata_without_attaching_or_writing(self):
        self.model.requires_file = True
        self.model.media_types = ["APPLICATION/JSON"]
        self.spec["resourceSpecCharacteristic"].append(characteristic("File", self.file_id))
        before = deepcopy(self.spec)
        self.validate()
        self.file_lookup.assert_called_once()
        self.assertEqual(before, self.spec)
        self.plugin.on_post_resource_spec_validation.assert_called_once()

    @parameterized.expand(
        [("missing", None), ("invalid", "invalid"), ("object", {"id": "507f1f77bcf86cd799439011"})]
    )
    def test_invalid_managed_file_blocks_post_validation(self, name, value):
        self.model.requires_file = True
        if value is not None:
            self.spec["resourceSpecCharacteristic"].append(characteristic("File", value))
        with self.assertRaises(ResourceError):
            self.validate()
        self.plugin.on_pre_resource_spec_validation.assert_called_once()
        self.plugin.on_post_resource_spec_validation.assert_not_called()

    def test_upload_owner_must_be_provider(self):
        self.model.requires_file = True
        self.upload.provider_id = "other-provider"
        self.spec["resourceSpecCharacteristic"].append(characteristic("File", self.file_id))
        with self.assertRaises(PermissionDenied):
            self.validate()

    def test_missing_upload_is_rejected(self):
        self.model.requires_file = True
        self.file_lookup.side_effect = Resource.DoesNotExist
        self.spec["resourceSpecCharacteristic"].append(characteristic("File", self.file_id))
        with self.assertRaises(ResourceError):
            self.validate()

    def test_url_only_upload_and_unsupported_media_type_are_rejected(self):
        self.model.requires_file = True
        self.spec["resourceSpecCharacteristic"].append(characteristic("File", self.file_id))
        for path, media_type in (("", "application/json"), ("media/file", "image/png")):
            with self.subTest(path=path, media_type=media_type):
                self.upload.resource_path, self.upload.content_type = path, media_type
                with self.assertRaises(ResourceError):
                    self.validate()
        self.plugin.on_post_resource_spec_validation.assert_not_called()

    def test_empty_media_type_list_does_not_restrict_upload(self):
        self.model.requires_file = True
        self.model.media_types = []
        self.spec["resourceSpecCharacteristic"].append(characteristic("File", self.file_id))
        self.validate()

    def test_configured_form_values_include_checkbox_false_and_explicit_defaults(self):
        self.model.form = {
            "enabled": {"type": "checkbox", "mandatory": True, "default": False},
            "region": {"type": "select", "mandatory": True, "options": [{"value": "eu"}]},
            "notes": {"type": "textarea"},
        }
        self.spec["resourceSpecCharacteristic"].extend(
            [characteristic("enabled", False), characteristic("region", "EU")]
        )
        self.validate()
        self.spec["resourceSpecCharacteristic"].pop(1)
        with self.assertRaisesRegex(ResourceError, "enabled"):
            self.validate()

    @parameterized.expand(
        [("text", "text", 12), ("checkbox", "checkbox", "false"), ("select", "select", "unknown")]
    )
    def test_form_type_and_select_constraints(self, name, field_type, value):
        self.model.form = {"field": {"type": field_type, "options": [{"value": "eu"}]}}
        self.spec["resourceSpecCharacteristic"].append(characteristic("field", value))
        with self.assertRaises(ResourceError):
            self.validate()

    def test_urls_and_media_type_have_no_implicit_platform_validation(self):
        self.model.form = {"URL": {"type": "text", "mandatory": True}}
        self.spec["resourceSpecCharacteristic"].extend(
            [characteristic("URL", "custom-value"), characteristic("Media Type", "custom")]
        )
        self.validate()

    def test_ordinary_update_reads_resource_catalog_and_validates_proposed_values(self):
        proposed = {**self.spec, "description": "updated"}
        self.validate("update", proposed)
        self.validator._catalog.get_specification.assert_called_once_with("resource-spec-1")
        self.plugin.on_post_resource_spec_validation.assert_called_once_with(self.provider, proposed)

    def test_update_rejects_version_changes_and_invalid_catalog_identity(self):
        with self.assertRaises(ResourceError):
            self.validate("update", {**self.spec, "version": "2.0"})
        self.validator._catalog.get_specification.return_value = {"id": "other-resource"}
        with self.assertRaises(ResourceCatalogError):
            self.validate("update")

    @parameterized.expand(
        [("pre", "on_pre_resource_spec_validation"), ("post", "on_post_resource_spec_validation")]
    )
    def test_plugin_rejections_propagate_before_catalog_write(self, name, handler):
        getattr(self.plugin, handler).side_effect = PluginError("rejected")
        with self.assertRaises(PluginError):
            self.validate()

    def endpoint(self, action="create"):
        request = RequestFactory().post(
            "/charging/api/assetManagement/assets/validateResourceJob",
            data=json.dumps({"action": action, "resource": self.spec}),
            content_type="application/json",
        )
        request.user = SimpleNamespace(
            is_anonymous=False,
            is_staff=False,
            userprofile=SimpleNamespace(
                current_organization=self.provider,
                get_current_roles=lambda: ["provider"],
            ),
        )
        return resolve(request.path).func(request)

    def test_endpoint_runs_real_resource_validator_and_hooks(self):
        self.assertEqual(200, self.endpoint().status_code)
        self.plugin.on_post_resource_spec_validation.assert_called_once_with(self.provider, self.spec)

    def test_endpoint_returns_plugin_rejection_and_upload_permission_failure(self):
        self.plugin.on_pre_resource_spec_validation.side_effect = PluginError("rejected")
        self.assertEqual(422, self.endpoint().status_code)
        self.plugin.on_pre_resource_spec_validation.side_effect = None
        self.model.requires_file = True
        self.spec["resourceSpecCharacteristic"].append(characteristic("File", self.file_id))
        self.upload.provider_id = "other-provider"
        self.assertEqual(403, self.endpoint().status_code)
        self.plugin.on_post_resource_spec_validation.assert_not_called()

    def test_update_reads_configured_resource_catalog(self):
        from wstore.store_commons.resource_catalog import ResourceCatalog
        from django.test import override_settings

        self.validator._catalog = ResourceCatalog()
        with override_settings(
            RESOURCE_CATALOG="https://resources.example/tmf-api/resourceCatalog/v4", VERIFY_REQUESTS=True
        ), patch("wstore.store_commons.resource_catalog.requests.get") as get:
            get.return_value.json.return_value = deepcopy(self.spec)
            self.validate("update")
            get.assert_called_once_with(
                "https://resources.example/tmf-api/resourceCatalog/v4/resourceSpecification/resource-spec-1",
                verify=True,
            )


class ResourceValidationEndpointTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(
            is_anonymous=False,
            is_staff=False,
            userprofile=SimpleNamespace(
                current_organization=object(),
                get_current_roles=lambda: ["provider"],
            ),
        )

    def request(self, body):
        request = self.factory.post(
            "/charging/api/assetManagement/assets/validateResourceJob",
            data=json.dumps(body),
            content_type="application/json",
        )
        request.user = self.user
        return request

    @patch("wstore.asset_manager.views.ResourceValidator")
    def test_resource_validation_route_and_payload(self, validator):
        body = {
            "action": "create",
            "resource": {"resourceSpecCharacteristic": [characteristic("Resource Type", "category")]},
        }
        request = self.request(body)
        self.assertEqual(200, resolve(request.path).func(request).status_code)
        validator.return_value.validate.assert_called_once_with(
            "create", self.user.userprofile.current_organization, body["resource"]
        )

    @patch("wstore.asset_manager.views.ResourceValidator")
    def test_error_mapping(self, validator):
        for error, status in (
            (ResourceError("invalid"), 400),
            (PluginError("reject"), 422),
            (ResourceCatalogError("offline"), 422),
            (PermissionDenied("owner"), 403),
        ):
            with self.subTest(error=error):
                validator.return_value.validate.side_effect = error
                request = self.request({"action": "create", "resource": {}})
                self.assertEqual(status, resolve(request.path).func(request).status_code)

    def test_required_fields_and_permissions(self):
        for body in ([], {"resource": {}}, {"action": "create"}):
            request = self.request(body)
            self.assertEqual(400, resolve(request.path).func(request).status_code)
        self.user.is_anonymous = True
        request = self.request({})
        self.assertEqual(401, resolve(request.path).func(request).status_code)
        self.user.is_anonymous = False
        self.user.userprofile.get_current_roles = lambda: ["customer"]
        request = self.request({})
        self.assertEqual(403, resolve(request.path).func(request).status_code)
