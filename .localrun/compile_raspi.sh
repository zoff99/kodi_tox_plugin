#! /bin/bash

_HOME2_=$(dirname "$0")
export _HOME2_
_HOME_=$(cd "$_HOME2_" || exit;pwd)
export _HOME_

echo "$_HOME_"
cd "$_HOME_" || exit 1

docker run --rm dockcross/linux-arm64 > ./dockcross-linux-arm64; chmod +x ./dockcross-linux-arm64 || exit 1

./dockcross-linux-arm64 bash -c 'ls -al;id;pwd;hostname;uname -a' || exit 1
# ./dockcross-linux-arm64 bash -c './deps_linux.sh raspi' || exit 1
./dockcross-linux-arm64 bash -c './deps_linux.sh raspi "" nodownload' || exit 1

./dockcross-linux-arm64 bash -c '
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
    -o libkoditox.so \
    -lpthread -lm -ldl
' || exit 1

file libkoditox.so
ls -al libkoditox.so
ls -hal $(pwd)/libkoditox.so || exit 1

cp -av libkoditox.so ../plugin.video.koditox/resources/lib/libkoditox.so
