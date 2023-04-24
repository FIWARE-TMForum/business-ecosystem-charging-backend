# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2021 Future Internet Consulting and Development Solutions S. L.

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


from djongo import models


class ReportsPayout(models.Model):
    _id = models.ObjectIdField()
    reports = models.JSONField(default=[])  # List
    payout_id = models.CharField(max_length=15)
    status = models.CharField(max_length=15)


class ReportSemiPaid(models.Model):
    _id = models.ObjectIdField()
    report = models.IntegerField()
    failed = models.JSONField(default=[])  # List
    success = models.JSONField(default=[])  # List
    errors = models.JSONField(default={})  # Dict
