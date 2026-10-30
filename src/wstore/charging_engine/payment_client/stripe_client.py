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


import hashlib
import hmac
import os

# import random
# import string

import stripe
from django.conf import settings
from logging import getLogger
from decimal import Decimal

from wstore.charging_engine.payment_client.payment_client import PaymentClient, PaymentClientError
from wstore.ordering.errors import PaymentError
from wstore.ordering.models import PaymentRecord
from wstore.store_commons.product_catalog import ProductCatalog, ProductCatalogError


logger = getLogger("wstore.default_logger")

MODE = "sandbox"  # sandbox or live

stripe.api_key = os.environ.get(
    "BAE_CB_STRIPE_API_KEY", "sk_test_CGGvfNiIPwLXiDwaOfZ3oX6Y"  # PUBLIC SAMPLE API KEY DO NOT USE!!!
)
if _test_api_base := os.environ.get("BAE_CB_STRIPE_TEST_API_BASE"):
    stripe.api_base = _test_api_base


class StripeClient(PaymentClient):
    NAME = "stripe"
    END_PAYMENT_PARAMS = ("session_id",)

    _purchase = None
    _checkout_url = None

    def __init__(self, order):
        """Creates a new Stripe Payment Client

        Args:
            order (ordering.models.Order): the order to pay.
        """
        self._order = order

    def start_redirection_payment(self, transactions):
        """Start the payment process and produces a url to the stripe payment gateway.

        Args:
            transactions (list): a list of the transactions to bundle in a payment
        """
        logger.debug(f"Starting redirection payment to Stripe for order {self._order}")

        # Build URL
        url = settings.SITE
        if url[-1] != "/":
            url += "/"

        accept_param = f"client=stripe&action=accept&ref={self._order.order_id}"
        cancel_param = f"client=stripe&action=cancel&ref={self._order.order_id}"

        success_sig = hmac.new(self._order.hash_key, accept_param.encode() , hashlib.sha256).hexdigest()
        cancel_sig = hmac.new(self._order.hash_key, cancel_param.encode() , hashlib.sha256).hexdigest()
        logger.debug("success signature:" + success_sig) # It is supposed that in production debug() method will not print in the logs.
        logger.debug("cancel signature:" + cancel_sig) # It is supposed that in production debug() method will not print in the logs.

        url += "checkout?session_id={CHECKOUT_SESSION_ID}&"
        return_url = url + accept_param + f"&sig={success_sig}"
        cancel_url = url + cancel_param + f"&sig={cancel_sig}"

        catalog = ProductCatalog()

        try:
            products = {
                contract.item_id: catalog.get_offering(contract.offering)
                for contract in self._order.contracts
            }
        except ProductCatalogError as exc:
            raise PaymentClientError(self.NAME, "The offering information cannot be retrieved.") from exc

        # Build payment object
        has_recurring = False
        line_items = []
        for t in transactions:
            if t.get("recurring"):
                has_recurring = True
            line_items.append({
                "quantity": 1,
                "metadata": {"paymentItemExternalId": t["billId"]},
                "price_data": {
                    "currency": t["currency"],
                    "unit_amount": int(Decimal(t["price"]) * Decimal(100)),
                    "product_data": {
                        "name": products[t["item"]]["name"],
                        "description": products[t["item"]].get("description") or "No description",
                    },
                },
            })

        try:
            logger.debug(f"Creating checkout session for order {self._order.order_id}")
            checkout = stripe.checkout.Session.create(
                success_url=return_url,
                cancel_url=cancel_url,
                client_reference_id=str(self._order.order_id),
                mode="payment",
                **({"customer_creation": "always", "payment_intent_data": {"setup_future_usage": "off_session"}} if has_recurring else {}),
                line_items=line_items,
            )

        # Check for errors in session
        except Exception as e:  # TODO: Narrow exceptions caught
            logger.error(e)
            raise PaymentClientError(self.NAME, "The checkout session cannot be created.") from e

        # Extract URL where redirecting the customer
        self._checkout_url = checkout.url
        logger.info("PAYMENT URL: %s", self._checkout_url)
        return checkout.url

    def direct_payment(self, currency, price, credit_card):
        pass

    def end_redirection_payment(self, **kwargs):
        """Finalizes the payment process

        Keyword Args:
            session_id: The checkout session id
        """
        session_id = kwargs["session_id"]
        logger.debug(f"Stripe payment for order {self._order.order_id} completed")

        session = stripe.checkout.Session.retrieve(session_id)

        if self._order.order_id != session.client_reference_id:
            raise PaymentError('Stripe redirection was manipulated')

        state = "processed" if session.payment_status == "paid" else "pending"

        payout_list = []
        page = stripe.checkout.Session.list_line_items(session_id, limit=100)
        while True:
            for item in page.data:
                cb_id = item.metadata.get("paymentItemExternalId")
                payout_list.append({
                    "paymentItemExternalId": cb_id,
                    "state": state,
                })
                # TODO: payment external key need to be set here
                PaymentRecord.create(cb_id, payment_type=self.NAME, payment_reference=session_id)
            if not page.has_more:
                break
            page = stripe.checkout.Session.list_line_items(session_id, limit=100, starting_after=page.data[-1].id)

        return [session_id], payout_list

    def refund(self, session_id):
        try:
            checkout = stripe.checkout.Session.retrieve(session_id)
            refund = stripe.Refund.create(payment_intent=checkout.payment_intent)
            logger.debug(f"Refunding Stripe payment for checkout {session_id}")
            return refund

        except Exception as e:
            logger.error(f"Couldn't refund Stripe payment for checkout {session_id}")
            raise PaymentClientError(self.NAME, "The refund cannot be completed") from e

    def get_checkout_url(self):
        return self._checkout_url

    def check_payment_status(self, payment_reference):
        if payment_reference.startswith('pi_'):
            pi = stripe.PaymentIntent.retrieve(payment_reference)
            if pi.status == 'succeeded':
                return 'succeeded'
            if pi.status in ('processing', 'requires_action', 'requires_confirmation'):
                return 'pending'
            return 'failed'

        session = stripe.checkout.Session.retrieve(payment_reference)
        if session.payment_status == 'paid':
            return 'succeeded'
        if session.payment_status == 'unpaid':
            return 'pending'
        return 'failed'

    def charge_recurring(self, cb, record, pre_auth_id, amount, currency):
        persisted_reference = None
        try:
            if pre_auth_id.startswith('pi_'):
                pi = stripe.PaymentIntent.retrieve(pre_auth_id)
                customer_id = pi.customer
                payment_method = pi.payment_method
            else:
                session = stripe.checkout.Session.retrieve(pre_auth_id)
                customer_id = session.customer
                pi = stripe.PaymentIntent.retrieve(session.payment_intent)
                payment_method = pi.payment_method

            if not customer_id or not payment_method:
                logger.error(f"Missing customer or payment method for pre-authorization {pre_auth_id}")
                return None, 'failed'

            retry_count = record.retry_count if record is not None else 0
            previous_reference = record.payment_reference if record is not None else 'new'
            new_pi = stripe.PaymentIntent.create(
                amount=int(Decimal(str(amount)) * 100),
                currency=currency.lower(),
                customer=customer_id,
                payment_method=payment_method,
                confirm=False,
                idempotency_key=f"recurring:{cb['id']}:{retry_count}:{previous_reference}",
            )

            if record is None:
                try:
                    record = PaymentRecord.create(cb['id'], payment_type=self.NAME, payment_reference=new_pi.id)
                except Exception:
                    persisted_record = PaymentRecord.get_by_customer_bill_id(cb['id'])
                    if (persisted_record.payment_type != self.NAME or persisted_record.payment_reference != new_pi.id):
                        raise PaymentClientError(self.NAME, "CustomerBill already belongs to another payment attempt")
                    record = persisted_record
            else:
                record.payment_reference = new_pi.id
                record.save()

            persisted_reference = new_pi.id
            confirmed_pi = new_pi.confirm(off_session=True)
            if confirmed_pi.status == 'succeeded':
                return confirmed_pi.id, 'succeeded'
            if confirmed_pi.status in ('processing', 'requires_action', 'requires_confirmation'):
                return confirmed_pi.id, 'pending'
            return confirmed_pi.id, 'failed'

        except stripe.error.CardError as e:
            logger.error(f"Card error during recurring charge for {pre_auth_id}: {e}")
            return persisted_reference, 'failed'
        except Exception as e:
            logger.error(f"Error during recurring charge for {pre_auth_id}: {e}")
            return persisted_reference, 'pending'

    def batch_payout(self, payouts):
        # TODO: Translate to Stripe API.
        pass
        # sender_batch_id = "".join(random.choice(string.ascii_uppercase) for i in range(12))
        # payout = paypalrestsdk.Payout(
        #     {
        #         "sender_batch_header": {
        #             "sender_batch_id": sender_batch_id,
        #             "email_subject": "You have a payment",
        #         },
        #         "items": payouts,
        #     }
        # )
        #
        # return payout, payout.create()
