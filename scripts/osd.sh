#!/bin/bash 

#fab -H ceph1 osd-destroy --id=1
#fab -H ceph1 osd-create --id=1
#fab -H ceph1 osd-start --id=1
#fab -H ceph2 osd-destroy --id=2
#fab -H ceph2 osd-create --id=2
#fab -H ceph2 osd-start --id=2
#fab -H ceph3 osd-destroy --id=3
#fab -H ceph3 osd-create --id=3
#fab -H ceph3 osd-start --id=3

for i in $(virsh list | awk '/ceph/{print $2}')
do
	id=${i##*ceph}
	fab -H ${i} osd-destroy --id=${id}
    fab -H ${i} osd-create --id=${id}
	fab -H ${i} osd-start --id=${id}
done

