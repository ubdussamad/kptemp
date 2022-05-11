## User/Developer Guide

This is a partial attempt at config based realtime kenel debloating.


## Requirements:
- Host computer Ubuntu or any linux distro of which one can get the kernel debug binary and source.
    - For a guide to download a ubuntu debug binary follow [this link.](https://askubuntu.com/questions/197016/how-to-install-a-package-that-contains-ubuntu-kernel-debug-symbols)
- Python3.7+
- All kernel building tools by running:
    - `sudo apt-get install libncurses-dev gawk flex bison openssl libssl-dev dkms libelf-dev libudev-dev libpci-dev libiberty-dev autoconf`
    - `sudo apt-get build-dep linux linux-image-$(uname -r)`
- Kconfiglib. ( Install it by `python3 -m pip install kconfiglib` )
- Kpatch framework. ( Usually already present in the repo itself.)
- Essence, ( Already there. )
- For now, the kernel boot parameters should include __nokaslr__ to disable ASLR to aid tracing.
- The kernel should be built with livepatch and ftrace.


Steps to get going:

- Download source code for your current running kernel
  - Type `lsb_release -c` in the terminal and note your distro codename. (e.g Bionic, Groovy, etc)
  - Download the kernel source by subsituting codename by your distro's actual code:
    - `git clone --depth=1 git://kernel.ubuntu.com/ubuntu/ubuntu-<codename>.git`
    - After downloading the source, copy the current set of configs to it by:
        - ```cp /boot/config-`uname -r` ubuntu-<codename>/.config```
        - `make olddefconfig`
        - Move to the kernel source directory by `cd ubuntu-bionic/`. Do this for both the kernels.
        - Run: `cp debian/scripts/retpoline-extract-one scripts/ubuntu-retpoline-extract-one`
        - Now run `scripts/config --disable SYSTEM_REVOCATION_KEYS`
        - and `scripts/config --disable SYSTEM_TRUSTED_KEYS`
        - and if you're having problems with APIC try: `scripts/config --disable CONFIG_X86_UV`
    - Also, make a copy of the downloaded source by appending `-mod` to it's name. (e.g. ubuntu-bionic-mod)
- Set the environment variables in the file main.py namely:
    - WORKLOAD_PATH ( The workload you wish to trace. e.g worload_starter_script.sh)
    - VMLINUX_PATH ( The kernel debug binary e.g vmlinux-x.x.x-abc)
    - SOURCE_PARSER_LINUX_TREE ( Path to the source code of the currently running kernel. e.g ubuntu-bionic/ , linux-x.x.x-abc)
    - DEP_SOLVER_LINUX_TREE ( Path to the source code of the currently running kernel. )
- Mount the ftrace vfs by  :  `sudo mount -t tracefs nodev /sys/kernel/tracing`
- Clone kpatch repository (if not done already) by:
    - `git clone --depth=1 https://github.com/dynup/kpatch.git`
    - Move to kpatch directory and build it by running `make`
    - Create a shortcut for kpatch binary (optional): `export kpb=kpatch/kpatch-build/kpatch-build`
    - You can then run kpatch by (optional): 
        - `$kpb -t vmlinux -v <debug-binary-path>  -s <path-to-kernel-source> -j <core-count> <source-diff-patch-name>`
- Run the framework by `sudo python3 main.py`