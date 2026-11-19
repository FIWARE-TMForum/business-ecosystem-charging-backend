# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid

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


import mock
from django.test import SimpleTestCase, TestCase
from mock import MagicMock
from parameterized import parameterized
from urllib.parse import parse_qs, urlparse
from xml.sax.saxutils import escape as xml_escape


from wstore.charging_engine.payment_client import payment_client
from wstore.charging_engine.payment_client import paypal_client
from wstore.charging_engine.payment_client import redsys_client
from wstore.charging_engine.payment_client import stripe_client


class _StripeCardError(Exception):
    """Stand-in for stripe.error.CardError so the ``except`` clause in
    charge_recurring catches a real exception class while ``stripe`` is mocked."""
    pass


class PaymentClientTestCase(TestCase):
    tags = "payment_client"

    @parameterized.expand(
        [
            ("wstore.charging_engine.payment_client.stripe_client.StripeClient", stripe_client.StripeClient),
            ("wstore.charging_engine.payment_client.error_client.ErrorClient"),
        ]
    )
    def test_get_payment_client_class(self, client_full_name, client_class=None):
        payment_client.settings = MagicMock(**{"PAYMENT_CLIENT": client_full_name})
        try:
            payment_client_class = payment_client.PaymentClient.get_payment_client_class()
            assert payment_client_class == client_class
        except ModuleNotFoundError:
            assert client_class is None


class PaypalTestCase(TestCase):
    tags = ("payment-client", "payment-client-paypal")

    def setUp(self):
        paypal_client.paypalrestsdk = MagicMock()

    def test_paypal(self):
        paypal = paypal_client.PayPalClient(None)
        paypal.batch_payout(["item1", "item2"])
        paypal_client.paypalrestsdk.Payout.assert_called_once_with(
            {
                "sender_batch_header": {
                    "sender_batch_id": mock.ANY,
                    "email_subject": "You have a payment",
                },
                "items": ["item1", "item2"],
            }
        )

        paypal_client.paypalrestsdk.Payout().create.assert_called_once()


class RedsysTestCase(TestCase):
    tags = ("payment-client", "payment-client-redsys")

    def test_start_redirection_payment_returns_frontend_post_route(self):
        order = MagicMock(
            order_id="order-1",
            hash_key=b"test-secret-key",
            contracts=[MagicMock(item_id="item-1", offering="offering-1")],
        )
        client = redsys_client.RedsysClient(order)
        transactions = [{
            "item": "item-1",
            "price": "6.29",
            "billId": "bill-1",
        }]
        offering = {"id": "offering-1", "name": "Test offering"}

        with mock.patch.object(redsys_client.settings, "SITE", "http://localhost:4200/"), \
                mock.patch.object(redsys_client, "_new_order_number", return_value="260727123456"), \
                mock.patch.object(
                    redsys_client.ProductCatalog,
                    "get_offering",
                    return_value=offering,
                ):
            checkout_url = client.start_redirection_payment(transactions)

        parsed_url = urlparse(checkout_url)
        query = parse_qs(parsed_url.query)

        self.assertEqual(
            parsed_url.geturl().split("?", 1)[0],
            "http://localhost:4200/redsys-payment",
        )
        self.assertEqual(
            set(query),
            {
                "RedsysPaymentUrl",
                "Ds_SignatureVersion",
                "Ds_MerchantParameters",
                "Ds_Signature",
            },
        )
        self.assertEqual(
            query["RedsysPaymentUrl"],
            [f"{redsys_client.REDSYS_BASE_URL}/realizarPago"],
        )
        self.assertEqual(
            query["Ds_SignatureVersion"],
            [redsys_client.SIGNATURE_VERSION],
        )

        merchant_parameters = query["Ds_MerchantParameters"][0]
        decoded_params = redsys_client._decode_params(merchant_parameters)
        self.assertEqual(decoded_params["DS_MERCHANT_AMOUNT"], "629")
        self.assertTrue(
            decoded_params["DS_MERCHANT_URLOK"].startswith(
                "http://localhost:4200/checkout?client=redsys&action=accept&ref=order-1&sig="
            )
        )
        self.assertEqual(
            query["Ds_Signature"],
            [redsys_client._sign("260727123456", merchant_parameters)],
        )

    def test_end_redirection_payment_decodes_form_encoded_merchant_data(self):
        order = MagicMock()
        order.order_id = "order-1"
        client = redsys_client.RedsysClient(order)
        encoded_params = redsys_client._encode_params({
            "Ds_Order": "260721034827",
            "Ds_Response": "0000",
            "Ds_Amount": "629",
            "Ds_MerchantData": (
                "%7B%22ref%22%3A+%22order-1%22%2C+%22bills%22%3A+"
                "%5B%22bill-1%22%5D%7D"
            ),
        })

        with mock.patch.object(redsys_client, "_verify_signature", return_value=True), \
                mock.patch.object(redsys_client, "PaymentRecord") as payment_record:
            references, payouts = client.end_redirection_payment(
                Ds_MerchantParameters=encoded_params,
                Ds_Signature="signature",
            )

        self.assertEqual(references, [])
        self.assertEqual(
            payouts,
            [{"paymentItemExternalId": "bill-1", "state": "processed"}],
        )
        payment_record.create.assert_called_once_with(
            "bill-1",
            payment_type="redsys",
            payment_reference="260721034827",
        )

    def test_end_redirection_payment_returns_redsys_pre_authorization(self):
        order = MagicMock()
        order.order_id = "order-1"
        client = redsys_client.RedsysClient(order)
        encoded_params = redsys_client._encode_params({
            "Ds_Order": "260721616918",
            "Ds_Response": "0000",
            "Ds_Amount": "1839",
            "Ds_Merchant_Identifier": "card-token",
            "Ds_Merchant_Cof_Txnid": "2607211916510",
            "Ds_MerchantData": (
                "%7B%22ref%22%3A+%22order-1%22%2C+%22bills%22%3A+"
                "%5B%22bill-1%22%5D%7D"
            ),
        })

        with mock.patch.object(redsys_client, "_verify_signature", return_value=True), \
                mock.patch.object(redsys_client, "PaymentRecord") as payment_record:
            pre_auth_ids, payouts = client.end_redirection_payment(
                Ds_MerchantParameters=encoded_params,
                Ds_Signature="signature",
            )

        self.assertEqual(pre_auth_ids, ["card-token:2607211916510"])
        payment_record.create.assert_called_once_with(
            "bill-1",
            payment_type="redsys",
            payment_reference="260721616918",
        )

    @parameterized.expand([
        ("authorized", "F", "0000", "succeeded"),
        ("denied", "F", "0190", "failed"),
        ("not_final", "P", "0000", "pending"),
    ])
    def test_check_payment_status_uses_soap(
        self,
        name,
        ds_state,
        ds_response,
        expected,
    ):
        client = redsys_client.RedsysClient(None)
        inner_xml = (
            '<Messages><Version Ds_Version="0.0"><Message>'
            '<Response Ds_Version="0.0">'
            "<Ds_Order>260721616918</Ds_Order>"
            f"<Ds_State>{ds_state}</Ds_State>"
            f"<Ds_Response>{ds_response}</Ds_Response>"
            "</Response></Message></Version></Messages>"
        )
        soap_response = (
            '<soapenv:Envelope '
            'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            "<soapenv:Body><consultaOperacionesResponse>"
            "<consultaOperacionesReturn>"
            f"{xml_escape(inner_xml)}"
            "</consultaOperacionesReturn>"
            "</consultaOperacionesResponse></soapenv:Body>"
            "</soapenv:Envelope>"
        )
        response = MagicMock(content=soap_response.encode())

        with mock.patch.object(
            redsys_client.requests,
            "post",
            return_value=response,
        ) as post:
            status = client.check_payment_status(
                "260721616918",
            )

        self.assertEqual(status, expected)
        response.raise_for_status.assert_called_once_with()
        request = post.call_args
        self.assertEqual(request.args[0], redsys_client.REDSYS_QUERY_URL)
        self.assertIn(
            b"<Ds_Order>260721616918</Ds_Order>",
            request.kwargs["data"],
        )
        self.assertIn(
            b"<SignatureVersion>HMAC_SHA256_V1</SignatureVersion>",
            request.kwargs["data"],
        )
        self.assertEqual(
            request.kwargs["headers"]["SOAPAction"],
            "consultaOperaciones",
        )

    def test_check_payment_status_treats_missing_operation_as_failed(self):
        client = redsys_client.RedsysClient(None)
        inner_xml = (
            '<Messages><Version Ds_Version="0.0"><Message><ErrorMsg>'
            "<Ds_ErrorCode>XML0024</Ds_ErrorCode>"
            "</ErrorMsg></Message></Version></Messages>"
        )
        soap_response = (
            "<Envelope><Body><consultaOperacionesReturn>"
            f"{xml_escape(inner_xml)}"
            "</consultaOperacionesReturn></Body></Envelope>"
        )
        response = MagicMock(content=soap_response.encode())

        with mock.patch.object(
            redsys_client.requests,
            "post",
            return_value=response,
        ):
            status = client.check_payment_status(
                "260721616918",
            )

        self.assertEqual(status, "failed")

    def test_check_payment_status_keeps_pending_when_soap_fails(self):
        client = redsys_client.RedsysClient(None)

        with mock.patch.object(
            redsys_client.requests,
            "post",
            side_effect=Exception("connection lost"),
        ):
            status = client.check_payment_status(
                "260721616918",
            )

        self.assertEqual(status, "pending")

    def test_soap_signature_matches_verified_sandbox_request(self):
        version_xml = (
            '<Version Ds_Version="0.0"><Message><Transaction>'
            "<Ds_MerchantCode>999008881</Ds_MerchantCode>"
            "<Ds_Terminal>001</Ds_Terminal>"
            "<Ds_Order>260723890989</Ds_Order>"
            "<Ds_TransactionType>0</Ds_TransactionType>"
            "</Transaction></Message></Version>"
        )

        with mock.patch.object(
            redsys_client,
            "SECRET_KEY",
            "sq7HjrUOBfKmC576ILgskD5srU870gJ7",
        ):
            signature = redsys_client._soap_signature(
                "260723890989",
                version_xml,
            )

        self.assertEqual(
            signature,
            "q7LbX1P32WQSisGT+A8ZV+fMeVJo6kR0OjYUBCxPkUI=",
        )

    def test_charge_recurring_uses_pre_authorization_token(self):
        client = redsys_client.RedsysClient(None)
        record = MagicMock(
            customerBill_id="bill-1",
            payment_reference="260721000001",
            retry_count=0,
            pk="record-1",
        )
        with mock.patch.object(
            redsys_client,
            "_new_order_number",
            return_value="260721999999",
        ), mock.patch.object(
            client,
            "_rest_request",
            return_value={"Ds_Response": "0000"},
        ) as rest_request:
            reference, status = client.charge_recurring(
                {"id": "bill-1"},
                record,
                "card-token:2607211916510",
                "18.39",
                "EUR",
            )

        self.assertEqual(reference, "260721999999")
        self.assertEqual(status, "succeeded")
        record.save.assert_called_once_with()
        request_params = rest_request.call_args[0][0]
        self.assertEqual(request_params["DS_MERCHANT_IDENTIFIER"], "card-token")
        self.assertEqual(
            request_params["DS_MERCHANT_COF_TXNID"],
            "2607211916510",
        )

    def test_charge_recurring_without_verifiable_response_is_pending(self):
        client = redsys_client.RedsysClient(None)
        created_record = MagicMock(
            customerBill_id="bill-1",
            payment_type="redsys",
            payment_reference="260721999999",
            retry_count=0,
        )

        with mock.patch.object(
            redsys_client,
            "_new_order_number",
            return_value="260721999999",
        ), mock.patch.object(
            client,
            "_rest_request",
            side_effect=Exception("connection lost"),
        ), mock.patch.object(
            redsys_client.PaymentRecord,
            "create",
            return_value=created_record,
        ) as create_record:
            reference, status = client.charge_recurring(
                {"id": "bill-1"},
                None,
                "card-token:2607211916510",
                "18.39",
                "EUR",
            )

        self.assertEqual(reference, "260721999999")
        self.assertEqual(status, "pending")
        create_record.assert_called_once_with(
            "bill-1",
            payment_type="redsys",
            payment_reference="260721999999",
        )

    def test_merchant_parameters_use_unpadded_base64url(self):
        encoded = redsys_client._encode_params({"DS_MERCHANT_AMOUNT": "629"})

        self.assertNotIn("=", encoded)
        self.assertEqual(
            redsys_client._decode_params(encoded),
            {"DS_MERCHANT_AMOUNT": "629"},
        )

    def test_signature_matches_redsys_hmac_sha512_v2_example(self):
        merchant_parameters = (
            "eyJEU19NRVJDSEFOVF9BTU9VTlQiOiI5OTkiLCJEU19NRVJDSEFOVF9PUkRFUiI6IjEyMzQ1Njc4OTAi"
            "LCJEU19NRVJDSEFOVF9NRVJDSEFOVENPREUiOiI5OTkwMDg4ODEiLCJEU19NRVJDSEFOVF9DVVJSRU5DWSI6"
            "Ijk3OCIsIkRTX01FUkNIQU5UX1RSQU5TQUNUSU9OVFlQRSI6IjAiLCJEU19NRVJDSEFOVF9URVJNSU5BTCI6"
            "IjEiLCJEU19NRVJDSEFOVF9NRVJDSEFOVFVSTCI6Imh0dHA6XC9cL3d3dy5wcnVlYmEuY29tXC91cmxOb3Rp"
            "ZmljYWNpb24ucGhwIiwiRFNfTUVSQ0hBTlRfVVJMT0siOiJodHRwOlwvXC93d3cucHJ1ZWJhLmNvbVwvdXJs"
            "T0sucGhwIiwiRFNfTUVSQ0hBTlRfVVJMS08iOiJodHRwOlwvXC93d3cucHJ1ZWJhLmNvbVwvdXJsS08ucGhw"
            "In0"
        )

        with mock.patch.object(
            redsys_client,
            "SECRET_KEY",
            "sq7HjrUOBfKmC576ILgskD5srU870gJ7",
        ):
            signature = redsys_client._sign("1234567890", merchant_parameters)

        self.assertEqual(
            signature,
            "Vjo02eSWq249IeZZp3R-ArFnGLhKY0OuzDDlx1BuVtZDC2yhczA7_11uZhsYzLZBCMFAz8u8uzGDX3AErHKmmw",
        )


class StripeTestCalse(TestCase):
    tags = ("payment-client", "payment-client-stripe")

    def setUp(self):
        stripe_client.stripe = MagicMock()
        stripe_client.stripe.error.CardError = _StripeCardError
        catalog_patch = mock.patch.object(stripe_client, "ProductCatalog")
        self.catalog = catalog_patch.start().return_value
        self.addCleanup(catalog_patch.stop)
        self.catalog.get_offering.return_value = {"name": "Test offering", "description": "Test description"}
        stripe_client.PaymentRecord = MagicMock()

    @parameterized.expand(
        [
            (
                "success",
                MagicMock(name="order"),
                [{"currency": "EUR", "price": 1000, "item": "test", "description": "test", "item_id": "test", "billId": "bill-1"}],
            ),
            ("no_transactions", MagicMock(name="order"), []),
            ("session_error", MagicMock(name="order"), [], Exception("Test Exception")),
        ]
    )
    def test_start_redirection_payment(self, name, order, transactions, checkout_error=None):
        stripe_payment_client = stripe_client.StripeClient(order)
        stripe_payment_client._order = MagicMock(
            **{
                "contracts": [MagicMock(**transaction) for transaction in transactions],
                "hash_key": b"test-secret-key",
            }
        )

        checkout_session = MagicMock(name="checkout_session")
        checkout_session.id = "cs_test_a11lpqo9KV8xxEBtrURbzgouesMb3mEZnIosnHpOzVCrjQ7pHeSNDAHwUA"
        checkout_session.url = "https://checkout.stripe.com/c/pay/test"
        stripe_client.stripe.configure_mock(
            **{
                "checkout.Session.create.return_value": checkout_session,
                "checkout.Session.create.side_effect": checkout_error,
            }
        )

        try:
            stripe_payment_client.start_redirection_payment(transactions)
            error = None
        except Exception as e:
            error = e

        stripe_client.stripe.checkout.Session.create.assert_called_once()
        if error:
            self.assertIsInstance(error, payment_client.PaymentClientError)
        else:
            self.assertEquals(stripe_payment_client.get_checkout_url(), "https://checkout.stripe.com/c/pay/test")

    def test_end_redirection_payment(self):
        order = MagicMock()
        order.order_id = "order-1"
        stripe_payment_client = stripe_client.StripeClient(order)
        stripe_client.PaymentRecord = MagicMock()

        session = MagicMock(name="session")
        session.client_reference_id = order.order_id
        session.payment_status = "paid"

        item = MagicMock(name="line_item")
        item.metadata = {"paymentItemExternalId": "cb-1"}

        page = MagicMock(name="page")
        page.data = [item]
        page.has_more = False

        stripe_client.stripe.configure_mock(
            **{
                "checkout.Session.retrieve.return_value": session,
                "checkout.Session.list_line_items.return_value": page,
            }
        )

        result = stripe_payment_client.end_redirection_payment(session_id="test")
        self.assertEquals(result, (["test"], [{"paymentItemExternalId": "cb-1", "state": "processed"}]))

    def test_refund(self):
        stripe_payment_client = stripe_client.StripeClient(MagicMock())

        checkout_session = MagicMock(name="checkout_session")
        checkout_session.id = "cs_test_a11lpqo9KV8xxEBtrURbzgouesMb3mEZnIosnHpOzVCrjQ7pHeSNDAHwUA"
        refund = MagicMock(name="refund")
        refund.id = "rf_test_a11lpqo9KV8xxEBtrURbzgouesMb3mEZnIosnHpOzVCrjQ7pHeSNDAHwUA"
        stripe_client.stripe.configure_mock(
            **{
                "checkout.Session.retrieve.return_value": checkout_session,
                "Refund.create.return_value": refund,
            }
        )

        self.assertEquals(stripe_payment_client.refund("test"), refund)

    def test_refund_error(self):
        stripe_payment_client = stripe_client.StripeClient(MagicMock())
        stripe_client.stripe.checkout.Session.retrieve.side_effect = Exception("boom")

        with self.assertRaises(payment_client.PaymentClientError):
            stripe_payment_client.refund("test")

    def test_end_redirection_payment_manipulated(self):
        order = MagicMock()
        order.order_id = "order-1"
        stripe_payment_client = stripe_client.StripeClient(order)

        session = MagicMock(name="session")
        session.client_reference_id = "another-order"
        session.payment_status = "paid"
        stripe_client.stripe.checkout.Session.retrieve.return_value = session

        with self.assertRaises(stripe_client.PaymentError):
            stripe_payment_client.end_redirection_payment(session_id="test")

    def test_end_redirection_payment_pending(self):
        order = MagicMock()
        order.order_id = "order-1"
        stripe_payment_client = stripe_client.StripeClient(order)
        stripe_client.PaymentRecord = MagicMock()

        session = MagicMock(name="session")
        session.client_reference_id = order.order_id
        session.payment_status = "unpaid"

        item = MagicMock(name="line_item")
        item.metadata = {"paymentItemExternalId": "cb-1"}
        page = MagicMock(name="page", data=[item], has_more=False)

        stripe_client.stripe.configure_mock(
            **{
                "checkout.Session.retrieve.return_value": session,
                "checkout.Session.list_line_items.return_value": page,
            }
        )

        result = stripe_payment_client.end_redirection_payment(session_id="test")
        self.assertEquals(result, (["test"], [{"paymentItemExternalId": "cb-1", "state": "pending"}]))

    def test_end_redirection_payment_pagination(self):
        order = MagicMock()
        order.order_id = "order-1"
        stripe_payment_client = stripe_client.StripeClient(order)
        stripe_client.PaymentRecord = MagicMock()

        session = MagicMock(name="session")
        session.client_reference_id = order.order_id
        session.payment_status = "paid"

        item1 = MagicMock(name="line_item_1", id="li_1")
        item1.metadata = {"paymentItemExternalId": "cb-1"}
        item2 = MagicMock(name="line_item_2", id="li_2")
        item2.metadata = {"paymentItemExternalId": "cb-2"}

        page1 = MagicMock(name="page_1", data=[item1], has_more=True)
        page2 = MagicMock(name="page_2", data=[item2], has_more=False)

        stripe_client.stripe.checkout.Session.retrieve.return_value = session
        stripe_client.stripe.checkout.Session.list_line_items.side_effect = [page1, page2]

        result = stripe_payment_client.end_redirection_payment(session_id="test")
        self.assertEquals(
            result,
            (
                ["test"],
                [
                    {"paymentItemExternalId": "cb-1", "state": "processed"},
                    {"paymentItemExternalId": "cb-2", "state": "processed"},
                ],
            ),
        )

    @parameterized.expand(
        [
            ("pi_succeeded", "pi_123", "succeeded", "succeeded"),
            ("pi_processing", "pi_123", "processing", "pending"),
            ("pi_requires_action", "pi_123", "requires_action", "pending"),
            ("pi_failed", "pi_123", "canceled", "failed"),
        ]
    )
    def test_check_payment_status_payment_intent(self, name, reference, pi_status, expected):
        stripe_payment_client = stripe_client.StripeClient(MagicMock())
        stripe_client.stripe.PaymentIntent.retrieve.return_value = MagicMock(status=pi_status)

        self.assertEquals(stripe_payment_client.check_payment_status(reference), expected)

    def test_check_payment_status_keeps_unconfirmed_payment_intent_pending(self):
        stripe_payment_client = stripe_client.StripeClient(MagicMock())
        payment_intent = MagicMock(
            id="pi_123",
            status="requires_confirmation",
        )
        stripe_client.stripe.PaymentIntent.retrieve.return_value = (
            payment_intent
        )

        status = stripe_payment_client.check_payment_status("pi_123")

        self.assertEqual(status, "pending")
        payment_intent.cancel.assert_not_called()

    @parameterized.expand(
        [
            ("session_paid", "cs_123", "paid", "succeeded"),
            ("session_unpaid", "cs_123", "unpaid", "pending"),
            ("session_failed", "cs_123", "no_payment_required", "failed"),
        ]
    )
    def test_check_payment_status_session(self, name, reference, payment_status, expected):
        stripe_payment_client = stripe_client.StripeClient(MagicMock())
        stripe_client.stripe.checkout.Session.retrieve.return_value = MagicMock(payment_status=payment_status)

        self.assertEquals(stripe_payment_client.check_payment_status(reference), expected)

    @parameterized.expand(
        [
            ("succeeded", "succeeded", "succeeded"),
            ("processing", "processing", "pending"),
            ("requires_action", "requires_action", "pending"),
            ("failed", "canceled", "failed"),
        ]
    )
    def test_charge_recurring_payment_intent(self, name, new_status, expected_state):
        stripe_payment_client = stripe_client.StripeClient(MagicMock())
        record = MagicMock(
            customerBill_id="cb-1",
            payment_reference="pi_old_attempt",
            retry_count=2,
            pk="record-1",
        )
        stripe_client.stripe.PaymentIntent.retrieve.return_value = MagicMock(
            customer="cus_1", payment_method="pm_1"
        )
        new_payment_intent = MagicMock(
            id="pi_new",
            status="requires_confirmation",
        )
        new_payment_intent.confirm.return_value = MagicMock(
            id="pi_new",
            status=new_status,
        )
        stripe_client.stripe.PaymentIntent.create.return_value = (
            new_payment_intent
        )
        result = stripe_payment_client.charge_recurring(
            {"id": "cb-1"},
            record,
            "pi_123",
            "10.00",
            "EUR",
        )

        self.assertEquals(result, ("pi_new", expected_state))
        stripe_client.stripe.PaymentIntent.create.assert_called_once_with(
            amount=1000,
            currency="eur",
            customer="cus_1",
            payment_method="pm_1",
            confirm=False,
            idempotency_key="recurring:cb-1:2:pi_old_attempt",
        )
        new_payment_intent.confirm.assert_called_once_with(
            off_session=True,
        )
        record.save.assert_called_once_with()

    def test_charge_recurring_from_session(self):
        stripe_payment_client = stripe_client.StripeClient(MagicMock())
        record = MagicMock(
            customerBill_id="cb-1",
            payment_reference="pi_old_attempt",
            retry_count=0,
            pk="record-1",
        )
        stripe_client.stripe.checkout.Session.retrieve.return_value = MagicMock(
            customer="cus_1", payment_intent="pi_old"
        )
        stripe_client.stripe.PaymentIntent.retrieve.return_value = MagicMock(payment_method="pm_1")
        new_payment_intent = MagicMock(
            id="pi_new",
            status="requires_confirmation",
        )
        new_payment_intent.confirm.return_value = MagicMock(
            id="pi_new",
            status="succeeded",
        )
        stripe_client.stripe.PaymentIntent.create.return_value = (
            new_payment_intent
        )
        result = stripe_payment_client.charge_recurring(
            {"id": "cb-1"},
            record,
            "cs_123",
            "5",
            "USD",
        )

        self.assertEquals(result, ("pi_new", "succeeded"))

    def test_charge_recurring_creates_record_after_preparing_intent(self):
        stripe_payment_client = stripe_client.StripeClient(MagicMock())
        created_record = MagicMock(
            customerBill_id="cb-1",
            payment_type="stripe",
            payment_reference="pi_new",
            retry_count=0,
        )
        stripe_client.stripe.PaymentIntent.retrieve.return_value = MagicMock(
            customer="cus_1",
            payment_method="pm_1",
        )
        new_payment_intent = MagicMock(
            id="pi_new",
            status="requires_confirmation",
        )
        new_payment_intent.confirm.return_value = MagicMock(
            id="pi_new",
            status="succeeded",
        )
        stripe_client.stripe.PaymentIntent.create.return_value = (
            new_payment_intent
        )
        stripe_client.PaymentRecord.create.return_value = created_record

        result = stripe_payment_client.charge_recurring(
            {"id": "cb-1"},
            None,
            "pi_123",
            "10",
            "EUR",
        )

        self.assertEqual(result, ("pi_new", "succeeded"))
        stripe_client.PaymentRecord.create.assert_called_once_with(
            "cb-1",
            payment_type="stripe",
            payment_reference="pi_new",
        )
        new_payment_intent.confirm.assert_called_once_with(
            off_session=True,
        )

    def test_charge_recurring_missing_payment_method(self):
        stripe_payment_client = stripe_client.StripeClient(MagicMock())
        record = MagicMock(
            customerBill_id="cb-1",
            retry_count=0,
            pk="record-1",
        )
        stripe_client.stripe.PaymentIntent.retrieve.return_value = MagicMock(
            customer="cus_1", payment_method=None
        )

        self.assertEquals(
            stripe_payment_client.charge_recurring(
                {"id": "cb-1"},
                record,
                "pi_123",
                "10",
                "EUR",
            ),
            (None, "failed"),
        )
        stripe_client.stripe.PaymentIntent.create.assert_not_called()

    def test_charge_recurring_card_error(self):
        stripe_payment_client = stripe_client.StripeClient(MagicMock())
        record = MagicMock(
            customerBill_id="cb-1",
            retry_count=0,
            pk="record-1",
        )
        stripe_client.stripe.PaymentIntent.retrieve.return_value = MagicMock(
            customer="cus_1", payment_method="pm_1"
        )
        stripe_client.stripe.PaymentIntent.create.side_effect = _StripeCardError("card declined")

        self.assertEquals(
            stripe_payment_client.charge_recurring(
                {"id": "cb-1"},
                record,
                "pi_123",
                "10",
                "EUR",
            ),
            (None, "failed"),
        )

    def test_charge_recurring_generic_error(self):
        stripe_payment_client = stripe_client.StripeClient(MagicMock())
        record = MagicMock(
            customerBill_id="cb-1",
            retry_count=0,
            pk="record-1",
        )
        stripe_client.stripe.PaymentIntent.retrieve.side_effect = Exception("boom")

        self.assertEquals(
            stripe_payment_client.charge_recurring(
                {"id": "cb-1"},
                record,
                "pi_123",
                "10",
                "EUR",
            ),
            (None, "pending"),
        )


class CatalogOfferingCheckoutTests(SimpleTestCase):
    def setUp(self):
        from types import SimpleNamespace

        self.order = SimpleNamespace(
            order_id="order-1",
            hash_key=b"test-secret-key",
            contracts=[
                SimpleNamespace(item_id="item-1", offering="offer-1"),
                SimpleNamespace(item_id="item-2", offering="offer-2"),
            ],
        )
        self.transactions = [
            {"item": "item-2", "price": "6.29", "currency": "EUR", "billId": "bill-2"},
            {"item": "item-1", "price": "3.50", "currency": "EUR", "billId": "bill-1"},
        ]
        self.offers = {
            "offer-1": {"id": "offer-1", "name": "First catalog offer", "description": "Current description"},
            "offer-2": {"id": "offer-2", "name": "Second catalog offer"},
        }

    def catalog_response(self, url, **kwargs):
        response = MagicMock()
        response.json.return_value = self.offers[url.rsplit("/", 1)[1]]

        return response

    def assert_catalog_requests(self, get):
        from django.conf import settings
        from wstore.store_commons.utils.url import get_service_url

        self.assertEqual(
            [
                mock.call(
                    get_service_url("catalog", "/productOffering/offer-1"), verify=settings.VERIFY_REQUESTS, timeout=30
                ),
                mock.call(
                    get_service_url("catalog", "/productOffering/offer-2"), verify=settings.VERIFY_REQUESTS, timeout=30
                ),
            ],
            get.call_args_list,
        )

    @mock.patch("wstore.store_commons.product_catalog.requests.get")
    def test_stripe_uses_catalog_names_and_optional_descriptions(self, get):
        get.side_effect = self.catalog_response

        with mock.patch.object(stripe_client, "stripe") as stripe:
            stripe.checkout.Session.create.return_value.url = "https://checkout.example/session"

            checkout_url = stripe_client.StripeClient(self.order).start_redirection_payment(self.transactions)

        self.assertEqual("https://checkout.example/session", checkout_url)
        self.assert_catalog_requests(get)
        line_items = stripe.checkout.Session.create.call_args.kwargs["line_items"]
        self.assertEqual(
            {"name": "Second catalog offer", "description": "No description"},
            line_items[0]["price_data"]["product_data"],
        )
        self.assertEqual(
            {"name": "First catalog offer", "description": "Current description"},
            line_items[1]["price_data"]["product_data"],
        )
        self.assertEqual([629, 350], [item["price_data"]["unit_amount"] for item in line_items])

    @mock.patch("wstore.store_commons.product_catalog.requests.get")
    def test_redsys_uses_catalog_names_in_transaction_order(self, get):
        get.side_effect = self.catalog_response

        checkout_url = redsys_client.RedsysClient(self.order).start_redirection_payment(self.transactions)

        self.assert_catalog_requests(get)
        query = parse_qs(urlparse(checkout_url).query)
        params = redsys_client._decode_params(query["Ds_MerchantParameters"][0])
        self.assertEqual("Second catalog offer, First catalog offer", params["DS_MERCHANT_PRODUCTDESCRIPTION"])
        self.assertEqual("979", params["DS_MERCHANT_AMOUNT"])

    @mock.patch("wstore.store_commons.product_catalog.requests.get")
    def test_catalog_failure_prevents_checkout_for_both_clients(self, get):
        from requests.exceptions import HTTPError

        get.return_value.raise_for_status.side_effect = HTTPError("catalog unavailable")

        for client_class in (stripe_client.StripeClient, redsys_client.RedsysClient):
            with self.subTest(client=client_class.NAME), mock.patch.object(stripe_client, "stripe") as stripe:
                client = client_class(self.order)

                with self.assertRaises(payment_client.PaymentClientError) as error:
                    client.start_redirection_payment(self.transactions)

                self.assertEqual(client.NAME, error.exception.client)
                self.assertIsNone(client.get_checkout_url())
                stripe.checkout.Session.create.assert_not_called()
