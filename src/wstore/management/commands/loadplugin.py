# -*- coding: utf-8 -*-

# Copyright (c) 2015 CoNWeT Lab., Universidad Politécnica de Madrid
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


from django.core.management.base import BaseCommand, CommandError

from wstore.asset_manager.resource_plugins.plugin_loader import PluginLoader


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("args", nargs="*")

    def handle(self, *args, **options):
        """
        Loads a new resource plugin
        """

        # Check arguments
        if len(args) != 1:
            raise CommandError("Error: Please specify the path to the plugin package")

        plugin_id = None
        try:
            path = args[0]
            # Load plugin
            plugin_loader = PluginLoader()
            plugin_id = plugin_loader.install_plugin(path)
        except Exception as e:
            raise CommandError(str(e))

        self.stdout.write("Your plugin has been loaded with id: " + plugin_id + "\n")
        self.stdout.write("If you want to retrieve the existing plugins, execute: python manage.py listplugins\n")
