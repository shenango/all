#!/bin/bash
set -e
set -x

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

pushd $ROOTDIR/shenango/apps/synthetic/
cargo clean
popd

make -C $ROOTDIR/memcached clean

# parsec (shenango and linux)
$ROOTDIR/parsec/bin/parsecmgmt -a fulluninstall
$ROOTDIR/parsec/bin/parsecmgmt -a fullclean

# linux
make -C $ROOTDIR/memcached-linux clean

# arachne
pushd memcached-arachne/arachne-all
./cleanAll.sh
popd
make -C $ROOTDIR/memcached-arachne clean

# spin servers and threading benchmarks
bench_dirs="bench/threading bench/servers"
for d in $bench_dirs; do
    make -C $ROOTDIR/$d clean
done

make -C $ROOTDIR/gdnsd clean uninstall
make -C $ROOTDIR/gdnsd-linux clean uninstall

pushd bench/simnet
cargo clean
popd
