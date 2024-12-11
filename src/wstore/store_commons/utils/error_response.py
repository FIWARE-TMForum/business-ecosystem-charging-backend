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

import json
from xml.dom.minidom import getDOMImplementation


def get_xml_response(request, mimetype, status_code, value, extra_content):
    dom = getDOMImplementation()
    if extra_content is None:
        extra_content = []
    if status_code >= 400:
        doc = dom.createDocument(None, "error", None)
    else:
        doc = dom.createDocument(None, "message", None)

    rootelement = doc.documentElement
    text = doc.createTextNode(value)
    rootelement.appendChild(text)
    errormsg = doc.toxml("utf-8")
    doc.unlink()

    return errormsg


def get_json_response(request, mimetype, status_code, message, extra_content):
    response = {}
    if extra_content is None:
        extra_content = []
    if status_code >= 400:
        response["result"] = "error"
        response["error"] = message
    else:
        response["result"] = "correct"
        response["message"] = message
        print("sssss")
        for name in extra_content:
            print(name)
            response[name] = extra_content[name]

    return json.dumps(response)


def get_unicode_response(request, mimetype, status_code, message, extra_content):
    response = ""
    if extra_content is None:
        extra_content = []
    if status_code >= 400:
        response += "Error: " + message
    else:
        response += "Correct: " + message

    return str(response)
