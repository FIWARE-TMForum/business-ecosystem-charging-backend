# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid

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


from django.core.management.base import BaseCommand, CommandError

from wstore.models import ResourcePlugin


class Command(BaseCommand):
    def handle(self, *args, **options):
        """
        List the existing plugins in the system
        """

        try:
            plugins = ResourcePlugin.objects.all()
            for plugin in plugins:
                self.stdout.write("Name: " + plugin.name + " type: " + plugin.type + " id: " + plugin.plugin_id + "\n")

        except Exception as e:
            raise CommandError(str(e))
