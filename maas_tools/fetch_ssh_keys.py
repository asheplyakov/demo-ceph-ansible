#!/usr/bin/env python
# encoding: utf-8
# Collect SSH public keys of nodes managed by MAAS

import json
import os
import sys

from optparse import OptionParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maas_base_client import MaasBaseClient as MaasClient
from sshutils import (
    get_ssh_host_key,
    update_ssh_known_hosts,
)


class Node(object):
    def __init__(self, thedict):
        self._d = thedict

    @property
    def ip_addresses(self):
        ips = sorted(link['ip_address']
                     for iface in self._d['interface_set']
                     for link in iface['links']
                     if link.get('ip_address') is not None)
        return list(ips)

    @property
    def hostname(self):
        return self._d['hostname']


def update_node_ssh_key(node):
    ssh_key = get_ssh_host_key(node.ip_addresses, node.hostname)
    update_ssh_known_hosts(node.ip_addresses, node.hostname, ssh_key=ssh_key)
    return {
        node.hostname: ssh_key,
    }


def update_ssh_keys(maas_client,
                    maas_host=None, maas_user=None, maas_token=None):
    if maas_client is None:
        maas_client = MaasClient(host=maas_host, user=maas_user,
                                 token=maas_token)
    ssh_keys = {}
    for _node in maas_client.nodes():
        node = Node(_node)
        ssh_keys.update(update_node_ssh_key(node))
    return ssh_keys


def main():
    parser = OptionParser()
    parser.add_option('-m', '--maas-host', dest='maas_host')
    parser.add_option('-u', '--maas-user', dest='maas_user')
    options, args = parser.parse_args()
    maas_client = MaasClient(host=options.maas_host, user=options.maas_user)
    data = update_ssh_keys(maas_client)
    print(json.dumps(data, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
