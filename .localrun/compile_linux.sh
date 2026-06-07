#! /bin/bash

_HOME2_=$(dirname "$0")
export _HOME2_
_HOME_=$(cd "$_HOME2_" || exit;pwd)
export _HOME_

echo "$_HOME_"
cd "$_HOME_" || exit 1

docker run --rm dockcross/linux-x86_64-full > ./dockcross-linux-x86_64-full; chmod +x ./dockcross-linux-x86_64-full || exit 1

./dockcross-linux-x86_64-full bash -c 'ls -al;id;pwd;hostname;uname -a' || exit 1
./dockcross-linux-x86_64-full bash -c './deps_linux.sh' || exit 1
# ./dockcross-linux-arm64 bash -c './deps_linux.sh "" "" nodownload' || exit 1

./dockcross-linux-x86_64-full bash -c '
$CC -shared -g -O3 -fPIC -D_FORTIFY_SOURCE=2 --param=ssp-buffer-size=1 -fstack-protector-all \
    -L./inst/lib/ \
    -I./ \
    -fvisibility=hidden \
    -Wl,-Bsymbolic \
    koditox.c \
    -Wl,--whole-archive \
    ./inst/lib/libtoxcore.a \
    ./inst/lib/libtoxav.a \
    ./inst/lib/libopus.a \
    ./inst/lib/libvpx.a \
    ./inst/lib/libx264.a \
    ./inst/lib/libx265.a \
    ./inst/lib/libavcodec.a \
    ./inst/lib/libavformat.a \
    ./inst/lib/libavutil.a \
    ./inst/lib/libsodium.a \
    -Wl,--no-whole-archive \
    -o libkoditox_x86_64.so \
    -lpthread -lm -ldl
' || exit 1

file libkoditox_x86_64.so
ls -al libkoditox_x86_64.so
ls -hal $(pwd)/libkoditox_x86_64.so || exit 1

cp -av libkoditox_x86_64.so ../plugin.video.koditox/resources/lib/libkoditox_x86_64.so
