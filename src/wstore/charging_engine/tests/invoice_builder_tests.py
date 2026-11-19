# -*- coding: utf-8 -*-

# Copyright (c) 2016 CoNWeT Lab., Universidad Politécnica de Madrid

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

from bson.objectid import ObjectId
from django.test import TestCase
from mock import MagicMock, patch
from parameterized import parameterized

from wstore.charging_engine import invoice_builder

TEMPLATE = "<html></html>"
USERNAME = "test-user"
COMPLETE_NAME = "Test User"

TIMESTAMP = "2016-06-06 10:00:00Z"
OFFERING_NAME = "Offering"
OFFERING_VERSION = "1.0"

OWNER_NAME = "owner-user"

BASEDIR = "/home/test"
BILL_ROOT = "/home/test/media/invoices"
MEDIA_URL = "/charging/media/"

TAX = {
    "street": "street",
    "postal": "12345",
    "province": "province",
    "city": "city",
    "country": "country",
}

SINGLE_MODEL = [{"value": "12.00", "tax_rate": "20", "duty_free": "10.00"}]

SUBS_MODEL = [
    {
        "value": "12.00",
        "tax_rate": "20",
        "duty_free": "10.00",
        "unit": "monthly",
        "renovation_date": str(TIMESTAMP),
    }
]

SINGLE_PAYMENT_TRANS = {
    "currency": "EUR",
    "related_model": {"single_payment": SINGLE_MODEL},
    "price": "12.00",
    "duty_free": "10",
}

SINGLE_PAYMENT_ALT_TRANS = {
    "currency": "EUR",
    "related_model": {
        "single_payment": SINGLE_MODEL,
        "alteration": {
            "type": "discount",
            "period": "one time",
            "value": {"value": "2.00", "duty_free": "2.00"},
        },
    },
    "price": "10.00",
    "duty_free": "8",
}

SUBSCRIPTION_TRANS = {
    "currency": "EUR",
    "related_model": {"subscription": SUBS_MODEL},
    "price": "12.00",
    "duty_free": "10",
}

SUBSCRIPTION_ALT_TRANS = {
    "currency": "EUR",
    "related_model": {
        "subscription": SUBS_MODEL,
        "alteration": {
            "type": "fee",
            "period": "recurring",
            "value": "50.00",
            "condition": {"operation": "lt", "value": "30.00"},
        },
    },
    "price": "18.00",
    "duty_free": "15",
}

MERGED_TRANS = {
    "currency": "EUR",
    "related_model": {"subscription": SUBS_MODEL, "single_payment": SINGLE_MODEL},
    "price": "12.00",
    "duty_free": "10",
}

USAGE_TRANS = {
    "price": "200.00",
    "duty_free": "166.60",
    "currency": "EUR",
    "related_model": {"pay_per_use": [{"value": "10.00", "unit": "call", "tax_rate": "20.00", "duty_free": "8.33"}]},
    "applied_accounting": [
        {
            "model": {
                "value": "10.00",
                "unit": "call",
                "tax_rate": "20.00",
                "duty_free": "8.33",
            },
            "accounting": [
                {
                    "usage_id": "1",
                    "price": "100.00",
                    "duty_free": "83.30",
                    "value": "10",
                },
                {
                    "usage_id": "3",
                    "price": "100.00",
                    "duty_free": "83.30",
                    "value": "10",
                },
            ],
            "price": "200.00",
            "duty_free": "166.60",
        }
    ],
}

COMMON_CONTEXT = {
    "basedir": BASEDIR,
    "offering_name": OFFERING_NAME,
    "off_organization": OWNER_NAME,
    "off_version": OFFERING_VERSION,
    "ref": "1111",
    "date": TIMESTAMP.split(" ")[0],
    "organization": USERNAME,
    "customer": COMPLETE_NAME,
    "address": TAX["street"],
    "postal": TAX["postal"],
    "city": TAX["city"],
    "province": TAX["province"],
    "country": TAX["country"],
}

NON_ALTERATIONS = {
    "exists_fees": False,
    "fees": [],
    "exists_discounts": False,
    "discounts": [],
}

BASIC_PRICES = {"subtotal": "10", "tax": "2.00", "total": "12.00", "cur": "EUR"}

SINGLE_PAYMENT_CONTEXT = {
    "exists_single": True,
    "exists_subs": False,
    "single_parts": [("10.00", "20", "12.00")],
}
SINGLE_PAYMENT_CONTEXT.update(COMMON_CONTEXT)
SINGLE_PAYMENT_CONTEXT.update(BASIC_PRICES)
SINGLE_PAYMENT_CONTEXT.update(NON_ALTERATIONS)

BASIC_ALTERATIONS = {
    "exists_fees": False,
    "fees": [],
    "exists_discounts": True,
    "discounts": [("discount", "Value: 2.00 EUR. Duty free: 2.00 EUR", "one time", "")],
}

BASIC_ALT_PRICES = {"subtotal": "8", "tax": "2.00", "total": "10.00", "cur": "EUR"}

SINGLE_PAYMENT_ALT_CONTEXT = {
    "exists_single": True,
    "exists_subs": False,
    "single_parts": [("10.00", "20", "12.00")],
}
SINGLE_PAYMENT_ALT_CONTEXT.update(COMMON_CONTEXT)
SINGLE_PAYMENT_ALT_CONTEXT.update(BASIC_ALT_PRICES)
SINGLE_PAYMENT_ALT_CONTEXT.update(BASIC_ALTERATIONS)

SUBSCRIPTION_CONTEXT = {
    "exists_single": False,
    "exists_subs": True,
    "subs_parts": [("10.00", "20", "12.00", "monthly", str(TIMESTAMP))],
}
SUBSCRIPTION_CONTEXT.update(COMMON_CONTEXT)
SUBSCRIPTION_CONTEXT.update(BASIC_PRICES)
SUBSCRIPTION_CONTEXT.update(NON_ALTERATIONS)

SUBSCRIPTION_ALT_PRICES = {
    "subtotal": "15",
    "tax": "3.00",
    "total": "18.00",
    "cur": "EUR",
}

SUBSCRIPTION_ALTERATIONS = {
    "exists_fees": True,
    "fees": [("fee", "50.00 %", "recurring", "< 30.00")],
    "exists_discounts": False,
    "discounts": [],
}

SUBSCRIPTION_ALT_CONTEXT = {
    # 'exists_single': False,
    # 'exists_subs': True,
    "subs_parts": [("10.00", "20", "12.00", "monthly", str(TIMESTAMP))]
}

SUBSCRIPTION_ALT_CONTEXT.update(COMMON_CONTEXT)
SUBSCRIPTION_ALT_CONTEXT.update(SUBSCRIPTION_ALT_PRICES)
SUBSCRIPTION_ALT_CONTEXT.update(SUBSCRIPTION_ALTERATIONS)

MERGED_CONTEXT = {
    "exists_single": True,
    "exists_subs": True,
    "subs_parts": [("10.00", "20", "12.00", "monthly", str(TIMESTAMP))],
    "single_parts": [("10.00", "20", "12.00")],
}
MERGED_CONTEXT.update(COMMON_CONTEXT)
MERGED_CONTEXT.update(BASIC_PRICES)
MERGED_CONTEXT.update(NON_ALTERATIONS)

RENEW_CONTEXT = {"subs_parts": [("10.00", "20", "12.00", "monthly", str(TIMESTAMP))]}
RENEW_CONTEXT.update(COMMON_CONTEXT)
RENEW_CONTEXT.update(BASIC_PRICES)
RENEW_CONTEXT.update(NON_ALTERATIONS)

USAGE_CONTEXT = {
    "subtotal": "166.60",
    "tax": "33.40",
    "total": "200.00",
    "cur": "EUR",
    "use_parts": [("call", "10.00", "20", "200.00")],
    "use_subtotal": "200.00",
    "deduction": False,
}
USAGE_CONTEXT.update(COMMON_CONTEXT)
USAGE_CONTEXT.update(NON_ALTERATIONS)


class InvoiceBuilderTestCase(TestCase):
    tags = ("invoices",)

    def setUp(self):
        self._order = MagicMock()
        self._order.pk = "1111"
        self._order.tax_address = TAX

        self._order.customer.userprofile.current_organization.name = USERNAME
        self._order.customer.userprofile.complete_name = COMPLETE_NAME

        self._contract = MagicMock()
        self._contract.item_id = "2"
        self._contract.last_charge = TIMESTAMP
        self._contract.offering = "61004aba5e05acc115f022f0"

        self._offering = MagicMock(version=OFFERING_VERSION)
        self._offering.name = OFFERING_NAME
        self._offering.owner_organization.name = OWNER_NAME

        invoice_builder.Offering = MagicMock()
        invoice_builder.Offering.objects.get.return_value = self._offering

        invoice_builder.loader = MagicMock()
        self._template = MagicMock()
        self._template.render.return_value = TEMPLATE
        invoice_builder.loader.get_template.return_value = self._template

        invoice_builder.Context = MagicMock()
        invoice_builder.settings.BILL_ROOT = BILL_ROOT
        invoice_builder.settings.BASEDIR = BASEDIR
        invoice_builder.settings.MEDIA_URL = MEDIA_URL

        invoice_builder.codecs = MagicMock()
        self._file_handler = MagicMock()
        invoice_builder.codecs.open.return_value = self._file_handler

        for target, name in (
            (invoice_builder.os.path, "exists"),
            (invoice_builder.os, "listdir"),
            (invoice_builder.os, "remove"),
        ):
            patcher = patch.object(target, name)
            patcher.start()
            self.addCleanup(patcher.stop)
        invoice_builder.os.path.exists.side_effect = [True, True, False]
        invoice_builder.os.listdir.return_value = ["file1.pdf", "file1.html"]

        invoice_builder.subprocess = MagicMock()

    @parameterized.expand(
        [
            (
                "initial_one_time",
                "initial",
                SINGLE_PAYMENT_TRANS,
                SINGLE_PAYMENT_CONTEXT,
            ),
            (
                "initial_one_time_trans",
                "initial",
                SINGLE_PAYMENT_ALT_TRANS,
                SINGLE_PAYMENT_ALT_CONTEXT,
            ),
            ("initial_recurring", "initial", SUBSCRIPTION_TRANS, SUBSCRIPTION_CONTEXT),
            ("initial_merged", "initial", MERGED_TRANS, MERGED_CONTEXT),
            ("renew_subs", "recurring", SUBSCRIPTION_TRANS, RENEW_CONTEXT),
            (
                "renew_subs_alt",
                "recurring",
                SUBSCRIPTION_ALT_TRANS,
                SUBSCRIPTION_ALT_CONTEXT,
            ),
            ("use_no_deducted", "usage", USAGE_TRANS, USAGE_CONTEXT),
        ]
    )
    def test_invoice_generation(self, name, concept, transaction, exp_context):
        templates = {
            "initial": "contracting/bill_template_initial.html",
            "recurring": "contracting/bill_template_renovation.html",
            "usage": "contracting/bill_template_use.html",
        }

        builder = invoice_builder.InvoiceBuilder(self._order)

        invoice_path = builder.generate_invoice(self._contract, transaction, concept)

        # Validate Path
        invoice_name = "{}_{}_{}_2.pdf".format(self._order.pk, self._contract.item_id, TIMESTAMP.split()[0])

        exp_path = MEDIA_URL + "bills/" + invoice_name
        html_path = BILL_ROOT + "/" + invoice_name.replace("_2.pdf", ".html")

        self.assertEquals(exp_path, invoice_path)

        # Validate calls
        invoice_builder.Offering.objects.get.assert_called_once_with(pk=ObjectId("61004aba5e05acc115f022f0"))

        invoice_builder.loader.get_template.assert_called_once_with(templates[concept])
        invoice_builder.Context.assert_called_once_with(exp_context)
        self._template.render.assert_called_once_with(invoice_builder.Context())

        invoice_builder.codecs.open.assert_called_once_with(html_path, "wb", "utf-8")
        self._file_handler.write.assert_called_once_with(TEMPLATE)
        self._file_handler.close.assert_called_once_with()

        invoice_builder.subprocess.call.assert_called_once_with(
            [BASEDIR + "/create_invoice.sh", html_path, BILL_ROOT + "/" + invoice_name]
        )

        invoice_builder.os.listdir.assert_called_once_with(BILL_ROOT)
        invoice_builder.os.remove.assert_called_once_with(BILL_ROOT + "/file1.html")
