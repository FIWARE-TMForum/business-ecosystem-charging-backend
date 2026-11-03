from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from wstore.asset_manager.errors import ServiceError
from wstore.asset_manager.service_validator import ServiceValidator
from wstore.asset_manager.resource_plugins import decorators as plugin_decorators
from wstore.asset_manager.resource_plugins.plugin_error import PluginError
from wstore.store_commons.service_catalog import ServiceCatalog, ServiceCatalogError


def characteristic(name, value):
    return {"name": name, "characteristicValueSpecification": [{"value": value}]}


def parse_values(validator, specification, form=None):
    characteristics = validator.parse_spec_characteristics(specification)
    return validator._get_service_characteristics(characteristics, form)


class ServiceSpecificationTests(SimpleTestCase):
    def setUp(self):
        self.validator = ServiceValidator()
        self.specification = {
            "specCharacteristic": [characteristic("Service Type", {"id": "plugin-category"})],
        }
        self.plugin = SimpleNamespace(requires_file=False, media_types=["application/json"], form={})

    def test_non_file_plugins_do_not_require_url_or_media_type(self):
        values = parse_values(self.validator, self.specification)
        self.assertEqual({}, values)
        self.validator.validate_asset_characteristics(self.plugin, values)

    def test_urls_are_ordinary_form_fields_without_platform_url_semantics(self):
        self.plugin.form = {"endpoint": {"type": "text", "mandatory": True}}
        self.specification["specCharacteristic"].append(characteristic("endpoint", "plugin-defined-value"))
        values = parse_values(self.validator, self.specification, self.plugin.form)
        self.validator.validate_asset_characteristics(self.plugin, values)
        self.assertEqual({"endpoint": "plugin-defined-value"}, values)

        with self.assertRaisesRegex(ServiceError, "endpoint"):
            self.validator.validate_asset_characteristics(self.plugin, {})

    def test_url_and_media_type_are_not_implicitly_validated(self):
        self.specification["specCharacteristic"].extend(
            [
                characteristic("URL", "not-a-url"),
                characteristic("Media Type", "not-a-media-type"),
            ]
        )
        self.assertEqual({}, parse_values(self.validator, self.specification))

    def test_other_service_characteristics_remain_general_purpose(self):
        self.specification["specCharacteristic"].extend(
            [
                {"name": "Regions", "characteristicValueSpecification": [{"value": "EU"}, {"value": "US"}]},
                characteristic("Format", "custom"),
                characteristic("Metadata", "ordinary characteristic"),
                characteristic("License", "ordinary characteristic"),
            ]
        )
        before = deepcopy(self.specification)
        self.assertEqual({}, parse_values(self.validator, self.specification))
        self.assertEqual(before, self.specification)

    def test_malformed_characteristic_is_rejected_for_plugin_service(self):
        self.specification["specCharacteristic"].append(None)
        with self.assertRaises(ServiceError):
            parse_values(self.validator, self.specification)


class ServiceLifecycleTests(SimpleTestCase):
    def setUp(self):
        self.validator = ServiceValidator()
        self.validator._catalog = Mock()
        self.provider = SimpleNamespace(name="seller", get_party_url=lambda: "https://party.example/seller")
        self.spec = {
            "id": "spec-1",
            "version": "1.0",
            "relatedParty": [{"id": "seller", "role": "Seller"}],
            "specCharacteristic": [
                characteristic("Service Type", {"id": "plugin-category"}),
                characteristic("URL", "https://provider.example/service"),
                characteristic("Media Type", "application/json"),
            ],
        }
        self.model = SimpleNamespace(requires_file=False, media_types=["application/json"], form={})
        self.plugin = Mock(_model=self.model)
        resolve_patch = patch.object(plugin_decorators, "_get_plugin_model", return_value=self.model)
        self.resolve_plugin = resolve_patch.start()
        self.addCleanup(resolve_patch.stop)
        load_patch = patch.object(plugin_decorators, "_load_plugin_model", return_value=self.plugin)
        self.load_plugin = load_patch.start()
        self.addCleanup(load_patch.stop)
        self.validator._catalog.get_specification.return_value = deepcopy(self.spec)

    def test_creation_validation_runs_pre_and_post_plugin_signals(self):
        proposed = deepcopy(self.spec)
        proposed.pop("id")
        self.validator.validate("create", self.provider, proposed)
        self.assertEqual(
            ["on_pre_service_spec_validation", "on_post_service_spec_validation"],
            [c[0] for c in self.plugin.method_calls],
        )
        self.resolve_plugin.assert_called_once_with(category_id="plugin-category")
        self.validator._catalog.get_specification.assert_not_called()

    def test_invalid_metadata_prevents_post_validation(self):
        self.model.requires_file = True
        with self.assertRaises(ServiceError):
            self.validator.validate("create", self.provider, self.spec)
        self.plugin.on_pre_service_spec_validation.assert_called_once()
        self.plugin.on_post_service_spec_validation.assert_not_called()

    def test_rejecting_plugin_propagates_and_stops_processing(self):
        self.plugin.on_pre_service_spec_validation.side_effect = PluginError("rejected")
        with self.assertRaises(PluginError):
            self.validator.validate("create", self.provider, self.spec)
        self.plugin.on_post_service_spec_validation.assert_not_called()

    def test_proxy_validated_ownership_is_not_rechecked(self):
        self.spec.pop("relatedParty")
        self.validator.validate("create", self.provider, self.spec)
        self.plugin.on_pre_service_spec_validation.assert_called_once_with(self.provider, self.spec)
        self.plugin.on_post_service_spec_validation.assert_called_once_with(self.provider, self.spec)

    def test_partial_update_merges_existing_characteristics(self):
        self.validator.validate(
            "update",
            self.provider,
            {"id": "spec-1", "description": "changed", "specCharacteristic": self.spec["specCharacteristic"]},
        )
        proposed = self.plugin.on_post_service_spec_validation.call_args.args[1]
        self.assertEqual(self.spec["specCharacteristic"], proposed["specCharacteristic"])
        self.assertEqual("changed", proposed["description"])

    def test_update_rejects_invalid_catalog_document_before_post_hook(self):
        for document in [None, [], {}, {"id": "wrong"}]:
            with self.subTest(document=document):
                self.validator._catalog.get_specification.return_value = document
                with self.assertRaises(ServiceCatalogError):
                    self.validator.validate("update", self.provider, self.spec)

        self.plugin.on_post_service_spec_validation.assert_not_called()

    def test_update_cannot_bypass_upgrade(self):
        for changes in [{"version": "2.0"}]:
            with self.subTest(changes=changes), self.assertRaises(ServiceError):
                self.validator.validate(
                    "update",
                    self.provider,
                    {"id": "spec-1", "specCharacteristic": self.spec["specCharacteristic"], **changes},
                )

    def test_ordinary_specification_does_not_invoke_plugins(self):
        self.resolve_plugin.return_value = None
        ordinary = {**self.spec, "specCharacteristic": []}
        self.validator.validate("create", self.provider, ordinary)
        self.load_plugin.assert_not_called()
        self.validator.validate("create", self.provider, self.spec)
        self.load_plugin.assert_not_called()

    def test_unimplemented_operations_are_inherited(self):
        from wstore.asset_manager.catalog_validator import CatalogValidator

        for name in (
            "validate_upgrade",
            "validate_deletion",
        ):
            self.assertNotIn(name, ServiceValidator.__dict__)
            self.assertIs(getattr(ServiceValidator, name), getattr(CatalogValidator, name))

    def test_parent_dispatch_and_callback_signatures_are_preserved(self):
        import inspect
        from wstore.asset_manager.catalog_validator import CatalogValidator

        self.assertIs(ServiceValidator.validate, CatalogValidator.validate)
        for name in (
            "validate_creation",
            "validate_update",
            "validate_upgrade",
            "validate_deletion",
        ):
            self.assertEqual(
                inspect.signature(getattr(CatalogValidator, name)), inspect.signature(getattr(ServiceValidator, name))
            )


class ServiceEndpointTests(SimpleTestCase):
    def setUp(self):
        import json
        from django.test import RequestFactory

        self.json = json
        self.factory = RequestFactory()
        self.user = SimpleNamespace(
            is_anonymous=False,
            is_staff=False,
            userprofile=SimpleNamespace(current_organization=object(), get_current_roles=lambda: ["provider"]),
        )

    def request(self, body):
        request = self.factory.post(
            "/charging/api/assetManagement/assets/validateServiceJob",
            data=self.json.dumps(body),
            content_type="application/json",
        )
        request.user = self.user
        return request

    @patch("wstore.asset_manager.views.ServiceValidator")
    def test_route_and_request_arguments(self, validator):
        from django.urls import resolve

        body = {
            "action": "create",
            "service": {
                "name": "example",
                "specCharacteristic": [characteristic("Service Type", {"id": "plugin-category"})],
            },
        }
        request = self.request(body)
        response = resolve(request.path).func(request)
        self.assertEqual(200, response.status_code)
        validator.return_value.validate.assert_called_once_with(
            "create",
            self.user.userprofile.current_organization,
            body["service"],
        )

    @patch("wstore.asset_manager.views.ServiceValidator")
    def test_validation_and_plugin_errors_are_exposed_as_failures(self, validator):
        from django.core.exceptions import PermissionDenied
        from wstore.asset_manager.views import ValidateServiceCollection

        for error, status in [
            (ServiceError("invalid"), 400),
            (PluginError("rejected"), 422),
            (ServiceCatalogError("invalid catalog response"), 422),
            (PermissionDenied("owner"), 403),
        ]:
            with self.subTest(status=status):
                validator.return_value.validate.side_effect = error
                response = ValidateServiceCollection(permitted_methods=("POST",)).create(
                    self.request({"action": "create", "service": {}})
                )
                self.assertEqual(status, response.status_code)

    def test_invalid_body_and_permissions(self):
        from wstore.asset_manager.views import ValidateServiceCollection

        for body in [[], {"service": {}}, {"action": "create"}]:
            with self.subTest(body=body):
                response = ValidateServiceCollection(permitted_methods=("POST",)).create(self.request(body))
                self.assertEqual(400, response.status_code)
        self.user.is_anonymous = True
        self.assertEqual(
            401, ValidateServiceCollection(permitted_methods=("POST",)).create(self.request({})).status_code
        )
        self.user.is_anonymous = False
        self.user.userprofile.get_current_roles = lambda: ["customer"]
        self.assertEqual(
            403, ValidateServiceCollection(permitted_methods=("POST",)).create(self.request({})).status_code
        )


class ServiceEndpointIntegrationTests(SimpleTestCase):
    def setUp(self):
        from django.test import RequestFactory

        self.factory = RequestFactory()
        self.provider = SimpleNamespace(name="seller", get_party_url=lambda: "https://party.example/seller")
        self.user = SimpleNamespace(
            is_anonymous=False,
            is_staff=False,
            userprofile=SimpleNamespace(current_organization=self.provider, get_current_roles=lambda: ["provider"]),
        )
        self.spec = {
            "name": "example",
            "version": "1.0",
            "relatedParty": [{"id": "seller", "role": "Seller"}],
            "specCharacteristic": [
                characteristic("Service Type", {"id": "plugin-category"}),
                characteristic("URL", "https://provider.example/service"),
                characteristic("Media Type", "application/json"),
            ],
        }
        self.model = SimpleNamespace(requires_file=False, media_types=["application/json"], form={})
        self.plugin = Mock(_model=self.model)

    def post(self, body):
        import json
        from django.urls import resolve

        request = self.factory.post(
            "/charging/api/assetManagement/assets/validateServiceJob",
            data=json.dumps(body),
            content_type="application/json",
        )
        request.user = self.user
        return resolve(request.path).func(request)

    @patch("wstore.asset_manager.resource_plugins.decorators._load_plugin_model")
    @patch("wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.filter")
    @patch("wstore.asset_manager.service_validator.ServiceCatalog")
    def test_creation_validation_through_route(self, catalog, lookup, load):
        lookup.return_value = [self.model]
        load.return_value = self.plugin
        response = self.post({"action": "create", "service": self.spec})
        self.assertEqual(200, response.status_code)
        self.plugin.on_post_service_spec_validation.assert_called_once_with(self.provider, self.spec)
        self.assertEqual([], catalog.return_value.method_calls)

    @patch("wstore.asset_manager.resource_plugins.decorators._load_plugin_model")
    @patch("wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.filter")
    def test_plugin_rejection_propagates_through_route(self, lookup, load):
        lookup.return_value = [self.model]
        load.return_value = self.plugin
        self.plugin.on_post_service_spec_validation.side_effect = PluginError("rejected")
        response = self.post({"action": "create", "service": self.spec})
        self.assertEqual(422, response.status_code)

    @patch("wstore.asset_manager.resource_plugins.decorators._load_plugin_model")
    @patch("wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.filter")
    @patch("wstore.store_commons.service_catalog.requests.get")
    def test_invalid_catalog_response_retains_422_through_route(self, get, lookup, load):
        lookup.return_value = [self.model]
        load.return_value = self.plugin
        get.return_value.json.return_value = {"id": "wrong"}
        self.spec["id"] = "spec-1"

        response = self.post({"action": "update", "service": self.spec})

        self.assertEqual(422, response.status_code)
        get.assert_called_once()
        self.plugin.on_post_service_spec_validation.assert_not_called()

    def test_malformed_json_rejected(self):
        from django.urls import resolve

        request = self.factory.post(
            "/charging/api/assetManagement/assets/validateServiceJob",
            data="{invalid",
            content_type="application/json",
        )
        request.user = self.user
        self.assertEqual(400, resolve(request.path).func(request).status_code)


class SharedValidatorContractTests(SimpleTestCase):
    def test_service_owns_its_parser_and_reuses_parent_dispatch(self):
        from wstore.asset_manager.catalog_validator import CatalogValidator

        self.assertIs(ServiceValidator.validate, CatalogValidator.validate)
        self.assertIn("parse_spec_characteristics", ServiceValidator.__dict__)
        self.assertNotIn("parse_spec_characteristics", CatalogValidator.__dict__)
        self.assertIn("parse_characteristics", CatalogValidator.__dict__)
        from wstore.asset_manager.product_validator import ProductValidator

        self.assertIs(ProductValidator.parse_characteristics, CatalogValidator.parse_characteristics)
        self.assertNotIn("parse_characteristics", ProductValidator.__dict__)

    def test_dispatch_calls_subclass_method(self):
        from wstore.asset_manager.catalog_validator import CatalogValidator

        validator = CatalogValidator()
        validator.validate_creation = Mock(return_value="validated")
        validator.validate("create", "provider", {"name": "example"})
        validator.validate_creation.assert_called_once_with("provider", {"name": "example"})

    def test_existing_product_parser_is_unchanged(self):
        from wstore.asset_manager.product_validator import ProductValidator

        specification = {
            "productSpecCharacteristic": [
                {"name": name, "productSpecCharacteristicValue": [{"value": value}]}
                for name, value in [
                    ("Asset Type", "legacy"),
                    ("Media Type", "application/json"),
                    ("Location", "https://example.org/asset"),
                    ("Asset", "old-id"),
                ]
            ]
        }
        self.assertEqual(
            ("legacy", "application/json", "https://example.org/asset", "old-id"),
            ProductValidator().parse_characteristics(specification),
        )


class ServicePluginDecoratorTests(SimpleTestCase):
    def setUp(self):
        self.model = object()
        self.validator = Mock()
        self.validator.parse_spec_characteristics.return_value = ({"id": "category"}, {})
        self.specification = {"specCharacteristic": [characteristic("Service Type", {"id": "category"})]}
        self.plugin = Mock(_model=self.model)
        resolve_patch = patch.object(plugin_decorators, "_get_plugin_model", return_value=self.model)
        self.resolve = resolve_patch.start()
        self.addCleanup(resolve_patch.stop)
        load_patch = patch.object(plugin_decorators, "_load_plugin_model", return_value=self.plugin)
        self.load = load_patch.start()
        self.addCleanup(load_patch.stop)

    def test_validation_decorator_wraps_backend_operation_in_order(self):
        events = []
        self.plugin.on_pre_service_spec_validation.side_effect = lambda *args: events.append("pre")
        self.plugin.on_post_service_spec_validation.side_effect = lambda *args: events.append("post")
        provider, specification = object(), self.specification

        @plugin_decorators.on_service_spec_validation
        def operation(validator, actual_provider, actual_specification, model):
            self.assertIs(provider, actual_provider)
            self.assertIs(specification, actual_specification)
            self.assertIs(self.model, model)
            events.append("backend")
            return "validated"

        self.assertEqual("validated", operation(self.validator, provider, specification))
        self.assertEqual(["pre", "backend", "post"], events)
        self.validator.parse_spec_characteristics.assert_not_called()

    def test_backend_failure_does_not_invoke_post_validation(self):
        @plugin_decorators.on_service_spec_validation
        def operation(validator, provider, specification, model):
            raise ServiceError("invalid")

        with self.assertRaises(ServiceError):
            operation(self.validator, object(), self.specification)
        self.plugin.on_pre_service_spec_validation.assert_called_once()
        self.plugin.on_post_service_spec_validation.assert_not_called()

    def test_no_matching_plugin_returns_without_running_backend_operation(self):
        self.resolve.return_value = None
        backend = Mock(return_value="ordinary")
        wrapped = plugin_decorators.on_service_spec_validation(backend)
        validator, provider, specification = self.validator, object(), self.specification
        self.assertIsNone(wrapped(validator, provider, specification))
        backend.assert_not_called()
        self.load.assert_not_called()


class ServiceFormCharacteristicTests(SimpleTestCase):
    def setUp(self):
        self.validator = ServiceValidator()
        self.provider = SimpleNamespace(name="seller", get_party_url=lambda: "https://party.example/seller")
        self.spec = {
            "relatedParty": [{"id": "seller", "role": "Seller"}],
            "specCharacteristic": [
                characteristic("Service Type", {"id": "plugin-category"}),
                characteristic("URL", "https://provider.example/service"),
                characteristic("Media Type", "application/json"),
                characteristic("region", "eu"),
                characteristic("enabled", False),
            ],
        }
        self.model = SimpleNamespace(
            requires_file=False,
            media_types=["application/json"],
            form={
                "region": {"type": "select", "mandatory": True, "options": [{"value": "EU"}, {"value": "US"}]},
                "enabled": {"type": "checkbox", "mandatory": True},
                "description": {"type": "textarea"},
            },
        )
        self.plugin = Mock(_model=self.model)
        resolve_patch = patch.object(plugin_decorators, "_get_plugin_model", return_value=self.model)
        resolve_patch.start()
        self.addCleanup(resolve_patch.stop)
        load_patch = patch.object(plugin_decorators, "_load_plugin_model", return_value=self.plugin)
        load_patch.start()
        self.addCleanup(load_patch.stop)

    def test_individual_form_characteristics_reach_post_validation(self):
        self.validator.validate("create", self.provider, self.spec)
        self.plugin.on_post_service_spec_validation.assert_called_once_with(self.provider, self.spec)
        values = parse_values(self.validator, self.spec, self.model.form)
        self.assertEqual("eu", values["region"])
        self.assertIs(False, values["enabled"])
        self.assertNotIn("metadata", values)

    def test_missing_required_form_characteristic_rejected(self):
        self.spec["specCharacteristic"].pop(3)
        with self.assertRaisesRegex(ServiceError, "region"):
            self.validator.validate("create", self.provider, self.spec)
        self.plugin.on_post_service_spec_validation.assert_not_called()

    def test_metadata_object_does_not_replace_individual_characteristics(self):
        self.spec["specCharacteristic"] = self.spec["specCharacteristic"][:3] + [
            characteristic("Metadata", {"region": "eu", "enabled": True})
        ]
        with self.assertRaisesRegex(ServiceError, "region"):
            self.validator.validate("create", self.provider, self.spec)

    def test_form_field_types_and_select_options_are_checked(self):
        for name, value in [("region", "unknown"), ("region", True), ("enabled", "false"), ("description", 123)]:
            with self.subTest(name=name, value=value):
                spec = deepcopy(self.spec)
                spec["specCharacteristic"] = [c for c in spec["specCharacteristic"] if c["name"] != name]
                spec["specCharacteristic"].append(characteristic(name, value))
                with self.assertRaises(ServiceError):
                    self.validator.validate("create", self.provider, spec)
        self.plugin.on_post_service_spec_validation.assert_not_called()

    def test_duplicate_multivalue_and_missing_form_values_are_rejected(self):
        for extra in [
            characteristic("REGION", "US"),
            {"name": "description", "characteristicValueSpecification": []},
            {"name": "description", "characteristicValueSpecification": [{}]},
            {"name": "description", "characteristicValueSpecification": [{"value": "a"}, {"value": "b"}]},
        ]:
            with self.subTest(extra=extra), self.assertRaises(ServiceError):
                spec = deepcopy(self.spec)
                spec["specCharacteristic"].append(extra)
                self.validator.validate("create", self.provider, spec)

    def test_default_does_not_satisfy_missing_mandatory_characteristic(self):
        self.model.form["region"]["default"] = "EU"
        self.spec["specCharacteristic"].pop(3)
        with self.assertRaisesRegex(ServiceError, "Missing mandatory service characteristic region"):
            self.validator.validate("create", self.provider, self.spec)
        self.plugin.on_post_service_spec_validation.assert_not_called()

    def test_optional_field_default_is_ignored_by_backend(self):
        self.model.form["description"]["default"] = 123
        before = deepcopy(self.spec)
        self.validator.validate("create", self.provider, self.spec)
        self.assertEqual(before, self.spec)
        self.plugin.on_post_service_spec_validation.assert_called_once()

    def test_partial_updates_validate_the_existing_form_characteristics(self):
        self.spec.update({"id": "spec-1", "version": "1.0"})
        self.validator._catalog = Mock()
        self.validator._catalog.get_specification.return_value = self.spec
        self.validator.validate(
            "update",
            self.provider,
            {"id": "spec-1", "description": "updated", "specCharacteristic": self.spec["specCharacteristic"]},
        )
        validated = self.plugin.on_post_service_spec_validation.call_args.args[1]
        self.assertEqual("eu", parse_values(self.validator, validated, self.model.form)["region"])


class ServiceTypeResolutionTests(SimpleTestCase):
    @patch("wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.filter")
    def test_category_reference_selects_local_plugin_without_catalog_calls(self, lookup):
        model = object()
        lookup.return_value = [model]
        specification = {"specCharacteristic": [characteristic("Service Type", {"id": "category-1"})]}
        with patch.object(ServiceCatalog, "_request") as request:
            self.assertIs(
                model,
                plugin_decorators._get_plugin_model(
                    category_id=ServiceValidator._get_spec_characteristic_value(
                        ServiceValidator().parse_spec_characteristics(specification), "service type"
                    )["id"]
                ),
            )
            request.assert_not_called()
        lookup.assert_called_once_with(category_id="category-1")

    @patch("wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.filter")
    def test_present_duplicate_or_malformed_service_type_rejected(self, lookup):
        valid = characteristic("Service Type", {"id": "category-1"})
        for characteristics in [
            [valid, characteristic("SERVICE TYPE", {"id": "category-2"})],
            [characteristic("Service Type", "internal-plugin-id")],
            [characteristic("Service Type", {})],
            [characteristic("Service Type", {"id": ""})],
            [characteristic("Service Type", {"id": "  "})],
            [characteristic("Service Type", {"id": None})],
            [{"name": "Service Type", "characteristicValueSpecification": []}],
            [
                {
                    "name": "Service Type",
                    "characteristicValueSpecification": [{"value": {"id": "a"}}, {"value": {"id": "b"}}],
                }
            ],
            [{"name": "Service Type", "characteristicValueSpecification": [{}]}],
        ]:
            with self.subTest(characteristics=characteristics), self.assertRaises(ServiceError):
                ServiceValidator().parse_spec_characteristics({"specCharacteristic": characteristics})
        lookup.assert_not_called()

    @patch("wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.filter")
    def test_ambiguous_category_binding_rejected(self, lookup):
        lookup.return_value = [object(), object()]
        with self.assertRaises(ServiceError):
            plugin_decorators._get_plugin_model(category_id="category-1")

    @patch("wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.filter")
    def test_category_without_plugin_skips_plugin_specific_validation(self, lookup):
        lookup.return_value = []
        specification = {"specCharacteristic": [characteristic("Service Type", {"id": "ordinary-category"})]}
        with patch.object(plugin_decorators, "_load_plugin_model") as load:
            ServiceValidator().validate("create", object(), specification)
            load.assert_not_called()

    @patch("wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.filter")
    def test_category_reference_id_is_used_and_other_reference_fields_preserved(self, lookup):
        lookup.return_value = [object()]
        reference = {"id": "category-1", "name": "Public service type", "href": "https://catalog.example/type"}
        specification = {"specCharacteristic": [characteristic(" service TYPE ", reference)]}
        original = deepcopy(specification)
        plugin_decorators._get_plugin_model(
            category_id=ServiceValidator._get_spec_characteristic_value(
                ServiceValidator().parse_spec_characteristics(specification), "service type"
            )["id"]
        )
        lookup.assert_called_once_with(category_id="category-1")
        self.assertEqual(original, specification)

    def test_service_without_service_type_is_accepted_by_backend_route(self):
        from django.test import RequestFactory
        from django.urls import resolve
        import json

        request = RequestFactory().post(
            "/charging/api/assetManagement/assets/validateServiceJob",
            data=json.dumps({"action": "create", "service": {"name": "example"}}),
            content_type="application/json",
        )
        request.user = SimpleNamespace(
            is_anonymous=False,
            is_staff=False,
            userprofile=SimpleNamespace(
                current_organization=object(),
                get_current_roles=lambda: ["provider"],
            ),
        )
        self.assertEqual(200, resolve(request.path).func(request).status_code)


class OrdinaryServiceEarlyReturnTests(SimpleTestCase):
    def test_no_service_type_prepares_then_skips_plugin_processing(self):
        validator = ServiceValidator()
        specification = {
            "id": "ordinary-spec",
            "version": "not a backend plugin version",
            "specCharacteristic": [characteristic("URL", 123), {"name": "arbitrary", "value": "catalog-owned"}],
        }
        with patch.object(validator, "_prepare") as prepare, patch.object(
            validator._catalog, "get_specification"
        ) as download, patch.object(plugin_decorators, "_get_plugin_model") as resolve, patch.object(
            plugin_decorators, "_load_plugin_model"
        ) as load, patch.object(
            validator, "parse_spec_characteristics"
        ) as parse:
            for action in ("create", "update"):
                with self.subTest(action=action):
                    self.assertIsNone(validator.validate(action, object(), specification))
            parse.assert_not_called()
            self.assertEqual(2, prepare.call_count)
            prepare.assert_called_with(specification)
            download.assert_not_called()
            resolve.assert_not_called()
            load.assert_not_called()

    def test_plugin_specification_is_parsed_once_inside_backend_operation(self):
        validator = ServiceValidator()
        model = SimpleNamespace(
            requires_file=False, media_types=["application/json"], form={"region": {"type": "text", "mandatory": True}}
        )
        specification = {
            "specCharacteristic": [
                characteristic("Service Type", {"id": "plugin-category"}),
                characteristic("URL", "https://provider.example/service"),
                characteristic("Media Type", "application/json"),
                characteristic("region", "EU"),
            ]
        }
        plugin = Mock(_model=model)
        with patch.object(
            validator, "parse_spec_characteristics", wraps=validator.parse_spec_characteristics
        ) as parse, patch.object(plugin_decorators, "_get_plugin_model", return_value=model) as resolve, patch.object(
            plugin_decorators, "_load_plugin_model", return_value=plugin
        ):
            validator.validate("create", object(), specification)
            parse.assert_called_once_with(specification)
            resolve.assert_called_once_with(category_id="plugin-category")
            plugin.on_post_service_spec_validation.assert_called_once()


class ManagedFileValidationTests(SimpleTestCase):
    def setUp(self):
        self.validator = ServiceValidator()
        self.provider = SimpleNamespace(pk="seller")
        self.file_id = "507f1f77bcf86cd799439011"
        self.file = SimpleNamespace(
            provider_id=self.provider.pk,
            resource_path="media/assets/seller/data.json",
            content_type="application/json",
            download_link="https://files.example/data.json",
        )
        self.spec = {
            "specCharacteristic": [
                characteristic("Service Type", {"id": "plugin-category"}),
                characteristic("File", {"id": self.file_id}),
            ],
        }
        self.model = SimpleNamespace(requires_file=True, media_types=["application/json"], form={})
        self.plugin = Mock(_model=self.model)
        lookup = patch("wstore.asset_manager.service_validator.Resource.objects.get", return_value=self.file)
        self.lookup = lookup.start()
        self.addCleanup(lookup.stop)
        resolve = patch.object(plugin_decorators, "_get_plugin_model", return_value=self.model)
        self.resolve = resolve.start()
        self.addCleanup(resolve.stop)
        load = patch.object(plugin_decorators, "_load_plugin_model", return_value=self.plugin)
        load.start()
        self.addCleanup(load.stop)

    def test_owned_upload_passes_without_url_or_media_type_characteristics(self):
        from bson import ObjectId

        original = deepcopy(self.spec)
        self.validator.validate("create", self.provider, self.spec)
        self.lookup.assert_called_once_with(pk=ObjectId(self.file_id))
        self.assertEqual(original, self.spec)
        self.plugin.on_post_service_spec_validation.assert_called_once_with(self.provider, self.spec)

    def test_missing_file_rejected_when_required(self):
        self.spec["specCharacteristic"].pop()
        with self.assertRaisesRegex(ServiceError, "File characteristic"):
            self.validator.validate("create", self.provider, self.spec)
        self.lookup.assert_not_called()
        self.plugin.on_post_service_spec_validation.assert_not_called()

    def test_non_file_plugin_needs_only_its_form_fields(self):
        self.model.requires_file = False
        self.model.form = {"endpoint": {"type": "text", "mandatory": True}}
        self.spec["specCharacteristic"][1] = characteristic("endpoint", "plugin-defined-value")
        self.validator.validate("create", self.provider, self.spec)
        self.lookup.assert_not_called()
        self.plugin.on_post_service_spec_validation.assert_called_once()

    def test_non_file_plugin_does_not_process_file_characteristic(self):
        self.model.requires_file = False
        self.spec["specCharacteristic"][1] = characteristic("File", "catalog-owned-value")
        self.validator.validate("create", self.provider, self.spec)
        self.lookup.assert_not_called()

    def test_malformed_file_references_are_rejected_without_lookup(self):
        for value in [None, self.file_id, {}, {"id": 123}, {"id": "invalid"}, {"id": ""}]:
            with self.subTest(value=value):
                self.spec["specCharacteristic"][1] = characteristic("File", value)
                with self.assertRaisesRegex(ServiceError, "uploaded file reference"):
                    self.validator.validate("create", self.provider, self.spec)
        self.lookup.assert_not_called()

    def test_file_must_have_one_characteristic_with_one_value(self):
        invalid_entries = [
            [characteristic("File", {"id": self.file_id}), characteristic("FILE", {"id": self.file_id})],
            [{"name": "File", "characteristicValueSpecification": []}],
            [{"name": "File", "characteristicValueSpecification": [{}]}],
            [{"name": "File", "characteristicValueSpecification": [{"value": {}}, {"value": {}}]}],
        ]
        for entries in invalid_entries:
            with self.subTest(entries=entries):
                self.spec["specCharacteristic"] = self.spec["specCharacteristic"][:1] + entries
                with self.assertRaises(ServiceError):
                    self.validator.validate("create", self.provider, self.spec)
        self.lookup.assert_not_called()

    def test_missing_upload_is_a_validation_error(self):
        from wstore.asset_manager.models import Resource

        self.lookup.side_effect = Resource.DoesNotExist
        with self.assertRaisesRegex(ServiceError, "does not exist"):
            self.validator.validate("create", self.provider, self.spec)

    def test_another_providers_upload_is_rejected_before_post_hook(self):
        from django.core.exceptions import PermissionDenied

        self.file.provider_id = "other-provider"
        with self.assertRaisesRegex(PermissionDenied, "does not belong"):
            self.validator.validate("create", self.provider, self.spec)
        self.plugin.on_post_service_spec_validation.assert_not_called()

    def test_url_only_resource_is_not_an_uploaded_file(self):
        self.file.resource_path = ""
        with self.assertRaisesRegex(ServiceError, "not an external URL"):
            self.validator.validate("create", self.provider, self.spec)

    def test_media_type_comes_from_upload_even_when_spec_claims_supported_type(self):
        self.file.content_type = "image/png"
        self.spec["specCharacteristic"].append(characteristic("Media Type", "application/json"))
        with self.assertRaisesRegex(ServiceError, "media type is not supported"):
            self.validator.validate("create", self.provider, self.spec)
        self.plugin.on_post_service_spec_validation.assert_not_called()

    def test_media_types_are_case_insensitive_and_empty_list_is_unrestricted(self):
        self.file.content_type = "APPLICATION/JSON"
        self.validator.validate("create", self.provider, self.spec)
        self.model.media_types = []
        self.file.content_type = "image/png"
        self.validator.validate("create", self.provider, self.spec)

    def test_update_checks_proposed_file_and_passes_original_specification_to_hooks(self):
        self.spec.update({"id": "spec-1", "version": "1.0"})
        previous = deepcopy(self.spec)
        previous["specCharacteristic"][1] = characteristic("File", {"id": "507f1f77bcf86cd799439012"})
        self.validator._catalog = Mock()
        self.validator._catalog.get_specification.return_value = previous
        self.validator.validate("update", self.provider, self.spec)
        self.plugin.on_post_service_spec_validation.assert_called_once_with(self.provider, self.spec)
        self.assertIs(self.spec, self.plugin.on_post_service_spec_validation.call_args.args[1])
        self.file.provider_id = "other-provider"
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            self.validator.validate("update", self.provider, self.spec)

    def test_no_plugin_means_file_characteristic_is_not_processed(self):
        self.resolve.return_value = None
        for action in ("create", "update"):
            with self.subTest(action=action):
                self.validator.validate(action, self.provider, self.spec)
        self.spec["specCharacteristic"].pop(0)
        self.spec["specCharacteristic"][0] = characteristic("File", "ordinary-catalog-value")
        self.validator.validate("create", self.provider, self.spec)
        self.lookup.assert_not_called()
        self.plugin.on_pre_service_spec_validation.assert_not_called()
        self.plugin.on_post_service_spec_validation.assert_not_called()

    def test_file_permissions_are_returned_as_403_by_service_endpoint(self):
        import json
        from django.test import RequestFactory
        from django.urls import resolve

        self.file.provider_id = "other-provider"
        request = RequestFactory().post(
            "/charging/api/assetManagement/assets/validateServiceJob",
            data=json.dumps({"action": "create", "service": self.spec}),
            content_type="application/json",
        )
        request.user = SimpleNamespace(
            is_anonymous=False,
            is_staff=False,
            userprofile=SimpleNamespace(current_organization=self.provider, get_current_roles=lambda: ["provider"]),
        )
        self.assertEqual(403, resolve(request.path).func(request).status_code)
