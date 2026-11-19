# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid

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

import re

ID_REGEX = re.compile(r"^[\w -]+$")
# Extensions are optional; exclude path separators, URL delimiters and controls.
FILE_REGEX = re.compile(r"\A(?!\.{1,2}\Z)(?=.*\S)[^/\\#?%\x00-\x1f\x7f-\x9f]+\Z")


def is_valid_id(id_):
    return ID_REGEX.match(id_)


def is_valid_file(file_name):
    return FILE_REGEX.match(file_name)
