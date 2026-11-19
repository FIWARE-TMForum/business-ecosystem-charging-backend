# -*- coding: utf-8 -*-

# Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

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


import base64
import hashlib
import hmac
import json
import os
import random
import xml.etree.ElementTree as ET

from datetime import datetime
from decimal import Decimal
from logging import getLogger
from urllib.parse import unquote_plus, urlencode
from xml.sax.saxutils import escape as xml_escape

import requests
from django.conf import settings

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from wstore.charging_engine.payment_client.payment_client import PaymentClient, PaymentClientError
from wstore.ordering.errors import PaymentError
from wstore.ordering.models import PaymentRecord
from wstore.store_commons.product_catalog import ProductCatalog, ProductCatalogError


logger = getLogger("wstore.default_logger")

MERCHANT_CODE = os.environ.get("BAE_CB_REDSYS_MERCHANT_CODE", "999008881")
TERMINAL = os.environ.get("BAE_CB_REDSYS_TERMINAL", "001")
SECRET_KEY = os.environ.get("BAE_CB_REDSYS_SECRET_KEY", "sq7HjrUOBfKmC576ILgskD5srU870gJ7")
REDSYS_BASE_URL = os.environ.get("BAE_CB_REDSYS_URL", "https://sis-t.redsys.es:25443/sis")
REDSYS_QUERY_URL = os.environ.get(
    "BAE_CB_REDSYS_QUERY_URL",
    f"{REDSYS_BASE_URL.rsplit('/sis', 1)[0]}/apl02/services/SerClsWSConsulta",
)

SIGNATURE_VERSION = "HMAC_SHA512_V2"
SOAP_SIGNATURE_VERSION = "HMAC_SHA256_V1"

CURRENCY = "978"  # ISO 4217 for EUR


def _encode_params(params):
    # Redsys expects unpadded Base64URL. Keeping the trailing ``=`` padding
    # makes /realizarPago reject the whole block with SIS0430 before it can
    # read fields such as the amount or merchant code.
    return base64.urlsafe_b64encode(json.dumps(params).encode()).decode().rstrip("=")


def _decode_params(encoded):
    normalized = encoded.replace("-", "+").replace("_", "/")
    normalized += "=" * (-len(normalized) % 4)
    return json.loads(base64.b64decode(normalized))


def _derive_key(ds_order):
    # HMAC_SHA512_V2: the merchant key is used as a plain string (NOT base64
    # decoded), truncated to its first 16 characters (zero-padded on the right
    # if shorter). The order number is AES-128-CBC encrypted with it, using a
    # zero IV and PKCS7 padding, and the result is base64 encoded because the
    # HMAC key is that base64 *string*, not the raw encrypted bytes.
    key = SECRET_KEY[:16].encode().ljust(16, b"\x00")
    data = ds_order.encode()
    pad_len = 16 - (len(data) % 16)
    data += bytes([pad_len]) * pad_len
    encryptor = Cipher(algorithms.AES(key), modes.CBC(b"\x00" * 16)).encryptor()
    return base64.b64encode(encryptor.update(data) + encryptor.finalize())


def _sign(ds_order, encoded_params):
    digest = hmac.new(_derive_key(ds_order), encoded_params.encode(), hashlib.sha512).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _verify_signature(ds_order, encoded_params, signature):
    expected = _sign(ds_order, encoded_params)
    normalized = signature.replace("+", "-").replace("/", "_").rstrip("=")
    return hmac.compare_digest(expected, normalized)


def _soap_signature(ds_order, version_xml):
    key = base64.b64decode(SECRET_KEY)
    order = ds_order.encode()
    order += b"\x00" * (-len(order) % 8)

    encryptor = Cipher(
        algorithms.TripleDES(key),
        modes.CBC(b"\x00" * 8),
    ).encryptor()
    operation_key = encryptor.update(order) + encryptor.finalize()
    digest = hmac.new(
        operation_key,
        version_xml.encode(),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode()


def _find_xml_element(root, name):
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == name:
            return element
    return None


def _xml_text(root, name):
    element = _find_xml_element(root, name)
    return element.text if element is not None else None


def _parse_soap_status(response_body, expected_order):
    try:
        envelope = ET.fromstring(response_body)
        result_element = _find_xml_element(
            envelope,
            "consultaOperacionesReturn",
        )
        if result_element is None or not result_element.text:
            raise ValueError("Missing consultaOperacionesReturn")
        result = ET.fromstring(result_element.text)
    except (ET.ParseError, ValueError) as e:
        raise PaymentClientError(
            "redsys",
            f"Invalid Redsys SOAP response: {e}",
        )

    error_code = _xml_text(result, "Ds_ErrorCode")
    if error_code:
        if error_code == "XML0024":
            return "failed"
        raise PaymentClientError(
            "redsys",
            f"Redsys SOAP query returned error {error_code}",
        )

    operation = _find_xml_element(result, "Response")
    if operation is None:
        raise PaymentClientError(
            "redsys",
            "Redsys SOAP query returned no operation",
        )

    returned_order = _xml_text(operation, "Ds_Order")
    if returned_order != expected_order:
        raise PaymentClientError(
            "redsys",
            "Redsys SOAP query returned a different order",
        )

    if _xml_text(operation, "Ds_State") != "F":
        return "pending"

    return _payment_status(_xml_text(operation, "Ds_Response"))


def _new_order_number():
    # Ds_Merchant_Order must be 4-12 chars, the first 4 numeric, and unique
    return datetime.utcnow().strftime("%y%m%d") + "".join(random.choices("0123456789", k=6))


def _pack_pre_auth_id(identifier, cof_txnid):
    if not identifier:
        return None
    return ":".join([identifier, cof_txnid or "-"])


def _unpack_pre_auth_id(pre_auth_id):
    parts = pre_auth_id.split(":")
    if len(parts) == 5:
        # Compatibility with products created with the old packed reference.
        identifier, cof_txnid = parts[2], parts[3]
    elif len(parts) == 2:
        identifier, cof_txnid = parts
    else:
        raise ValueError("Invalid Redsys pre-authorization identifier")

    return {
        "identifier": identifier if identifier != "-" else None,
        "cof_txnid": cof_txnid if cof_txnid != "-" else None,
    }


def _payment_status(ds_response):
    if ds_response is None:
        return "pending"

    try:
        response_code = int(ds_response)
    except (TypeError, ValueError):
        return "failed"

    return "succeeded" if 0 <= response_code <= 99 else "failed"


class RedsysClient(PaymentClient):
    NAME = "redsys"
    END_PAYMENT_PARAMS = ("Ds_MerchantParameters", "Ds_Signature")

    _purchase = None
    _checkout_url = None

    def __init__(self, order):
        """Creates a new Redsys Payment Client

        Args:
            order (ordering.models.Order): the order to pay.
        """
        self._order = order

    def start_redirection_payment(self, transactions):
        """Start the payment process and produces a url to the Redsys payment gateway (TPV Virtual).

        Args:
            transactions (list): a list of the transactions to bundle in a payment
        """
        logger.debug(f"Starting redirection payment to Redsys for order {self._order}")

        # Build frontend callback URLs
        frontend_url = settings.SITE.rstrip("/")

        accept_param = f"client=redsys&action=accept&ref={self._order.order_id}"
        cancel_param = f"client=redsys&action=cancel&ref={self._order.order_id}"

        success_sig = hmac.new(self._order.hash_key, accept_param.encode(), hashlib.sha256).hexdigest()
        cancel_sig = hmac.new(self._order.hash_key, cancel_param.encode(), hashlib.sha256).hexdigest()
        logger.debug("success signature:" + success_sig)
        logger.debug("cancel signature:" + cancel_sig)

        # Redsys appends its Ds_* response params to these URLs when the
        # terminal has "send parameters in the URLs" enabled
        return_url = f"{frontend_url}/checkout?{accept_param}&sig={success_sig}"
        cancel_url = f"{frontend_url}/checkout?{cancel_param}&sig={cancel_sig}"

        catalog = ProductCatalog()

        try:
            products = {
                contract.item_id: catalog.get_offering(contract.offering)
                for contract in self._order.contracts
            }
        except ProductCatalogError as exc:
            raise PaymentClientError(self.NAME, "The offering information cannot be retrieved.") from exc

        # Redsys handles a single aggregated charge, so the total amount is
        # computed here and the customer bill ids travel in Ds_MerchantData
        has_recurring = False
        total = Decimal("0")
        bills = []
        names = []
        for t in transactions:
            if t.get("recurring"):
                has_recurring = True
            total += Decimal(t["price"])
            bills.append(t["billId"])
            names.append(products[t["item"]]["name"])

        ds_order = _new_order_number()
        merchant_data = json.dumps({"ref": str(self._order.order_id), "bills": bills})

        params = {
            "DS_MERCHANT_AMOUNT": str(int(total * Decimal(100))),
            "DS_MERCHANT_ORDER": ds_order,
            "DS_MERCHANT_MERCHANTCODE": MERCHANT_CODE,
            "DS_MERCHANT_CURRENCY": CURRENCY,
            "DS_MERCHANT_TRANSACTIONTYPE": "0",
            "DS_MERCHANT_TERMINAL": TERMINAL,
            "DS_MERCHANT_URLOK": return_url,
            "DS_MERCHANT_URLKO": cancel_url,
            "DS_MERCHANT_MERCHANTDATA": merchant_data,
            "DS_MERCHANT_PRODUCTDESCRIPTION": ", ".join(names)[:125],
            # Tokenize the card (credentials-on-file) to allow recurring charges
            **({"DS_MERCHANT_IDENTIFIER": "REQUIRED", "DS_MERCHANT_COF_INI": "S", "DS_MERCHANT_COF_TYPE": "R"} if has_recurring else {}),
        }

        encoded_params = _encode_params(params)
        signature = _sign(ds_order, encoded_params)

        # The frontend owns the browser navigation and converts these three
        # signed values into the POST form required by Redsys.
        payment_query = urlencode({
            "RedsysPaymentUrl": f"{REDSYS_BASE_URL}/realizarPago",
            "Ds_SignatureVersion": SIGNATURE_VERSION,
            "Ds_MerchantParameters": encoded_params,
            "Ds_Signature": signature,
        })
        self._checkout_url = f"{frontend_url}/redsys-payment?{payment_query}"
        logger.info("PAYMENT URL for order %s ready", ds_order)
        return self._checkout_url

    def direct_payment(self, currency, price, credit_card):
        pass

    def end_redirection_payment(self, **kwargs):
        """Finalizes the payment process

        Keyword Args:
            Ds_MerchantParameters: base64 encoded response parameters sent by Redsys
            Ds_Signature: signature of the response parameters
        """
        encoded_params = kwargs["Ds_MerchantParameters"]
        signature = kwargs["Ds_Signature"]
        logger.debug(f"Redsys payment for order {self._order.order_id} completed")

        response = _decode_params(encoded_params)
        ds_order = response.get("Ds_Order")

        if not ds_order or not _verify_signature(ds_order, encoded_params, signature):
            raise PaymentError("Redsys response signature is incorrect")

        merchant_data = json.loads(unquote_plus(response.get("Ds_MerchantData", "{}")))
        if str(self._order.order_id) != merchant_data.get("ref"):
            raise PaymentError("Redsys redirection was manipulated")

        raw_ds_response = response.get("Ds_Response")
        try:
            ds_response = int(raw_ds_response)
        except (TypeError, ValueError):
            ds_response = -1

        # Ds_Response codes 0000-0099 mean the payment was authorized
        if not 0 <= ds_response <= 99:
            raise PaymentError(f"Redsys payment not authorized (Ds_Response: {ds_response})")

        pre_auth_id = _pack_pre_auth_id(
            response.get("Ds_Merchant_Identifier"),
            response.get("Ds_Merchant_Cof_Txnid"),
        )

        payout_list = []
        for cb_id in merchant_data.get("bills", []):
            payout_list.append({
                "paymentItemExternalId": cb_id,
                "state": "processed",
            })
            PaymentRecord.create(cb_id, payment_type=self.NAME, payment_reference=ds_order)

        return ([pre_auth_id] if pre_auth_id else []), payout_list

    def _rest_request(self, params):
        encoded_params = _encode_params(params)
        payload = {
            "Ds_SignatureVersion": SIGNATURE_VERSION,
            "Ds_MerchantParameters": encoded_params,
            "Ds_Signature": _sign(params["DS_MERCHANT_ORDER"], encoded_params),
        }

        response = requests.post(f"{REDSYS_BASE_URL}/rest/trataPeticionREST", json=payload)
        response.raise_for_status()
        body = response.json()

        if "errorCode" in body:
            raise PaymentClientError(self.NAME, f"Redsys returned error {body['errorCode']}")

        result = _decode_params(body["Ds_MerchantParameters"])
        if not _verify_signature(result.get("Ds_Order", ""), body["Ds_MerchantParameters"], body["Ds_Signature"]):
            raise PaymentClientError(self.NAME, "Redsys response signature is incorrect")

        return result

    def refund(self, sale_id):
        raise NotImplementedError("It is not possible to do a refund currently")

    def get_checkout_url(self):
        return self._checkout_url

    def _query_payment_status(self, ds_order):
        version_xml = (
            '<Version Ds_Version="0.0"><Message><Transaction>'
            f"<Ds_MerchantCode>{xml_escape(MERCHANT_CODE)}</Ds_MerchantCode>"
            f"<Ds_Terminal>{xml_escape(TERMINAL)}</Ds_Terminal>"
            f"<Ds_Order>{xml_escape(ds_order)}</Ds_Order>"
            "<Ds_TransactionType>0</Ds_TransactionType>"
            "</Transaction></Message></Version>"
        )
        signature = _soap_signature(ds_order, version_xml)
        query_xml = (
            f"<Messages>{version_xml}"
            f"<Signature>{signature}</Signature>"
            f"<SignatureVersion>{SOAP_SIGNATURE_VERSION}</SignatureVersion>"
            "</Messages>"
        )
        soap_body = (
            '<?xml version="1.0"?>'
            '<soapenv:Envelope '
            'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            'xmlns:web="http://webservices.apl02.redsys.es">'
            "<soapenv:Header/><soapenv:Body>"
            "<web:consultaOperaciones><cadenaXML><![CDATA["
            f"{query_xml}"
            "]]></cadenaXML></web:consultaOperaciones>"
            "</soapenv:Body></soapenv:Envelope>"
        )

        response = requests.post(
            REDSYS_QUERY_URL,
            data=soap_body.encode(),
            headers={
                "Content-Type": "text/xml;charset=utf-8",
                "SOAPAction": "consultaOperaciones",
            },
        )
        response.raise_for_status()
        return _parse_soap_status(response.content, ds_order)

    def check_payment_status(self, payment_reference):
        try:
            return self._query_payment_status(payment_reference)
        except Exception as e:
            logger.error("Unable to query Redsys status for order %s: %s", payment_reference, e)
            return "pending"

    def charge_recurring(self, cb, record, pre_auth_id, amount, currency):
        ds_order = None
        try:
            pre_auth = _unpack_pre_auth_id(pre_auth_id)

            if not pre_auth["identifier"]:
                logger.error(f"Missing card token (Ds_Merchant_Identifier) for pre-authorization {pre_auth_id}")
                return None, "failed"

            ds_order = _new_order_number()
            if record is None:
                try:
                    record = PaymentRecord.create(cb['id'], payment_type=self.NAME, payment_reference=ds_order)
                except Exception:
                    persisted_record = PaymentRecord.get_by_customer_bill_id(cb['id'])
                    if persisted_record.payment_type != self.NAME:
                        raise PaymentClientError(self.NAME, "CustomerBill already belongs to another payment client")
                    # Another scheduler already prepared this same attempt.
                    record = persisted_record
                    ds_order = persisted_record.payment_reference
            else:
                record.payment_reference = ds_order
                record.save()
            amount_cents = str(int(Decimal(str(amount)) * 100))

            result = self._rest_request({
                "DS_MERCHANT_AMOUNT": amount_cents,
                "DS_MERCHANT_ORDER": ds_order,
                "DS_MERCHANT_MERCHANTCODE": MERCHANT_CODE,
                "DS_MERCHANT_CURRENCY": CURRENCY,
                "DS_MERCHANT_TRANSACTIONTYPE": "0",
                "DS_MERCHANT_TERMINAL": TERMINAL,
                # Merchant initiated transaction with the stored credential
                "DS_MERCHANT_IDENTIFIER": pre_auth["identifier"],
                "DS_MERCHANT_DIRECTPAYMENT": "true",
                "DS_MERCHANT_EXCEP_SCA": "MIT",
                "DS_MERCHANT_COF_INI": "N",
                "DS_MERCHANT_COF_TYPE": "R",
                **(
                    {"DS_MERCHANT_COF_TXNID": pre_auth["cof_txnid"]}
                    if pre_auth["cof_txnid"]
                    else {}
                ),
            })

            return ds_order, _payment_status(result.get("Ds_Response"))

        except Exception as e:
            logger.error(f"Error during recurring charge for {pre_auth_id}: {e}")
            if ds_order is not None:
                # The request may have reached Redsys. Keep the attempt pending
                # rather than retrying it and risking a duplicate charge.
                return ds_order, "pending"
            return None, "failed"

    def batch_payout(self, payouts):
        # Not supported by Redsys
        pass
