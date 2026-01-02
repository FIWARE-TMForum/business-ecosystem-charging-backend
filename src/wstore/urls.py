# -*- coding: utf-8 -*-

# Copyright (c) 2013 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

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

from django.conf.urls import url

from wstore.admin import views as admin_views
from wstore.asset_manager import views as offering_views
from wstore.asset_manager.resource_plugins import views as plugins_views
from wstore.charging_engine import views as charging_views
from wstore.charging_engine.accounting import views as accounting_views
from wstore.ordering import views as ordering_views
from wstore.rss import views as rss_views
from wstore.service import views as service_views

urlpatterns = [
    # FIXME: Workaround for saving services while the service inventory API is implemented
    url(
        r"^service/?$",
        service_views.ServiceCollection(permitted_methods=("GET",)),
    ),
    url(
        r"^service/(?P<service_id>.+)/?$",
        service_views.ServiceEntry(permitted_methods=("GET",)),
    ),
    # API
    url(
        r"^charging/api/assetManagement/assets/?$",
        offering_views.AssetCollection(permitted_methods=("GET",)),
    ),
    url(
        r"^charging/api/assetManagement/assets/uploadJob/?$",
        offering_views.UploadCollection(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/assetManagement/assets/validateJob/?$",
        offering_views.ValidateCollection(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/assetManagement/assets/offeringJob/?$",
        offering_views.ValidateOfferingCollection(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/assetManagement/assets/(?P<asset_id>\w+)/?$",
        offering_views.AssetEntry(permitted_methods=("GET",)),
    ),
    url(
        r"^charging/api/assetManagement/assets/(?P<asset_id>\w+)/upgradeJob/?$",
        offering_views.UpgradeCollection(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/assetManagement/assets/product/(?P<product_id>\w+)/?$",
        offering_views.AssetEntryFromProduct(permitted_methods=("GET",)),
    ),
    url(
        r"^charging/api/assetManagement/assetTypes/?$",
        plugins_views.PluginCollection(permitted_methods=("GET",)),
    ),
    url(
        r"^charging/api/assetManagement/assetTypes/(?P<plugin_id>[\w -]+)/?$",
        plugins_views.PluginEntry(permitted_methods=("GET",)),
    ),
    url(
        r"^charging/api/assetManagement/chargePeriods/?$",
        admin_views.ChargePeriodCollection(permitted_methods=("GET",)),
    ),
    url(
        r"^charging/api/assetManagement/currencyCodes/?$",
        admin_views.CurrencyCodeCollection(permitted_methods=("GET",)),
    ),
    url(
        r"^charging/api/orderManagement/orders/?$",
        ordering_views.OrderingCollection(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/orderManagement/orders/completed/(?P<order_id>[^/]+)/?$",
        ordering_views.NotifyOrderCollection(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/orderManagement/orders/confirm/?$",
        charging_views.PaymentConfirmation(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/orderManagement/orders/refund/?$",
        charging_views.PaymentRefund(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/orderManagement/orders/preview/?$",
        charging_views.PaymentPreview(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/orderManagement/products/?$",
        ordering_views.InventoryCollection(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/orderManagement/products/renewJob/?$",
        ordering_views.RenovationCollection(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/orderManagement/products/unsubscribeJob/?$",
        ordering_views.UnsubscriptionCollection(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/orderManagement/accounting/?$",
        accounting_views.ServiceRecordCollection(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/orderManagement/accounting/refresh/?$",
        accounting_views.SDRRefreshCollection(permitted_methods=("POST",)),
    ),
    # url(
    #     r"^charging/api/reportManagement/created/?$",
    #     reports_views.ReportReceiver(permitted_methods=("POST",)),
    # ),
    url(
        r"^charging/api/revenueSharing/models/?$",
        rss_views.RevenueSharingModels(permitted_methods=("GET", "POST", "PUT")),
    ),
    url(
        r"^charging/api/revenueSharing/algorithms/?$",
        rss_views.RevenueSharingAlgorithms(permitted_methods=("GET",)),
    ),
    url(
        r"^charging/api/revenueSharing/settlement/?$",
        rss_views.Settlements(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/revenueSharing/settlement/reports/?$",
        rss_views.SettlementReports(permitted_methods=("GET",)),
    ),
    url(
        r"^charging/api/revenueSharing/cdrs/?$",
        rss_views.CDRs(permitted_methods=("GET",)),
    ),
    url(
        r"^charging/api/orderManagement/notify/?$",
        admin_views.NotificationCollection(permitted_methods=("POST",)),
    ),
    url(
        r"^charging/api/orderManagement/notify/config/?$",
        admin_views.NotificationConfigCollection(permitted_methods=("GET", "POST")),
    )
]
