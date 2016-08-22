#!/usr/bin/env python

import argparse
import json
import os
import re
import subprocess
import sys
import uuid

from math import ceil

import oauth.oauth as oauth
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MAAS_HOST = '10.40.0.2'
MAAS_USER = 'root'
MAAS_TOKEN = None
MAAS_DOMAIN = 'maas'
OSD_DATA_TAG = 'ansible_osd_data'
OSD_JOURNAL_TAG = 'ansible_osd_journal'
CLIENT_NET = 'client_net'
CLUSTER_NET = 'cluster_net'

# must match ceph-ansible variables
OSD_DATA_DEVICES_KEY = 'devices'
OSD_JOURNAL_DEVICES_KEY = 'raw_journal_devices'


class Inventory(object):
    def __init__(self, maas_api_url, maas_token):
        self.maas_api = maas_api_url
        self.token = maas_token
        self.public_net = CLIENT_NET
        self.cluster_net = CLUSTER_NET

    def _auth(self):
        consumer_key, key, secret = self.token.split(':')
        resource_token = oauth.OAuthToken(key, secret)
        consumer_token = oauth.OAuthConsumer(consumer_key, '')
        oauth_request = oauth.OAuthRequest.from_consumer_and_token(
            consumer_token,
            token=resource_token,
            http_url=self.maas_api,
            parameters={
                'auth_nonce': uuid.uuid4().get_hex(),
            },
        )
        oauth_request.sign_request(oauth.OAuthSignatureMethod_PLAINTEXT(),
                                   consumer_token,
                                   resource_token)
        headers = oauth_request.to_header()
        return headers

    def _node_data(self, node):
        data = {
            'mac_address': node['macaddress_set'][0]['mac_address'],
            'system_id': node['system_id'],
            'power_type': node['power_type'],
            'os': node['osystem'],
            'os_release': node['distro_series'],
        }
        data.update(self._node_drives_by_tag(node))
        return {node['hostname']: data}

    def _node_drives_by_tag(self, node,
                            osd_tag=OSD_DATA_TAG,
                            journal_tag=OSD_JOURNAL_TAG):
        all_drives = node['physicalblockdevice_set']
        devices = [blk['id_path'] for blk in all_drives
                   if osd_tag in blk['tags']]
        journal_devices = [blk['id_path'] for blk in all_drives
                           if journal_tag in blk['tags']]
        osds_count = len(devices)
        journals_count = len(journal_devices)
        if (journals_count > 0) and (journals_count < osds_count):
            osds_per_journal = int(ceil(float(osds_count) / journals_count))
            # list each journal device N times so ceph-ansible will partition
            # each journal drive for N OSDs
            journal_devices *= osds_per_journal
            # truncate the journals list so there's exactly 1 entry per an OSD
            journal_devices = journal_devices[:osds_count]
        elif (journals_count > 0) and (journals_count > osds_count):
            # got more journals than OSDs? That's strange, but anyway:
            # truncate the journals list so there's exactly 1 entry per an OSD
            journal_devices = journal_devices[:osds_count]

        if (osds_count == 0) and (journals_count == 0):
            return {}
        else:
            return {
                OSD_DATA_DEVICES_KEY: devices,
                OSD_JOURNAL_DEVICES_KEY: journal_devices,
            }

    def host(self):
        return {}

    def tags(self):
        url = '%s/tags/?op=list' % self.maas_api.rstrip()
        rq = requests.get(url, headers=self._auth())
        rq.raise_for_status()
        ret = json.loads(rq.text)
        matcher = re.compile(r'ansible_')
        return [tag['name'] for tag in
                filter(lambda t: re.match(matcher, t['name']), ret)]

    def _nodes_by_role(self):
        ret = {}
        for tag in self.tags():
            url = '%s/tags/%s/?op=nodes' % (self.maas_api, tag)
            # ansible_foo => foo
            group_name = tag.partition('_')[2]
            rq = requests.get(url, headers=self._auth())
            rq.raise_for_status()
            nodes = json.loads(rq.text)
            group_vars = {
                'ansible_user': 'ubuntu',
            }
            group_vars.update(self._nodes_ifaces_by_role(nodes, group_name))
            ret[group_name] = {
                'hosts': [node['hostname'] for node in nodes],
                'vars': group_vars,
            }
        return ret

    def inventory(self):
        ansible = self._nodes_by_role()
        hostvars = {
            '_meta': {
                'hostvars': {}
            }
        }
        for node in self.nodes():
            if not node['tag_names']:
                continue
            hostvars['_meta']['hostvars'].update(self._node_data(node))

        result = ansible.copy()
        result.update(hostvars)
        return result

    def _get_interfaces_by_fabric(self, node):
        ret = {}
        for iface in node['interface_set']:
            for link in iface['links']:
                fabric = link['subnet']['vlan']['fabric']
                ret[fabric] = {
                    'cidr': link['subnet']['cidr'],
                    'name': iface['name'],
                }
        return ret

    def _nodes_ifaces_by_role(self, nodes, nodes_role):
        if len(nodes) == 0:
            return {}
        ifaces_by_role = self._get_interfaces_by_fabric(nodes[0])
        if not self.public_net in ifaces_by_role:
            return {}
        if any(self._get_interfaces_by_fabric(node) != ifaces_by_role
               for node in nodes):
            return {}
        ret = {
            'public_network': ifaces_by_role[self.public_net]['cidr'],
        }
        if nodes_role == 'mons':
            ret['monitor_interface'] = ifaces_by_role[self.public_net]['name']
        if nodes_role == 'osds':
            ret['cluster_network'] = ifaces_by_role[self.cluster_net]['cidr']
        return ret

    def nodes(self):
        url = '%s/nodes/?op=list' % self.maas_api
        rq = requests.get(url, headers=self._auth())
        rq.raise_for_status()
        _nodes = json.loads(rq.text)
        return _nodes


def get_maas_token(maas_host=MAAS_HOST, maas_user=MAAS_USER):
    cmd = [
        'ssh', 'ubuntu@%s' % maas_host,
        'sudo', 'maas-region-admin', 'apikey',
        '--username=%s' % maas_user,
    ]
    token = subprocess.check_output(cmd).strip()
    return token


def main(maas_host=MAAS_HOST, maas_token=None):
    maas_api_url = 'http://%s:5240/MAAS/api/1.0' % maas_host
    if maas_token is None:
        maas_token = get_maas_token(maas_host=maas_host)

    parser = argparse.ArgumentParser(
        description='Produce an ansible inventory from MAAS')
    parser.add_argument('--list', action='store_true',
                        help='list nodes by tag')
    parser.add_argument('--host', action='store_true',
                        help='get host specific variables')
    parser.add_argument('--nodes', action='store_true',
                        help='list all nodes known to MAAS')
    parser.add_argument('--ssh-keys', action='store_true',
                        help="update ~/.ssh/known_hosts with nodes' host keys")
    args = parser.parse_args()

    inventory = Inventory(maas_api_url, maas_token)
    if args.list:
        data = inventory.inventory()
    elif args.nodes:
        data = inventory.nodes()
    elif args.host:
        data = inventory.host()
    elif args.ssh_keys:
        from maas_tools.fetch_ssh_keys import update_ssh_keys
        data = update_ssh_keys(maas_host=maas_host, maas_user=MAAS_USER)
    else:
        sys.exit(1)
    print(json.dumps(data, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
