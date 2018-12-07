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
import pytest
import random

from api.client import ApiClient
from common import mongo, clean_mongo
from infra.cli import CliUseradm, CliDeviceauth, CliTenantadm
import api.deviceauth as deviceauth_v1
import api.deviceauth_v2 as deviceauth_v2
import api.useradm as useradm
import api.tenantadm as tenantadm
import api.deployments as deployments
import util.crypto
from common import User, Device, Tenant, \
        create_user, create_tenant, create_tenant_user, \
        create_random_device, create_device

@pytest.yield_fixture(scope='function')
def clean_migrated_mongo(clean_mongo):
    deviceauth_cli = CliDeviceauth()
    useradm_cli = CliUseradm()

    deviceauth_cli.migrate()
    useradm_cli.migrate()

    yield clean_mongo

@pytest.yield_fixture(scope='function')
def clean_migrated_mongo_mt(clean_mongo):
    deviceauth_cli = CliDeviceauth()
    useradm_cli = CliUseradm()
    for t in ['tenant1', 'tenant2']:
        deviceauth_cli.migrate(t)
        useradm_cli.migrate(t)

    yield clean_mongo

@pytest.yield_fixture(scope="function")
def user(clean_migrated_mongo):
    yield create_user('user-foo@acme.com', 'correcthorse')

@pytest.yield_fixture(scope="function")
def devices(clean_migrated_mongo):
    devauthd = ApiClient(deviceauth_v1.URL_DEVICES)

    devices = []

    for _ in range(5):
        d = create_random_device()
        devices.append(d)

    yield devices

@pytest.yield_fixture(scope="function")
def tenants_users(clean_migrated_mongo_mt):
    cli = CliTenantadm()
    api = ApiClient(tenantadm.URL_INTERNAL)

    names = ['tenant1', 'tenant2']
    tenants=[]

    for n in names:
        tenants.append(create_tenant(n))

    for t in tenants:
        for i in range(2):
            user = create_tenant_user(i, t)
            t.users.append(user)

    yield tenants

@pytest.yield_fixture(scope="function")
def tenants_users_devices(clean_migrated_mongo_mt, tenants_users):
    for t in tenants_users:
        for _ in range(5):
            dev = create_random_device(t.tenant_token)
            t.devices.append(dev)

    yield tenants_users

class TestPreauthBase:
    def do_test_ok(self, user, tenant_token=''):
        useradmm = ApiClient(useradm.URL_MGMT)
        devauthm = ApiClient(deviceauth_v2.URL_MGMT)
        devauthd = ApiClient(deviceauth_v1.URL_DEVICES)

        # log in user
        r = useradmm.call('POST',
                          useradm.URL_LOGIN,
                          auth=(user.name, user.pwd))
        assert r.status_code == 200

        utoken = r.text

        # preauth device
        priv, pub = util.crypto.rsa_get_keypair()
        id_data = {'mac': 'pretenditsamac'}
        body = deviceauth_v2.preauth_req(
                    id_data,
                    pub)
        r = devauthm.with_auth(utoken).call('POST',
                                            deviceauth_v2.URL_DEVICES,
                                            body)
        assert r.status_code == 201

        # device appears in device list
        r = devauthm.with_auth(utoken).call('GET',
                                            deviceauth_v2.URL_DEVICES)
        assert r.status_code == 200
        api_devs = r.json()

        assert len(api_devs) == 1
        api_dev = api_devs[0]

        assert api_dev['status'] == 'preauthorized'
        assert api_dev['identity_data'] == id_data
        assert len(api_dev['auth_sets']) == 1
        aset = api_dev['auth_sets'][0]

        assert aset['identity_data'] == id_data
        assert util.crypto.rsa_compare_keys(aset['pubkey'], pub)
        assert aset['status'] == 'preauthorized'

        # actual device can obtain auth token
        body, sighdr = deviceauth_v1.auth_req(id_data,
                                              pub,
                                              priv,
                                              tenant_token)

        r = devauthd.call('POST',
                          deviceauth_v1.URL_AUTH_REQS,
                          body,
                          headers=sighdr)

        assert r.status_code == 200

    def do_test_fail_duplicate(self, user, devices):
        useradmm = ApiClient(useradm.URL_MGMT)
        devauthm = ApiClient(deviceauth_v2.URL_MGMT)

        # log in user
        r = useradmm.call('POST',
                          useradm.URL_LOGIN,
                          auth=(user.name, user.pwd))
        assert r.status_code == 200

        utoken = r.text

        # preauth duplicate device
        priv, pub = util.crypto.rsa_get_keypair()
        id_data = devices[0].id_data
        body = deviceauth_v2.preauth_req(
                    id_data,
                    pub)
        r = devauthm.with_auth(utoken).call('POST',
                                            deviceauth_v2.URL_DEVICES,
                                            body)
        assert r.status_code == 409

        # device list is unmodified
        r = devauthm.with_auth(utoken).call('GET',
                                            deviceauth_v2.URL_DEVICES)
        assert r.status_code == 200
        api_devs = r.json()

        assert len(api_devs) == len(devices)

        # existing device has no new auth sets
        existing = [d for d in api_devs if d['identity_data'] == id_data]
        assert len(existing) == 1
        existing = existing[0]

        assert len(existing['auth_sets']) == 1
        aset = existing['auth_sets'][0]
        assert util.crypto.rsa_compare_keys(aset['pubkey'], devices[0].pubkey)
        assert aset['status'] == 'pending'


class TestPreauth(TestPreauthBase):
    def test_ok(self, user):
        self.do_test_ok(user)

    def test_fail_duplicate(self, user, devices):
        self.do_test_fail_duplicate(user, devices)

    def test_fail_bad_request(self, user):
        useradmm = ApiClient(useradm.URL_MGMT)
        devauthm = ApiClient(deviceauth_v2.URL_MGMT)

        # log in user
        r = useradmm.call('POST',
                          useradm.URL_LOGIN,
                          auth=(user.name, user.pwd))
        assert r.status_code == 200

        utoken = r.text

        # id data not json
        priv, pub = util.crypto.rsa_get_keypair()
        id_data = '{\"mac\": \"foo\"}'
        body = deviceauth_v2.preauth_req(
                    id_data,
                    pub)
        r = devauthm.with_auth(utoken).call('POST',
                                            deviceauth_v2.URL_DEVICES,
                                            body)
        assert r.status_code == 400

        # not a valid key
        id_data = {'mac': 'foo'}
        body = deviceauth_v2.preauth_req(
                    id_data,
                    'not a public key')
        r = devauthm.with_auth(utoken).call('POST',
                                            deviceauth_v2.URL_DEVICES,
                                            body)
        assert r.status_code == 400

class TestPreauthMultitenant(TestPreauthBase):
    def test_ok(self, tenants_users):
        user = tenants_users[0].users[0]

        self.do_test_ok(user, tenants_users[0].tenant_token)

        # check other tenant's devices unmodified
        user1 = tenants_users[1].users[0]
        devs1 = tenants_users[1].devices
        self.verify_devices_unmodified(user1, devs1)

    def test_fail_duplicate(self, tenants_users_devices):
        user = tenants_users_devices[0].users[0]
        devices = tenants_users_devices[0].devices

        self.do_test_fail_duplicate(user, devices)

        # check other tenant's devices unmodified
        user1 = tenants_users_devices[1].users[0]
        devs1 = tenants_users_devices[1].devices
        self.verify_devices_unmodified(user1, devs1)

    def verify_devices_unmodified(self, user, in_devices):
        devauthm = ApiClient(deviceauth_v2.URL_MGMT)
        useradmm = ApiClient(useradm.URL_MGMT)

        r = useradmm.call('POST',
                          useradm.URL_LOGIN,
                          auth=(user.name, user.pwd))
        assert r.status_code == 200

        utoken = r.text

        r = devauthm.with_auth(utoken).call('GET',
                                            deviceauth_v2.URL_DEVICES)
        assert r.status_code == 200
        api_devs = r.json()

        assert len(api_devs) == len(in_devices)
        for ad in api_devs:
            assert ad['status'] == 'pending'

            orig_device = [d for d in in_devices if d.id_data == ad['identity_data']]
            assert len(orig_device) == 1
            orig_device = orig_device[0]

            assert len(ad['auth_sets']) == 1
            aset = ad['auth_sets'][0]
            assert util.crypto.rsa_compare_keys(aset['pubkey'], orig_device.pubkey)


class DevWithAuthsets:
    def __init__(self, id_data, id, status):
        self.id = id
        self.id_data = id_data
        self.status = status
        self.authsets = []

    def __repr__(self):
        ret = 'ID {} ID_DATA {} AUTHSETS: \n'.format(self.id, self.id_data)
        for a in self.authsets:
            ret += '{}\n'.format(a)

        return ret


class Authset:
    def __init__(self, id, id_data, pubkey, privkey, status):
        self.id = id
        self.id_data = id_data
        self.pubkey = pubkey
        self.privkey = privkey
        self.status = status

    def __repr__(self):
        return 'ID {} ID_DATA {} PUBKEY {}\n'.format(self.id, self.id_data, self.pubkey)


def get_device_by_id_data(id_data, utoken):
    devauthm = ApiClient(deviceauth_v2.URL_MGMT)
    r = devauthm.with_auth(utoken).call('GET',
                                        deviceauth_v2.URL_DEVICES)
    assert r.status_code == 200
    api_devs = r.json()

    found = [d for d in api_devs if d['identity_data']==id_data]
    assert len(found) == 1

    return found[0]

def change_authset_status(did, aid, status, utoken):
    devauthm = ApiClient(deviceauth_v2.URL_MGMT)
    r = devauthm.with_auth(utoken).call('PUT',
                                   deviceauth_v2.URL_AUTHSET_STATUS,
                                   deviceauth_v2.req_status(status),
                                   path_params={'did': did, 'aid': aid })
    assert r.status_code == 204


@pytest.yield_fixture(scope="function")
def devs_authsets(user):
    """ create a good number of devices, some with >1 authsets, with different statuses.
        returns DevWithAuthsets objects."""

    useradmm = ApiClient(useradm.URL_MGMT)

    # log in user
    r = useradmm.call('POST',
                      useradm.URL_LOGIN,
                      auth=(user.name, user.pwd))
    assert r.status_code == 200

    utoken = r.text

    devices = []

    # some vanilla 'pending' devices, single authset
    for _ in range(5):
        dev = make_pending_device(utoken, 1)
        devices.append(dev)

    # some pending devices with > 1 authsets
    for i in range(2):
        dev = make_pending_device(utoken, 3)
        devices.append(dev)

    # some 'accepted' devices, single authset
    for _ in range(3):
        dev = make_accepted_device(utoken, 1)
        devices.append(dev)

    # some 'accepted' devices with >1 authsets
    for _ in range(2):
        dev = make_accepted_device(utoken, 3)
        devices.append(dev)

    # some rejected devices
    for _ in range(2):
        dev = make_rejected_device(utoken, 3)
        devices.append(dev)

    # preauth'd devices
    for i in range(2):
        dev = make_preauthd_device(utoken)
        devices.append(dev)

    yield devices

def rand_id_data():
    mac = ":".join(["{:02x}".format(random.randint(0x00, 0xFF), 'x') for i in range(6)])
    sn = "".join(["{}".format(random.randint(0x00, 0xFF)) for i in range(6)])

    return {'mac': mac, 'sn': sn}

def make_pending_device(utoken, num_auth_sets=1):
    id_data = rand_id_data()
    keys = []

    for i in range(num_auth_sets):
        priv, pub = util.crypto.rsa_get_keypair()
        keys.append((priv, pub))

    for priv, pub in keys:
        new_set = create_device(id_data, pub, priv)

    api_dev = get_device_by_id_data(id_data, utoken)
    assert len(api_dev['auth_sets']) == num_auth_sets

    dev = DevWithAuthsets(id_data, api_dev['id'], 'pending')

    # gotcha: authsets not guaranteed to be returned in the order of insertion
    # rely on the order in the api when preparing reference data
    for aset in api_dev['auth_sets']:
        keypair = [k for k in keys if util.crypto.rsa_compare_keys(k[1], aset['pubkey'])]
        assert len(keypair) == 1
        keypair = keypair[0]

        dev.authsets.append(Authset(aset['id'], id_data, keypair[1], keypair[0], 'pending'))

    return dev

def make_accepted_device(utoken, num_auth_sets=1, num_accepted=1):
    dev = make_pending_device(utoken, num_auth_sets)

    api_dev = get_device_by_id_data(dev.id_data, utoken)

    for i in range(num_accepted):
        aset_id = api_dev['auth_sets'][i]['id']
        change_authset_status(api_dev['id'], aset_id, 'accepted', utoken)

        dev.authsets[i].status = 'accepted'

    dev.status = 'accepted'

    return dev

def make_rejected_device(utoken, num_auth_sets=1):
    dev = make_pending_device(utoken, num_auth_sets)

    api_dev = get_device_by_id_data(dev.id_data, utoken)

    for i in range(num_auth_sets):
        aset_id = api_dev['auth_sets'][i]['id']
        change_authset_status(api_dev['id'], aset_id, 'rejected', utoken)

        dev.authsets[i].status = 'rejected'

    dev.status = 'rejected'

    return dev

def make_preauthd_device(utoken):
    devauthm = ApiClient(deviceauth_v2.URL_MGMT)

    priv, pub = util.crypto.rsa_get_keypair()
    id_data = rand_id_data()

    body = deviceauth_v2.preauth_req(
                id_data,
                pub)
    r = devauthm.with_auth(utoken).call('POST',
                                        deviceauth_v2.URL_DEVICES,
                                        body)
    assert r.status_code == 201

    api_dev = get_device_by_id_data(id_data, utoken)
    assert len(api_dev['auth_sets']) == 1
    aset = api_dev['auth_sets'][0]

    dev = DevWithAuthsets(id_data, api_dev['id'], 'preauthorized')
    dev.authsets.append(Authset(aset['id'], id_data, pub, priv, 'preauthorized'))

    dev.status = 'preauthorized'

    return dev


class TestDeviceMgmt:
    def test_ok_get_devices(self, devs_authsets, user):
        da = ApiClient(deviceauth_v2.URL_MGMT)
        ua = ApiClient(useradm.URL_MGMT)

        # log in user
        r = ua.call('POST',
                    useradm.URL_LOGIN,
                    auth=(user.name, user.pwd))
        assert r.status_code == 200

        utoken = r.text

        # test cases
        for status, page, per_page in [
                (None, None, None),
                ('pending', None, None),
                ('accepted', None, None),
                ('rejected', None, None),
                ('preauthorized', None, None),
                (None, 1, 10),
                (None, 3, 10),
                (None, 2, 5),
                ('accepted', 1, 4),
                ('accepted', 2, 4),
                ('accepted', 5, 2),
                ('pending', 2, 2)]:
            qs_params = {}

            if status is not None:
                qs_params['status'] = status
            if page is not None:
                qs_params['page'] = page
            if per_page is not None:
                qs_params['per_page'] = per_page

            r = da.with_auth(utoken).call('GET',
                                      deviceauth_v2.URL_DEVICES,
                                      qs_params=qs_params)
            assert r.status_code == 200
            api_devs = r.json()

            ref_devs = self._filter_and_page_devs(devs_authsets, page=page, per_page=per_page, status=status)

            self._compare_devs(ref_devs, api_devs)

    def test_get_device(self, devs_authsets, user):
        da = ApiClient(deviceauth_v2.URL_MGMT)
        ua = ApiClient(useradm.URL_MGMT)

        # log in user
        r = ua.call('POST',
                    useradm.URL_LOGIN,
                    auth=(user.name, user.pwd))
        assert r.status_code == 200

        utoken = r.text

        # existing devices
        for dev in devs_authsets:
            r = da.with_auth(utoken).call('GET',
                                      deviceauth_v2.URL_DEVICE,
                                      path_params={'id': dev.id})
            assert r.status_code == 200
            api_dev = r.json()

            self._compare_dev(dev, api_dev)

        # non-existent devices
        for id in ['foo', 'bar']:
            r = da.with_auth(utoken).call('GET',
                                      deviceauth_v2.URL_DEVICE,
                                      path_params={'id': id})
            assert r.status_code == 404

    def test_delete_device_ok(self, devs_authsets, user):
        devapim = ApiClient(deviceauth_v2.URL_MGMT)
        devapid = ApiClient(deviceauth_v1.URL_DEVICES)
        userapi = ApiClient(useradm.URL_MGMT)
        depapi = ApiClient(deployments.URL_DEVICES)

        # log in user
        r = userapi.call('POST',
                    useradm.URL_LOGIN,
                    auth=(user.name, user.pwd))
        assert r.status_code == 200

        utoken = r.text

        # decommission a pending device
        dev_pending = self._filter_and_page_devs(devs_authsets, status='pending')[0]
        r = devapim.with_auth(utoken).call('DELETE',
                                  deviceauth_v2.URL_DEVICE,
                                  path_params={'id': dev_pending.id})
        assert r.status_code == 204

        # only verify the device is gone
        r = devapim.with_auth(utoken).call('GET',
                                  deviceauth_v2.URL_DEVICE,
                                  path_params={'id': dev_pending.id})
        assert r.status_code == 404

        # log in an accepted device
        dev_acc = self._filter_and_page_devs(devs_authsets, status='accepted')[0]

        body, sighdr = deviceauth_v1.auth_req(dev_acc.id_data,
                                        dev_acc.authsets[0].pubkey,
                                        dev_acc.authsets[0].privkey)

        r = devapid.call('POST',
                         deviceauth_v1.URL_AUTH_REQS,
                         body,
                         headers=sighdr)
        assert r.status_code == 200
        dtoken = r.text

        # decommission the accepted device
        r = devapim.with_auth(utoken).call('DELETE',
                                   deviceauth_v2.URL_DEVICE,
                                   path_params={'id': dev_acc.id})
        assert r.status_code == 204

        # verify the device lost access
        r = depapi.with_auth(dtoken).call('GET',
                                   deployments.URL_NEXT,
                                   qs_params={'device_type': 'foo',
                                              'artifact_name': 'bar'})
        assert r.status_code == 401

        # verify the device is gone
        r = devapim.with_auth(utoken).call('GET',
                                   deviceauth_v2.URL_DEVICE,
                                   path_params={'id': dev_acc.id})
        assert r.status_code == 404

    def test_delete_device_not_found(self, devs_authsets, user):
        ua = ApiClient(useradm.URL_MGMT)
        da = ApiClient(deviceauth_v2.URL_MGMT)

        # log in user
        r = ua.call('POST',
                    useradm.URL_LOGIN,
                    auth=(user.name, user.pwd))
        assert r.status_code == 200

        utoken = r.text

        # try delete
        r = da.with_auth(utoken).call('DELETE',
                                   deviceauth_v2.URL_DEVICE,
                                   path_params={'id': 'foo'})
        assert r.status_code == 404

        # check device list unmodified
        r = da.with_auth(utoken).call('GET',
                                  deviceauth_v2.URL_DEVICES)

        assert r.status_code == 200
        api_devs = r.json()

        self._compare_devs(devs_authsets, api_devs)

    def test_device_count(self, devs_authsets, user):
        ua = ApiClient(useradm.URL_MGMT)
        da = ApiClient(deviceauth_v2.URL_MGMT)

        # log in user
        r = ua.call('POST',
                    useradm.URL_LOGIN,
                    auth=(user.name, user.pwd))
        assert r.status_code == 200

        utoken = r.text

        # test cases: successful counts
        for status in [None, \
                    'pending', \
                    'accepted', \
                    'rejected', \
                    'preauthorized']:
            qs_params={}
            if status is not None:
                qs_params={'status': status}

            r = da.with_auth(utoken).call('GET',
                                          deviceauth_v2.URL_DEVICES_COUNT,
                                          qs_params=qs_params)
            assert r.status_code == 200
            count = r.json()

            ref_devs = self._filter_and_page_devs(devs_authsets, status=status)

            ref_count = len(ref_devs)

            assert ref_count == count['count']

        # fail: bad request
        r = da.with_auth(utoken).call('GET',
                                      deviceauth_v2.URL_DEVICES_COUNT,
                                      qs_params={'status': 'foo'})
        assert r.status_code == 400

    def _compare_devs(self, devs, api_devs):
        assert len(api_devs) == len(devs)

        for i in range(len(api_devs)):
            self._compare_dev(devs[i], api_devs[i])

    def _compare_dev(self, dev, api_dev):
            assert api_dev['id'] == dev.id
            assert api_dev['identity_data'] == dev.id_data
            assert api_dev['status'] == dev.status

            assert len(api_dev['auth_sets']) == len(dev.authsets)

            for i in range(len(api_dev['auth_sets'])):
                aset = dev.authsets[i]
                api_aset = api_dev['auth_sets'][i]

                self._compare_aset(aset, api_aset)

    def _compare_aset(self, authset, api_authset):
            assert authset.id == api_authset['id']
            assert authset.id_data == api_authset['identity_data']
            assert util.crypto.rsa_compare_keys(authset.pubkey, api_authset['pubkey'])
            assert authset.status == api_authset['status']

    def _filter_and_page_devs(self, devs, page=None, per_page=None, status=None):
        if status is not None:
            devs = [d for d in devs if d.status==status]

        if page is None:
            page = 1

        if per_page is None:
            per_page = 20

        lo = (page-1)*per_page
        hi = lo + per_page

        return devs[lo:hi]
