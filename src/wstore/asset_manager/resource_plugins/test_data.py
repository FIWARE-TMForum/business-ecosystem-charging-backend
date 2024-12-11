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

PLUGIN_INFO = {
    "name": "test plugin",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "category_id": "cat_2",
    "media_types": [
        "application/x-widget+mashable-application-component",
        "application/x-mashup+mashable-application-component",
        "application/x-operator+mashable-application-component",
    ],
    "formats": ["FILE"],
    "form": {
        "vendor": {
            "type": "text",
            "placeholder": "Vendor",
            "default": "default vendor",
            "label": "Vendor",
        },
        "name": {
            "type": "text",
            "placeholder": "Name",
            "default": "default name",
            "label": "Name",
            "mandatory": True,
        },
        "type": {
            "type": "select",
            "label": "Select",
            "options": [
                {"text": "Option 1", "value": "opt1"},
                {"text": "Option 2", "value": "opt2"},
            ],
        },
        "is_op": {
            "type": "checkbox",
            "label": "Is a checkbox",
            "text": "The checkbox",
            "default": True,
        },
        "area": {
            "type": "textarea",
            "label": "Area",
            "default": "default value",
            "placeholder": "placeholder",
        },
    },
}

PLUGIN_INFO2 = {
    "name": "test plugin 5",
    "author": "test author",
    "category_id": "cat2",
    "version": "1.0",
    "module": "test.TestPlugin",
    "formats": ["FILE"],
}

PLUGIN_INFO3 = {
    "name": "test plugin 8",
    "author": "test author",
    "category_id": "cat2",
    "version": "1.0",
    "module": "test.TestPlugin",
    "formats": ["FILE"],
    "pull_accounting": True
}

PLUGIN_INFO_ACCOUNTING = {
    "name": "test plugin",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "formats": ["FILE"],
    "pull_accounting": True,
}

PLUGIN_INFO_DOWNGRADE = {
    "name": "test plugin",
    "author": "test author dg",
    "version": "0.2",
    "module": "test.TestPluginDg",
    "formats": ["FILE", "URL"],
}

PLUGIN_INFO_DOWNGRADE_ACCOUNTING = {
    "name": "test plugin",
    "author": "test author dg",
    "version": "0.2",
    "module": "test.TestPluginDg",
    "formats": ["FILE", "URL"],
    "pull_accounting": True,
}

PLUGIN_INFO_ACCOUNTING = {
    "name": "test plugin",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "formats": ["FILE"],
    "pull_accounting": True,
}

PLUGIN_INFO_DOWNGRADE = {
    "name": "test plugin",
    "author": "test author dg",
    "version": "0.2",
    "module": "test.TestPluginDg",
    "formats": ["FILE", "URL"],
    "category_id": "cat_2"
}

PLUGIN_INFO_DOWNGRADE_ACCOUNTING = {
    "name": "test plugin",
    "author": "test author dg",
    "version": "0.2",
    "module": "test.TestPluginDg",
    "formats": ["FILE", "URL"],
    "pull_accounting": True,
    "category_id": "cat_2"
}

MISSING_NAME = {
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": [],
    "formats": ["FILE"],
}

INVALID_NAME = {
    "name": "inv&name",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": [],
    "formats": ["FILE"],
}

MISSING_AUTHOR = {
    "name": "plugin name",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": [],
    "formats": ["FILE"],
}

MISSING_FORMATS = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": [],
}

MISSING_MODULE = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.0",
    "media_types": [],
    "formats": ["FILE"],
}

MISSING_VERSION = {
    "name": "plugin name",
    "author": "test author",
    "module": "test.TestPlugin",
    "media_types": [],
    "formats": ["FILE"],
}

INVALID_NAME_TYPE = {
    "name": 9,
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": [],
    "formats": ["FILE"],
}

INVALID_AUTHOR_TYPE = {
    "name": "plugin name",
    "author": 10,
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": [],
    "formats": ["FILE"],
}

INVALID_FORMAT_TYPE = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": [],
    "formats": "FILE",
}

INVALID_FORMAT = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": [],
    "formats": ["FILE", "URL", "INV"],
}

INVALID_MEDIA_TYPE = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": "text/plain",
    "formats": ["FILE", "URL"],
}

INVALID_MODULE_TYPE = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.0",
    "module": [],
    "media_types": ["text/plain"],
    "formats": ["FILE", "URL"],
}

INVALID_VERSION = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.a",
    "module": "test.TestPlugin",
    "media_types": ["text/plain"],
    "formats": ["FILE", "URL"],
}

INVALID_VERSION = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.a",
    "module": "test.TestPlugin",
    "media_types": ["text/plain"],
    "formats": ["FILE", "URL"],
}

INVALID_ACCOUNTING = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": ["text/plain"],
    "formats": ["FILE", "URL"],
    "pull_accounting": "true",
}

BASIC_PLUGIN_DATA = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": ["text/plain"],
    "formats": ["FILE", "URL"],
}

INVALID_FORM_TYPE = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_TYPE["form"] = ""

INVALID_FORM_ENTRY_TYPE = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_ENTRY_TYPE["form"] = {"name": "input"}

INVALID_FORM_MISSING_TYPE = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_MISSING_TYPE["form"] = {
    "name": {
        "placeholder": "Name",
        "default": "Default name",
        "label": "Name",
        "mandatory": True,
    }
}

INVALID_FORM_INV_TYPE = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_INV_TYPE["form"] = {
    "name": {
        "type": "invalid",
        "placeholder": "Name",
        "default": "Default name",
        "label": "Name",
        "mandatory": True,
    }
}

INVALID_FORM_INVALID_NAME = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_INVALID_NAME["form"] = {
    "inv&name": {
        "type": "text",
        "placeholder": "Name",
        "default": "Default name",
        "label": "Name",
        "mandatory": True,
    }
}

INVALID_FORM_CHECKBOX_DEF = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_CHECKBOX_DEF["form"] = {"check": {"type": "checkbox", "default": "Default name", "label": "Name"}}

INVALID_FORM_TEXT = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_TEXT["form"] = {"textf": {"type": "text", "default": True, "label": {}, "mandatory": "true"}}

INVALID_FORM_TEXTAREA = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_TEXTAREA["form"] = {"textf": {"type": "textarea", "placeholder": 25}}

INVALID_FORM_SELECT = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_SELECT["form"] = {
    "select": {
        "type": "select",
        "default": 25,
        "label": 30,
        "mandatory": "true",
        "options": [{"text": "value", "value": "value"}],
    }
}

INVALID_FORM_SELECT_MISS_OPT = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_SELECT_MISS_OPT["form"] = {
    "select": {
        "type": "select",
    }
}

INVALID_FORM_SELECT_INV_OPT = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_SELECT_INV_OPT["form"] = {"select": {"type": "select", "options": "option1"}}

INVALID_FORM_SELECT_EMPTY_OPT = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_SELECT_EMPTY_OPT["form"] = {"select": {"type": "select", "options": []}}

INVALID_FORM_SELECT_INV_OPT_VAL = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_SELECT_INV_OPT_VAL["form"] = {"select": {"type": "select", "options": ["option1"]}}


INVALID_FORM_SELECT_INV_OPT_VAL2 = deepcopy(BASIC_PLUGIN_DATA)
INVALID_FORM_SELECT_INV_OPT_VAL2["form"] = {
    "select": {"type": "select", "options": [{}, {"text": 1, "value": "value"}]}
}


INVALID_OVERRIDES = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": ["text/plain"],
    "formats": ["FILE", "URL"],
    "overrides": ["INVALID"],
}

INVALID_FORM_ORDER_FORMAT = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": ["text/plain"],
    "formats": ["FILE", "URL"],
    "overrides": [],
    "form_order": {},
    "form": {
        "name": {
            "type": "text",
            "placeholder": "Name",
            "default": "Default name",
            "label": "Name",
            "mandatory": True,
        }
    },
}

INVALID_FORM_ORDER_NO_FORM = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": ["text/plain"],
    "formats": ["FILE", "URL"],
    "overrides": [],
    "form_order": [],
}

INVALID_FORM_ORDER_MISSING_KEY = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": ["text/plain"],
    "formats": ["FILE", "URL"],
    "overrides": [],
    "form_order": [],
    "form": {
        "name": {
            "type": "text",
            "placeholder": "Name",
            "default": "Default name",
            "label": "Name",
            "mandatory": True,
        }
    },
}

INVALID_FORM_ORDER_DIFFERENT_KEY = {
    "name": "plugin name",
    "author": "test author",
    "version": "1.0",
    "module": "test.TestPlugin",
    "media_types": ["text/plain"],
    "formats": ["FILE", "URL"],
    "overrides": [],
    "form_order": ["version"],
    "form": {
        "name": {
            "type": "text",
            "placeholder": "Name",
            "default": "Default name",
            "label": "Name",
            "mandatory": True,
        }
    },
}
