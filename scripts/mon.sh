#!/bin/bash 


for i in $(virsh list | awk '/ceph/{print $2}')
do
	echo "Destroy the monitor for ${i}"
	fab -H root@${i} mon-destroy --node ${i}
	sleep 1
done


flsid=$(uuidgen)
echo "Generate the uuid and conf for ceph "
fab conf --uuid ${flsid}

fab -H root@ceph1 mon-admin --node ceph1

fab -H ceph1 getFile --name=/tmp/monmap
fab -H ceph1 getFile --name=/etc/ceph/ceph.client.admin.keyring
fab -H ceph1 getFile --name=/tmp/ceph.mon.keyring
fab -H ceph1 getFile --name=/var/lib/ceph/bootstrap-osd/ceph.keyring

fab mon-copy


rm monmap ceph.client.admin.keyring ceph.mon.keyring ceph.keyring -rfv 

for i in $(virsh list | awk '/ceph/{print $2}')
do
	echo "Create the monitor for ${i}"
	fab -H root@${i} mon-start --node ${i}
done
