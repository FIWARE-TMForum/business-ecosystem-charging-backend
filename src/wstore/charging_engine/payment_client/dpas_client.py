import hashlib
import hmac
from wstore.charging_engine.payment_client.payment_client import PaymentClient
from wstore.ordering.errors import PaymentError
from django.conf import settings

import os
import requests
import jwt
import uuid

from decimal import Decimal
from logging import getLogger

logger = getLogger("wstore.default_logger")

DPAS_CLIENT_API_URL = os.environ.get("BAE_CB_DPAS_CLIENT_API_URL", "https://dpas-sbx.egroup.hu/api/payment-start")

class DpasClient(PaymentClient):
    _checkout_url = None

    def __init__(self, order):
        self._order = order
        self.api_url = DPAS_CLIENT_API_URL 

    def start_redirection_payment(self, transactions):
        logger.debug(f"Using DPAS : {self.api_url}")

        payment_items = []
        for t in transactions:
            payment_item = {
                "productProviderExternalId": t["provider"], # This is the provider party ID
                "currency": t.get("currency", "EUR"),
                "productProviderSpecificData": {},
                "paymentItemExternalId" : t["billId"], # this is the ID of the customer bill
                "recurring": t["recurring"],
                **({ "amount": float(t['price'])} if t['price'] else {})
            }

            payment_items.append(payment_item)

        redirect_uri = settings.SITE
        if redirect_uri[-1] != "/":
            redirect_uri += "/"

        logger.debug("order reference: %s", self._order.pk)
        success_sig = hmac.new(self._order.hash_key, f"client=dpas&action=accept&ref={str(self._order.pk)}".encode() , hashlib.sha256).hexdigest()
        cancel_sig = hmac.new(self._order.hash_key, f"client=dpas&action=cancel&ref={str(self._order.pk)}".encode() , hashlib.sha256).hexdigest()
        logger.debug("success signature:" + success_sig) # It is supposed that in production debug() method will not print in the logs.
        logger.debug("cancel signature:" + cancel_sig) # It is supposed that in production debug() method will not print in the logs.

        redirect_uri += "checkout?client=dpas"
        success_url = redirect_uri + "&action=accept&ref=" + str(self._order.pk) + "&sig=" + success_sig
        cancel_url = redirect_uri + "&action=cancel&ref=" + str(self._order.pk) + "&sig=" + cancel_sig

        payload = {
            "baseAttributes": {
                "externalId": str(self._order.order_id),  ## Use the raw order ID
                "customerOrganizationId": str(self._order.owner_organization.actor_id), ## Use the organization Party ID
                "invoiceId": "invoice id", #
                "paymentItems": payment_items
            },
            "customerId": str(self._order.customer.userprofile.actor_id), ## Use the user Party ID
            "processSuccessUrl": success_url,
            "processErrorUrl": cancel_url,
            "responseUrlJwtQueryName": "jwt"
        }

        headers = {
            "Authorization": "Bearer " + self._order.customer.userprofile.access_token
        }

        try:
            logger.debug(f"Using access token: {self._order.customer.userprofile.access_token}")
            logger.debug(f"Contacting DPAS with payload: {payload}")

            response = requests.post(self.api_url, json=payload, headers=headers)
            response.raise_for_status()
            self._checkout_url = response.json()["redirectUrl"]
            # self._checkout_url = "http://example.com"
            return self._checkout_url
        except Exception as e:
            logger.debug(f"Error contacting payment API: {e}")
            raise PaymentError(f"Failed to initiate DPAS payment: {str(e)}") from e

    #TODO: change the return values in other payment_clients when we start using it.
    def end_redirection_payment(self, **kwargs):
        token = kwargs.get("jwt", None)
        logger.debug("end redirecting...")
        pre_auth_id = None
        if token is not None:
            unverified_header = jwt.get_unverified_header(token)
            algorithm = unverified_header['alg']
            try:
                # decode() throws a exception, so it will not set the order as failed. This is a desired behaviour
                decoded = jwt.decode(token, settings.DPAS_KEY, algorithms=[algorithm])
            except:
                logger.error("dpas decode failed")
                raise PaymentError("DPAS sign is incorrect")
            if 'paymentPreAuthorizationExternalId' in decoded:
                pre_auth_id = decoded['paymentPreAuthorizationExternalId']
        logger.debug("finish end redirection with:" + pre_auth_id)
        return [pre_auth_id], decoded['payoutList']

    def refund(self, sale_id):
        pass

    def get_checkout_url(self):
        return self._checkout_url
