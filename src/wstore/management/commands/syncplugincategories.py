# -*- coding: utf-8 -*-

# Copyright (c) 2026 Future Internet Consulting and Development Solutions S. L.

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

"""Publish categories for packages installed before service catalog integration."""
from django.core.management.base import BaseCommand, CommandError

from wstore.asset_manager.resource_plugins.plugin_loader import PluginLoader
from wstore.models import ResourcePlugin


class Command(BaseCommand):
    help = "Create missing service categories for installed plugins"

    def handle(self, *args, **options):
        loader = PluginLoader()
        for plugin in ResourcePlugin.objects.all():
            try:
                category_id = loader.synchronize_plugin_category(plugin.plugin_id)
            except Exception as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(f"{plugin.plugin_id}: {category_id}")
