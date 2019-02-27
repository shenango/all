# shenango-all
Shenango, applications, benchmarks, and other systems evaluated.

## Installing prereqs
```
sudo apt install build-essential libnuma-dev clang autoconf autotools-dev m4 automake libevent-dev  libpcre++-dev libtool ragel libev-dev moreutils parallel
```
Install rust, and use the nightly toolchain. See http://rust-lang.org/ for details.


## Compiling
To build everything for Shenango, Linux, and Arachne:
```
git submodule update --init --recursive
./build_all.sh
```
For instructions on building ZygOS or Memcached for ZygOS, please see
[their repositories](https://github.com/ix-project). After building
ZygOS, the spin server can be built with:
```
make -C ./bench/servers spin-ix
```
We built and ran ZygOS on Ubuntu 16.04.
