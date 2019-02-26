ROOTDIR=`pwd`

# shenango
pushd shenango/dpdk
git checkout .
rm -fr build
popd

shenango_dirs="shenango shenango/shim shenango/bindings/cc shenango/apps/bench"
for d in $shenango_dirs; do
    make -C $ROOTDIR/$d clean
done
sudo su -l $USER /bin/bash -c "cd $ROOTDIR/shenango/apps/synthetic/ && cargo clean"
sudo su -l $USER /bin/bash -c "cd $ROOTDIR/memcached && make clean"

# parsec (shenango and linux)
$ROOTDIR/parsec/bin/parsecmgmt -a fulluninstall
$ROOTDIR/parsec/bin/parsecmgmt -a fullclean

# linux
sudo su -l $USER /bin/bash -c "cd $ROOTDIR/memcached-linux && make clean"

# arachne
pushd memcached-arachne/arachne-all
./cleanAll.sh
popd
sudo su -l $USER /bin/bash -c "cd $ROOTDIR/memcached-arachne && make clean"

# spin servers and threading benchmarks
bench_dirs="bench/threading bench/servers"
for d in $bench_dirs; do
    make -C $ROOTDIR/$d clean
done
