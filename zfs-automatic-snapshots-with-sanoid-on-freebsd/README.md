# ZFS automatic snapshots with Sanoid on FreeBSD

You can run this with:

`ansible-playbook -b --become-method doas -iHOST, sanoid_autosnap.yml`

...where `HOST` can be a hostname or IP address. Don't forget the trailing `,`!

If you have an inventory file, remove the `-i`. Set your [become-method](https://docs.ansible.com/ansible/latest/plugins/become.html) appropriately. This assumes connecting as an ordinary user and escalating privileges. You may want to do that differently.

The accompanying blog post for this play [can be found here](https://freebsdfoundation.org/blog/zfs-automatic-snapshots-with-sanoid-on-freebsd/).
