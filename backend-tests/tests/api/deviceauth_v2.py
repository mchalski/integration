# Copyright 2018 Northern.tech AS
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        https://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5
from Crypto.Hash import SHA256
from base64 import b64encode, urlsafe_b64decode, urlsafe_b64encode
import json

import api.client

URL_MGMT = api.client.GATEWAY_URL + '/api/management/v2/devauth'
URL_AUTHSET_STATUS = '/devices/{did}/auth/{aid}/status'

URL_DEVICES = '/devices'
URL_DEVICE  = '/devices/{id}'
URL_DEVICES_COUNT = '/devices/count'

def preauth_req(id_data, pubkey):
    return {
        "identity_data": id_data,
        "pubkey": pubkey
    }

def req_status(status):
    return {'status': status}
