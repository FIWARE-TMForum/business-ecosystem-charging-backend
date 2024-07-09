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

from functools import wraps
from logging import getLogger
from shutil import rmtree
from wstore.asset_manager import service_category_imp

logger = getLogger("wstore.default_logger")

#Fijarse

def installPluginRollback(func):
    class Logger:
        _state = {}

        def get_state(self):
            return self._state

        def log_action(self, action, value):
            self._state[action] = value

    @wraps(func)
    def wrapper(self, path, rb_log=None):
        try:
            rb_log = Logger()
            result = func(self, path, rb_log=rb_log)
        except Exception as e:

            ##############################
            # Remove plugin from API if existing
            if "API" in rb_log.get_state():
                s_cat = service_category_imp.ServiceCategory()
                s_cat.get_service_category(rb_log.get_state()["API"])
            ##############################

            # Remove directory if existing
            if "PATH" in rb_log.get_state():
                logger.debug("Removing path")
                rmtree(rb_log.get_state()["PATH"], True)

            if "MODEL" in rb_log.get_state():
                logger.debug("Deleting model")
                rb_log.get_state()["MODEL"].delete()

            # Raise the exception
            raise (e)
        return result

    return wrapper
