# cp linux*/Kconfig ./
# export srctree=linux-*


# export srctree="linux-5.16.7/"
# export SRCARCH="x86"
# export ARCH="x86"
# export CC=gcc
# export LD=ldd

# To doewnload a kernel's debug binray https://askubuntu.com/questions/197016/how-to-install-a-package-that-contains-ubuntu-kernel-debug-symbols

export kpb=/home/ubdussamad/live-patching/kpatch/kpatch-build/kpatch-build
export dbg_bin=/usr/lib/debug/boot/vmlinux-5.13.0-27-generic
gsdiff() {
        diff -u $1/ubuntu-$1/$2  $1/ubuntu-$1-mod/$2
}

sdiff() {
        diff -u ubuntu-impish/$1 ubuntu-impish-mod/$1
}

build-patch() {
        echo "$kpb -j 12 -t vmlinux --vmlinux /usr/lib/debug/boot/vmlinux-5.13.0-27-generic -s $1/ubuntu-$1/  $2"
        $kpb -j 12 -t vmlinux --vmlinux /usr/lib/debug/boot/vmlinux-5.13.0-27-generic -s $1/ubuntu-$1  $2
}

disable_patch() {
        echo 0 > /sys/kernel/livepatch/$1/enabled
}

build_debian_src() {
        git clone --depth=1 git://kernel.ubuntu.com/ubuntu/ubuntu-$1.git $1/ubuntu-$1/
        cp $1/debian/scripts/retpoline-extract-one $1/scripts/ubuntu-retpoline-extract-one
        # Weird config that causes beef while building with kpatch-build
        # Notes to make my life easier.
        echo "Now copy the .config file from your distro to the source folder and execute the following commands. Stuff: cp /boot/config-`uname -r` src_dir/.config"
        echo "$scripts/config --disable SYSTEM_REVOCATION_KEYS"
        echo "$scripts/config --disable SYSTEM_TRUSTED_KEYS"
        echo "Finally build modules first using the next command. kpatch build requires modules.symverse beofer building for some reason so we comply. :("
        echo "$make  -j `nproc` modules"
        echo "After makeing everything, make a copy of the whole source folder and name it as {codename}/ubuntu-{codename}-mod, you can make changes to source function in mod >"
}

"srctree="./linux-4.19.231/",
"ARCH="x86",
"SRCARCH="x86",
"KERNELVERSION="4.19.231",
"CC="gcc",
"HOSTCC="gcc",
"HOSTCXX="g++",
"CC_VERSION_TEXT="gcc (Ubuntu 7.5.0-3ubuntu1~18.04) 7.5.0",
"LD="ld",