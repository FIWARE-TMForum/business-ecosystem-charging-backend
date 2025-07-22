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
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urljoin
from logging import getLogger

from bson.objectid import ObjectId
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from wstore.models import User
from wstore.ordering.models import Offering

logger = getLogger("wstore.default_logger")


class NotificationsHandler:
    def __init__(self):
        # Read email configuration
        self._mailuser = settings.WSTOREMAILUSER
        self._password = settings.WSTOREMAILPASS
        self._fromaddr = settings.WSTOREMAIL
        self._server = settings.SMTPSERVER
        self._port = settings.SMTPPORT

        if not len(self._mailuser) or not len(self._password) or not len(self._fromaddr) or not len(self._server):
            raise ImproperlyConfigured("Missing email configuration")

    def _send_email(self, recipient, msg):
        logger.debug(f"Sending email with {self._server}, {self._port}, {self._mailuser}, {self._fromaddr}, {self._password}")

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

    def send_acquired_notification(self, order):
        org = order.owner_organization
        recipients = [User.objects.get(pk=pk).email for pk in org.managers]
        domain = settings.SITE

        order_url = urljoin(domain, "/#/inventory/order")
        product_url = urljoin(domain, "/#/inventory/product")

        text = "We have received the payment of your order with reference " + str(order.pk) + "\n"
        text += "containing the following product offerings: \n\n"
        for cont in order.get_contracts():
            offering = Offering.objects.get(pk=ObjectId(cont.offering))
            text += offering.name + " with id " + offering.off_id + "\n\n"

        text += "You can review your orders at: \n" + order_url + "\n"
        text += "and your acquired products at: \n" + product_url + "\n"

        bills = self.extract_bills_paths(order)

        self._send_multipart_email(text, recipients, "Product order accepted", bills)

    def send_product_upgraded_notification(self, order, contract, product_name):
        org = order.owner_organization
        recipients = [User.objects.get(pk=pk).email for pk in org.managers]
        domain = settings.SITE

        product_url = urljoin(domain, "/#/inventory/product/{}".format(contract.product_id))

        text = "There is a new version available for your acquired product {}\n".format(product_name)
        text += "You can review your new product version at {}\n".format(product_url)

        self._send_text_email(text, recipients, "Product upgraded")

    def send_provider_notification(self, order, contract):
        # Get destination email
        offering = Offering.objects.get(pk=ObjectId(contract.offering))
        org = offering.owner_organization
        recipients = [User.objects.get(pk=pk).email for pk in org.managers]
        domain = settings.SITE

        url = urljoin(domain, "/#/inventory/order")

        text = "Your product offering with name " + offering.name + " and id " + offering.off_id + "\n"
        text += "has been acquired by the user " + order.owner_organization.name + "\n"
        text += "Please review you pending orders at: \n\n" + url

        self._send_text_email(text, recipients, "Product offering acquired")

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
        self._send_text_email(text, recipients, subject)
