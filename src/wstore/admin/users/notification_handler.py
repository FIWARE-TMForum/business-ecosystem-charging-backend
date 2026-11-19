# -*- coding: utf-8 -*-

# Copyright (c) 2016 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid

# Copyright (c) 2025 Future Internet Consulting and Development Solutions S.L.

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


import os
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from logging import getLogger
from urllib.parse import quote, urljoin

import requests
from bson.objectid import ObjectId
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from wstore.admin.users.email_config import get_email_config
from wstore.models import User
from wstore.ordering.models import Offering
from wstore.store_commons.utils.url import get_service_url

logger = getLogger("wstore.default_logger")


class NotificationsHandler:
    def __init__(self):
        # Read email configuration
        self._set_config()

    def _set_config(self):
        config = get_email_config()
        if config is None:
            raise ImproperlyConfigured("Missing email configuration")

        self._mailuser = config.email_user
        self._password = config.email_password
        self._fromaddr = config.email
        self._server = config.smtp_server
        self._port = config.smtp_port

    def test_connection(self):
        """Check saved SMTP settings without sending a message."""
        with smtplib.SMTP(self._server, self._port, timeout=10) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(self._mailuser, self._password)

    def _send_email(self, recipient, msg):
        logger.debug(
            f"Sending email with {self._server}, {self._port}, {self._mailuser}, {self._fromaddr}, {self._password}"
        )

        server = smtplib.SMTP(self._server, self._port)
        server.starttls()
        server.login(self._mailuser, self._password)

        server.sendmail(self._fromaddr, recipient, msg.as_string())

    def _send_text_email(self, text, recipients, subject):
        logger.debug("Sending email to " + ",".join(recipients) + "with subject " + subject)

        msg = MIMEText(text)
        msg["Subject"] = subject
        msg["From"] = self._fromaddr
        msg["To"] = ",".join(recipients)

        self._send_email(recipients, msg)

    def _send_html_email(self, text, recipients, subject):
        logger.debug("Sending email to " + ",".join(recipients) + "with subject " + subject)

        html = f"""\
            <!doctype html>
            <html lang="en">
                <body style="margin:0;padding:0;background-color:#f6f9fc;">
                <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f6f9fc;padding:24px 0;">
                    <tr>
                    <td align="center">
                    <table role="presentation" cellpadding="0" cellspacing="0" width="600"
                        style="max-width:600px;background-color:#ffffff;border-radius:10px;overflow:hidden;font-family:Arial,Helvetica,sans-serif;">
                    <tr>
                        <td style="padding:18px 22px;background-color:#2e58a7;color:#ffffff;font-size:18px;font-weight:bold;">
                            {subject}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:22px;color:#111827;font-size:14px;line-height:1.6;">
                            {text}
                        </td>
                    </tr>
                </table>
                </td>
            </tr>
            </table>
            </body>
            </html>
        """

        msg = MIMEText(html, "html")
        msg["Subject"] = subject
        msg["From"] = self._fromaddr
        msg["To"] = ",".join(recipients)

        self._send_email(recipients, msg)

    def _send_multipart_email(self, text, recipients, subject, bills):
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = self._fromaddr
        msg["To"] = ",".join(recipients)

        message = MIMEText(text)
        msg.attach(message)

        for bill in bills:
            path = os.path.join(settings.BASEDIR, bill)

            with open(path, "rb") as fp:
                b_msg = MIMEBase("application", "pdf")
                b_msg.set_payload(fp.read())

            # Encode the payload using Base64
            encoders.encode_base64(b_msg)
            b_msg.add_header("Content-Disposition", "attachment", filename=bill.split("/")[-1])
            msg.attach(b_msg)

        self._send_email(recipients, msg)

    def extract_bills_paths(self, order):
        return [
            charge.invoice[10:] if charge.invoice.startswith("/charging/") else charge.invoice
            for contract in order.get_contracts()
            for charge in contract.charges
        ]

    @classmethod
    def send_acquired_notification(cls, product, offering_info):
        """Send a ready email using the full offering loaded during completion."""
        try:
            buyers = cls._parties(product.get("relatedParty", []), settings.CUSTOMER_ROLE)
            if not buyers:
                logger.warning("No buyer party for product %s", product["id"])
                return

            message = (
                "<p>Good news! <strong>{}</strong> is now active and ready to use.</p>"
                "<p>You can view your product and its details in your inventory.</p><p>{}</p>"
            ).format(
                cls._offering_label(offering_info),
                cls._link("/#/inventory/product/" + quote(str(product["id"]), safe=""), "View your product"),
            )

            for party in buyers.values():
                cls().send_custom_email(cls._party_email(party), "Your product is ready", message)

        except Exception:
            logger.exception("Could not prepare customer notification for product %s", product.get("id"))

    def send_product_upgraded_notification(self, order, contract, product_name):
        org = order.owner_organization
        recipients = [User.objects.get(pk=pk).email for pk in org.managers]
        domain = settings.SITE

        product_url = urljoin(domain, "/#/inventory/product/{}".format(contract.product_id))

        text = "There is a new version available for your acquired product {}\n".format(product_name)
        text += "You can review your new product version at {}\n".format(product_url)

        self._send_text_email(text, recipients, "Product upgraded")

    @classmethod
    def send_provider_notification(cls, order, offering_names):
        """Send one email for the order; all items belong to the same provider."""
        try:
            items = order.get("productOrderItem", [])
            if not items:
                return

            parties = {party["role"].lower(): party for party in order.get("relatedParty", [])}
            provider = parties.get(settings.PROVIDER_ROLE.lower())

            if provider is None:
                logger.warning("No provider party for order %s", order.get("id"))
                return

            customer = parties[settings.CUSTOMER_ROLE.lower()]
            customer_name = customer.get("name") or customer["id"]

            rows = []
            for index in range(len(items)):
                offering_name = offering_names[index]
                rows.append(
                    "<li><strong>{}</strong> — ordered by {}</li>".format(
                        escape(str(offering_name or "Your product")),
                        escape(str(customer_name)),
                    )
                )

            message = (
                "<p>You have received a new order for:</p><ul>{}</ul>"
                "<p>Open your orders to review the request and take the next steps.</p><p>{}</p>"
            ).format("".join(rows), cls._link("/#/inventory/order", "Manage orders"))

            cls().send_custom_email(cls._party_email(provider), "You have a new order", message)
        except Exception:
            logger.exception("Could not send provider notification for order %s", order.get("id"))

    def send_payment_required_notification(self, order, contract):
        org = order.owner_organization
        recipients = [User.objects.get(pk=pk).email for pk in org.managers]

        domain = settings.SITE
        url = urljoin(domain, "/#/inventory/order/" + order.order_id)

        offering = Offering.objects.get(pk=ObjectId(contract.offering))

        text = "Your subscription belonging to the product offering " + offering.name + " has expired.\n"
        text += "You can renovate all your pending subscriptions of the order with reference " + str(order.pk) + "\n"
        text += "in the web portal or accessing the following link: \n\n"
        text += url

        self._send_text_email(text, recipients, offering.name + " subscription expired")

    def send_near_expiration_notification(self, order, contract, days):
        org = order.owner_organization
        recipients = [User.objects.get(pk=pk).email for pk in org.managers]

        domain = settings.SITE
        url = urljoin(domain, "/#/inventory/order/" + order.order_id)

        offering = Offering.objects.get(pk=ObjectId(contract.offering))

        text = "Your subscription belonging to the product offering " + offering.name + "\n"
        text += "is going to expire in " + str(days) + " days. \n\n"
        text += "You can renovate all your pending subscriptions of the order with reference " + str(order.pk) + "\n"
        text += "in the web portal or accessing the following link: \n\n"
        text += url

        self._send_text_email(text, recipients, offering.name + " subscription is about to expire")

    def send_renovation_notification(self, order, transactions):
        org = order.owner_organization
        recipients = [User.objects.get(pk=pk).email for pk in org.managers]
        domain = settings.SITE

        order_url = urljoin(domain, "/#/inventory/order")
        product_url = urljoin(domain, "/#/inventory/product")

        text = "We have received your recurring payment for renovating products offerings\n"
        text += "acquired in the order with reference " + str(order.pk) + "\n"

        text += "The following product offerings have been renovated: \n\n"
        for t in transactions:
            cont = order.get_item_contract(t["item"])
            offering = Offering.objects.get(pk=ObjectId(cont.offering))

            text += offering.name + " with id " + offering.off_id + "\n\n"

        text += "You can review your orders at: \n" + order_url + "\n"
        text += "and your acquired products at: \n" + product_url + "\n"

        bills = self.extract_bills_paths(order)

        self._send_multipart_email(text, recipients, "Product order accepted", bills[-len(transactions) :])

    def send_payout_error(self, recipient, error_msg):
        recipients = [recipient]
        subject = "Automatic payout error."

        text = """We had some problem processing a payout to {}.

The error was: {}""".format(
            recipient, error_msg
        )

        self._send_text_email(text, recipients, subject)

    def send_custom_email(self, recipient, subject, text):
        recipients = [recipient]
        self._send_html_email(text, recipients, subject)

    @staticmethod
    def _parties(parties, role):
        return {
            str(party["id"]): party
            for party in parties
            if party.get("id") and party.get("role", "").lower() == role.lower()
        }

    @staticmethod
    def _link(path, label):
        return '<a href="{}">{}</a>'.format(escape(urljoin(settings.SITE, path), quote=True), label)

    @staticmethod
    def _offering_label(offering_info):
        return escape(str(offering_info.get("name") or "Your product"))

    @staticmethod
    def _party_email(party):
        party_type = "individual" if party.get("@referredType", "").lower() == "individual" else "organization"

        url = get_service_url("party", "/{}/{}".format(party_type, quote(str(party["id"]), safe="")))
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        for medium in response.json().get("contactMedium", []):
            email = medium.get("characteristic", {}).get("emailAddress")
            if medium.get("mediumType", "").lower() == "email" and email and email.strip():
                return email.strip()

        raise ValueError("Party {} has no email contact medium".format(party["id"]))
