# -*- coding: utf-8 -*-

# Copyright (c) 2015 CoNWeT Lab., Universidad Politécnica de Madrid
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

from functools import wraps
from logging import getLogger
from shutil import rmtree

logger = getLogger("wstore.default_logger")


class RollbackLog:
    def __init__(self):
        self._actions = []

    def log_action(self, action, value):
        self._actions.append((action, value))

    def rollback(self):
        for action, value in reversed(self._actions):
            try:
                if action == "PATH":
                    rmtree(value, True)
                elif action == "MODEL":
                    if value.pk is not None:
                        value.delete()
                else:
                    value()
            except Exception:
                logger.exception("Plugin rollback failed for %s; reconciliation required", action)


def installPluginRollback(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        rb_log = RollbackLog()
        kwargs["rb_log"] = rb_log
        try:
            return func(self, *args, **kwargs)
        except Exception:
            rb_log.rollback()
            raise

    return wrapper
