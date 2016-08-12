#!/usr/bin/env python
# encoding: utf-8
# tag all nodes as OSDs
# tag all unused storage as OSD data

import os
import requests
import sys

from collections import defaultdict
from optparse import OptionParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maas_base_client import MaasBaseClient

CLIENT_TAG = 'ansible_clients'
OSD_TAG = 'ansible_osds'
OSD_DATA_TAG = 'ansible_osd_data'
OSD_JOURNAL_TAG = 'ansible_osd_journal'


class MaasClient(MaasBaseClient):

    def tag_nodes(self, system_ids, tag, remove=False):
        url = '%s/tags/%s/?op=update_nodes' % (self._api_url, tag)
        op = 'remove' if remove else 'add'
        rq = requests.post(url, data={op: system_ids},
                           headers=self._auth())
        rq.raise_for_status()

    def tag_drive(self, drive_uri, tag, remove=False):
        drive_url = self._base_url + drive_uri
        params = {
            'tag': tag,
            'op': 'remove_tag' if remove else 'add_tag',
        }
        rq = requests.get(drive_url, params=params, headers=self._auth())
        try:
            rq.raise_for_status()
        except:
            print("failed to tag: %s" % drive_uri)
            raise

    def classify_nodes(self, nodes=None,
                       osd_tag=OSD_TAG,
                       client_tag=CLIENT_TAG,
                       storage_tag=OSD_DATA_TAG,
                       journal_tag=OSD_JOURNAL_TAG,
                       data_size_threshold=0,
                       remove=False):
        if not nodes:
            nodes = self.nodes()
        nodes_to_tag = defaultdict(list)
        drives_to_tag = defaultdict(list)
        data_size_threshold = data_size_threshold * 1024 * 1024 * 1024
        for node in nodes:
            drives = filter(lambda blk: blk['used_for'] == 'Unused',
                            node['physicalblockdevice_set'])
            if len(drives) == 0:
                nodes_to_tag[client_tag].append(node['system_id'])
            else:
                nodes_to_tag[osd_tag].append(node['system_id'])
                drives_to_tag[storage_tag].extend(
                    disk['resource_uri'] for disk in drives
                    if disk['size'] >= data_size_threshold)
                drives_to_tag[journal_tag].extend(
                    disk['resource_uri'] for disk in drives
                    if disk['size'] < data_size_threshold)
        for tag, node_ids in dict(nodes_to_tag).iteritems():
            self.tag_nodes(node_ids, tag, remove=remove)
        for tag, drives in drives_to_tag.iteritems():
            map(lambda drive_uri: self.tag_drive(drive_uri, tag, remove),
                drives)


def main():
    parser = OptionParser()
    parser.add_option('-m', '--maas-host', dest='maas_host')
    parser.add_option('-u', '--maas-user', dest='maas_user')
    parser.add_option('-t', '--osd-tag', dest='osd_tag')
    parser.add_option('-s', '--storage-tag', dest='storage_tag')
    parser.add_option('-j', '--journal-tag', dest='journal_tag')
    parser.add_option('-c', '--client-tag', dest='client_tag')
    parser.add_option('-T', '--data-size-threshold',
                      dest='data_size_threshold', type=int, default=0)
    parser.add_option('-U', '--untag', dest='clear_tags',
                      action='store_true', default=False)
    options, args = parser.parse_args()
    maas_client = MaasClient(host=options.maas_host, user=options.maas_user)
    maas_client.classify_nodes(
        osd_tag=options.osd_tag,
        storage_tag=options.storage_tag,
        client_tag=options.client_tag,
        journal_tag=options.journal_tag,
        data_size_threshold=options.data_size_threshold,
        remove=options.clear_tags,
    )


if __name__ == '__main__':
    main()
