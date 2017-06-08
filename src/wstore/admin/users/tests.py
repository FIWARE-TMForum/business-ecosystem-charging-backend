# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid

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

from django.core.exceptions import ImproperlyConfigured

from mock import MagicMock, mock_open, call
from nose_parameterized import parameterized

from django.test import TestCase

from wstore.admin.users import notification_handler

__test__ = False


class NotificationsTestCase(TestCase):
    tags = ('notifications', )

    def setUp(self):
        # Mock email configuration
        notification_handler.settings.WSTOREMAIL = 'wstore@email.com'
        notification_handler.settings.WSTOREMAILPASS = 'passwd'
        notification_handler.settings.WSTOREMAILUSER = 'wstore'
        notification_handler.settings.SMTPSERVER = 'smtp.gmail.com'
        notification_handler.settings.SMTPPORT = 587

        notification_handler.settings.BASEDIR = '/home/test/wstore'

        # Mock charges
        charge1 = MagicMock()
        charge1.invoice = '/charging/media/bills/bill1.pdf'

        # Mock contracts
        contract1 = MagicMock()
        contract1.offering.name = 'Offering1'
        contract1.offering.off_id = '1'
        contract1.offering.owner_organization.managers = ['33333', '44444']
        contract1.charges = [charge1]

        contract2 = MagicMock()
        contract2.offering.name = 'Offering2'
        contract2.offering.off_id = '2'
        contract2.charges = []

        # Mock order
        self._order = MagicMock()
        self._order.pk = 'orderid'
        self._order.order_id = '67'
        self._order.owner_organization.managers = ['11111', '22222']
        self._order.owner_organization.name = 'customer'
        self._order.get_item_contract.return_value = contract1

        self._order.contracts = [contract1, contract2]

        # Mock user
        notification_handler.User = MagicMock()
        self._user1 = MagicMock()
        self._user1.email = 'user1@email.com'
        self._user2 = MagicMock()
        self._user2.email = 'user2@email.com'
        notification_handler.User.objects.get.side_effect = [self._user1, self._user2]

        # Mock context
        notification_handler.Context = MagicMock()
        context = MagicMock()
        context.site.domain = 'http://localhost:8000'
        notification_handler.Context.objects.all.return_value = [context]

        # Mock email libs
        notification_handler.MIMEMultipart = MagicMock()
        notification_handler.MIMEText = MagicMock()
        notification_handler.MIMEBase = MagicMock()
        notification_handler.encoders = MagicMock()
        notification_handler.smtplib = MagicMock()

        # Mock open method
        self._mock_open = mock_open()
        self._old_open = notification_handler.__builtins__['open']
        notification_handler.__builtins__['open'] = self._mock_open

    def tearDown(self):
        notification_handler.__builtins__['open'] = self._old_open
        reload(notification_handler)

    def _empty_email(self):
        notification_handler.settings.WSTOREMAIL = ''

    def _empty_pass(self):
        notification_handler.settings.WSTOREMAILPASS = ''

    def _empty_user(self):
        notification_handler.settings.WSTOREMAILUSER = ''

    def _empty_server(self):
        notification_handler.settings.SMTPSERVER = ''

    @parameterized.expand([
        (_empty_email, ),
        (_empty_pass, ),
        (_empty_user, ),
        (_empty_server, )
    ])
    def test_improperly_configured(self, empty_param):
        empty_param(self)

        error = None
        try:
            notification_handler.NotificationsHandler()
        except ImproperlyConfigured as e:
            error = e

        self.assertTrue(error is not None)
        self.assertEquals('Missing email configuration', unicode(error))

    def _validate_user_call(self):
        self.assertEquals([
            call(pk='11111'),
            call(pk='22222')
        ], notification_handler.User.objects.get.call_args_list)

    def _validate_provider_call(self):
        self.assertEquals([
            call(pk='33333'),
            call(pk='44444')
        ], notification_handler.User.objects.get.call_args_list)

    def _validate_mime_text_info(self, subject):
        self.assertEquals([
            call('Subject', subject),
            call('From', 'wstore@email.com'),
            call('To', 'user1@email.com,user2@email.com')
        ], notification_handler.MIMEText().__setitem__.call_args_list)

    def _validate_email_call(self, mime, emails=None):
        if emails is None:
            emails = ['user1@email.com', 'user2@email.com']
        notification_handler.smtplib.SMTP.assert_called_once_with('smtp.gmail.com', 587)
        notification_handler.smtplib.SMTP().starttls.assert_called_once_with()
        notification_handler.smtplib.SMTP().login.assert_called_once_with('wstore', 'passwd')
        notification_handler.smtplib.SMTP().sendmail.assert_called_once_with(
            'wstore@email.com',
            emails,
            mime().as_string()
        )

    def _validate_multipart_call(self):
        self._mock_open.assert_called_once_with('/home/test/wstore/media/bills/bill1.pdf', 'rb')

        notification_handler.MIMEBase.assert_called_once_with('application', 'pdf')
        notification_handler.MIMEBase().set_payload.assert_called_once_with(self._mock_open().read())

        notification_handler.encoders.encode_base64.assert_called_once_with(notification_handler.MIMEBase())
        notification_handler.MIMEBase().add_header.assert_called_once_with(
            'Content-Disposition',
            'attachment',
            filename='bill1.pdf'
        )

        self.assertEquals([
            call(notification_handler.MIMEText()),
            call(notification_handler.MIMEBase())
        ], notification_handler.MIMEMultipart().attach.call_args_list)

    def test_acquisition_notification(self):
        # Execute method
        handler = notification_handler.NotificationsHandler()
        handler.send_acquired_notification(self._order)

        # Validate calls
        self._validate_user_call()

        notification_handler.MIMEMultipart.assert_called_once_with()

        self.assertEquals([
            call('Subject', 'Product order accepted'),
            call('From', 'wstore@email.com'),
            call('To', 'user1@email.com,user2@email.com')
        ], notification_handler.MIMEMultipart().__setitem__.call_args_list)

        text = "We have received the payment of your order with reference orderid\n"
        text += "containing the following product offerings: \n\n"
        text += "Offering1 with id 1\n\n"
        text += "Offering2 with id 2\n\n"
        text += "You can review your orders at: \nhttp://localhost:8000/#/inventory/order\n"
        text += "and your acquired products at: \nhttp://localhost:8000/#/inventory/product\n"

        notification_handler.MIMEText.assert_called_once_with(text)

        self._validate_multipart_call()
        self._validate_email_call(notification_handler.MIMEMultipart)

    def test_renovation_notification(self):
        handler = notification_handler.NotificationsHandler()
        transactions = [{
            'item': '0'
        }]

        handler.send_renovation_notification(self._order, transactions)

        self._validate_user_call()
        self._order.get_item_contract.assert_called_once_with('0')

        text = 'We have received your recurring payment for renovating products offerings\n'
        text += 'acquired in the order with reference orderid\n'
        text += 'The following product offerings have been renovated: \n\n'
        text += 'Offering1 with id 1\n\n'
        text += 'You can review your orders at: \nhttp://localhost:8000/#/inventory/order\n'
        text += 'and your acquired products at: \nhttp://localhost:8000/#/inventory/product\n'

        notification_handler.MIMEText.assert_called_once_with(text)

        self._validate_multipart_call()
        self._validate_email_call(notification_handler.MIMEMultipart)

    def test_payout_error(self):
        handler = notification_handler.NotificationsHandler()

        handler.send_payout_error("user1@email.com", "Some error!")

        text = "We had some problem processing a payout to {user1@email.com}.\n\n"
        text += "The error was: Some error!"

        self._validate_email_call(notification_handler.MIMEText, ["user1@email.com"])

    def test_provider_notification(self):
        handler = notification_handler.NotificationsHandler()
        handler.send_provider_notification(self._order, self._order.contracts[0])

        # Validate calls
        self._validate_provider_call()

        text = 'Your product offering with name Offering1 and id 1\n'
        text += 'has been acquired by the user customer\n'
        text += 'Please review you pending orders at: \n\nhttp://localhost:8000/#/inventory/order'

        notification_handler.MIMEText.assert_called_once_with(text)

        self._validate_mime_text_info('Product offering acquired')

        self._validate_email_call(notification_handler.MIMEText)

    def test_payment_required_notification(self):
        handler = notification_handler.NotificationsHandler()
        handler.send_payment_required_notification(self._order, self._order.contracts[0])

        text = 'Your subscription belonging to the product offering Offering1 has expired.\n'
        text += 'You can renovate all your pending subscriptions of the order with reference orderid\n'
        text += 'in the web portal or accessing the following link: \n\n'
        text += 'http://localhost:8000/#/inventory/order/67'

        notification_handler.MIMEText.assert_called_once_with(text)

        self._validate_mime_text_info('Offering1 subscription expired')

        self._validate_email_call(notification_handler.MIMEText)

    def test_near_expiration_notification(self):
        handler = notification_handler.NotificationsHandler()
        handler.send_near_expiration_notification(self._order, self._order.contracts[0], 3)

        self._validate_user_call()

        text = 'Your subscription belonging to the product offering Offering1\n'
        text += 'is going to expire in 3 days. \n\n'
        text += 'You can renovate all your pending subscriptions of the order with reference orderid\n'
        text += 'in the web portal or accessing the following link: \n\n'
        text += 'http://localhost:8000/#/inventory/order/67'

        notification_handler.MIMEText.assert_called_once_with(text)

        self._validate_mime_text_info('Offering1 subscription is about to expire')
