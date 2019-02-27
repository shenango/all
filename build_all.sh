#!/bin/bash
set -e
set -x

ROOTDIR=`pwd`

# shenango
pushd shenango

pushd dpdk
git apply ../ixgbe_18_11.patch || true

if lspci | grep -q 'ConnectX-3'; then
    git apply ../mlx4_18_11.patch || true
    sed -i 's/CONFIG_RTE_LIBRTE_MLX4_PMD=n/CONFIG_RTE_LIBRTE_MLX4_PMD=y/g' config/common_base
fi

# Configure/compile dpdk
make config T=x86_64-native-linuxapp-gcc
make

popd
git apply ../shenango_16_ht.patch || true # restrict to 16 hyperthreads
popd

shenango_dirs="shenango shenango/shim shenango/bindings/cc shenango/apps/bench"
for d in $shenango_dirs; do
    make -C $ROOTDIR/$d
done

pushd $ROOTDIR/shenango/apps/synthetic/
cargo build --release
popd

pushd $ROOTDIR/memcached
./autogen.sh
./configure --with-shenango=$PWD/../shenango/
make
popd

SHENANGODIR=$ROOTDIR/shenango $ROOTDIR/parsec/bin/parsecmgmt -a build -p swaptions -c gcc-shenango

# linux
pushd $ROOTDIR/memcached-linux
./autogen.sh
./configure
make
popd
$ROOTDIR/parsec/bin/parsecmgmt -a build -p swaptions -c gcc-pthreads

# arachne
pushd memcached-arachne
pushd arachne-all
pushd CoreArbiter
git apply ../../interleaved_numa.patch || true
git apply ../../corerestrict.patch || true
popd
./buildAll.sh
popd
./autogen.sh
./configure
make
popd

# spin servers and threading benchmarks
make -C $ROOTDIR/bench/threading
make -C $ROOTDIR/bench/servers spin-linux spin-arachne

pushd gdnsd
autoreconf --install
./configure --with-rundir=$PWD/run --without-urcu --prefix=$PWD/build/ --with-shenango=$PWD/../shenango
make install || true
mkdir -p $PWD/run/gdnsd $PWD/build/var/lib/gdnsd $PWD/build/etc/gdnsd/zones
gunzip -c com.gz > $PWD/build/etc/gdnsd/zones/com
popd

pushd gdnsd-linux
autoreconf --install
./configure --with-rundir=$PWD/run --without-urcu --prefix=$PWD/build/
make install || true
mkdir -p $PWD/run/gdnsd $PWD/build/var/lib/gdnsd $PWD/build/etc/gdnsd/zones
gunzip -c com.gz > $PWD/build/etc/gdnsd/zones/com
popd

pushd bench/simnet
cargo build --release
popd

pushd shenango/scripts
gcc cstate.c -o cstate
popd
