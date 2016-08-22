#!/usr/bin/env python
# encoding: utf-8
# deploy (or comission) nodes one by one

import json
import os
import requests
import sys
import time

from optparse import OptionParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maas_base_client import MaasBaseClient

NEW = 'New'
READY = 'Ready'
DEPLOYED = 'Deployed'
ALLOCATED = 'Allocated'


def node_state(node):
    return node['substatus_name']


class MaasClient(MaasBaseClient):

    def commission(self, system_id, **kwargs):
        url = '%s/nodes/%s/?op=commission' % (self._api_url, system_id)
        rq = requests.post(url, headers=self._auth())
        rq.raise_for_status()

    def _acquire(self, system_ids):
        url = '%s/nodes/?op=acquire' % self._api_url
        rq = requests.post(url, data={'nodes': system_ids},
                           headers=self._auth())
        rq.raise_for_status()
        for system_id in system_ids:
            self.wait_for(system_id, ALLOCATED, interval=3)

    def _deploy(self, system_id, **kwargs):
        url = '%s/nodes/%s/?op=start' % (self._api_url, system_id)
        rq = requests.post(url, data=kwargs, headers=self._auth())
        rq.raise_for_status()

    def deploy(self, system_id, **kwargs):
        self._acquire([system_id])
        self._deploy(system_id, **kwargs)

    def wait_for(self, system_id, state, interval=10):
        url = '%s/nodes/%s/' % (self._api_url, system_id)
        while True:
            rq = requests.get(url, headers=self._auth())
            rq.raise_for_status()
            node = json.loads(rq.text)
            if node_state(node) == state:
                return True
            print("waiting for node {0} {want_state} (now: {state})".
                  format(system_id, want_state=state, state=node_state(node)))
            time.sleep(interval)
        return False

    def serial_apply(self, action, initial_state, final_state, interval=10):
        nodes = (n for n in self.nodes() if node_state(n) == initial_state)
        for node in nodes:
            action(node)
            self.wait_for(node['system_id'], final_state, interval=interval)

    def commission_all(self, **kwargs):
        self.serial_apply(lambda node: self.commission, NEW, READY)

    def deploy_all(self, **kwargs):
        def deploy(node):
            system_id = node['system_id']
            hostname = node['hostname']
            print("start deploying %s (%s)" % (hostname, system_id))
            self.deploy(system_id, **kwargs)

        self.serial_apply(deploy, READY, DEPLOYED)


def main():
    parser = OptionParser()
    parser.add_option('-m', '--maas-host', dest='maas_host')
    parser.add_option('-u', '--maas-user', dest='maas_user')
    parser.add_option('-n', '--node', dest='node')
    parser.add_option('-r', '--release', dest='os_release')
    parser.add_option('-k', '--kernel', dest='kernel', default='hwe-x')
    options, args = parser.parse_args()
    maas_client = MaasClient(host=options.maas_host, user=options.maas_user)
    maas_client.deploy_all(distro_series=options.os_release,
                           hwe_kernel=options.kernel)


if __name__ == '__main__':
    main()
