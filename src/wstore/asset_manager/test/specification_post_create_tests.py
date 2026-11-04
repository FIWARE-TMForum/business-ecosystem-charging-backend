"""Post-write callbacks use persisted documents without repeating pre-write checks."""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve
from parameterized import parameterized_class

from wstore.asset_manager.product_validator import ProductValidator
from wstore.asset_manager.offering_validator import OfferingValidator
from wstore.asset_manager.resource_plugins import decorators
from wstore.asset_manager.resource_plugins.plugin import ServicePlugin, ResourcePlugin
from wstore.asset_manager.resource_plugins.plugin_error import PluginError
from wstore.asset_manager.resource_validator import ResourceValidator
from wstore.asset_manager.service_validator import ServiceValidator


@parameterized_class(
    ("kind", "validator_class", "handler_class", "characteristics_field", "values_field", "operation"),
    [
        (kind, validator, handler, field, values, operation)
        for kind, validator, handler, field, values in (
            ("service", ServiceValidator, ServicePlugin, "specCharacteristic", "characteristicValueSpecification"),
            (
                "resource",
                ResourceValidator,
                ResourcePlugin,
                "resourceSpecCharacteristic",
                "resourceSpecCharacteristicValue",
            ),
        )
        for operation in ("creation", "update")
    ],
)
class SpecificationPostActionTests(SimpleTestCase):
    def setUp(self):
        self.provider = object()
        self.user = SimpleNamespace(
            is_anonymous=False,
            is_staff=False,
            userprofile=SimpleNamespace(current_organization=self.provider, get_current_roles=lambda: ["provider"]),
        )
        self.spec = {
            "id": "created-spec-1",
            "href": "https://catalog.example/specifications/created-spec-1",
            "name": "Created specification",
            self.characteristics_field: [
                {"name": self.kind.title() + " Type", self.values_field: [{"value": "category-1"}]}
            ],
        }
        self.model = SimpleNamespace(requires_file=True, form={"required": {"mandatory": True}})
        self.plugin = Mock(spec=self.handler_class, _model=self.model)
        self.hook = getattr(self.plugin, "on_post_" + self.kind + "_spec_" + self.operation)
        self.pre_action = "create" if self.operation == "creation" else "update"
        self.post_action = "post-" + self.pre_action
        self.validator = self.validator_class()
        self.validator._catalog = Mock()
        self.validator._catalog.get_specification.return_value = deepcopy(self.spec)
        catalog_read = patch(
            "wstore.store_commons." + self.kind + "_catalog." + self.kind.title() + "Catalog.get_specification",
            return_value=deepcopy(self.spec),
        )
        self.catalog_read = catalog_read.start()
        self.addCleanup(catalog_read.stop)
        registry = patch.object(decorators.ResourcePlugin.objects, "filter", return_value=[self.model])
        loader = patch.object(decorators, "_load_plugin_model", return_value=self.plugin)
        file_lookup = patch("wstore.asset_manager.specification_validator.Resource.objects.get")
        self.registry = registry.start()
        self.addCleanup(registry.stop)
        self.loader = loader.start()
        self.addCleanup(loader.stop)
        self.file_lookup = file_lookup.start()
        self.addCleanup(file_lookup.stop)

    def post(self, specification=None, action=None):
        action = self.post_action if action is None else action
        request = RequestFactory().post(
            "/charging/api/assetManagement/assets/validate" + self.kind.title() + "Job",
            data=json.dumps({"action": action, self.kind: self.spec if specification is None else specification}),
            content_type="application/json",
        )
        request.user = self.user
        return resolve(request.path).func(request)

    def test_post_action_delivers_persisted_document_without_validation_or_writes(self):
        original = deepcopy(self.spec)
        self.validator.validate(self.post_action, self.provider, self.spec)
        self.hook.assert_called_once_with(self.provider, self.spec)
        self.assertIs(self.spec, self.hook.call_args.args[1])
        self.assertEqual(["on_post_" + self.kind + "_spec_" + self.operation], [c[0] for c in self.plugin.method_calls])
        self.registry.assert_called_once_with(category_id="category-1", type=self.kind)
        self.file_lookup.assert_not_called()
        self.assertEqual([], self.validator._catalog.method_calls)
        self.catalog_read.assert_not_called()
        self.assertEqual(original, self.spec)

    def test_real_endpoint_dispatches_persisted_document(self):
        response = self.post()
        self.assertEqual(200, response.status_code)
        self.hook.assert_called_once_with(self.provider, self.spec)
        self.file_lookup.assert_not_called()

    def test_plugin_error_is_reported_without_modifying_persisted_document(self):
        original = deepcopy(self.spec)
        self.hook.side_effect = PluginError("post-write failed")
        response = self.post()
        self.assertEqual(422, response.status_code)
        self.assertIn("post-write failed", response.content.decode())
        self.assertEqual(original, self.spec)

    def test_unexpected_plugin_error_uses_existing_server_error_response(self):
        self.hook.side_effect = RuntimeError("private plugin detail")
        with self.assertLogs("wstore.default_logger", level="ERROR"):
            response = self.post()
        self.assertEqual(500, response.status_code)
        self.assertNotIn("private plugin detail", response.content.decode())

    def test_persisted_document_requires_nonempty_string_id(self):
        for value in (None, "", "  ", 1, {}, []):
            with self.subTest(value=value):
                spec = {**self.spec, "id": value}
                self.assertEqual(400, self.post(spec).status_code)
        spec = deepcopy(self.spec)
        del spec["id"]
        self.assertEqual(400, self.post(spec).status_code)
        self.hook.assert_not_called()
        self.registry.assert_not_called()

    def test_malformed_document_is_rejected(self):
        for spec in ([], "created-spec-1", 1):
            with self.subTest(spec=spec):
                self.assertEqual(400, self.post(spec).status_code)
        self.registry.assert_not_called()

    def test_ordinary_specification_skips_plugin_and_file_checks(self):
        spec = {
            "id": "ordinary-spec",
            self.characteristics_field: [{"name": "File", self.values_field: [{"value": "not-a-file"}]}],
        }
        self.assertEqual(200, self.post(spec).status_code)
        self.registry.assert_not_called()
        self.hook.assert_not_called()
        self.file_lookup.assert_not_called()

    def test_uninstalled_category_skips_callback(self):
        self.registry.return_value = []
        self.assertEqual(200, self.post().status_code)
        self.loader.assert_not_called()

    def test_malformed_or_ambiguous_type_does_not_notify_plugin(self):
        entry = self.spec[self.characteristics_field][0]
        for entries in ([entry, deepcopy(entry)], [{**entry, self.values_field: [{"value": ""}]}]):
            with self.subTest(entries=entries):
                self.assertEqual(400, self.post({**self.spec, self.characteristics_field: entries}).status_code)
        self.registry.return_value = [self.model, self.model]
        self.assertEqual(400, self.post().status_code)
        self.hook.assert_not_called()

    def test_default_hook_is_optional_for_existing_domain_plugins(self):
        self.loader.return_value = self.handler_class(self.model)
        self.assertEqual(200, self.post().status_code)

    def test_pre_action_does_not_invoke_post_hook(self):
        self.model.requires_file = False
        self.model.form = {}
        proposed = deepcopy(self.spec)
        if self.operation == "creation":
            del proposed["id"]
        self.assertEqual(200, self.post(proposed, action=self.pre_action).status_code)
        getattr(self.plugin, "on_pre_" + self.kind + "_spec_" + self.operation).assert_called_once()
        self.hook.assert_not_called()

    def test_pre_and_post_actions_invoke_only_their_matching_phase(self):
        self.model.requires_file = False
        self.model.form = {}
        proposed = deepcopy(self.spec)
        if self.operation == "creation":
            del proposed["id"]
        self.assertEqual(200, self.post(proposed, action=self.pre_action).status_code)
        self.assertEqual(200, self.post().status_code)
        self.assertEqual(
            ["on_pre_" + self.kind + "_spec_" + self.operation, "on_post_" + self.kind + "_spec_" + self.operation],
            [call[0] for call in self.plugin.method_calls],
        )
        getattr(self.plugin, "on_pre_" + self.kind + "_spec_" + self.operation).assert_called_once_with(
            self.provider, proposed
        )
        self.hook.assert_called_once_with(self.provider, self.spec)
        other = "update" if self.operation == "creation" else "creation"
        for phase in ("pre", "post"):
            getattr(self.plugin, "on_" + phase + "_" + self.kind + "_spec_" + other).assert_not_called()

    def test_plugin_interface_uses_matching_names_for_both_phases(self):
        for phase in ("pre", "post"):
            self.assertTrue(hasattr(self.handler_class, "on_" + phase + "_" + self.kind + "_spec_" + self.operation))
            self.assertFalse(hasattr(self.handler_class, "on_" + phase + "_" + self.kind + "_spec_validation"))

    def test_authentication_and_seller_permissions_apply_to_post_action(self):
        self.user.is_anonymous = True
        self.assertEqual(401, self.post().status_code)
        self.user.is_anonymous = False
        self.user.userprofile.get_current_roles = lambda: ["customer"]
        self.assertEqual(403, self.post().status_code)
        self.hook.assert_not_called()

    def test_invalid_action_reports_supported_actions(self):
        response = self.post(action="not-an-action")
        self.assertEqual(400, response.status_code)
        self.assertIn(self.post_action, response.content.decode())
        self.hook.assert_not_called()


class PostActionScopeTests(SimpleTestCase):
    def test_products_and_offerings_inherit_default_post_actions_without_plugin_dispatch(self):
        from wstore.asset_manager.catalog_validator import CatalogValidator

        for validator in (ProductValidator(), OfferingValidator()):
            for action, method in (("post-create", "post_create"), ("post-update", "post_update")):
                with self.subTest(validator=validator, action=action):
                    self.assertIs(getattr(type(validator), method), getattr(CatalogValidator, method))
                    validator.validate(action, object(), {"id": "spec-1"})
