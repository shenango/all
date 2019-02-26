
ROOTDIR=`pwd`

# shenango
pushd shenango
./dpdk.sh
sudo ./scripts/setup_machine.sh
git apply ../shenango_16_ht.patch # restrict to 16 hyperthreads
popd

shenango_dirs="shenango shenango/shim shenango/bindings/cc shenango/apps/bench"
for d in $shenango_dirs; do
    make -C $ROOTDIR/$d
done
sudo su -l $USER /bin/bash -c "cd $ROOTDIR/shenango/apps/synthetic/ && cargo build --release"
sudo su -l $USER  /bin/bash -c "cd $ROOTDIR/memcached && make -j"
SHENANGODIR=$ROOTDIR/shenango $ROOTDIR/parsec/bin/parsecmgmt -a build -p swaptions -c gcc-shenango

# linux
sudo su -l $USER  /bin/bash -c "cd $ROOTDIR/memcached-linux && make -j"
$ROOTDIR/parsec/bin/parsecmgmt -a build -p swaptions -c gcc-pthreads

# arachne
if [ `ls memcached-arachne/arachne-all | wc -l` -le "2" ]; then
    pushd memcached-arachne
    ./scripts/prepare.sh

    # apply patches to restrict Arachne to 16 hyperthreads on first NUMA node
    pushd arachne-all/CoreArbiter
    git apply ../../interleaved_numa.patch
    git apply ../../corerestrict.patch
    popd

    popd
else
    pushd memcached-arachne/arachne-all
    ./buildAll.sh
    popd
fi
sudo su -l $USER  /bin/bash -c "cd $ROOTDIR/memcached-arachne && make -j"

# spin servers and threading benchmarks
make -C $ROOTDIR/bench/threading
make -C $ROOTDIR/bench/servers spin-linux spin-arachne
