#!/bin/sh -x

default_disk="FreeBSD-14.2-RELEASE-arm64-aarch64-zfs.raw"
disk="${1:-$default_disk}"

qemu-system-aarch64 \
    -m 4096M -M virt,accel=hvf \
    -cpu cortex-a72 \
    -bios edk2-aarch64-code.fd \
    -rtc base=localtime,clock=rt \
    -nographic \
    -serial mon:stdio \
    -device qemu-xhci \
    -device usb-kbd \
    -device usb-tablet \
    -device virtio-net,netdev=net0 \
    -netdev user,id=net0,hostfwd=tcp::2222-:22,hostfwd=tcp::3389-:3389 \
    -drive if=virtio,file=${disk},format=raw,cache=writethrough
