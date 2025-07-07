# How To Install and Configure the Galene Video Meeting Server on FreeBSD

You can run this with:

`ansible-playbook -b --become-method doas -iHOST, setup_galene.yml`

...where `HOST` can be a hostname or IP address. Don't forget the trailing `,`!

If you have an inventory file, remove the `-i`. Set your [become-method](https://docs.ansible.com/ansible/latest/plugins/become.html) appropriately. This assumes connecting as an ordinary user and escalating privileges. You may want to do that differently.

The accompanying blog post for this play [can be found here](https://freebsdfoundation.org/blog/how-to-install-and-configure-the-galene-video-meeting-server-on-freebsd).
