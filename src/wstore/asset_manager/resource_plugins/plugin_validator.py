# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid

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
# along with this program.  If not, see <http://www.gnu.org/licenses/>..


from logging import getLogger

from wstore.store_commons.utils.name import is_valid_id
from wstore.store_commons.utils.version import is_valid_version

logger = getLogger("wstore.default_logger")


class PluginValidator:
    REQUIRED_FIELDS = [
        ("name", str),
        ("type", str),
        ("author", str),
        ("requires_file", bool),
        ("module", str),
        ("version", str),
    ]

    VALID_OVERRIDE_VALUES = ["NAME", "VERSION", "OPEN"]

    PULL_ACCOUNTING_REQ_METHODS = ["get_pending_accounting", "get_usage_specs"]

    def _validate_plugin_form(self, form_info):
        """
        Validates the structure of the form definition of a plugin
        included in the package.json file
        """

        logger.debug("Validating plugin form")

        reason = None

        def _text_type(key, value, attrs):
            reasonStr = ""
            for attr in attrs:
                if attr in value and not isinstance(value[attr], str):
                    reasonStr += f"\nInvalid form field: {attr} field in {key} entry must be an string"

            return reasonStr

        def _bool_type(key, value, attrs):
            reasonStr = ""
            for attr in attrs:
                if attr in value and not isinstance(value[attr], bool):
                    reasonStr += f"\nInvalid form field: {attr} field in {key} entry must be a boolean"

            return reasonStr

        def _validate_text_type(key, value):
            reasonStr = _text_type(key, value, ["default", "placeholder", "label"])
            reasonStr += _bool_type(key, value, ["mandatory"])
            return reasonStr if len(reasonStr) else None

        def _validate_checkbox_type(key, value):
            reasonStr = _text_type(key, value, ["label"])
            reasonStr += _bool_type(key, value, ["default", "mandatory"])

            return reasonStr if len(reasonStr) else None

        def _validate_select_type(key, value):
            reasonStr = _text_type(key, value, ["default", "label"])
            reasonStr += _bool_type(key, value, ["mandatory"])

            if "options" not in value or not isinstance(value["options"], list) or not len(value["options"]):
                reasonStr += "\nInvalid form field: Missing or invalid options in " + k + " field"
            else:
                for option in value["options"]:
                    if not isinstance(option, dict) or "text" not in option or "value" not in option:
                        reasonStr += (
                            "\nInvalid form field: Invalid option in "
                            + k
                            + " field, wrong option type or missing field"
                        )
                    else:
                        reasonStr += _text_type(key, option, ["text", "value"])

            return reasonStr if len(reasonStr) else None

        valid_types = {
            "text": _validate_text_type,
            "textarea": _validate_text_type,
            "checkbox": _validate_checkbox_type,
            "select": _validate_select_type,
        }

        for k, v in form_info.items():
            if k.strip().lower() in ("file", "service type", "resource type"):
                return "Invalid form field: " + k + " is reserved for specification references"

            # Validate component
            if not isinstance(v, dict):
                reason = "Invalid form field: " + k + " entry is not an object"
                break

            # Validate type value
            if "type" not in v:
                reason = "Invalid form field: Missing type in " + k + " entry"
                break

            if not v["type"] in valid_types:
                reason = "Invalid form field: type " + v["type"] + " in " + k + " entry is not a valid type"
                break

            # Validate name format
            if not is_valid_id(k):
                reason = "Invalid form field: " + k + " is not a valid name"
                break

            # Validate specific fields
            reason = valid_types[v["type"]](k, v)
            if reason is not None:
                break

        return reason

    def _check_required_fields(self, plugin_info):
        errors = []
        # Validate structure
        for field in self.REQUIRED_FIELDS:
            if field[0] not in plugin_info:
                errors.append(f"Missing required field: {field[0]}")
            elif not isinstance(plugin_info[field[0]], field[1]):
                errors.append(
                    f"Field `{field[0]}` should be {field[1].__name__} but found {type(plugin_info[field[0]]).__name__}."
                )
        return errors

    def validate_plugin_info(self, plugin_info):
        """
        Validates the structure of the package.json file of a plugin
        """

        logger.debug("Validating plugin info.")

        # Check plugin_info format
        if not isinstance(plugin_info, dict):
            logger.error("Plugin info is not a dictionary")
            return ["Plugin info must be a dict instance"]

        errors = self._check_required_fields(plugin_info)
        if errors:
            logger.error("Errors in required fields in plugin info")
            return errors

        if plugin_info["type"] not in ("service", "resource"):
            errors.append("Plugin `type` must be service or resource")

        if not is_valid_id(plugin_info["name"]):
            logger.error("Invalid name format: invalid character")
            errors.append("Invalid name format: invalid character")

        # Validate overrides
        if "overrides" in plugin_info and not all(
            ovrd in self.VALID_OVERRIDE_VALUES for ovrd in plugin_info["overrides"]
        ):
            logger.error("Invalid override values")
            errors.append(f"Override values should be one of: {self.VALID_OVERRIDE_VALUES}")

        if "media_types" in plugin_info and (
            not isinstance(plugin_info["media_types"], list)
            or any(
                not isinstance(media_type, str) or not media_type.strip()
                for media_type in plugin_info["media_types"]
            )
        ):
            logger.error("Invalid media types")
            errors.append("Plugin `media_types` must be a list of non-empty strings")

        if not is_valid_version(plugin_info["version"]):
            logger.error("Invalid plugin version")
            errors.append("Invalid format in plugin version")

        if "pull_accounting" in plugin_info and not isinstance(plugin_info["pull_accounting"], bool):
            logger.error("Invalid pull accounting")
            errors.append("Plugin `pull_accounting` property must be a boolean")

        if "form" in plugin_info:
            if not isinstance(plugin_info["form"], dict):
                logger.error("Invalid form")
                errors.append("Invalid format in `form` field, must be an object")
            else:
                validate_form_error = self._validate_plugin_form(plugin_info["form"])
                if validate_form_error:
                    logger.error("Invalid form")
                    errors.append(validate_form_error)

        if "form_order" in plugin_info:
            can_check_keys = True
            if not isinstance(plugin_info["form_order"], list):
                logger.error("Invalid form order")
                errors.append("Invalid format in `form_order`")
                can_check_keys = False
            if "form" not in plugin_info:
                logger.error("Form order but no form")
                errors.append("`form_order` cannot be specified without a `form`")
                can_check_keys = False
            else:
                matched_keys = [key for key in plugin_info["form"].keys() if key in plugin_info["form_order"]]
                if can_check_keys and (
                    len(plugin_info["form"].keys()) != len(plugin_info["form_order"])
                    or len(matched_keys) != len(plugin_info["form_order"])
                ):
                    logger.error("Form incomplete")
                    errors.append("If `form_order` is provided all form keys need to be provided")

        return errors

    def validate_pull_accounting(self, plugin_info, plugin_class):
        pulls_accounting = plugin_info.get("pull_accounting", False)
        pull_accounting_implemented = {
            method: method in plugin_class.__dict__ for method in self.PULL_ACCOUNTING_REQ_METHODS
        }

        if pulls_accounting and sum(pull_accounting_implemented.values()) != 2:
            logger.error("Pull accounting methods missing")
            return (
                "Pull accounting is true, but some neccesary methods are missing. Here are the neccesary methods: \n"
                + "\n".join(
                    f"{method}: {'IMPLEMENTED' if value else 'MISSING'}"
                    for method, value in pull_accounting_implemented.items()
                )
            )
        elif not pulls_accounting and sum(pull_accounting_implemented.values()) != 0:
            logger.error("Pull accounting methods unnecessary")
            return (
                "Pull accounting is false, but some methods are implemented. Here are the neccesary methods: \n"
                + "\n".join(
                    f"{method}: {'IMPLEMENTED' if value else 'OK'}"
                    for method, value in pull_accounting_implemented.items()
                )
            )
