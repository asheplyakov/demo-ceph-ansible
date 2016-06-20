Preliminaries
=============

Lab description
---------------

* (virtual) hardware: a handful of libvirt/kvm VMs:
  - 3 OSD nodes having 3 (virtual) hard drives per a node
  - 3 monitor nodes
  - 1 radosgw node
  - 1 client node
* software: Ubuntu 14.04, ceph 10.2.1 (jewel), `self built packages`_
* ansible version: 2.1.0 from *ppa:ansible/ansible*

.. _self built packages: http://asheplyakov.srt.mirantis.net/Public/repos/ceph
.. _ceph-ansible: http://github.com/ceph/ceph-ansible

Preparation
-----------

* Setup 8 VMs running Ubuntu 14.04 (cloud image)
* Install ansible on the host::

    sudo apt-add-repository ppa:ansible/ansible
    sudo apt-get update
    sudo apt-get install -y ansible


Deployment
==========

Cluster configuration
---------------------

Mandatory and important settings:

* ``group_vars/all``

  - enable ``cephx`` authentication::

      cephx: true

  - use filestore, set journal size to 3 GB::

      osd_objectstore: filestore
      journal_size: 3072

  - pools' settings:: 

      pool_default_size: 3
      pool_default_min_size: 2
      pool_default_pg_num: 128
      pool_default_pgp_num: 128

  - network settings::
    
      public_network: 10.253.0.0/24
      monitor_interface: eth0

    Every node has a single (virtual) NIC, hence no separate cluster network.

  - client settings: specify rbd features compatible with rbd client included in
    Linux kernel 3.13.x (the default kernel version shipped with Ubuntu 14.04)::

      ceph_conf_overrides:
        client:
          rbd default features: 3

  - tell ceph-ansible to *not* touch APT configuration::

      ceph_origin: 'distro'

  - radosgw and ``civetweb`` settings: ``radosgw_civetweb_bind_ip`` *must*
    be specified to avoid ansible failure::

      radosgw_frontend: civetweb
      radosgw_civetweb_bind_ip: 0.0.0.0
      radosgw_civetweb_port: 8080

* ``group_vars/osds``

  - put all journals to the same drive (presumably SSD)::

      raw_multi_journal: true

  - set the actual data and journal devices on a per node basis.
    ``host_vars/saceph-osd1.vm.ceph.asheplyakov``::

      devices:
        - /dev/disk/by-id/virtio-OSD1_DATA
        - /dev/disk/by-id/virtio-OSD2_DATA

      raw_journal_devices:
        - /dev/disk/by-id/virtio-OSD1_JOURNAL
        - /dev/disk/by-id/virtio-OSD1_JOURNAL


    Note: the drives should have a valid GPT with no paritions defined,
    otherwise ``ceph-ansible`` refuses to use the device

  - mandatory settings::

      fsid "{{ cluster_uuid.stdout }}"
      cephx: true

* ``group_vars/mons``

  - nothing special here, just a boilerplate::

      fsid: "{{ cluster_uuid.stdout }}"
      monitor_secret: "{{ monitor_keyring.stdout }}"
      cephx: true
      pool_default_pg_num: 128


Preflight checks
----------------

* Check if VMs are reachable via ssh::

    $ cat hosts
    [osds]
    saceph-osd1.vm.ceph.asheplyakov
    saceph-osd2.vm.ceph.asheplyakov
    saceph-osd3.vm.ceph.asheplyakov
    [mons]
    saceph-mon.vm.ceph.asheplyakov
    saceph-mon2.vm.ceph.asheplyakov
    saceph-mon3.vm.ceph.asheplyakov
    [clients]
    saceph-adm.vm.ceph.asheplyakov
    [rgws]
    saceph-rgw.vm.ceph.asheplyakov


    $ ansible -m ping -i hosts all
    saceph-adm.vm.ceph.asheplyakov | SUCCESS => {
       "changed": false, 
       "ping": "pong"
    }
    # and so on


Deploy it
---------

 ::
    ansible-playbook -i hosts site.yml.sample


Benchmark
---------

Create 32G rbd image named ``test.img``, map it, create ext4 filesystem,
mount it and write ``fio`` randwrite benchmark::

  ansible -m apt -i hosts clients -a "name=fio state=present"
  ansible -m copy -i hosts clients -a "src=rbd-test.sh dest=/opt/rbd-test.sh mode=0755"
  ansible -m shell -i hosts clients -a "/opt/rbd-test.sh"

